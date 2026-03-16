"""
Sorting solution — branch 'sort' owns this file only.
Improved: use list.sort() in-place (Timsort).
Contract: must define sort(arr) that sorts the list in place or returns a sorted copy.
"""


def sort(arr: list) -> list:
    """Sort list in-place using list.sort()."""
    arr.sort()
    return arr
