"""
PTCG Deck Builder — Streamlit UI (multi-deck)
Usage:
    streamlit run tools/deck_builder.py
"""
import csv
import json
import os
import shutil
import urllib.error
import urllib.parse
import urllib.request

import streamlit as st

_ROOT      = os.path.join(os.path.dirname(__file__), "..")
MASTER_PATH    = os.path.join(_ROOT, "data", "card_master.csv")
KNOWLEDGE_PATH = os.path.join(_ROOT, "data", "card_knowledge.csv")
DETAIL_PATH    = os.path.join(_ROOT, "data", "card_detail_raw.csv")
JA_CACHE_PATH  = os.path.join(_ROOT, "data", "card_effects_ja.json")
DECKS_DIR      = os.path.join(_ROOT, "data", "decks")
SUBMIT_PATH    = os.path.join(_ROOT, "deck.csv")
DATA_DECK_PATH = os.path.join(_ROOT, "data", "deck.csv")

os.makedirs(DECKS_DIR, exist_ok=True)

# TCGdex CDN set code mapping (PTCGO code → TCGdex set ID)
SET_MAP = {
    "SVE":   "sve",
    "SVI":   "sv01",
    "PAL":   "sv02",
    "OBF":   "sv03",
    "MEW":   "sv03.5",
    "PAR":   "sv04",
    "PFL":   "sv04.5",
    "TEF":   "sv05",
    "TWM":   "sv06",
    "SFA":   "sv06.5",
    "SCR":   "sv07",
    "SSP":   "sv08",
    "PRE":   "sv08.5",
    "SVP":   "svp",
    "JTG":   "sv09",
    "DRI":   "sv10",
    "BLK":   "sv10.5b",
    "WHT":   "sv10.5w",
}

# Basic energy cards have no CDN image in SVE → use copies from sets that do
ENERGY_FALLBACK_IMAGES = {
    "Basic Grass Energy":     "https://assets.tcgdex.net/en/sv/sv02/278",
    "Basic Fire Energy":      "https://assets.tcgdex.net/en/sv/sv03/230",
    "Basic Water Energy":     "https://assets.tcgdex.net/en/sv/sv02/279",
    "Basic Lightning Energy": "https://assets.tcgdex.net/en/sv/sv01/257",
    "Basic Psychic Energy":   "https://assets.tcgdex.net/en/sv/sv03.5/207",
    "Basic Fighting Energy":  "https://assets.tcgdex.net/en/sv/sv01/258",
    "Basic Darkness Energy":  "https://assets.tcgdex.net/en/sv/sv06.5/098",
    "Basic Metal Energy":     "https://assets.tcgdex.net/en/sv/sv06.5/099",
}

# Energy type → Japanese symbol (PTCG convention)
ENERGY_JP = {
    "Grass":      "草",
    "Fire":       "炎",
    "Water":      "水",
    "Lightning":  "雷",
    "Psychic":    "超",
    "Fighting":   "闘",
    "Darkness":   "悪",
    "Metal":      "鋼",
    "Dragon":     "龍",
    "Fairy":      "妖",
    "Colorless":  "無",
}

TRAINER_TYPE_JP = {
    "Item":      "グッズ",
    "Supporter": "サポート",
    "Stadium":   "スタジアム",
    "Tool":      "ポケモンのどうぐ",
}

WEAKNESS_TYPE_JP = {"×2": "×2", "×4": "×4"}

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(page_title="PTCG Deck Builder", page_icon="🃏", layout="wide")

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

