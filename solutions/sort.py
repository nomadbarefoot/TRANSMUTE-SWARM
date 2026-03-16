"""
Sorting solution — branch 'sort' owns this file only.
Baseline: bubble sort (single forward pass per round). O(n^2).
Contract: must define sort(arr) that sorts the list in place or returns a sorted copy.
"""

def sort(arr: list) -> list:
    """Standard bubble sort: forward pass only. O(n^2)."""
    n = len(arr)
    for i in range(n):
        for j in range(0, n - 1 - i):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
    return arr
