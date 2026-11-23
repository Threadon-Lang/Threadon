# checksum

Small deterministic checksums: 32-bit FNV-1a, Adler-32 and CRC-8. All
arithmetic is in Int64/Int32 with explicit modulo reduction, so there is no
overflow. Threadon has no bitwise operators, so XOR is computed one bit at a
time.

```threadon
import checksum

def main() -> Int32
    print(checksum.fnv1a("foobar"))          # 3214735720
    print(checksum.adler32("foobar"))        # 145425018
    print(checksum.crc8("123456789"))        # 244
    xs: List[Int32] = [0, 255, 1]
    print(checksum.checksum_bytes(xs))       # 4086252147
    return 0
```

| Function | Result |
| --- | --- |
| `fnv1a(s)` | 32-bit FNV-1a hash of `s` as Int64, masked with `0xFFFFFFFF` |
| `adler32(s)` | Adler-32 of `s` with `s1`, `s2` modulo 65521, returned as Int64 |
| `crc8(s)` | CRC-8 of `s`, polynomial `0x07`, init 0, Int32 in 0..255 |
| `checksum_bytes(xs)` | 32-bit FNV-1a over a `List[Int32]` of byte values |

Caveats:

- These are **not cryptographic**. They are fine for quick integrity checks,
  hash-table keys and checksums, but collisions are easy to construct.
- Input bytes in `checksum_bytes` are reduced modulo 256, so negative values
  wrap into 0..255. String bytes are taken as raw 0..255 byte values.
- CRC-8 here uses the non-reflected variant with no final XOR; other CRC-8
  conventions (e.g. reflected poly 0x8C) give different numbers.
- Every function is `puredef`, using a local binary-search ASCII helper
  rather than importing `strings.ord`.

Tests: `python3 -m threadon --run-tests compiler/stdlib/checksum/test.th`.
