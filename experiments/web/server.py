"""Human-vs-AI web sandbox for the PTCG agent.

You pilot the Ethan's Typhlosion (Quilava) deck; the computer plays a meta deck
(Crustle / Lucario). At every one of YOUR decisions the panel shows what OUR
agent would do and the score it gives each legal option — so you can compare your
intuition with the strategy and spot where the agent is wrong (optimization points).

Run:  venv/bin/python web/server.py   then open http://localhost:8000
"""
import sys, os, json, ctypes, types
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT + '/docs/official/models/cg-lib')
from cg.game import battle_start, battle_finish, _get_battle_data
from cg.api import (to_observation_class, all_card_data, all_attack,
                    OptionType, SelectContext, AreaType, LogType, CardType)
from cg.sim import lib, Battle

CT = {c.cardId: c for c in all_card_data()}
AT = {a.attackId: a for a in all_attack()}
CTX = {v: k for k, v in vars(SelectContext).items() if isinstance(v, int)}


def cname(cid):
    c = CT.get(cid)
    return (c.name if c else f"#{cid}")


# ── generic card helpers (server-level, so ANY agent works on either side) ───
def _safe_get(seq, i):
    try:
        if seq is None or i is None or i < 0 or i >= len(seq):
            return None
        return seq[i]
    except Exception:
        return None


def get_card(obs, area, index, pi):
    try:
        player = obs.current.players[pi]
        if area == AreaType.DECK: return _safe_get(getattr(obs.select, 'deck', None), index)
        if area == AreaType.HAND: return _safe_get(getattr(player, 'hand', None), index)
        if area == AreaType.DISCARD: return _safe_get(getattr(player, 'discard', None), index)
        if area == AreaType.ACTIVE: return _safe_get(getattr(player, 'active', None), index)
        if area == AreaType.BENCH: return _safe_get(getattr(player, 'bench', None), index)
        if area == AreaType.PRIZE: return _safe_get(getattr(player, 'prize', None), index)
        if area == AreaType.STADIUM: return _safe_get(getattr(obs.current, 'stadium', None), index)
        if hasattr(AreaType, 'LOOKING') and area == AreaType.LOOKING:
            return _safe_get(getattr(obs.current, 'looking', None), index)
    except Exception:
        pass
    return None


def normalize_selection(ranked, scores, select):
    n = len(select.option)
    minc = max(0, min(select.minCount, n)); maxc = max(minc, min(select.maxCount, n))
    out, seen = [], set()
    for i in ranked:
        if not (0 <= i < n) or i in seen:
            continue
        s = scores[i] if i < len(scores) else 0
        if s > 0 or len(out) < minc:
            out.append(i); seen.add(i)
        if len(out) >= maxc:
            break
    for i in range(n):
        if len(out) >= minc:
            break
        if i not in seen:
            out.append(i); seen.add(i)
    return out


# ── card images from pokemontcg.io (cached locally) ──────────────────────────
import urllib.request as _urllib_request
_IMG_CACHE = ROOT + '/web/card_imgs'
os.makedirs(_IMG_CACHE, exist_ok=True)
_CARD_IMG_MAP = {}
try:
    with open(ROOT + '/web/card_images.json', encoding='utf-8') as _f:
        _CARD_IMG_MAP = json.load(_f)
    print(f'card images: {len(_CARD_IMG_MAP)} cards mapped (cache {_IMG_CACHE})')
except Exception as _e:
    print(f'card_images.json load error: {_e}')


def render_card_png(cid):
    """Fetch card image from pokemontcg.io (disk-cached). Bytes or None."""
    path = f'{_IMG_CACHE}/{cid}.png'
    if os.path.exists(path):
        return open(path, 'rb').read()
    slug = _CARD_IMG_MAP.get(str(cid))
    if not slug:
        return None
    parts = slug.split('/')
    if len(parts) != 2:
        return None
    set_id, num = parts
    url = f'https://images.pokemontcg.io/{set_id}/{num}_hires.png'
    try:
        req = _urllib_request.Request(url, headers={'User-Agent': 'ptcg-sandbox/1.0'})
        resp = _urllib_request.urlopen(req, timeout=10)
        data = resp.read()
        with open(path, 'wb') as f:
            f.write(data)
        return data
    except Exception:
        try:
            url2 = f'https://images.pokemontcg.io/{set_id}/{num}.png'
            req2 = _urllib_request.Request(url2, headers={'User-Agent': 'ptcg-sandbox/1.0'})
            resp2 = _urllib_request.urlopen(req2, timeout=10)
            data2 = resp2.read()
            with open(path, 'wb') as f:
                f.write(data2)
            return data2
        except Exception:
            return None


