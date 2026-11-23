# validate

Format checks for strings that come from `input()`, a native module or a
file-like source. Every function returns `Bool`; no check throws or mutates its
argument. These are shape checks only: a valid-looking email is not verified,
and a valid IPv4 string says nothing about whether the host exists.

```threadon
import validate

def main() -> Int32
    print(validate.is_ipv4("127.0.0.1"))
    print(validate.luhn("4111111111111111"))
    return 0
```

| Function | Result |
| --- | --- |
| `is_int_string(s)` | optional sign and at least one digit, nothing else |
| `is_float_string(s)` | sign, at most one dot, digits before the dot (`1.` is fine, `.5` is not) |
| `is_ipv4(s)` | four 0..255 octets, no leading zeros |
| `is_hex_color(s)` | `#` followed by exactly six hex digits |
| `is_email_like(s)` | one `@`, non-empty sides, a dot in the domain, no spaces |
| `luhn(s)` | digits only, length at least 2, Luhn checksum passes |

Caveat: no exponent notation in `is_float_string`, no RFC 5322 grammar in
`is_email_like`, and no cryptographic claims for `luhn`.

Tests: `python3 -m threadon --run-tests compiler/stdlib/validate/test.th`.
