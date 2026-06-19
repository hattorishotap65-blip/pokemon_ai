"""
Fallback index selector.
Returns a safe list of option indices when policy scoring is unavailable.
Never raises; the caller must never time out or crash because of us.

OptionType.END = 14 (from cabt API docs).
"""

_OT_END = 14


def fallback_index(options: list, max_count: int = 1, min_count: int = 0) -> list:
    """
    Return up to max_count indices, preferring END (pass) options.
    Satisfies min_count even if that means picking non-END options.
    """
    if not options:
        return []

    n = len(options)
    count = max(min_count, min(max_count, n))

    # Prefer END option to avoid risky choices
    end_indices = [
        i for i, a in enumerate(options)
        if isinstance(a, dict) and a.get("type") == _OT_END
    ]
    if end_indices:
        result = end_indices[:count]
        if len(result) < count:
            extra = [i for i in range(n) if i not in result]
            result += extra[:count - len(result)]
        return result

    return list(range(count))
