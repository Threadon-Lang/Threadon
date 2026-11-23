// 64x64 integer matrix multiply checksum. Keep in sync with matmul.th / .py.
#include <cstdint>
#include <cstdio>
#include <vector>

int main() {
    const int n = 32;
    const int size = n * n;
    std::vector<int64_t> a(size), b(size), c(size, 0);
    for (int i = 0; i < n; ++i) {
        for (int j = 0; j < n; ++j) {
            a[i * n + j] = (i + j) % 100;
            b[i * n + j] = (i * 3 + j * 7) % 100;
        }
    }
    for (int i = 0; i < n; ++i) {
        for (int k = 0; k < n; ++k) {
            int64_t aik = a[i * n + k];
            for (int j = 0; j < n; ++j) {
                c[i * n + j] += aik * b[k * n + j];
            }
        }
    }
    int64_t checksum = 0;
    for (int i = 0; i < size; ++i) checksum += c[i];
    std::printf("%lld\n", (long long)checksum);
    return 0;
}
