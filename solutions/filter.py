"""
Filter solution — branch 'filter' owns this file only.
Improved: Use bisect to find split point, then slice.
Contract: must define filter_le(arr, threshold) returning list of elements <= threshold. arr is sorted.
"""
import bisect


def filter_le(arr: list, threshold: int) -> list:
    """Binary search to find first element > threshold, then slice."""
    idx = bisect.bisect_right(arr, threshold)
    return arr[:idx]