@st.cache_data
def load_master() -> list[dict]:
    if not os.path.exists(MASTER_PATH):
        return []
    with open(MASTER_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@st.cache_data
def load_knowledge() -> dict[str, dict]:
    if not os.path.exists(KNOWLEDGE_PATH):
        return {}
    with open(KNOWLEDGE_PATH, newline="", encoding="utf-8") as f:
        return {str(r["card_id"]): r for r in csv.DictReader(f)}


@st.cache_data
def load_card_detail() -> dict[str, dict]:
    if not os.path.exists(DETAIL_PATH):
        return {}
    with open(DETAIL_PATH, newline="", encoding="utf-8") as f:
        return {str(r["card_id"]): r for r in csv.DictReader(f)}


def get_image_base_url(cid: str, expn: str, cno: str, detail_map: dict,
                       card_name: str = "") -> str:
    """Return TCGdex CDN base URL (no quality/format suffix). Empty string if unknown."""
    # Energy cards in SVE have no CDN image → use a known copy from another set
    if card_name in ENERGY_FALLBACK_IMAGES:
        return ENERGY_FALLBACK_IMAGES[card_name]

    # Prefer existing SV-era URL stored in card_detail_raw.csv
    existing = detail_map.get(cid, {}).get("images_small", "").strip()
    if existing and "/sv/" in existing:
        return existing

    set_id = SET_MAP.get((expn or "").upper(), "")
    if not set_id or set_id == "sve" or not cno:
        return ""
    try:
        cno_padded = f"{int(cno):03d}"
    except (ValueError, TypeError):
        cno_padded = str(cno)
    return f"https://assets.tcgdex.net/en/sv/{set_id}/{cno_padded}"


def get_api_card_id(cid: str, expn: str, cno: str, detail_map: dict) -> str:
    """Return TCGdex API card ID (e.g. 'sv06-130'). Used for full card data fetch."""
    stored = detail_map.get(cid, {}).get("api_card_id", "").strip()
    if stored:
        # Normalise stored IDs like 'sve-2' → 'sve-002'
        parts = stored.rsplit("-", 1)
        if len(parts) == 2 and parts[1].isdigit():
            stored = f"{parts[0]}-{int(parts[1]):03d}"
        return stored
    set_id = SET_MAP.get((expn or "").upper(), "")
    if not set_id or not cno:
        return ""
    try:
        return f"{set_id}-{int(cno):03d}"
    except (ValueError, TypeError):
        return f"{set_id}-{cno}"


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_tcgdex_full(api_card_id: str) -> dict:
    """Fetch full card data (attacks, abilities, effect) from TCGdex EN API."""
    if not api_card_id:
        return {}
    url = f"https://api.tcgdex.net/v2/en/cards/{api_card_id}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Japanese translation (Google Translate unofficial, file-cached)
# ---------------------------------------------------------------------------

def _ja_cache() -> dict:
    """Load per-session translation cache (backed by JA_CACHE_PATH)."""
    if "ja_cache" not in st.session_state:
        try:
            with open(JA_CACHE_PATH, encoding="utf-8") as f:
                st.session_state.ja_cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            st.session_state.ja_cache = {}
    return st.session_state.ja_cache


def _save_ja_cache():
    try:
        with open(JA_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(st.session_state.ja_cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _translate_ja(text: str, key: str) -> str:
    """Return Japanese translation of text (cached; empty string on failure)."""
    if not text:
        return ""
    cache = _ja_cache()
    if key in cache:
        return cache[key]
    try:
        q = urllib.parse.quote(text[:1500])
        url = (
            "https://translate.googleapis.com/translate_a/single"
            f"?client=gtx&sl=en&tl=ja&dt=t&q={q}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=7) as r:
            data = json.loads(r.read().decode("utf-8"))
        translated = "".join(seg[0] for seg in data[0] if seg[0])
        cache[key] = translated
        _save_ja_cache()
        return translated
    except Exception:
        return ""


def _deck_path(name: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip()
    return os.path.join(DECKS_DIR, f"{safe}.csv")


def list_decks() -> list[str]:
    files = sorted(
        f[:-4] for f in os.listdir(DECKS_DIR)
        if f.endswith(".csv") and not f.startswith(".")
    )
    return files


def read_deck(name: str) -> dict[str, int]:
    path = _deck_path(name)
    if not os.path.exists(path):
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    result = {}
    for r in rows:
        cid = str(r.get("card_id", "")).strip()
        try:
            result[cid] = int(r.get("count", 1))
        except (ValueError, TypeError):
            result[cid] = 1
    return result


def write_deck(name: str, deck: dict[str, int], master_map: dict):
    rows = _deck_to_rows(deck, master_map)
    path = _deck_path(name)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["card_id", "card_name", "count"])
        w.writeheader()
        w.writerows(rows)


def _deck_to_rows(deck: dict[str, int], master_map: dict) -> list[dict]:
    rows = []
    for cid, cnt in sorted(deck.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 9999):
        name = master_map.get(cid, {}).get("card_name_en", "")
        rows.append({"card_id": cid, "card_name": name, "count": cnt})
    return rows


def set_active_deck(name: str, deck: dict[str, int], master_map: dict):
    rows = _deck_to_rows(deck, master_map)
    for path in (SUBMIT_PATH, DATA_DECK_PATH):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["card_id", "card_name", "count"])
            w.writeheader()
            w.writerows(rows)


def active_deck_name() -> str:
    if not os.path.exists(SUBMIT_PATH):
        return ""
    active = read_deck_from_path(SUBMIT_PATH)
    for name in list_decks():
        if read_deck(name) == active:
            return name
    return ""


def read_deck_from_path(path: str) -> dict[str, int]:
    if not os.path.exists(path):
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    result = {}
    for r in rows:
        cid = str(r.get("card_id", "")).strip()
        try:
            result[cid] = int(r.get("count", 1))
        except (ValueError, TypeError):
            result[cid] = 1
    return result


# ---------------------------------------------------------------------------
# Card type helpers
# ---------------------------------------------------------------------------

TYPE_EMOJI = {"Pokemon": "🔴", "Trainer": "🔵", "Energy": "⚡"}


def _infer_type(cid: str, knowledge: dict) -> str:
    if cid in knowledge:
        t = knowledge[cid].get("card_type", "")
        if t:
            return t
    try:
        n = int(cid)
        if 1 <= n <= 20:    return "Energy"
        if 21 <= n <= 1076: return "Pokemon"
        if n >= 1077:       return "Trainer"
    except (ValueError, TypeError):
        pass
    return ""


# ---------------------------------------------------------------------------
# Card detail popover renderer
# ---------------------------------------------------------------------------

def _cost_str(cost_list: list) -> str:
    """Convert cost array to Japanese energy symbols string."""
    return "".join(ENERGY_JP.get(c, c) for c in (cost_list or []))


def _render_bilingual(text_en: str, cache_key: str, bg: str, border: str):
    """Render effect text with Japanese translation above English original."""
    text_ja = _translate_ja(text_en, cache_key)
    if text_ja:
        st.markdown(
            f'<div style="background:{bg};border-left:3px solid {border};'
            f'padding:8px 12px;border-radius:4px">'
            f'<div style="font-size:0.92em">{text_ja}</div>'
            f'<div style="margin-top:6px;font-size:0.78em;color:#888;'
            f'border-top:1px solid #ccc;padding-top:4px">{text_en}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div style="background:{bg};border-left:3px solid {border};'
            f'padding:8px 12px;border-radius:4px;font-size:0.9em">{text_en}</div>',
            unsafe_allow_html=True,
        )


def _render_card_detail(cid: str, name: str, ct: str, expn: str, cno: str,
                        know: dict, detail: dict, base_url: str,
                        api_card_id: str = ""):
    # Fetch full card data from TCGdex (cached)
    full = fetch_tcgdex_full(api_card_id) if api_card_id else {}

    # Large card image
    if base_url:
        st.markdown(
            f'<div style="text-align:center;margin-bottom:8px">'
            f'<img src="{base_url}/high.webp" width="230" style="border-radius:8px" '
            f'onerror="this.onerror=null;this.src=\'{base_url}/low.png\'">'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Card header ──────────────────────────────────────────────────────────
    hp        = full.get("hp") or detail.get("hp", "")
    stage     = full.get("stage") or detail.get("subtypes", "")
    evolves   = full.get("evolvesFrom") or detail.get("evolvesFrom", "")
    types_raw = full.get("types") or []
    trainer_type = full.get("trainerType", "")

    st.markdown(f"### {name}")

    meta_parts = []
    if ct == "Pokemon":
        if stage:
            meta_parts.append(stage)
        if hp:
            meta_parts.append(f"HP **{hp}**")
        if types_raw:
            type_jp = "・".join(ENERGY_JP.get(t, t) for t in types_raw)
            meta_parts.append(f"タイプ: {type_jp}")
    elif ct == "Trainer":
        trainer_jp = TRAINER_TYPE_JP.get(trainer_type, trainer_type or "トレーナーズ")
        meta_parts.append(f"**{trainer_jp}**")
    elif ct == "Energy":
        meta_parts.append("**基本エネルギー**")

    st.markdown("　".join(meta_parts) if meta_parts else ct)
    st.caption(f"{expn} {cno}")

    if evolves:
        st.caption(f"進化元: {evolves}")

    # ── Trainer / Energy effect text ─────────────────────────────────────────
    effect_text = full.get("effect", "")
    if effect_text and ct != "Pokemon":
        st.divider()
        st.markdown("**効果**")
        _render_bilingual(effect_text, f"{api_card_id}_effect", "#f0f4ff", "#4a90d9")

    # ── Pokemon abilities ────────────────────────────────────────────────────
    abilities = full.get("abilities") or []
    if abilities:
        st.divider()
        for i, ab in enumerate(abilities):
            ab_type    = ab.get("type", "Ability")
            ab_name_en = ab.get("name", "")
            ab_eff     = ab.get("effect", "")
            type_label = "特性" if ab_type == "Ability" else ab_type
            ab_name_ja = _translate_ja(ab_name_en, f"{api_card_id}_ab{i}_name") if api_card_id else ""
            display_name = f"{ab_name_ja}　<small style='color:#888'>({ab_name_en})</small>" if ab_name_ja and ab_name_ja != ab_name_en else ab_name_en
            ja_body = _translate_ja(ab_eff, f"{api_card_id}_ab{i}_eff") if api_card_id else ""
            eff_html = ""
            if ja_body:
                eff_html = (
                    f'<div style="margin-top:6px;font-size:0.9em">{ja_body}</div>'
                    f'<div style="margin-top:4px;font-size:0.78em;color:#999">{ab_eff}</div>'
                )
            elif ab_eff:
                eff_html = f'<div style="margin-top:6px;font-size:0.88em">{ab_eff}</div>'
            st.markdown(
                f'<div style="background:#fff8e1;border-left:3px solid #f5a623;'
                f'padding:8px 12px;border-radius:4px;margin-bottom:8px">'
                f'<span style="color:#b07d00;font-weight:bold;font-size:0.8em">【{type_label}】</span>'
                f'<strong> {display_name}</strong>'
                f'{eff_html}'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ── Pokemon attacks ──────────────────────────────────────────────────────
    attacks = full.get("attacks") or []
    if attacks:
        st.divider()
        st.markdown("**ワザ**")
        for i, atk in enumerate(attacks):
            cost_display = _cost_str(atk.get("cost", []))
            atk_name_en  = atk.get("name", "")
            dmg          = atk.get("damage", "")
            eff_en       = atk.get("effect", "")
            atk_name_ja  = _translate_ja(atk_name_en, f"{api_card_id}_atk{i}_name") if api_card_id else ""
            eff_ja       = _translate_ja(eff_en,      f"{api_card_id}_atk{i}_eff")  if (api_card_id and eff_en) else ""
            display_name = (
                f"{atk_name_ja}　<small style='color:#888'>({atk_name_en})</small>"
                if atk_name_ja and atk_name_ja != atk_name_en else atk_name_en
            )
            dmg_str = f'<span style="color:#c0392b;font-weight:bold;float:right">{dmg}</span>' if dmg else ""
            eff_html = ""
            if eff_ja:
                eff_html = (
                    f'<br><span style="font-size:0.9em">{eff_ja}</span>'
                    f'<br><span style="font-size:0.78em;color:#999">{eff_en}</span>'
                )
            elif eff_en:
                eff_html = f'<br><span style="font-size:0.88em">{eff_en}</span>'
            st.markdown(
                f'<div style="background:#f5f5f5;border:1px solid #ddd;'
                f'padding:8px 12px;border-radius:4px;margin-bottom:6px">'
                f'<span style="font-size:1.1em">{cost_display}</span>'
                f'　<strong>{display_name}</strong>{dmg_str}'
                f'{eff_html}'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ── Retreat / Weakness ───────────────────────────────────────────────────
    retreat  = full.get("retreatCost") or []
    weakness = full.get("weaknesses") or []
    if retreat or weakness:
        r1, r2 = st.columns(2)
        if retreat:
            r1.markdown(f"**にげる:** {_cost_str(retreat)}")
        if weakness:
            w = weakness[0] if isinstance(weakness, list) else weakness
            if isinstance(w, dict):
                wtype = ENERGY_JP.get(w.get("type", ""), w.get("type", ""))
                wmult = w.get("value", "×2")
                r2.markdown(f"**弱点:** {wtype}{wmult}")

    # ── AI スコア（card_knowledge.csv）────────────────────────────────────────
    if know:
        st.divider()
        st.markdown("**AIスコア**")
        role     = know.get("role", "")
        sub_role = know.get("sub_role", "")
        priority = know.get("priority", "")
        phase    = know.get("phase", "")
        notes    = know.get("notes", "")
        tags     = know.get("tags", "")

        if role:
            label = role + (f" / {sub_role}" if sub_role else "")
            st.caption(f"ロール: {label}　優先度: {priority}　フェーズ: {phase}")

        score_defs = [
            ("keep_score",          "キープ"),
            ("use_score",           "使用"),
            ("search_score",        "サーチ"),
            ("discard_penalty",     "廃棄ペナ"),
            ("bench_score",         "ベンチ"),
            ("energy_attach_score", "エネ付加"),
            ("attack_score",        "攻撃"),
            ("evolution_score",     "進化"),
            ("risk_score",          "リスク"),
        ]
        nonzero = [(lbl, know.get(key, "0")) for key, lbl in score_defs
                   if know.get(key, "0") not in ("0", "", None)]
        if nonzero:
            cols = st.columns(3)
            for i, (lbl, val) in enumerate(nonzero):
                cols[i % 3].metric(lbl, val)

        if tags:
            st.caption(f"タグ: {tags}")
        if notes:
            st.caption(f"📝 {notes}")


# ---------------------------------------------------------------------------
# Session state bootstrap
# ---------------------------------------------------------------------------

master_rows = load_master()
knowledge   = load_knowledge()
detail_map  = load_card_detail()
master_map  = {str(r["card_id"]): r for r in master_rows}

if list_decks() == [] and os.path.exists(SUBMIT_PATH):
    existing = read_deck_from_path(SUBMIT_PATH)
    if existing:
        write_deck("Default", existing, master_map)

if "deck" not in st.session_state:
    st.session_state.deck: dict[str, int] = {}
if "deck_name" not in st.session_state:
    saved = list_decks()
    st.session_state.deck_name: str = saved[0] if saved else ""
    if st.session_state.deck_name:
        st.session_state.deck = read_deck(st.session_state.deck_name)
if "dirty" not in st.session_state:
    st.session_state.dirty = False

deck: dict[str, int] = st.session_state.deck
total = sum(deck.values())

# ---------------------------------------------------------------------------
# ── Sidebar ─────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🃏 デッキ管理")

    saved_decks = list_decks()
    current_idx = saved_decks.index(st.session_state.deck_name) if st.session_state.deck_name in saved_decks else 0

    selected = st.selectbox(
        "デッキを選択",
        options=saved_decks if saved_decks else ["(なし)"],
        index=current_idx,
        key="deck_selector",
    )

    if saved_decks and selected != st.session_state.deck_name:
        if st.session_state.dirty:
            st.warning("未保存の変更があります。このまま切り替えますか？")
        st.session_state.deck_name = selected
        st.session_state.deck = read_deck(selected)
        st.session_state.dirty = False
        st.rerun()

    st.divider()
    st.markdown("**✨ 新規デッキ**")
    new_name = st.text_input("デッキ名", placeholder="例: Dragapult ex v2", key="new_name_input")
    if st.button("➕ 新規作成", use_container_width=True):
        if not new_name.strip():
            st.error("デッキ名を入力してください")
        elif new_name.strip() in list_decks():
            st.error("同名のデッキが既に存在します")
        else:
            st.session_state.deck_name = new_name.strip()
            st.session_state.deck = {}
            st.session_state.dirty = False
            st.rerun()

    st.divider()
    st.markdown("**💾 保存**")

    save_name = st.text_input(
        "保存名（変更可）",
        value=st.session_state.deck_name,
        key="save_name_input",
    )

    col_s1, col_s2 = st.columns(2)
    if col_s1.button("保存", use_container_width=True, type="primary"):
        if not save_name.strip():
            st.error("名前を入力してください")
        else:
            write_deck(save_name.strip(), deck, master_map)
            st.session_state.deck_name = save_name.strip()
            st.session_state.dirty = False
            st.success(f"「{save_name.strip()}」を保存しました")
            st.rerun()

    act = active_deck_name()
    is_active = (act == st.session_state.deck_name and not st.session_state.dirty)
    if col_s2.button(
        "🚀 提出用に設定" if not is_active else "✅ 提出中",
        use_container_width=True,
        disabled=is_active or total != 60,
        help="deck.csv に書き出して提出デッキに設定します（60枚必要）",
    ):
        write_deck(st.session_state.deck_name, deck, master_map)
        set_active_deck(st.session_state.deck_name, deck, master_map)
        st.session_state.dirty = False
        st.success(f"「{st.session_state.deck_name}」を提出デッキに設定しました")
        st.rerun()

    if total != 60 and not is_active:
        st.caption(f"提出には60枚必要（現在{total}枚）")

    st.divider()
    if st.session_state.deck_name in list_decks():
        with st.expander("🗑️ デッキ削除"):
            st.warning(f"「{st.session_state.deck_name}」を削除しますか？")
            if st.button("削除する", type="primary", use_container_width=True):
                os.remove(_deck_path(st.session_state.deck_name))
                remaining = list_decks()
                st.session_state.deck_name = remaining[0] if remaining else ""
                st.session_state.deck = read_deck(st.session_state.deck_name) if st.session_state.deck_name else {}
                st.session_state.dirty = False
                st.rerun()

    st.divider()
    color = "green" if total == 60 else ("orange" if total > 50 else "red")
    st.markdown(
        f"**{st.session_state.deck_name or '(新規)'}**"
        + ("　⚠️ 未保存" if st.session_state.dirty else ""),
        unsafe_allow_html=False,
    )
    st.markdown(
        f"合計: <span style='color:{color};font-weight:bold;font-size:1.4em'>{total}</span>/60",
        unsafe_allow_html=True,
    )
    st.progress(min(total / 60, 1.0))

    groups: dict[str, list] = {"Pokemon": [], "Trainer": [], "Energy": []}
    for cid, cnt in sorted(deck.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 9999):
        info = master_map.get(cid, {})
        name = info.get("card_name_en", f"ID:{cid}")
        ct = _infer_type(cid, knowledge)
        groups.get(ct, groups.setdefault(ct, [])).append((cid, name, cnt))

    for gname, entries in groups.items():
        if not entries:
            continue
        g_total = sum(e[2] for e in entries)
        st.markdown(f"**{TYPE_EMOJI.get(gname,'⬜')} {gname} ({g_total})**")
        for cid, name, cnt in entries:
            c1, c2, c3 = st.columns([5, 1, 1])
            c1.markdown(f"<small>{name[:20]}</small>", unsafe_allow_html=True)
            c2.markdown(f"<small>×{cnt}</small>", unsafe_allow_html=True)
            if c3.button("－", key=f"sb_rm_{cid}"):
                if st.session_state.deck.get(cid, 0) > 1:
                    st.session_state.deck[cid] -= 1
                else:
                    del st.session_state.deck[cid]
                st.session_state.dirty = True
                st.rerun()


# ---------------------------------------------------------------------------
# ── Main area ───────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

act_name = active_deck_name()
st.title("🃏 PTCG Deck Builder")
if act_name:
    st.caption(f"🚀 提出中デッキ: **{act_name}** | カードプール: {len(master_rows)}枚")
else:
    st.caption(f"カードプール: {len(master_rows)}枚 | 提出デッキ未設定")

if list_decks():
    with st.expander("📋 保存済みデッキ一覧", expanded=False):
        cols = st.columns(4)
        for i, dname in enumerate(list_decks()):
            d = read_deck(dname)
            dtotal = sum(d.values())
            is_act = (dname == act_name)
            badge = "🚀" if is_act else ("✅" if dtotal == 60 else "⚠️")
            with cols[i % 4]:
                label = f"{badge} {dname}\n({dtotal}/60)"
                if st.button(label, key=f"switch_{dname}", use_container_width=True):
                    st.session_state.deck_name = dname
                    st.session_state.deck = read_deck(dname)
                    st.session_state.dirty = False
                    st.rerun()

st.divider()

# Filters
f1, f2, f3 = st.columns([3, 2, 2])
with f1:
    search = st.text_input("🔍 カード名で検索", placeholder="Dragapult / Ultra Ball / …")
with f2:
    all_exp = sorted({r.get("expansion", "") for r in master_rows if r.get("expansion")})
    exp_filter = st.selectbox("拡張パック", ["すべて"] + all_exp)
with f3:
    type_filter = st.selectbox("カードタイプ", ["すべて", "Pokemon", "Trainer", "Energy"])

filtered = master_rows
if search:
    q = search.lower()
    filtered = [r for r in filtered if q in r.get("card_name_en", "").lower()]
if exp_filter != "すべて":
    filtered = [r for r in filtered if r.get("expansion") == exp_filter]
if type_filter != "すべて":
    filtered = [r for r in filtered if _infer_type(str(r["card_id"]), knowledge) == type_filter]

st.markdown(f"**{len(filtered)}枚** 表示中")

if not filtered:
    st.info("該当するカードがありません。")
    st.stop()

# Pagination
PAGE_SIZE   = 48
total_pages = max(1, (len(filtered) - 1) // PAGE_SIZE + 1)
if total_pages > 1:
    c_pg1, c_pg2 = st.columns([1, 5])
    page = c_pg1.number_input("ページ", 1, total_pages, 1, step=1, label_visibility="collapsed")
    c_pg2.caption(f"ページ {page}/{total_pages}")
else:
    page = 1
paged = filtered[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]

# Card grid (4 columns)
COLS = 4
for chunk in [paged[i:i+COLS] for i in range(0, len(paged), COLS)]:
    cols = st.columns(COLS)
    for col, card in zip(cols, chunk):
        cid    = str(card["card_id"])
        name   = card.get("card_name_en", "")
        expn   = card.get("expansion", "")
        cno    = card.get("collection_no", "")
        ct     = _infer_type(cid, knowledge)
        emoji  = TYPE_EMOJI.get(ct, "⬜")
        know   = knowledge.get(cid, {})
        detail = detail_map.get(cid, {})
        role   = know.get("role", "")
        in_deck = deck.get(cid, 0)

        base_url    = get_image_base_url(cid, expn, cno, detail_map, name)
        api_card_id = get_api_card_id(cid, expn, cno, detail_map)

        with col:
            with st.container(border=True):
                # Card illustration thumbnail (loaded client-side via <img>)
                if base_url:
                    st.markdown(
                        f'<div style="text-align:center;margin-bottom:4px">'
                        f'<img src="{base_url}/low.png" width="130"'
                        f' style="border-radius:6px;max-height:180px;object-fit:contain"'
                        f' onerror="this.parentElement.style.display=\'none\'">'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                # Card name + meta
                hp_str = detail.get("hp", "")
                meta = f"{expn} {cno}"
                if hp_str:
                    meta += f" | HP {hp_str}"
                if role:
                    meta += f"  `{role}`"
                st.markdown(
                    f"{emoji} **{name}**  \n<small>{meta}</small>",
                    unsafe_allow_html=True,
                )

                # Action row: [🔍詳細 | count | ＋ | －]
                b1, b2, b3, b4 = st.columns([2, 2, 1, 1])

                with b1.popover("🔍詳細", use_container_width=True):
                    _render_card_detail(cid, name, ct, expn, cno, know, detail, base_url, api_card_id)

                b2.markdown(
                    f"<div style='text-align:center;padding-top:4px'>"
                    f"{'<b>✅ ' + str(in_deck) + '枚</b>' if in_deck else '&nbsp;'}</div>",
                    unsafe_allow_html=True,
                )

                can_add = in_deck < 4 and total < 60
                if b3.button("＋", key=f"add_{cid}", disabled=not can_add):
                    st.session_state.deck[cid] = in_deck + 1
                    st.session_state.dirty = True
                    st.rerun()

                if in_deck > 0:
                    if b4.button("－", key=f"sub_{cid}"):
                        if in_deck > 1:
                            st.session_state.deck[cid] = in_deck - 1
                        else:
                            del st.session_state.deck[cid]
                        st.session_state.dirty = True
                        st.rerun()
                else:
                    b4.button("－", key=f"sub_{cid}_off", disabled=True)
