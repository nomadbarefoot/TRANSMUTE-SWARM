"""
Search solution — branch 'search' owns this file only.
Improvement: use bisect module (C implementation) for binary search.
Contract: must define search(arr, target) returning index of target in sorted arr, or -1.
"""
from bisect import bisect_left


def search(arr: list, target: int) -> int:
    """Binary search using bisect_left."""
    i = bisect_left(arr, target)
    if i < len(arr) and arr[i] == target:
        return i
    return -1
