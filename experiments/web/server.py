"""Human-vs-AI web sandbox for PTCG battle.

Run via launch.py:
    python3 experiments/web/launch.py
    # open http://localhost:8000

Based on wmh/ptcg-abc. Japanese localized.
"""
import sys, os, json, ctypes, types, copy
import time as _time
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
try:
    from deck_registry import (DECKS, resolve_deck_dir, available_decks,
                               deck_csv_path as _deck_csv_path,
                               agent_main_path as _agent_main_path)
except ImportError:
    from experiments.web.deck_registry import (DECKS, resolve_deck_dir, available_decks,
                                               deck_csv_path as _deck_csv_path,
                                               agent_main_path as _agent_main_path)

try:
    import live_tuning as LT
except ImportError:
    from experiments.web import live_tuning as LT

def _find_available_decks():
    return available_decks(ROOT)

ME = {'mod': None, 'deck': None, 'Policy': None, 'name': None, 'base_params': {}}
_LOADED = {}   # name -> {deck, mod, Policy, base_params}


def _load_deck(name):
    """Load a deck's main.py once: its deck list, module (has agent()), and *Policy if any."""
    if name not in DECKS:
        name = list(DECKS.keys())[0]
    if name in _LOADED:
        return _LOADED[name]
    dc = _deck_csv_path(name, ROOT)
    ag = _agent_main_path(name, ROOT)
    if dc is None or not os.path.exists(dc):
        raise FileNotFoundError("deck.csv not found for '%s'" % name)
    if ag is None or not os.path.exists(ag):
        raise FileNotFoundError("main.py not found for '%s'" % name)
    print("[load] deck=%s csv=%s agent=%s" % (name, dc, ag))
    deck = [int(l) for l in open(dc) if l.strip()]
    mod = types.ModuleType('deck_' + name)
    agent_dir = os.path.dirname(os.path.abspath(ag))
    mod.__dict__['__file__'] = os.path.abspath(ag)
    base_dir = ROOT + '/agents/_base'
    if os.path.isdir(base_dir):
        sys.path.insert(0, base_dir)
    sys.path.insert(0, agent_dir)
    cur = os.getcwd(); os.chdir(agent_dir)
    try:
        exec(compile(open(ag).read(), ag, 'exec'), mod.__dict__)
    finally:
        os.chdir(cur)
    cands = [v for k, v in mod.__dict__.items()
             if k.endswith('Policy') and isinstance(v, type)
             and k not in ('BasePolicy', 'GenericPolicy')
             and not getattr(v, '__abstractmethods__', None)]
    Policy = cands[0] if cands else None
    # Snapshot of the agent's params.json-derived P dict, captured before any
    # runtime override is ever applied -- this is the "params.json" half of
    # the live-tuning override layer (we never write back to the file itself).
    base_params = dict(getattr(mod, 'P', {}) or {})
    _LOADED[name] = {'deck': deck, 'mod': mod, 'Policy': Policy, 'base_params': base_params}
    return _LOADED[name]



def load_me(name):
    """Load the deck you pilot (per-option AI scores shown if it has a *Policy)."""
    avail = _find_available_decks()
    if not avail:
        raise FileNotFoundError(
            "No agent decks found under %s/agents/. "
            "Copy ptcg-abc agents/ directory first." % ROOT)
    pick = name if name in avail else avail[0]
    L = _load_deck(pick)
    ME.update(mod=L['mod'], deck=L['deck'], Policy=L['Policy'], name=pick,
              base_params=L.get('base_params', {}))
    LT.reset_runtime_overrides()


avail = _find_available_decks()
if avail:
    load_me(avail[0])
    print("[init] %d decks available: %s" % (len(avail), ', '.join(avail)))
else:
    print("[warn] No agent decks found under %s/agents/. "
          "Copy ptcg-abc agents/ directory to start." % ROOT)


def load_opp(name):
    avail = _find_available_decks()
    pick = name if name in avail else avail[0]
    L = _load_deck(pick)
    return L['mod'], L['deck']


