"""
Sorting solution — branch 'sort' owns this file only.
Improvement 3: use list.sort() in-place (Timsort, O(n log n), may avoid extra copy).
Contract: must define sort(arr) that sorts the list in place or returns a sorted copy.
"""


def sort(arr: list) -> list:
    """Use list.sort() in-place for O(n log n) sorting."""
    arr.sort()
    return arr
