# random

A deterministic pseudo-random generator in pure Threadon. It uses a linear
congruential generator with a 31-bit state:

```
state = (state * 1103515245 + 12345) mod 2**31
```

The same seed always produces the same stream. It is **not** cryptographically
secure, and no entropy is read from the operating system.

```threadon
import random

def main() -> Int32
    random.seed(42)
    print(random.randint(1, 6))
    print(random.rand_float())
    return 0
```

| Function | Result |
| --- | --- |
| `seed(value)` | reset the generator state (same value &rarr; same stream) |
| `next_int()` | next `Int64` in `[0, 2**31)` |
| `randint(lo, hi)` | inclusive `Int32` range (bounds are swapped if reversed) |
| `rand_float()` | `Float64` in `[0, 1)` |
| `chance(percent)` | `Bool`, true with the given percentage probability |
| `choice_int(xs)` | one element of a `List[Int32]`, or `0` for an empty list |
| `shuffle_int(xs)` | Fisher-Yates shuffle of a **copy** of the list |
| `dice(sides)` | inclusive roll from `1` to `sides` |

The state is module-level, so every importer shares the same stream.

Tests: `python3 -m threadon --run-tests compiler/stdlib/random/test.th`.
