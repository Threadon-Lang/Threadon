"""Mandelbrot escape-time checksum. Keep in sync with mandelbrot.th / .cpp."""

WIDTH = 256
HEIGHT = 256
MAX_ITER = 255


def main() -> None:
    checksum = 0
    for py in range(HEIGHT):
        ci = -1.0 + py * 2.0 / HEIGHT
        for px in range(WIDTH):
            cr = -2.0 + px * 3.0 / WIDTH
            zr = zi = 0.0
            n = 0
            while n < MAX_ITER and zr * zr + zi * zi <= 4.0:
                tmp = zr * zr - zi * zi + cr
                zi = 2.0 * zr * zi + ci
                zr = tmp
                n += 1
            checksum += n
    print(checksum)


if __name__ == "__main__":
    main()
