"""
Sorting solution — branch 'sort' owns this file only.
Improvement 2: use Python's built-in sorted() (Timsort, O(n log n), C implementation).
Contract: must define sort(arr) that sorts the list in place or returns a sorted copy.
"""


def sort(arr: list) -> list:
    """Use built-in sorted() for O(n log n) sorting."""
    return sorted(arr)
