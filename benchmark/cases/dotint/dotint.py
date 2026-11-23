"""Integer dot product checksum. Keep in sync with dotint.th / .cpp."""


def main() -> None:
    n = 4096
    reps = 500
    a = [(i * 3 + 7) % 1000 for i in range(n)]
    b = [(i * 11 + 13) % 1000 for i in range(n)]
    checksum = 0
    for r in range(reps):
        s = 0
        for j in range(n):
            s += a[j] * b[j]
        checksum += s + r
    print(checksum)


if __name__ == "__main__":
    main()
