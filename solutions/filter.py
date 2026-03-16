"""
Filter solution — branch 'filter' owns this file only.
Improved: Use list comprehension for O(n) filtering.
Contract: must define filter_le(arr, threshold) returning list of elements <= threshold. arr is sorted.
"""


def filter_le(arr: list, threshold: int) -> list:
    """List comprehension: O(n) single pass."""
    return [x for x in arr if x <= threshold]