# ── strong decks: selectable for BOTH player and opponent ────────────────────
# (display name, agent dir). All have an agent() callable; those with a *Policy class
# also show per-option AI scores when you pilot them.
DECKS = {
    'dragapult':      ('👻 Dragapult ex 多龍', 'agents/dragapult'),
    'megastarmie':    ('💧🔥 Mega Starmie ex + Cinderace 寶石海星', 'agents/megastarmie'),
    'megastarmie_v2': ('💧🔥 Mega Starmie v2', 'agents/megastarmie_v2'),
    'alakazam':       ('🔮 Alakazam 胡地', 'agents/alakazam'),
    'trevenant':      ("🌳 Hop's Trevenant", 'agents/trevenant'),
    'lucario_v3':     ('🥊 Mega Lucario ex v3', 'agents/lucario_v3'),
    'chandelure':     ('🕯 Chandelure 水晶燈火靈', 'agents/chandelure'),
    'froslass':       ('❄ Mega Froslass ex', 'agents/froslass'),
    'mewtwo':         ("🧬 Team Rocket's Mewtwo ex", 'agents/mewtwo'),
}
ME = {'mod': None, 'deck': None, 'Policy': None, 'name': None}
_LOADED = {}   # name -> {deck, mod, Policy}


def _load_deck(name):
    """Load a deck's main.py once: its deck list, module (has agent()), and *Policy if any."""
    if name not in DECKS:
        name = 'dragapult'
    if name in _LOADED:
        return _LOADED[name]
    d = ROOT + '/' + DECKS[name][1]
    deck = [int(l) for l in open(d + '/deck.csv') if l.strip()]
    mod = types.ModuleType('deck_' + name)
    mod.__dict__['__file__'] = d + '/main.py'
    sys.path.insert(0, d); sys.path.insert(0, ROOT + '/agents/_base')
    cur = os.getcwd(); os.chdir(d)
    try:
        exec(compile(open(d + '/main.py').read(), d + '/main.py', 'exec'), mod.__dict__)
    finally:
        os.chdir(cur)
    # pick the CONCRETE deck Policy — exclude the imported abstract bases (BasePolicy/GenericPolicy
    # also end in 'Policy' and would shadow the real one).
    cands = [v for k, v in mod.__dict__.items()
             if k.endswith('Policy') and isinstance(v, type)
             and k not in ('BasePolicy', 'GenericPolicy')
             and not getattr(v, '__abstractmethods__', None)]
    Policy = cands[0] if cands else None
    _LOADED[name] = {'deck': deck, 'mod': mod, 'Policy': Policy}
    return _LOADED[name]


def load_me(name):
    """Load the deck you pilot (per-option AI scores shown if it has a *Policy)."""
    L = _load_deck(name if name in DECKS else 'megastarmie')
    ME.update(mod=L['mod'], deck=L['deck'], Policy=L['Policy'],
              name=(name if name in DECKS else 'megastarmie'))


load_me('megastarmie')   # default


def load_opp(name):
    L = _load_deck(name if name in DECKS else 'dragapult')
    return L['mod'], L['deck']


# ── game session (single global game; single-threaded server) ────────────────
GAME = {'obs_dict': None, 'opp_mod': None, 'opp_deck': None, 'human': 0, 'over': True, 'log': [], 'logseq': 0}

AREA = {AreaType.DECK: 'deck', AreaType.HAND: 'hand', AreaType.DISCARD: 'discard',
        AreaType.ACTIVE: 'active', AreaType.BENCH: 'bench', AreaType.PRIZE: 'prize'}
AREATC = {AreaType.DECK: '山札', AreaType.HAND: '手札', AreaType.DISCARD: 'トラッシュ',
          AreaType.ACTIVE: 'バトル場', AreaType.BENCH: 'ベンチ', AreaType.PRIZE: 'サイド'}


