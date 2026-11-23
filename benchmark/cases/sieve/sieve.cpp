// Sieve of Eratosthenes prime count. Keep in sync with sieve.th / .py.
#include <cstdio>
#include <vector>

int main() {
    const int limit = 10000;
    std::vector<bool> is_prime(limit + 1, true);
    is_prime[0] = false;
    is_prime[1] = false;
    for (int p = 2; p * p <= limit; ++p) {
        if (is_prime[p]) {
            for (int m = p * p; m <= limit; m += p) {
                is_prime[m] = false;
            }
        }
    }
    int count = 0;
    for (int i = 0; i <= limit; ++i) {
        if (is_prime[i]) ++count;
    }
    std::printf("%d\n", count);
    return 0;
}
