// Iterative Fibonacci mod checksum. Keep in sync with fibmod.th / .py.
#include <cstdint>
#include <cstdio>

int main() {
    const int64_t n = 2000000;
    const int64_t modv = 1000000007;
    int64_t a = 0, b = 1;
    for (int64_t i = 0; i < n; ++i) {
        int64_t t = (a + b) % modv;
        a = b;
        b = t;
    }
    std::printf("%lld\n", (long long)a);
    return 0;
}
