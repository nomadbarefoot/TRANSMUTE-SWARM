"""
Filter solution — branch 'filter' owns this file only.
Improved: Use simple loop with append and early break (sorted array).
Contract: must define filter_le(arr, threshold) returning list of elements <= threshold. arr is sorted.
"""


def filter_le(arr: list, threshold: int) -> list:
    """Simple loop with early break for sorted array."""
    result = []
    for x in arr:
        if x <= threshold:
            result.append(x)
        else:
            break
    return result
