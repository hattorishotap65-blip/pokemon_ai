"""Value model inference for RagingBolt agent."""
import json
import os
import pickle

_MODEL = None
_META = None
_LOADED = False

_MODEL_DIR = os.path.dirname(os.path.abspath(__file__))
_MODEL_PATH = os.path.join(_MODEL_DIR, "value_model.pkl")
_META_PATH = os.path.join(_MODEL_DIR, "value_model_meta.json")


def load_value_model():
    """Load model from disk. Returns True if loaded, False if not available."""
    global _MODEL, _META, _LOADED
    if _LOADED:
        return _MODEL is not None
    _LOADED = True
    if not os.path.exists(_MODEL_PATH) or not os.path.exists(_META_PATH):
        return False
    try:
        with open(_MODEL_PATH, "rb") as f:
            _MODEL = pickle.load(f)
        with open(_META_PATH, "r", encoding="utf-8") as f:
            _META = json.load(f)
        return True
    except Exception:
        _MODEL = None
        _META = None
        return False


def predict_state_value(obs, my_index):
    """Predict win probability for current state. Returns float or None."""
    if not load_value_model():
        return None
    try:
        from feature_extractor import extract_features
    except ImportError:
        try:
            from experiments.agents.raging_bolt.feature_extractor import extract_features
        except ImportError:
            return None
    try:
        features = extract_features(obs, my_index)
        feature_names = _META.get("feature_names", [])
        x = [float(features.get(k, 0)) for k in feature_names]
        proba = _MODEL.predict_proba([x])[0][1]
        return float(proba)
    except Exception:
        return None


def _get_card(obs, area, index, player_index):
    """Local copy of main.py's get_card() so this module stays import-independent."""
    try:
        from cg.api import AreaType
    except ImportError:
        return None
    player = obs.current.players[player_index]
    try:
        if area == AreaType.HAND:
            return player.hand[index]
        if area == AreaType.ACTIVE:
            return player.active[index]
        if area == AreaType.BENCH:
            return player.bench[index]
    except (IndexError, TypeError):
        pass
    return None


def _recompute_derived(features):
    """Keep bolt_ready/field_ready consistent after mutating their inputs."""
    features["bolt_ready"] = int(bool(features.get("bolt_has_lightning")) and bool(features.get("bolt_has_fighting")))
    features["field_ready"] = int(
        features.get("ogerpon_count", 0) >= 1
        and features.get("raging_bolt_count", 0) >= 1
        and features.get("bolt_has_lightning")
        and features.get("bolt_has_fighting")
    )


def predict_action_value(obs, my_index, opt):
    """Predict win probability after taking a specific action.
    Approximates post-action state by modifying features based on the
    actual target/card involved, instead of a flat per-type nudge."""
    if not load_value_model():
        return None
    try:
        from feature_extractor import extract_features, RAGING_BOLT, OGERPON, GRASS, LIGHTNING, FIGHTING
    except ImportError:
        try:
            from experiments.agents.raging_bolt.feature_extractor import (
                extract_features, RAGING_BOLT, OGERPON, GRASS, LIGHTNING, FIGHTING)
        except ImportError:
            return None
    try:
        from cg.api import AreaType
    except ImportError:
        AreaType = None

    try:
        features = extract_features(obs, my_index)
        ot = getattr(opt, 'type', None)

        if ot == 13:  # ATTACK: approximate a KO instead of an unrelated energy cost
            opp_hp = features.get("opp_active_hp", 0)
            bt_dmg = features.get("total_field_energy", 0) * 70
            if opp_hp > 0 and bt_dmg >= opp_hp:
                features["opp_active_hp"] = 0
                features["opp_active_hp_pct"] = 0
                features["my_prizes"] = features.get("my_prizes", 0) + 1
                features["prize_diff"] = features["my_prizes"] - features.get("opp_prizes", 0)
        elif ot == 10:  # ABILITY (Teal Dance attaches a Grass Energy)
            features["total_field_energy"] = features.get("total_field_energy", 0) + 1
            features["grass_energy_on_field"] = features.get("grass_energy_on_field", 0) + 1
        elif ot == 8:  # ATTACH
            energy_card = _get_card(obs, AreaType.HAND if AreaType else None, opt.index, my_index)
            target = _get_card(obs, getattr(opt, 'inPlayArea', None),
                                getattr(opt, 'inPlayIndex', None), my_index)
            features["hand_size"] = max(0, features.get("hand_size", 0) - 1)
            if energy_card and target:
                features["total_field_energy"] = features.get("total_field_energy", 0) + 1
                if energy_card.id == GRASS:
                    features["grass_energy_on_field"] = features.get("grass_energy_on_field", 0) + 1
                    features["grass_in_hand"] = max(0, features.get("grass_in_hand", 0) - 1)
                elif energy_card.id == LIGHTNING:
                    features["lightning_energy_on_field"] = features.get("lightning_energy_on_field", 0) + 1
                    features["lightning_in_hand"] = max(0, features.get("lightning_in_hand", 0) - 1)
                    if target.id == RAGING_BOLT:
                        features["bolt_has_lightning"] = 1
                elif energy_card.id == FIGHTING:
                    features["fighting_energy_on_field"] = features.get("fighting_energy_on_field", 0) + 1
                    features["fighting_in_hand"] = max(0, features.get("fighting_in_hand", 0) - 1)
                    if target.id == RAGING_BOLT:
                        features["bolt_has_fighting"] = 1
                if target.id == RAGING_BOLT and AreaType and getattr(opt, 'inPlayArea', None) == AreaType.BENCH:
                    if features.get("bolt_has_lightning") and features.get("bolt_has_fighting"):
                        features["bench_bolt_ready"] = 1
            _recompute_derived(features)
        elif ot == 7:  # PLAY
            played = _get_card(obs, AreaType.HAND if AreaType else None, opt.index, my_index)
            features["hand_size"] = max(0, features.get("hand_size", 0) - 1)
            if played:
                if played.id == RAGING_BOLT:
                    features["raging_bolt_count"] = features.get("raging_bolt_count", 0) + 1
                elif played.id == OGERPON:
                    features["ogerpon_count"] = features.get("ogerpon_count", 0) + 1
                _recompute_derived(features)
        elif ot == 14:  # END
            pass

        feature_names = _META.get("feature_names", [])
        x = [float(features.get(k, 0)) for k in feature_names]
        proba = _MODEL.predict_proba([x])[0][1]
        return float(proba)
    except Exception:
        return None


def model_available():
    """Check if model is loaded and ready."""
    return load_value_model()
