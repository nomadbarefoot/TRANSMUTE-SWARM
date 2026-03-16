"""
Search solution — branch 'search' owns this file only.
Wonky baseline: linear scan with no early exit — always walks the full list.
Improvement path: add early exit when arr[i] > target -> then try binary search.
Contract: must define search(arr, target) returning index of target in sorted arr, or -1.
"""


def search(arr: list, target: int) -> int:
    """Wonky linear: no early exit. Always scans entire list then returns. O(n) with 2x comparisons."""
    found = -1
    for i in range(len(arr)):
        if arr[i] == target:
            found = i
    return found
