# bitops

Bitwise operations for `UInt32`, implemented in pure Threadon. Threadon has no
`&`, `|`, `~`, `<<` or `>>` operators, so each function peels bits off with
`/` and `%`. Correct, but slower than a hardware instruction.

```threadon
import bitops

def main() -> Int32
    print(bitops.band(UInt32(12), UInt32(10)))  # 8
    print(bitops.shl(UInt32(1), 5))             # 32
    return 0
```

| Function | Meaning |
| --- | --- |
| `band(a, b)`, `bor(a, b)`, `bxor(a, b)` | bitwise AND, OR, XOR over 32 bits |
| `bnot(a)` | bitwise NOT |
| `shl(a, n)`, `shr(a, n)` | shift left/right by `n` bits (wraps/truncates) |
| `pow2(n)` | `2 ** n` as `UInt32` |
| `full()` | all 32 bits set (`4294967295`) |
| `popcount(a)` | number of set bits, as `Int32` |
| `bit(a, n)` | is bit `n` set? |
| `set_bit(a, n)`, `clear_bit(a, n)`, `toggle_bit(a, n)` | return a new `UInt32` |
| `trailing_zeros(a)` | number of trailing zero bits (`32` for `0`) |

All arguments and results are `UInt32`; pass `UInt32(...)` explicitly because
Threadon has no implicit conversion from `Int32`.

Tests: `python3 -m threadon --run-tests compiler/stdlib/bitops/test.th`.
