"""
Sorting solution — branch 'sort' owns this file only.
Deliberately bad: bubble sort O(n^2). Agent improves this.
Contract: must define sort(arr) that sorts the list in place or returns a sorted copy.
"""


def sort(arr: list) -> list:
    """Bubble sort: O(n^2). In-place, returns the same list."""
    n = len(arr)
    for i in range(n):
        for j in range(0, n - i - 1):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
    return arr
