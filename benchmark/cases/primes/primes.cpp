// Count primes below 20000 by trial division. Keep in sync with primes.th / .py.
#include <cstdio>

int main() {
    const long long LIMIT = 20000;
    long long count = 0;
    for (long long n = 2; n < LIMIT; ++n) {
        bool prime = true;
        for (long long d = 2; d * d <= n && prime; ++d) {
            if (n % d == 0) prime = false;
        }
        count += prime;
    }
    std::printf("%lld\n", count);
    return 0;
}
