"""64x64 integer matrix multiply checksum. Keep in sync with matmul.th / .cpp."""


def main() -> None:
    n = 32
    a = [0] * (n * n)
    b = [0] * (n * n)
    c = [0] * (n * n)
    for i in range(n):
        for j in range(n):
            a[i * n + j] = (i + j) % 100
            b[i * n + j] = (i * 3 + j * 7) % 100
    for i in range(n):
        for k in range(n):
            aik = a[i * n + k]
            for j in range(n):
                c[i * n + j] += aik * b[k * n + j]
    checksum = 0
    for v in c:
        checksum += v
    print(checksum)


if __name__ == "__main__":
    main()
