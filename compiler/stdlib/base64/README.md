# base64

RFC 4648 base64 with the standard alphabet and `=` padding. Encoding works on
byte values 0..255; `encode`/`decode` treat a Threadon `String` as a byte
string, while `encode_bytes`/`decode_bytes` use `List[Int32]` so byte 0 is
preserved exactly.

```threadon
import base64

def main() -> Int32
    s: String = base64.encode("hello")
    print(s)                     # aGVsbG8=
    print(base64.decode(s))      # hello
    xs: List[Int32] = [0, 255, 1]
    print(base64.encode_bytes(xs))  # AP8B
    return 0
```

| Function | Result |
| --- | --- |
| `encode(s)` | base64 text for the bytes of `s`, with `=` padding |
| `decode(s)` | byte String decoded from base64 text |
| `encode_bytes(xs)` | base64 text for a `List[Int32]` of byte values (0..255) |
| `decode_bytes(s)` | `List[Int32]` of decoded byte values |

Caveats:

- Decoding ignores ASCII whitespace (space, tab, CR, LF, VT, FF), stops at the
  first `=`, and maps every other non-alphabet character to the value **0**.
  Incomplete trailing groups are dropped.
- Input bytes outside 0..255 are reduced modulo 256.
- Threadon strings are NUL-terminated and `len()` uses `strlen`, so a `String`
  containing byte 0 cannot be iterated reliably. Use `encode_bytes` and
  `decode_bytes` when byte 0 matters.
- All functions are `puredef` and use a small binary-search ASCII helper
  instead of `strings.ord`, avoiding that function's 256-step linear scan.

Tests: `python3 -m threadon --run-tests compiler/stdlib/base64/test.th`.
