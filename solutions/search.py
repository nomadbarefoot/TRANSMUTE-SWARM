"""Search solution — branch 'search' owns this file only.
Improved: binary search O(log n) on sorted list.
Contract: must define search(arr, target) returning index of target in sorted arr, or -1.
"""

def search(arr: list, target: int) -> int:
    """Binary search: O(log n). arr is sorted."""
    lo, hi = 0, len(arr) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1
