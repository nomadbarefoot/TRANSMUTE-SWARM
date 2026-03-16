"""
Sorting solution — branch 'sort' owns this file only.
Improved: bubble sort with redundant backward pass removed.
Contract: must define sort(arr) that sorts the list in place or returns a sorted copy.
"""


def sort(arr: list) -> list:
    """Bubble sort without redundant backward pass. Still O(n^2)."""
    n = len(arr)
    for i in range(n):
        # Forward pass only - removed redundant backward pass
        for j in range(0, n - 1 - i):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
    return arr
