"""Sum of Collatz stopping times for 1..N. Keep in sync with collatz.th / .cpp."""


def main() -> None:
    limit = 200_000
    total = 0
    i = 1
    while i <= limit:
        n = i
        steps = 0
        while n != 1:
            if n % 2 == 0:
                n = n // 2
            else:
                n = 3 * n + 1
            steps += 1
        total += steps
        i += 1
    print(total)


if __name__ == "__main__":
    main()
