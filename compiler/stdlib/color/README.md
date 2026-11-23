# color

Small colour helpers for 8-bit RGB values. `RGB` is a struct with value
semantics. Every channel is clamped into `0..255` by `make`, `from_hex`, `mix`
and `to_hex`, so an out-of-range channel never escapes into a rendered colour.

```threadon
import color

def main() -> Int32
    c: color.RGB = color.from_hex("#1a2b3c")
    print(color.to_hex(c))                       # #1a2b3c
    print(color.brightness(c))                   # 39
    half: color.RGB = color.mix(color.make(0, 0, 0), color.make(255, 255, 255), 0.5)
    print(color.to_hex(half))                    # #808080
    print(color.is_dark(c))                      # True
    return 0
```

| Function | Result |
| --- | --- |
| `make(r, g, b)` | `RGB` with each channel clamped to `0..255` |
| `from_hex(s)` | parse `#RRGGBB` or `RRGGBB`; invalid input becomes black |
| `to_hex(c)` | lowercase `#rrggbb`, clamping each field first |
| `brightness(c)` | perceived brightness `0..255` using weights 299/587/114 |
| `mix(a, b, t)` | rounded linear interpolation; `t` is clamped to `0..1` |
| `is_dark(c)` | `True` when `brightness(c) < 128` |
| `clamp_byte(x)` | helper: restrict an `Int32` to `0..255` |
| `hex_char(n)` / `hex_upper_char(n)` | helper: one hex digit |
| `hex_value(c)` | helper: value `0..15` of a hex digit, or `-1` |

Caveats:

- Direct construction (`color.RGB(r=300, ...)`) bypasses clamping; use `make`
  or pass the value through a function that clamps.
- `from_hex` expects exactly six hex digits (with or without a leading `#`);
  any other length, a wrong prefix or a non-hex digit yields black.
- `brightness` is integer arithmetic with truncating division, not afloat
  float calculation.
- `mix` rounds half up via `math.round_f`; negative halves round towards zero.
- Strings are immutable and `RGB` has value semantics: functions return new
  values instead of modifying their arguments.

Tests: `python3 -m threadon --run-tests compiler/stdlib/color/test.th`.