def decode_log(e):
    """Turn one raw engine log event into a display entry {txt, side, from, to, reveal}."""
    t = e.get('type'); pi = e.get('playerIndex'); cid = e.get('cardId')
    side = 'me' if pi == GAME['human'] else ('opp' if pi is not None else '')
    who = 'あなた' if side == 'me' else ('CPU' if side == 'opp' else '')
    nm = cname(cid).replace("Ethan's ", "").replace("Iono's ", "") if cid else ''
    d = {'side': side, 'type': int(t) if t is not None else -1}
    fa, ta = e.get('fromArea'), e.get('toArea')
    if t in (LogType.DRAW, LogType.DRAW_REVERSE):
        d.update(txt=f'{who} ドロー' + (f'({nm})' if cid and side == 'me' else ''), frm='deck', to='hand')
    elif t == LogType.TURN_START:
        d.update(txt=f'──── {who} のターン ────', hd=True)
    elif t == LogType.TURN_END:
        d.update(txt=f'{who} ターン終了')
    elif t == LogType.SHUFFLE:
        d.update(txt=f'{who} シャッフル')
    elif t == LogType.PLAY:
        d.update(txt=f'{who} {nm} を使用', frm='hand', reveal=cid)
    elif t == LogType.ATTACH:
        d.update(txt=f'{who} {nm} をつける', frm='hand', to='active', reveal=cid)
    elif t == LogType.EVOLVE:
        d.update(txt=f'{who} {nm} に進化', reveal=cid)
    elif t == LogType.DEVOLVE:
        d.update(txt=f'{who} {nm} 退化')
    elif t == LogType.MOVE_CARD:
        d.update(txt=f'{who} {nm} {AREATC.get(fa, "?")}→{AREATC.get(ta, "?")}',
                 frm=AREA.get(fa), to=AREA.get(ta), reveal=(cid if ta == AreaType.DISCARD else None))
    elif t in (LogType.SWITCH, LogType.CHANGE):
        d.update(txt=f'{who} ポケモンを入れ替え')
    elif t == LogType.ATTACK:
        a = AT.get(e.get('attackId')); d.update(txt=f'⚔ {who} ワザ {a.name if a else ""}', reveal=cid)
    elif t == LogType.HP_CHANGE:
        v = e.get('value', 0)
        d.update(txt=f'  {nm} HP {"+" if v > 0 else ""}{v}' + ('(ダメカン)' if e.get('putDamageCounter') else ''))
    elif t in (LogType.POISONED, LogType.BURNED, LogType.ASLEEP, LogType.PARALYZED, LogType.CONFUSED):
        st = {LogType.POISONED: 'どく', LogType.BURNED: 'やけど', LogType.ASLEEP: 'ねむり',
              LogType.PARALYZED: 'マヒ', LogType.CONFUSED: 'こんらん'}[t]
        d.update(txt=f'  {nm} {st}{"回復" if e.get("isRecover") else ""}')
    elif t == LogType.COIN:
        d.update(txt=f'🪙 コイン:{"オモテ" if e.get("head") else "ウラ"}')
    elif t == LogType.RESULT:
        d.update(txt='🏁 対戦終了')
    else:
        return None   # skip noise (HAS_BASIC_POKEMON, reverse-moves, etc.)
    return d


def _note_action(obs_dict, indices):
    """The engine logs an ability's EFFECTS (draws, moves) but not the ability itself.
    Inject a synthetic entry naming the Ability being used, so the draws that follow
    are attributable (e.g. '✨ 你 使用特性「Dudunsparce」' before the draw lines)."""
    try:
        obs = to_observation_class(obs_dict)
        if obs.select is None or not indices:
            return
        opt = obs.select.option[indices[0]]
        if opt.type != OptionType.ABILITY:
            return
        pi = obs.current.yourIndex
        side = 'me' if pi == GAME['human'] else 'opp'
        who = 'あなた' if side == 'me' else 'CPU'
        c = get_card(obs, opt.area, opt.index, pi)
        nm = cname(c.id).replace("Ethan's ", "").replace("Iono's ", "") if c else '?'
        GAME['log'].append({'side': side, 'type': 90, 'txt': f'✨ {who} 特性「{nm}」を使用',
                            'reveal': (c.id if c else None), 'seq': GAME['logseq']})
        GAME['logseq'] += 1
    except Exception:
        pass


