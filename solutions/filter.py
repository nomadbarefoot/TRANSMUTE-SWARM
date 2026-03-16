"""
Filter solution — branch 'filter' owns this file only.
Even faster: list comprehension (C-level loop).
Contract: must define filter_le(arr, threshold) returning list of elements <= threshold. arr is sorted.
"""


def filter_le(arr: list, threshold: int) -> list:
    """List comprehension for speed."""
    return [x for x in arr if x <= threshold]
