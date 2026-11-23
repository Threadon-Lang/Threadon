// Sum of Collatz stopping times for 1..N. Keep in sync with collatz.th / .py.
#include <cstdint>
#include <cstdio>

int main() {
    const int64_t limit = 200000;
    int64_t total = 0;
    for (int64_t i = 1; i <= limit; ++i) {
        int64_t n = i;
        int64_t steps = 0;
        while (n != 1) {
            if (n % 2 == 0) n = n / 2;
            else n = 3 * n + 1;
            ++steps;
        }
        total += steps;
    }
    std::printf("%lld\n", (long long)total);
    return 0;
}
