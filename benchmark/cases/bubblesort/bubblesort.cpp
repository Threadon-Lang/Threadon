// Bubble sort checksum. Keep in sync with bubblesort.th / .py.
#include <cstdint>
#include <cstdio>
#include <vector>

int main() {
    const int n = 24;
    const int reps = 5;
    int64_t checksum = 0;
    for (int r = 0; r < reps; ++r) {
        std::vector<int> arr(n);
        for (int i = 0; i < n; ++i) arr[i] = (i * 17 + r * 3) % 10000;
        for (int i = 0; i < n; ++i) {
            int limit = n - i - 1;
            for (int j = 0; j < limit; ++j) {
                if (arr[j] > arr[j + 1]) {
                    int tmp = arr[j];
                    arr[j] = arr[j + 1];
                    arr[j + 1] = tmp;
                }
            }
        }
        checksum += arr[0] + arr[n / 2] + arr[n - 1];
    }
    std::printf("%lld\n", (long long)checksum);
    return 0;
}
