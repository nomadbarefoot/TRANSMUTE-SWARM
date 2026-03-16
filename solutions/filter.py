"""
Filter solution — branch 'filter' owns this file only.
Improved: O(n) single-pass with append.
Contract: must define filter_le(arr, threshold) returning list of elements <= threshold. arr is sorted.
"""


def filter_le(arr: list, threshold: int) -> list:
    """Single-pass loop with append for O(n) time."""
    result = []
    for x in arr:
        if x <= threshold:
            result.append(x)
    return result
