"""
Loads data/card_knowledge.csv and provides fast lookup by card_id.

Supports both schemas:
  Legacy (v1): card_id, card_name, card_type, role, priority, timing, notes
  Rich   (v2): card_id, card_name_en, card_type, role, sub_role, priority, phase,
               keep_score, use_score, search_score, discard_penalty, bench_score,
               energy_attach_score, attack_score, evolution_score, risk_score, tags, notes

Editing data/card_knowledge.csv changes AI behaviour without touching code.
"""
import csv
import os

try:
    _DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "card_knowledge.csv")
except NameError:
    _DEFAULT_PATH = '/kaggle_simulations/agent/data/card_knowledge.csv'

PRIORITY_WEIGHT = {"high": 3, "medium": 2, "low": 1}


class CardKnowledge:
    def __init__(self, path: str = None):
        self._data: dict[str, dict] = {}
        self._schema: str = "unknown"
        self._load(path or _DEFAULT_PATH)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load(self, path: str):
        try:
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames or []
                self._schema = "v3" if "card_adv" in headers else ("v2" if "energy_attach_score" in headers else "v1")
                for row in reader:
                    cid = str(row.get("card_id", "")).strip()
                    if not cid:
                        continue
                    # Normalise column names between schemas
                    name = row.get("card_name_en") or row.get("card_name") or ""
                    phase = row.get("phase") or row.get("timing") or "any"
                    self._data[cid] = {
                        # Core identity
                        "card_name":     name.strip(),
                        "card_type":     row.get("card_type", "").strip(),
                        # Role
                        "role":          row.get("role", "unknown").strip(),
                        "sub_role":      row.get("sub_role", "").strip(),
                        # Priority / timing
                        "priority":      row.get("priority", "low").strip(),
                        "phase":         phase.strip(),
                        # Numeric scores (v2 only; default to sensible values)
                        "keep_score":         _int(row, "keep_score",         5),
                        "use_score":          _int(row, "use_score",          5),
                        "search_score":       _int(row, "search_score",       5),
                        "discard_penalty":    _int(row, "discard_penalty",    4),
                        "bench_score":        _int(row, "bench_score",        5),
                        "energy_attach_score":_int(row, "energy_attach_score",5),
                        "attack_score":       _int(row, "attack_score",       0),
                        "evolution_score":    _int(row, "evolution_score",    5),
                        "risk_score":         _int(row, "risk_score",         0),
                        # Advantage columns (v3 schema)
                        "card_adv":           _int(row, "card_adv",           3),
                        "board_adv":          _int(row, "board_adv",          3),
                        "energy_adv":         _int(row, "energy_adv",         2),
                        "tempo_adv":          _int(row, "tempo_adv",          3),
                        "prize_adv":          _int(row, "prize_adv",          3),
                        "resource_adv":       _int(row, "resource_adv",       3),
                        "info_adv":           _int(row, "info_adv",           2),
                        "risk_reduction_adv": _int(row, "risk_reduction_adv", 3),
                        # Tags
                        "tags":          {t.strip() for t in row.get("tags", "").split(",") if t.strip()},
                        "concept_tags":  {t.strip() for t in row.get("concept_tags", "").split(",") if t.strip()},
                        "win_condition_tags": {t.strip() for t in row.get("win_condition_tags", "").split(",") if t.strip()},
                        "notes":         row.get("notes", "").strip(),
                    }
        except FileNotFoundError:
            pass  # Graceful: knowledge starts empty; AI uses fallback defaults

    def reload(self, path: str = None):
        self._data = {}
        self._load(path or _DEFAULT_PATH)

    # ------------------------------------------------------------------
    # Core lookup
    # ------------------------------------------------------------------

    def get(self, card_id) -> dict | None:
        return self._data.get(str(card_id))

    # ------------------------------------------------------------------
    # Role / priority helpers
    # ------------------------------------------------------------------

    def get_role(self, card_id) -> str:
        info = self.get(card_id)
        return info["role"] if info else "unknown"

    def get_sub_role(self, card_id) -> str:
        info = self.get(card_id)
        return info["sub_role"] if info else ""

    def get_priority(self, card_id) -> str:
        info = self.get(card_id)
        return info["priority"] if info else "low"

    def get_priority_weight(self, card_id) -> int:
        return PRIORITY_WEIGHT.get(self.get_priority(card_id), 1)

    def get_phase(self, card_id) -> str:
        info = self.get(card_id)
        return info["phase"] if info else "any"

    # ------------------------------------------------------------------
    # Numeric score lookups (v2 schema)
    # ------------------------------------------------------------------

    def get_score(self, card_id, score_key: str, default: int = 0) -> int:
        info = self.get(card_id)
        if info is None:
            return default
        return info.get(score_key, default)

    def energy_attach_score(self, card_id) -> int:
        return self.get_score(card_id, "energy_attach_score", 5)

    def attack_score(self, card_id) -> int:
        return self.get_score(card_id, "attack_score", 0)

    def bench_score(self, card_id) -> int:
        return self.get_score(card_id, "bench_score", 5)

    def discard_penalty(self, card_id) -> int:
        return self.get_score(card_id, "discard_penalty", 4)

    def evolution_score(self, card_id) -> int:
        return self.get_score(card_id, "evolution_score", 5)

    def risk_score(self, card_id) -> int:
        return self.get_score(card_id, "risk_score", 0)

    def use_score(self, card_id) -> int:
        return self.get_score(card_id, "use_score", 5)

    def search_score(self, card_id) -> int:
        return self.get_score(card_id, "search_score", 5)

    # ------------------------------------------------------------------
    # Tag helpers
    # ------------------------------------------------------------------

    def has_tag(self, card_id, tag: str) -> bool:
        info = self.get(card_id)
        if info is None:
            return False
        return tag in info["tags"]

    def is_ex(self, card_id) -> bool:
        return self.has_tag(card_id, "ex")

    def has_ability(self, card_id) -> bool:
        return self.has_tag(card_id, "ability")

    # ------------------------------------------------------------------
    # Boolean convenience
    # ------------------------------------------------------------------

    def is_main_attacker(self, card_id) -> bool:
        return self.get_role(card_id) == "main_attacker"

    def is_engine(self, card_id) -> bool:
        return self.get_role(card_id) == "engine"

    def is_high_priority(self, card_id) -> bool:
        return self.get_priority(card_id) == "high"

    def is_early_game(self, card_id) -> bool:
        return self.get_phase(card_id) in ("early", "early_mid")

    # ------------------------------------------------------------------
    # Bulk access
    # ------------------------------------------------------------------

    def all_cards(self) -> dict:
        return dict(self._data)

    @property
    def schema(self) -> str:
        return self._schema


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _int(row: dict, key: str, default: int) -> int:
    try:
        return int(str(row.get(key, default) or default).strip())
    except (ValueError, TypeError):
        return default
