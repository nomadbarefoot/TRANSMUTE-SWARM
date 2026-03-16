"""
Sorting solution — branch 'sort' owns this file only.
Radix sort for integers (base 256, 3 passes for 24-bit numbers).
Contract: must define sort(arr) that sorts the list in place or returns a sorted copy.
"""


def sort(arr: list) -> list:
    """Radix sort using counting sort as stable sort for each digit."""
    if len(arr) <= 1:
        return arr
    
    # 3 passes for base 256 (bits 0-7, 8-15, 16-23)
    for shift in range(0, 24, 8):
        count = [0] * 256
        for x in arr:
            count[(x >> shift) & 0xFF] += 1
        
        # Prefix sum
        total = 0
        for i in range(256):
            count[i], total = total, total + count[i]
        
        # Build output array
        output = [0] * len(arr)
        for x in arr:
            idx = (x >> shift) & 0xFF
            output[count[idx]] = x
            count[idx] += 1
        
        arr = output
    
    return arr
