"""
Search solution — branch 'search' owns this file only.
Binary search: O(log n) on sorted list.
Contract: must define search(arr, target) returning index of target in sorted arr, or -1.
"""

def search(arr: list, target: int) -> int:
    """Binary search: O(log n). arr is sorted."""
    low, high = 0, len(arr) - 1
    while low <= high:
        mid = (low + high) // 2
        if arr[mid] == target:
            return mid
        if arr[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1
