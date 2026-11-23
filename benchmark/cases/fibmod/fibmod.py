"""Iterative Fibonacci mod checksum. Keep in sync with fibmod.th / .cpp."""


def main() -> None:
    n = 2_000_000
    modv = 1_000_000_007
    a, b = 0, 1
    for _ in range(n):
        t = (a + b) % modv
        a = b
        b = t
    print(a)


if __name__ == "__main__":
    main()