def _select(indices):
    arg = (ctypes.c_int * len(indices))(*indices)
    lib.Select(Battle.battle_ptr, arg, len(indices))
    obs = _get_battle_data()
    for e in (obs.get('logs') or []):
        d = decode_log(e)
        if d:
            d['seq'] = GAME['logseq']; GAME['logseq'] += 1
            GAME['log'].append(d)
    GAME['log'] = GAME['log'][-200:]
    return obs


def _advance_opponent():
    """Auto-play the opponent until it's the human's decision or game over."""
    g = GAME
    for _ in range(500):
        obs = to_observation_class(g['obs_dict'])
        if obs.current.result != -1 or obs.select is None:
            g['over'] = obs.current.result != -1
            return
        if obs.current.yourIndex == g['human']:
            return
        try:
            action = g['opp_mod'].agent(g['obs_dict'])
        except Exception:
            n = len(obs.select.option); action = list(range(min(max(0, obs.select.minCount), n)))
        _note_action(g['obs_dict'], action)
        g['obs_dict'] = _select(action)


def poke_json(p):
    if p is None:
        return None
    return {'id': p.id, 'name': cname(p.id).replace("Ethan's ", "").replace("Iono's ", ""),
            'hp': p.hp, 'maxHp': p.maxHp, 'energy': len(p.energies),
            'tools': [cname(t.id) for t in p.tools]}


def option_ids(obs, opt, my_index):
    """(cardId, attackId) for an option, so the UI can show its card details."""
    try:
        t = opt.type
        if t == OptionType.ATTACK:
            return (obs.current.players[my_index].active[0].id
                    if obs.current.players[my_index].active else None), opt.attackId
        if t in (OptionType.PLAY, OptionType.EVOLVE):
            c = get_card(obs, AreaType.HAND, opt.index, my_index)
            return (c.id if c else None), None
        if t == OptionType.ABILITY:
            c = get_card(obs, opt.area, opt.index, my_index)
            return (c.id if c else None), None
        if t in (OptionType.ENERGY, OptionType.ATTACH):
            c = get_card(obs, opt.inPlayArea, opt.inPlayIndex, my_index)
            return (c.id if c else None), None
        if t == OptionType.CARD:
            c = get_card(obs, getattr(opt, 'area', None) or AreaType.HAND, opt.index, my_index)
            return (c.id if c else None), None
    except Exception:
        pass
    return None, None


def label_option(obs, opt, my_index):
    t = opt.type
    if t == OptionType.END:
        return '⏹ ターン終了'
    if t == OptionType.YES:
        return '✔ はい' + (' (先攻)' if obs.select.context == SelectContext.IS_FIRST else '')
    if t == OptionType.NO:
        return '✘ いいえ' + (' (後攻)' if obs.select.context == SelectContext.IS_FIRST else '')
    if t == OptionType.NUMBER:
        cc = getattr(obs.select, 'contextCard', None)
        ctx = f' ({cname(cc.id)})' if cc is not None and getattr(cc, 'id', None) else ''
        return f'数量を選択 {opt.number}{ctx}'
    if t == OptionType.ATTACK:
        a = AT.get(opt.attackId)
        return f'⚔ ワザ {a.name} ({a.damage})' if a else f'⚔ ワザ #{opt.attackId}'
    if t == OptionType.RETREAT:
        return '↩ にげる'
    if t == OptionType.ABILITY:
        c = get_card(obs, opt.area, opt.index, my_index)
        return f'✨ 特性 {cname(c.id) if c else ""}'
    if t == OptionType.EVOLVE:
        c = get_card(obs, AreaType.HAND, opt.index, my_index)
        return f'⬆ 進化 → {cname(c.id) if c else ""}'
    cn = CTX.get(obs.select.context, '') or ''   # context name, e.g. 'DISCARD_ENERGY'
    if t in (OptionType.ENERGY, OptionType.ATTACH):
        tgt = get_card(obs, opt.inPlayArea, opt.inPlayIndex, my_index)
        tn = cname(tgt.id).replace(chr(39), '') if tgt else '?'
        if 'DISCARD' in cn:
            return f'🗑 エネルギーをトラッシュ ({tn})'
        if 'TO_HAND' in cn:
            return f'✋ エネルギーを手札に ({tn})'
        return f'🔋 エネルギーをつける → {tn}'
    if t in (OptionType.PLAY, OptionType.CARD, OptionType.TOOL_CARD, OptionType.ENERGY_CARD):
        c = get_card(obs, getattr(opt, 'area', None) or AreaType.HAND, opt.index, my_index)
        nm = cname(c.id) if c else 'card'
        if t == OptionType.PLAY:
            return f'▶ {nm} を使う'
        if 'DISCARD' in cn:
            return f'🗑 {nm} をトラッシュ'
        if 'TO_HAND' in cn:
            return f'🔍 {nm} を手札に加える'
        if 'TO_DECK' in cn or 'TO_PRIZE' in cn:
            return f'↩ {nm} を戻す'
        if 'SWITCH' in cn or 'ACTIVE' in cn:
            return f'⬆ {nm} をバトル場に'
        if 'BENCH' in cn or 'FIELD' in cn:
            return f'➕ {nm} をベンチに'
        return f'▶ {nm}'
    return f'option(type={t})'


