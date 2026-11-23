// Integer dot product checksum. Keep in sync with dotint.th / .py.
#include <cstdint>
#include <cstdio>
#include <vector>

int main() {
    const int n = 4096;
    const int reps = 500;
    std::vector<int64_t> a(n), b(n);
    for (int i = 0; i < n; ++i) {
        a[i] = (i * 3 + 7) % 1000;
        b[i] = (i * 11 + 13) % 1000;
    }
    int64_t checksum = 0;
    for (int r = 0; r < reps; ++r) {
        int64_t s = 0;
        for (int j = 0; j < n; ++j) s += a[j] * b[j];
        checksum += s + r;
    }
    std::printf("%lld\n", (long long)checksum);
    return 0;
}
