"""Count primes below 20000 by trial division. Keep in sync with primes.th / .cpp."""

LIMIT = 20000


def main() -> None:
    count = 0
    for n in range(2, LIMIT):
        prime = True
        d = 2
        while d * d <= n and prime:
            if n % d == 0:
                prime = False
            d += 1
        if prime:
            count += 1
    print(count)


if __name__ == "__main__":
    main()
