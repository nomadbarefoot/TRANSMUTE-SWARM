"""
Search solution — branch 'search' owns this file only.
Deliberately bad: linear search O(n) on sorted list. Agent improves this.
Contract: must define search(arr, target) returning index of target in sorted arr, or -1.
"""


def search(arr: list, target: int) -> int:
    """Linear search: O(n). arr is sorted."""
    for i, x in enumerate(arr):
        if x == target:
            return i
        if x > target:
            return -1
    return -1
