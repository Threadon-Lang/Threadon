# math

Pure-Threadon math helpers. No external libraries are needed.

```threadon
import math

def main() -> Int32
    print(math.pow_int(2, 10))     # 1024
    print(math.gcd(48, 18))        # 6
    print(math.sqrt_f(81.0))       # 9.000000
    return 0
```

`import math`, `from math import gcd, is_prime`, or `lazyimport math` all work.

## Integer functions

| Function | Result |
| --- | --- |
| `iabs(n)` | absolute value of `n` |
| `pow_int(base, exp)` | `base ** exp` by repeated squaring; a negative exponent gives `0` |
| `factorial(n)` | `n!` as an `Int64` (`1` when `n < 2`) |
| `gcd(a, b)` | greatest common divisor, always non-negative |
| `lcm(a, b)` | least common multiple as an `Int64` |
| `sign(n)` | `-1`, `0`, or `1` |
| `is_prime(n)` | trial-division primality test |
| `integer_sqrt(n)` | floor of the integer square root |

## Float64 functions

| Function | Result |
| --- | --- |
| `trunc_f(x)` | truncate towards zero |
| `floor_f(x)` / `ceil_f(x)` / `round_f(x)` | floor, ceiling, round-half-up (returns `Int64`) |
| `sqrt_f(x)` | square root by Newton's method (`0.0` for `x <= 0`) |
| `hypot_f(a, b)` | hypotenuse of a right triangle |
| `pi()` / `e()` | mathematical constants |
| `to_radians(d)` / `to_degrees(r)` | angle conversion |
| `clamp_f(x, lo, hi)` | restrict `x` to a range |
| `lerp_f(a, b, t)` | linear interpolation, with `t` clamped to `[0, 1]` |

Threadon has no overloading, so integer and float variants have different names.

Tests: `python3 -m threadon --run-tests compiler/stdlib/math/test.th`.