def state_json(msg=''):
    g = GAME
    obs = to_observation_class(g['obs_dict']) if g['obs_dict'] else None
    if obs is None:
        return {'started': False, 'msg': msg}
    st = obs.current
    me = st.players[g['human']]; op = st.players[1 - g['human']]
    over = st.result != -1
    out = {
        'started': True, 'over': over, 'msg': msg,
        'result': ('あなたの勝ち 🏆' if over and st.result == g['human'] else
                   'CPUの勝ち 💀' if over and st.result == (1 - g['human']) else
                   '引き分け' if over else ''),
        'turn': st.turn, 'context': CTX.get(obs.select.context, str(obs.select.context)) if obs.select else None,
        'yourTurn': (obs.select is not None and st.yourIndex == g['human']),
        'log': g['log'][-90:],
        'me': {'active': poke_json(me.active[0] if me.active else None),
               'bench': [poke_json(b) for b in me.bench if b is not None],
               'prizes': len(me.prize),
               'hand': [{'id': c.id, 'name': cname(c.id)} for c in (me.hand or [])],
               'deck': me.deckCount, 'discard': len(me.discard or [])},
        'opp': {'active': poke_json(op.active[0] if op.active else None),
                'bench': [poke_json(b) for b in op.bench if b is not None],
                'prizes': len(op.prize), 'handCount': op.handCount, 'deck': op.deckCount,
                'discard': len(op.discard or [])},
        'stadium': cname(st.stadium[0].id) if st.stadium else None,
        'options': [], 'ai_pick': [],
    }
    if not over and obs.select is not None and st.yourIndex == g['human']:
        # AI suggestion + per-option scores. Decks with a *Policy show per-option scores;
        # the rest (sample/generic pilots) just highlight the agent()'s recommended pick.
        scores = [0] * len(obs.select.option); ai_pick = []
        try:
            if ME['Policy'] is not None:
                policy = ME['Policy'](obs)
                ranked, scores = policy.rank()
                ai_pick = normalize_selection(ranked, scores, obs.select)
            elif ME['mod'].__dict__.get('agent') is not None:
                ai_pick = sorted(set(ME['mod'].agent(g['obs_dict'])))
        except Exception:
            scores = [0] * len(obs.select.option); ai_pick = []
        out['ai_pick'] = ai_pick
        for i, opt in enumerate(obs.select.option):
            cid, aid = option_ids(obs, opt, g['human'])
            out['options'].append({
                'i': i, 'label': label_option(obs, opt, g['human']),
                'score': round(float(scores[i]), 1) if i < len(scores) else 0,
                'recommended': i in ai_pick, 'cardId': cid, 'attackId': aid,
            })
        out['multi'] = {'min': obs.select.minCount, 'max': obs.select.maxCount}
    return out


