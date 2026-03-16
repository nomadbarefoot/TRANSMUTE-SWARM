"""
Search solution — branch 'search' owns this file only.
Binary search using bisect module from standard library.
Contract: must define search(arr, target) returning index of target in sorted arr, or -1.
"""

import bisect


def search(arr: list, target: int) -> int:
    """Binary search using bisect_left."""
    idx = bisect.bisect_left(arr, target)
    if idx < len(arr) and arr[idx] == target:
        return idx
    return -1
