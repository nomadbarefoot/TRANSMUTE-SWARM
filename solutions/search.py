"""
Search solution — branch 'search' owns this file only.
Wonky baseline: linear scan with no early exit — always walks the full list.
Improvement path: add early exit when arr[i] > target -> then try binary search.
Contract: must define search(arr, target) returning index of target in sorted arr, or -1.
"""


def search(arr: list, target: int) -> int:
    """Linear scan with early exit when arr[i] > target."""
    for i in range(len(arr)):
        if arr[i] == target:
            return i
        if arr[i] > target:
            break
    return -1
