"""Sieve of Eratosthenes prime count. Keep in sync with sieve.th / .cpp."""


def main() -> None:
    limit = 10_000
    is_prime = [True] * (limit + 1)
    is_prime[0] = False
    is_prime[1] = False
    p = 2
    while p * p <= limit:
        if is_prime[p]:
            m = p * p
            while m <= limit:
                is_prime[m] = False
                m += p
        p += 1
    count = 0
    for v in is_prime:
        if v:
            count += 1
    print(count)


if __name__ == "__main__":
    main()
