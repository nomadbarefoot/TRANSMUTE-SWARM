"""
Filter solution — branch 'filter' owns this file only.
Wonky baseline: O(n^2) — build result with result = result + [x] so each append copies whole list.
Improvement path: use list comprehension or single pass with result.append(x).
Contract: must define filter_le(arr, threshold) returning list of elements <= threshold. arr is sorted.
"""


def filter_le(arr: list, threshold: int) -> list:
    """Single-pass with append: O(n)."""
    result = []
    for x in arr:
        if x <= threshold:
            result.append(x)
    return result
