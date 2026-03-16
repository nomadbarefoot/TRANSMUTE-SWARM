"""
Search solution — branch 'search' owns this file only.
Improvement: linear scan with early exit when arr[i] > target (since sorted).
Contract: must define search(arr, target) returning index of target in sorted arr, or -1.
"""


def search(arr: list, target: int) -> int:
    """Linear scan with early exit: break when arr[i] > target."""
    found = -1
    for i in range(len(arr)):
        if arr[i] == target:
            found = i
        elif arr[i] > target:
            break
    return found
