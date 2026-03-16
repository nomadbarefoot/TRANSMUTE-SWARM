import bisect

def search(arr: list, target: int) -> int:
    """Search using bisect_left."""
    idx = bisect.bisect_left(arr, target)
    if idx < len(arr) and arr[idx] == target:
        return idx
    return -1
