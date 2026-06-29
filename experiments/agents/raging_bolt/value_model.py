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


def model_available():
    """Check if model is loaded and ready."""
    return load_value_model()