# ── per-deck strategy pages (decklist + 中文使用策略) ─────────────────────────
STRATEGIES = {
 'dragapult': "ダメカンばら撒き/コントロール。主力 <b>Phantom Dive [炎][超]=200</b> +ベンチに6ダメカン(=60)。サブ Jet Headbutt[無]=70。<b>4× Crushing Hammer</b> でエネ破壊。Rare Candy で直進化。<b>後攻</b>推奨。苦手: Cinderace。",
 'megastarmie': "水炎デュアルアタッカー (天梯1位)。主力 <b>Jetting Blow [水]=120 +ベンチ50</b>。フィニッシャー <b>Nebula Beam [無]×3=210</b> 弱抵無視。Ignition Energy=進化ポケに無色3個分(ターン終了トラッシュ)。<b>先攻</b>推奨。⚠ たねは Staryu のみ。",
 'megastarmie_v2': "Mega Starmie v2。Jetting Blow主軸 + Crushing Hammer妨害強化。Ignition は KO/貫通時のみ。",
 'alakazam': "フーディン全1サイド。主力 <b>Powerful Hand = 手札×20</b>(15-20枚→300-400)。Dudunsparce(3枚ドロー)エンジン。⚠ Powerful Handはダメカン=ミスト/岩闘エネで無効。",
 'trevenant': "Hopオーロット、全1サイド。<b>Horrifying Revenge [無]=30</b>、前ターンKO+100(=130)。Choice Band+Postwickで+30。サイドレース型。",
 'lucario_v3': "メガルカリオex(闘,3サイド)。高HP+Mega Braveで正面突破。闘対策なしデッキに圧倒的。",
 'chandelure': "シャンデラ ダメカンコンボ。特性エンジンで蓄積→回収。<b>先に特性+エネ+Crushing Hammer、攻撃は急がない</b>。Trevenant/Alakazamに有利。苦手:Cinderace(0%)。",
 'froslass': "メガユキメノコex+Starmie。Absolute Snowで<b>ねむり</b>拘束。約70%勝率。",
 'mewtwo': "ロケット団ミュウツーex(超)。約75%勝率。超エネ高火力速攻。",
}
_TYPE_ORDER = [('ポケモン Pokémon', 'poke'), ('トレーナーズ Trainer', 'trainer'), ('エネルギー Energy', 'energy')]


def _card_group(cid):
    c = CT.get(cid)
    if c is None:
        return 'trainer'
    if getattr(c, 'hp', None):
        return 'poke'
    if c.cardType in (CardType.BASIC_ENERGY, CardType.SPECIAL_ENERGY):
        return 'energy'
    return 'trainer'


def deck_page_html(name):
    nav = ('<div class="dnav"><a href="/">← バトルへ戻る</a>' +
           ''.join(f'<a href="/deck/{k}" class="{"on" if k==name else ""}">{v[0]}</a>' for k, v in DECKS.items()) +
           '</div>')
    if name not in DECKS:
        body = '<h1>デッキ図鑑</h1><p>上のデッキ名をクリックすると、デッキリストと戦略を表示します。</p>'
        return _DECK_HTML.replace('{{nav}}', nav).replace('{{body}}', body).replace('{{title}}', 'デッキ図鑑')
    from collections import Counter
    deck = [int(l) for l in open(ROOT + '/' + DECKS[name][1] + '/deck.csv') if l.strip()]
    cnt = Counter(deck)
    groups = {'poke': [], 'trainer': [], 'energy': []}
    for cid, n in sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0])):
        groups[_card_group(cid)].append((cid, n))
    sections = ''
    for label, key in _TYPE_ORDER:
        items = groups[key]
        if not items:
            continue
        cards = ''.join(
            f'<div class="dcard"><img loading="lazy" src="/card_img/{cid}.png" '
            f'onclick="zoom(this.src)" onerror="this.style.display=\'none\'">'
            f'<span class="dn">{n}×</span>'
            f'<span class="dl">{cname(cid)}</span></div>' for cid, n in items)
        sub = sum(n for _, n in items)
        sections += f'<h2>{label} <small>({sub})</small></h2><div class="dgrid">{cards}</div>'
    strat = STRATEGIES.get(name, '(戦略準備中)')
    body = (f'<h1>{DECKS[name][0]}</h1>'
            f'<div class="strat"><h2>使用戦略</h2><p>{strat}</p></div>{sections}')
    return _DECK_HTML.replace('{{nav}}', nav).replace('{{body}}', body).replace('{{title}}', DECKS[name][0])


