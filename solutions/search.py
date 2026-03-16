"""
Search solution — branch 'search' owns this file only.
Binary search implementation.
Contract: must define search(arr, target) returning index of target in sorted arr, or -1.
"""


def search(arr: list, target: int) -> int:
    """Binary search for sorted list."""
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1
