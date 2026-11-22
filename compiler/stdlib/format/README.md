# format

Number formatting helpers built on `strings` and `math`. Threadon prints
floats with six decimals and has no `printf`, so this module fills the common
gaps: hex/binary, padding, fixed decimals and thousands separators.

```threadon
import format

def main() -> Int32
    print(format.hex32(UInt32(255)))   # ff
    print(format.fixed(3.14159, 2))   # 3.14
    print(format.commas(1234567))     # 1,234,567
    return 0
```

| Function | Result |
| --- | --- |
| `hex32(x)` / `bin32(x)` | lowercase hex / binary text for a `UInt32` |
| `pad_int(v, width, pad)` / `pad_float(v, width, pad)` | pad with the first byte of `pad` |
| `fixed(x, decimals)` | float with a chosen number of decimals, rounded half up |
| `percent(x, decimals)` | `x * 100` plus a `%` sign |
| `commas(n)` | integer with thousands separators |

Tests: `python3 -m threadon --run-tests compiler/stdlib/format/test.th`.