_DECK_HTML = """<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{{title}}</title>
<style>
body{margin:0;background:#0f1117;color:#e6e6e6;font-family:system-ui,'Noto Sans TC',sans-serif;line-height:1.7}
.wrap{max-width:1000px;margin:0 auto;padding:20px}
a{color:#7cc4ff;text-decoration:none}
.dnav{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:18px}
.dnav a{padding:6px 11px;border:1px solid #2a2f3a;border-radius:8px;background:#171a22;font-size:14px}
.dnav a.on{background:#2563eb;border-color:#2563eb;color:#fff}
h1{font-size:24px;margin:10px 0}
h2{font-size:17px;margin:22px 0 10px;border-bottom:1px solid #2a2f3a;padding-bottom:6px}
.strat{background:#171a22;border:1px solid #2a2f3a;border-radius:12px;padding:14px 18px;margin:14px 0}
.strat p{margin:6px 0;font-size:15px}
.dgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(86px,1fr));gap:10px}
.dcard{background:#171a22;border:1px solid #2a2f3a;border-radius:9px;padding:6px;text-align:center}
.dcard img{width:100%;border-radius:6px;display:block;cursor:zoom-in;transition:transform .08s}
.dcard img:hover{transform:scale(1.04)}
.dn{display:inline-block;font-weight:700;color:#ffd479;font-size:13px}
.dl{display:block;font-size:11px;color:#aab;margin-top:3px;line-height:1.3}
.lb{position:fixed;inset:0;background:rgba(0,0,0,.88);display:none;align-items:center;justify-content:center;z-index:100;cursor:zoom-out}
.lb.on{display:flex}
.lb img{max-width:92vw;max-height:94vh;border-radius:14px;box-shadow:0 10px 50px rgba(0,0,0,.6)}
</style></head><body><div class="wrap">{{nav}}{{body}}</div>
<div class="lb" id="lb" onclick="this.classList.remove('on')"><img id="lbimg" alt=""></div>
<script>
function zoom(src){var lb=document.getElementById('lb');document.getElementById('lbimg').src=src;lb.classList.add('on');}
document.addEventListener('keydown',function(e){if(e.key==='Escape')document.getElementById('lb').classList.remove('on');});
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype='application/json'):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ('/', '/index.html'):
            return self._send(200, open(ROOT + '/web/index.html', 'rb').read(), 'text/html; charset=utf-8')
        if u.path == '/card_db.json':
            return self._send(200, open(ROOT + '/web/card_db.json', 'rb').read(), 'application/json; charset=utf-8')
        if u.path == '/card_images.json':
            return self._send(200, open(ROOT + '/web/card_images.json', 'rb').read(), 'application/json; charset=utf-8')
        if u.path.startswith('/card_img/'):
            try:
                cid = int(u.path.rsplit('/', 1)[1].split('.')[0])
            except Exception:
                return self._send(404, b'', 'image/png')
            data = render_card_png(cid)
            if data:
                return self._send(200, data, 'image/png')
            return self._send(404, b'', 'image/png')
        if u.path == '/decks':   # list of all decks (JSON, for the UI dropdowns)
            return self._send(200, json.dumps([{'id': k, 'name': v[0]} for k, v in DECKS.items()]))
        if u.path == '/deck' or u.path.startswith('/deck/'):
            name = u.path[len('/deck/'):] if u.path.startswith('/deck/') else ''
            return self._send(200, deck_page_html(name).encode('utf-8'), 'text/html; charset=utf-8')
        if u.path == '/new':
            q = parse_qs(u.query)
            opp = q.get('opp', ['dragapult'])[0]
            load_me(q.get('me', ['megastarmie'])[0])   # which deck you pilot
            m, deck = load_opp(opp)
            GAME['opp_mod'], GAME['opp_deck'] = m, deck
            GAME['human'] = 0
            GAME['log'] = []; GAME['logseq'] = 0
            GAME['obs_dict'], _ = battle_start(ME['deck'], deck)
            GAME['over'] = False
            _advance_opponent()
            mn = DECKS.get(ME['name'], (ME['name'],))[0]; on = DECKS.get(opp, (opp,))[0]
            return self._send(200, json.dumps(state_json(f'新対戦:{mn} vs {on}')))
        if u.path == '/state':
            return self._send(200, json.dumps(state_json()))
        return self._send(404, '{}')

    def do_POST(self):
        u = urlparse(self.path)
        if u.path == '/select':
            ln = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(ln) or '{}')
            idx = body.get('indices', [])
            try:
                _note_action(GAME['obs_dict'], idx)
                GAME['obs_dict'] = _select(idx)
                _advance_opponent()
                return self._send(200, json.dumps(state_json()))
            except Exception as e:
                return self._send(200, json.dumps(state_json(f'錯誤: {e}')))
        return self._send(404, '{}')


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f'PTCG sandbox: http://localhost:{port}  (Ctrl-C to stop)')
    ThreadingHTTPServer(('0.0.0.0', port), H).serve_forever()
