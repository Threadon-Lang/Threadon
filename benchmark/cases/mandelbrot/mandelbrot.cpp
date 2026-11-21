// Mandelbrot escape-time checksum. Keep in sync with mandelbrot.th / .py.
#include <cstdio>

int main() {
    const int WIDTH = 256;
    const int HEIGHT = 256;
    const int MAX_ITER = 255;
    int checksum = 0;
    for (int py = 0; py < HEIGHT; ++py) {
        double ci = -1.0 + double(py) * 2.0 / double(HEIGHT);
        for (int px = 0; px < WIDTH; ++px) {
            double cr = -2.0 + double(px) * 3.0 / double(WIDTH);
            double zr = 0.0, zi = 0.0;
            int n = 0;
            while (n < MAX_ITER && zr * zr + zi * zi <= 4.0) {
                double tmp = zr * zr - zi * zi + cr;
                zi = 2.0 * zr * zi + ci;
                zr = tmp;
                ++n;
            }
            checksum += n;
        }
    }
    std::printf("%d\n", checksum);
    return 0;
}