# ── game session (single global game; single-threaded server) ────────────────
GAME = {'obs_dict': None, 'opp_mod': None, 'opp_deck': None, 'human': 0, 'over': True, 'log': [], 'logseq': 0,
        'trace_path': None, 'last_state': None, 'recording': False,
        'game_id': None, 'last_live_review': None, 'last_override': None,
        'frozen_review_obs': None}

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
            if g['over']:
                _record_game_result(obs.current)
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
    energy_detail = [_ENERGY_NAMES.get(e, '?') for e in (p.energies or [])]
    return {'id': p.id, 'name': cname(p.id).replace("Ethan's ", "").replace("Iono's ", ""),
            'hp': p.hp, 'maxHp': p.maxHp, 'energy': len(p.energies),
            'energyDetail': energy_detail,
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


_ENERGY_NAMES = {1: '草', 2: '炎', 3: '水', 4: '雷', 5: '超', 6: '闘', 7: '悪', 8: '鋼', 9: '竜', 0: '無'}


def _energy_type_label(card_id):
    """Return energy type name for a basic energy card."""
    _ID_TO_TYPE = {1: '草', 2: '炎', 3: '水', 4: '雷', 5: '超', 6: '闘', 7: '悪', 8: '鋼'}
    label = _ID_TO_TYPE.get(card_id, '')
    if label:
        return label
    cd = CT.get(card_id)
    if cd:
        et = getattr(cd, 'energyType', None)
        if et is not None:
            return _ENERGY_NAMES.get(et, '')
    return ''


def _energy_label_from_card(c):
    """Return energy type label from a card object (energy card or attached energy)."""
    if c is None:
        return ''
    label = _energy_type_label(c.id)
    if label:
        return label
    et = getattr(c, 'energyType', None)
    if et is not None:
        return _ENERGY_NAMES.get(et, '')
    return ''


def _resolve_energy_type(obs, opt, player_index):
    """Get energy type from a Pokemon's energyCards using energyIndex."""
    ei = getattr(opt, 'energyIndex', None)
    area = getattr(opt, 'area', None)
    idx = opt.index
    if ei is None or area is None:
        return ''
    try:
        player = obs.current.players[player_index]
        poke = None
        if area == AreaType.ACTIVE and player.active:
            poke = player.active[idx] if idx < len(player.active) else player.active[0]
        elif area == AreaType.BENCH and player.bench:
            poke = player.bench[idx] if idx < len(player.bench) else None
        if poke and hasattr(poke, 'energyCards') and poke.energyCards:
            if ei < len(poke.energyCards):
                ec = poke.energyCards[ei]
                return _energy_type_label(ec.id)
        if poke and hasattr(poke, 'energies') and poke.energies:
            if ei < len(poke.energies):
                return _ENERGY_NAMES.get(poke.energies[ei], '')
    except Exception:
        pass
    return ''


def _pos_label(area, index):
    """Return a position label like 'バトル場' or 'ベンチ2'."""
    if area == AreaType.ACTIVE:
        return 'バトル場'
    if area == AreaType.BENCH:
        return f'ベンチ{index + 1}' if index is not None else 'ベンチ'
    if area == AreaType.HAND:
        return '手札'
    if area == AreaType.DISCARD:
        return 'トラッシュ'
    return ''


def _resolve_player_index(obs, opt, my_index):
    """Determine which player's card an option refers to.
    Try my_index first; if no card found, try opponent."""
    area = getattr(opt, 'area', None)
    if area is None or area not in (AreaType.ACTIVE, AreaType.BENCH):
        return my_index
    c = get_card(obs, area, opt.index, my_index)
    if c is not None:
        return my_index
    c2 = get_card(obs, area, opt.index, 1 - my_index)
    if c2 is not None:
        return 1 - my_index
    return my_index


def _card_detail(c):
    """Return short detail string for a Pokemon (HP/energy) to distinguish copies."""
    if c is None:
        return ''
    hp = getattr(c, 'hp', None)
    maxhp = getattr(c, 'maxHp', None)
    energies = getattr(c, 'energies', None)
    parts = []
    if hp is not None and maxhp:
        parts.append(f'HP{hp}/{maxhp}')
    if energies:
        e_types = [_ENERGY_NAMES.get(e, '?') for e in energies]
        parts.append(''.join(e_types))
    return f' [{", ".join(parts)}]' if parts else ''


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
        pos = _pos_label(opt.area, opt.index)
        detail = _card_detail(c) if c else ''
        return f'✨ 特性 {cname(c.id) if c else ""} ({pos}){detail}'
    if t == OptionType.EVOLVE:
        c = get_card(obs, AreaType.HAND, opt.index, my_index)
        return f'⬆ 進化 → {cname(c.id) if c else ""}'
    cn = CTX.get(obs.select.context, '') or ''
    if t in (OptionType.ENERGY, OptionType.ATTACH):
        tgt = get_card(obs, opt.inPlayArea, opt.inPlayIndex, my_index)
        tn = cname(tgt.id).replace(chr(39), '') if tgt else '?'
        pos = _pos_label(opt.inPlayArea, opt.inPlayIndex)
        detail = _card_detail(tgt) if tgt else ''
        etype = ''
        if t == OptionType.ATTACH:
            src = get_card(obs, getattr(opt, 'area', None) or AreaType.HAND, opt.index, my_index)
            etype = _energy_label_from_card(src)
        elif t == OptionType.ENERGY:
            etype = _resolve_energy_type(obs, opt, my_index)
        etype_s = f'{etype}エネ ' if etype else 'エネルギー'
        if 'DISCARD' in cn:
            return f'🗑 {etype_s}をトラッシュ ({tn} {pos}){detail}'
        if 'TO_HAND' in cn:
            return f'✋ {etype_s}を手札に ({tn} {pos}){detail}'
        return f'🔋 {etype_s}をつける → {tn} ({pos}){detail}'
    if t in (OptionType.PLAY, OptionType.CARD, OptionType.TOOL_CARD, OptionType.ENERGY_CARD):
        area = getattr(opt, 'area', None) or AreaType.HAND
        pi = _resolve_player_index(obs, opt, my_index)
        c = get_card(obs, area, opt.index, pi)
        nm = cname(c.id) if c else 'card'
        etype = ''
        if t == OptionType.ENERGY_CARD:
            etype = _resolve_energy_type(obs, opt, pi)
            if not etype and c:
                etype = _energy_label_from_card(c)
        elif c:
            cd = CT.get(c.id)
            if cd and cd.cardType in (CardType.BASIC_ENERGY, CardType.SPECIAL_ENERGY):
                etype = _energy_label_from_card(c)
        if etype:
            nm = f'{etype}エネ ({nm})'
        pos = _pos_label(area, opt.index)
        detail = _card_detail(c) if c and area != AreaType.HAND else ''
        opp_tag = ' [相手]' if pi != my_index and area in (AreaType.ACTIVE, AreaType.BENCH) else ''
        pos_suffix = f' ({pos}){opp_tag}' if pos and area != AreaType.HAND else ''
        if t == OptionType.PLAY:
            return f'▶ {nm} を使う'
        if 'DISCARD' in cn:
            return f'🗑 {nm} をトラッシュ{pos_suffix}{detail}'
        if 'TO_HAND' in cn:
            return f'🔍 {nm} を手札に加える{pos_suffix}{detail}'
        if 'TO_DECK' in cn or 'TO_PRIZE' in cn:
            return f'↩ {nm} を戻す{pos_suffix}{detail}'
        if 'SWITCH' in cn or 'ACTIVE' in cn:
            return f'⬆ {nm} をバトル場に{pos_suffix}{detail}'
        if 'BENCH' in cn or 'FIELD' in cn:
            return f'➕ {nm} をベンチに{pos_suffix}{detail}'
        return f'▶ {nm}{pos_suffix}{detail}'
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
    dc = _deck_csv_path(name, ROOT)
    if dc is None or not os.path.exists(dc):
        body = f'<h1>{DECKS[name][0]}</h1><p>deck.csv が見つかりません。agents/ をコピーしてください。</p>'
        return _DECK_HTML.replace('{{nav}}', nav).replace('{{body}}', body).replace('{{title}}', DECKS[name][0])
    from collections import Counter
    deck = [int(l) for l in open(dc) if l.strip()]
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


_VALID_GOALS = {
    'setup_board', 'prepare_next_turn_attack', 'take_ko_now', 'take_two_prizes',
    'close_game', 'prevent_loss', 'improve_hand', 'preserve_resources', 'disrupt_opponent',
}
_VALID_WIN_PLANS = {
    'ko_active', 'boss_two_prize_target', 'raging_bolt_big_damage_next_turn',
    'ogerpon_energy_engine', 'remove_main_attacker', 'win_by_prize_race',
    'win_by_resource', 'win_by_deck_out_avoidance',
}
_VALID_RISKS = {
    'active_may_be_ko_next_turn', 'no_next_attacker', 'not_enough_energy',
    'low_hand', 'low_deck', 'boss_needed_for_win', 'bench_liability', 'behind_prize_race',
}
_VALID_REASONS = {
    'take_ko_now', 'take_two_prizes', 'prepare_next_turn_attack',
    'build_raging_bolt_damage', 'prioritize_energy_acceleration',
    'improve_hand', 'avoid_bad_hand', 'preserve_resources', 'avoid_deck_out',
    'gust_win_condition', 'disrupt_opponent', 'setup_board',
    'retreat_or_switch_safety', 'other',
}


def _sanitize_strategy_tags(body, option_count):
    """Validate and sanitize strategy tags from client."""
    goal = body.get('turn_goal', '')
    if goal not in _VALID_GOALS:
        goal = ''
    return {
        'turn_goal': goal,
        'win_plan_tags': [t for t in body.get('win_plan_tags', []) if t in _VALID_WIN_PLANS],
        'risk_flags': [t for t in body.get('risk_flags', []) if t in _VALID_RISKS],
        'human_reason_tags': [t for t in body.get('human_reason_tags', []) if t in _VALID_REASONS],
        'human_considered': [i for i in body.get('human_considered', [])
                             if isinstance(i, int) and 0 <= i < option_count],
    }


def _record_game_result(state):
    """Record game result to trace JSONL. Never raises."""
    try:
        if not GAME.get('recording'):
            return
        tp = GAME.get('trace_path')
        if not tp:
            return
        try:
            from human_trace_writer import build_game_result_entry, write_trace_entry
        except ImportError:
            from experiments.web.human_trace_writer import build_game_result_entry, write_trace_entry

        if state.result == GAME['human']:
            result = "win"
        elif state.result == 1 - GAME['human']:
            result = "loss"
        else:
            result = "draw"

        entry = build_game_result_entry(
            deck_name=ME.get('name', ''),
            opp_deck=GAME.get('opp_name', ''),
            result=result,
            turns=state.turn,
        )
        write_trace_entry(tp, entry)
    except Exception:
        pass


def _poke_trace_info(p):
    """Build detailed Pokemon info for trace recording."""
    if p is None:
        return None
    cd = CT.get(p.id)
    energy_types = [_ENERGY_NAMES.get(e, '?') for e in (p.energies or [])]
    info = {
        'id': p.id, 'name': cname(p.id),
        'hp': p.hp, 'maxHp': p.maxHp,
        'energy': len(p.energies),
        'energy_types': energy_types,
    }
    if cd:
        info['type'] = _ENERGY_NAMES.get(cd.energyType, '')
        info['weakness'] = cd.weakness
        info['ex'] = cd.ex
    return info


def _live_review_for(entry):
    """Build the live disagreement-review payload for the decision the human
    just submitted. Never raises -- a failure here must not break /select."""
    try:
        try:
            from disagreement_review_builder import build_live_review
        except ImportError:
            from experiments.web.disagreement_review_builder import build_live_review
        return build_live_review(entry)
    except Exception:
        return None


def _suggested_params_payload(live_review):
    """[{param, current_value, description}] for the Live Tuning Panel. Never raises."""
    try:
        eff = LT.effective_params(ME.get('base_params', {}))
        names = LT.suggest_params_for_live_review(live_review, ME.get('base_params', {}))
        return [{'param': p, 'current_value': eff.get(p), 'description': LT.describe_param(p)} for p in names]
    except Exception:
        return []


def _tuning_compute_fn(params_dict):
    """Re-run the *reviewed* decision under a given effective-params dict.
    Used only by the Live Tuning Panel's preview -- restores ME['mod'].P
    to whatever it was before returning, so this never leaks into real play.

    Uses GAME['frozen_review_obs'] (a snapshot taken right before the human's
    flagged decision was applied) rather than the live GAME['obs_dict'] --
    by the time the human opens the panel, /select has already advanced the
    game to the *next* decision, so scoring the live obs_dict would compare
    candidates for a different decision than the one being reviewed. Falls
    back to the live obs_dict when there's no frozen snapshot (e.g. a
    preview requested with no active disagreement).

    For MAIN-context decisions the real agent() picks via
    choose_with_search(), which layers an impact_*/search_weight_* lookahead
    score on top of rank()'s immediate score -- not rank() alone. Mirroring
    that same formula here (read-only calls into the policy's existing
    _estimate_action_impact/_simulate_opponent_turn helpers, no main.py
    changes) keeps the preview honest about what the competition agent would
    actually do, confirmed by driving real games through this server in WSL."""
    obs_dict = GAME.get('frozen_review_obs') or GAME.get('obs_dict')
    if obs_dict is None or ME.get('Policy') is None:
        return []
    obs = to_observation_class(obs_dict)
    if obs.select is None:
        return []
    mod = ME['mod']
    snapshot = dict(mod.P)
    try:
        mod.P.clear(); mod.P.update(params_dict)
        policy = ME['Policy'](obs)
        ranked, scores = policy.rank()
        out = []
        use_lookahead = (obs.select.context == SelectContext.MAIN
                          and hasattr(policy, '_estimate_action_impact'))
        if use_lookahead:
            try:
                opp_scenarios = policy._simulate_opponent_turn()
                avg_risk = sum(s[2] for s in opp_scenarios) / len(opp_scenarios) if opp_scenarios else 0
            except Exception:
                avg_risk = 0
            w_imm = policy.p("search_weight_immediate", 0.6)
            w_fut = policy.p("search_weight_future", 0.3)
            w_risk = policy.p("search_weight_risk", 0.1)
            # Score every option, not just rank()'s base top-5 -- the human's
            # actual pick can fall outside the base ranking (that's often
            # *why* it's a disagreement), and the value-search feature needs
            # every candidate's score to find a param value that makes the
            # human's pick the new top recommendation.
            for i in ranked:
                opt = obs.select.option[i]
                try:
                    future_delta = policy._estimate_action_impact(opt)
                except Exception:
                    future_delta = 0
                risk_adj = avg_risk if opt.type in (OptionType.ATTACK, OptionType.END) else 0
                final = scores[i] * w_imm + future_delta * w_fut + risk_adj * w_risk
                out.append({'label': label_option(obs, opt, GAME['human']), 'score': round(float(final), 1)})
        else:
            for i, opt in enumerate(obs.select.option):
                out.append({'label': label_option(obs, opt, GAME['human']),
                            'score': round(float(scores[i]), 1) if i < len(scores) else 0})
        return out
    finally:
        mod.P.clear(); mod.P.update(snapshot)


def _runtime_tuning_preview():
    """Before/after AI recommendation comparison using the currently staged
    runtime overrides. Never raises -- a broken policy just yields no preview."""
    try:
        return LT.build_tuning_preview(_tuning_compute_fn, ME.get('base_params', {}))
    except Exception:
        return {'before': {'recommended_action': None, 'top_candidates': []},
                'after': {'recommended_action': None, 'top_candidates': []}, 'changed': False}


def _log_tuning_event(param=None, old_value=None, new_value=None, preview=None,
                       review_label='', confidence='', note=''):
    """Append one session_tuning_log.jsonl row. Never raises -- logging must
    never be able to break gameplay."""
    try:
        _turn_obs_dict = GAME.get('frozen_review_obs') or GAME.get('obs_dict')
        entry = LT.build_tuning_log_entry(
            game_id=GAME.get('game_id'),
            turn=(to_observation_class(_turn_obs_dict).current.turn if _turn_obs_dict else None),
            live_review=GAME.get('last_live_review'),
            param=param, old_value=old_value, new_value=new_value,
            preview=preview or {}, review_label=review_label, confidence=confidence, note=note,
        )
        LT.append_tuning_log(entry)
    except Exception:
        pass


def _record_human_trace(human_indices, strategy_tags=None):
    """Record a human decision to the trace JSONL. Never raises."""
    try:
        tp = GAME.get('trace_path')
        if not tp:
            return
        obs = to_observation_class(GAME['obs_dict']) if GAME['obs_dict'] else None
        if obs is None or obs.select is None:
            return
        if obs.current.yourIndex != GAME['human']:
            return

        st = obs.current
        options_info = []
        scores = [0] * len(obs.select.option)
        ai_pick = []
        try:
            if ME['Policy'] is not None:
                policy = ME['Policy'](obs)
                ranked, scores = policy.rank()
                ai_pick = normalize_selection(ranked, scores, obs.select)
            elif ME['mod'].__dict__.get('agent') is not None:
                ai_pick = sorted(set(ME['mod'].agent(GAME['obs_dict'])))
        except Exception:
            pass

        for i, opt in enumerate(obs.select.option):
            cid, aid = option_ids(obs, opt, GAME['human'])
            options_info.append({
                'i': i,
                'label': label_option(obs, opt, GAME['human']),
                'score': round(float(scores[i]), 1) if i < len(scores) else 0,
                'type': int(opt.type) if opt.type is not None else -1,
                'cardId': cid,
                'attackId': aid,
            })

        try:
            from human_trace_writer import build_trace_entry, write_trace_entry
        except ImportError:
            from experiments.web.human_trace_writer import build_trace_entry, write_trace_entry

        me = st.players[GAME['human']]
        op = st.players[1 - GAME['human']]
        my_act = me.active[0] if me.active else None
        op_act = op.active[0] if op.active else None

        params_path = os.environ.get("POKEMON_AI_PARAMS_PATH", "")
        entry = build_trace_entry(
            deck_name=ME.get('name', ''),
            turn=st.turn,
            context=CTX.get(obs.select.context, str(obs.select.context)),
            options=options_info,
            ai_pick=ai_pick,
            human_pick=human_indices,
            params_path=params_path,
            opp_deck=GAME.get('opp_name', ''),
            opp_active=_poke_trace_info(op_act),
            my_active=_poke_trace_info(my_act),
            my_prizes=len(me.prize),
            opp_prizes=len(op.prize),
        )
        if strategy_tags:
            entry.update(strategy_tags)
        try:
            if ME['Policy'] is not None:
                p = ME['Policy'](obs)
                entry['agent_goals'] = sorted(p.goals) if hasattr(p, 'goals') else []
                entry['agent_risks'] = sorted(p.risks) if hasattr(p, 'risks') else []
        except Exception:
            pass
        write_trace_entry(tp, entry)
        return entry
    except Exception:
        pass


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
        if u.path == '/decks':
            avail = _find_available_decks()
            return self._send(200, json.dumps([{'id': k, 'name': DECKS[k][0]} for k in avail]))
        if u.path == '/deck' or u.path.startswith('/deck/'):
            name = u.path[len('/deck/'):] if u.path.startswith('/deck/') else ''
            return self._send(200, deck_page_html(name).encode('utf-8'), 'text/html; charset=utf-8')
        if u.path == '/new':
            q = parse_qs(u.query)
            opp = q.get('opp', ['dragapult'])[0]
            load_me(q.get('me', ['megastarmie'])[0])   # which deck you pilot
            m, deck = load_opp(opp)
            GAME['opp_mod'], GAME['opp_deck'] = m, deck
            GAME['opp_name'] = opp
            GAME['human'] = 0
            GAME['recording'] = q.get('rec', ['0'])[0] == '1'
            GAME['log'] = []; GAME['logseq'] = 0
            GAME['game_id'] = _time.strftime("%Y%m%d_%H%M%S")
            GAME['last_live_review'] = None
            GAME['last_override'] = None
            GAME['frozen_review_obs'] = None
            LT.reset_runtime_overrides()
            if ME.get('mod') is not None:
                ME['mod'].P.clear(); ME['mod'].P.update(ME.get('base_params', {}))
            try:
                from human_trace_writer import trace_path as _tp
                GAME['trace_path'] = _tp(_time.strftime("%Y%m%d_%H%M%S"))
            except ImportError:
                try:
                    from experiments.web.human_trace_writer import trace_path as _tp
                    GAME['trace_path'] = _tp(_time.strftime("%Y%m%d_%H%M%S"))
                except ImportError:
                    GAME['trace_path'] = None
            GAME['obs_dict'], _ = battle_start(ME['deck'], deck)
            GAME['over'] = False
            _advance_opponent()
            mn = DECKS.get(ME['name'], (ME['name'],))[0]; on = DECKS.get(opp, (opp,))[0]
            return self._send(200, json.dumps(state_json(f'新対戦:{mn} vs {on}')))
        if u.path == '/state':
            return self._send(200, json.dumps(state_json()))
        if u.path == '/runtime_params':
            return self._send(200, json.dumps({
                'params': ME.get('base_params', {}),
                'overrides': LT.get_runtime_overrides(),
            }))
        return self._send(404, '{}')

    def do_POST(self):
        u = urlparse(self.path)
        if u.path == '/select':
            ln = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(ln) or '{}')
            idx = body.get('indices', [])
            recording = body.get('recording', False)
            GAME['recording'] = recording
            obs_for_san = to_observation_class(GAME['obs_dict']) if GAME.get('obs_dict') else None
            opt_count = len(obs_for_san.select.option) if obs_for_san and obs_for_san.select else 0
            strategy_tags = _sanitize_strategy_tags(body, opt_count) if recording else {}
            try:
                traced_entry = None
                pre_select_obs_dict = None
                if recording:
                    traced_entry = _record_human_trace(idx, strategy_tags)
                    if traced_entry is not None and GAME.get('obs_dict') is not None:
                        # Snapshot the decision being reviewed *before* _select()
                        # advances the game -- the tuning preview must re-score
                        # this exact disagreement, not whatever decision comes
                        # next.
                        pre_select_obs_dict = copy.deepcopy(GAME['obs_dict'])
                _note_action(GAME['obs_dict'], idx)
                GAME['obs_dict'] = _select(idx)
                _advance_opponent()
                payload = state_json()
                if traced_entry is not None:
                    payload['live_review'] = _live_review_for(traced_entry)
                    payload['suggested_params'] = _suggested_params_payload(payload['live_review'])
                    GAME['last_live_review'] = payload['live_review']
                    lr = payload['live_review']
                    GAME['frozen_review_obs'] = pre_select_obs_dict if (lr and lr.get('show')) else None
                return self._send(200, json.dumps(payload))
            except Exception as e:
                return self._send(200, json.dumps(state_json(f'エラー: {e}')))
        if u.path == '/runtime_params':
            # Stage one runtime-only param override and apply it to the live
            # agent immediately (session-scoped; params.json is never touched).
            ln = int(self.headers.get('Content-Length', 0))
            try:
                body = json.loads(self.rfile.read(ln) or '{}')
            except Exception:
                body = {}
            param = body.get('param')
            value = body.get('value')
            base = ME.get('base_params', {})
            old_value = base.get(param) if isinstance(param, str) else None
            ok, err = LT.set_runtime_override(base, param, value)
            if not ok:
                return self._send(400, json.dumps({'ok': False, 'error': err}))
            if ME.get('mod') is not None:
                ME['mod'].P.clear(); ME['mod'].P.update(LT.effective_params(base))
            GAME['last_override'] = {'param': param, 'old_value': old_value, 'new_value': value}
            preview = _runtime_tuning_preview()
            _log_tuning_event(param=param, old_value=old_value, new_value=value, preview=preview)
            return self._send(200, json.dumps({
                'ok': True, 'overrides': LT.get_runtime_overrides(), 'preview': preview,
            }))
        if u.path == '/runtime_params/reset':
            LT.reset_runtime_overrides()
            if ME.get('mod') is not None:
                ME['mod'].P.clear(); ME['mod'].P.update(ME.get('base_params', {}))
            GAME['last_override'] = None
            return self._send(200, json.dumps({'ok': True, 'overrides': LT.get_runtime_overrides()}))
        if u.path == '/runtime_params/preview':
            preview = _runtime_tuning_preview()
            last = GAME.get('last_override') or {}
            _log_tuning_event(param=last.get('param'), old_value=last.get('old_value'),
                              new_value=last.get('new_value'), preview=preview)
            return self._send(200, json.dumps(preview))
        if u.path == '/runtime_params/suggest_value':
            # "What value would make the AI recommend what I picked instead?"
            # -- searches for a param value that flips the reviewed
            # decision's top recommendation to the human's actual pick.
            ln = int(self.headers.get('Content-Length', 0))
            try:
                body = json.loads(self.rfile.read(ln) or '{}')
            except Exception:
                body = {}
            param = body.get('param')
            base = ME.get('base_params', {})
            if not isinstance(param, str) or param not in base:
                return self._send(400, json.dumps({'ok': False, 'error': 'unknown param'}))
            lr = GAME.get('last_live_review') or {}
            target_label = lr.get('human_action')
            if not target_label:
                return self._send(200, json.dumps({'ok': False, 'error': 'no active disagreement to target'}))
            try:
                eff = LT.effective_params(base)
                result = LT.find_param_value_for_target(_tuning_compute_fn, eff, param, target_label)
                result['ok'] = True
                return self._send(200, json.dumps(result))
            except Exception as e:
                return self._send(200, json.dumps({'ok': False, 'error': str(e)}))
        if u.path == '/runtime_params/log':
            # Explicit "調整ログに保存" -- attach a reviewer label/confidence/note
            # to the latest before/after comparison.
            ln = int(self.headers.get('Content-Length', 0))
            try:
                body = json.loads(self.rfile.read(ln) or '{}')
            except Exception:
                body = {}
            review_label = body.get('review_label', '') if body.get('review_label') in LT.LABELS else ''
            confidence = body.get('confidence', '') if body.get('confidence') in LT.CONFIDENCES else ''
            note = str(body.get('note', ''))[:2000]
            preview = _runtime_tuning_preview()
            last = GAME.get('last_override') or {}
            _log_tuning_event(param=last.get('param'), old_value=last.get('old_value'),
                              new_value=last.get('new_value'), preview=preview,
                              review_label=review_label, confidence=confidence, note=note)
            return self._send(200, json.dumps({'ok': True}))
        return self._send(404, '{}')


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f'PTCG sandbox: http://localhost:{port}  (Ctrl-C to stop)')
    ThreadingHTTPServer(('0.0.0.0', port), H).serve_forever()
