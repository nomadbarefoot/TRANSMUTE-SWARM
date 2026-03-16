"""
Search solution — branch 'search' owns this file only.
Improvement: binary search (O(log n)).
Contract: must define search(arr, target) returning index of target in sorted arr, or -1.
"""


def search(arr: list, target: int) -> int:
    """Binary search."""
    lo = 0
    hi = len(arr) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1
