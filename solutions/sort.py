"""
Sorting solution — branch 'sort' owns this file only.
Wonky baseline: bubble sort with a redundant backward pass every round (double work).
Improvement path: remove backward pass -> try better algorithm (e.g. sorted).
Contract: must define sort(arr) that sorts the list in place or returns a sorted copy.
"""


def sort(arr: list) -> list:
    """Wonky bubble: forward pass then redundant backward pass each round. O(n^2) with 2x constant."""
    n = len(arr)
    for i in range(n):
        # Forward pass
        for j in range(0, n - 1):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
        # Redundant backward pass (list already correct for this round; wastes time)
        for j in range(n - 2, -1, -1):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
    return arr
