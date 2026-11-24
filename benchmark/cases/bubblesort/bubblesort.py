"""Bubble sort checksum. Keep in sync with bubblesort.th / .cpp."""


def main() -> None:
    n = 24
    reps = 5
    checksum = 0
    for r in range(reps):
        arr = [(i * 17 + r * 3) % 10000 for i in range(n)]
        for i in range(n):
            limit = n - i - 1
            for j in range(limit):
                if arr[j] > arr[j + 1]:
                    arr[j], arr[j + 1] = arr[j + 1], arr[j]
        checksum += arr[0] + arr[n // 2] + arr[n - 1]
    print(checksum)


if __name__ == "__main__":
    main()
