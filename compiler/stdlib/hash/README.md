# hash

Deterministic, non-cryptographic hashes for strings and integers. Arithmetic
stays in `Int64` by reducing modulo the prime 1,000,000,007.

```threadon
import hash

def main() -> Int32
    print(hash.string_hash("hello"))
    print(hash.checksum16("hello"))
    return 0
```

| Function | Result |
| --- | --- |
| `string_hash(s)` | polynomial rolling hash: `(h * 31 + byte) mod 1e9+7`, starting at `7` |
| `djb2(s)` | djb2-style hash with multiplier 33 |
| `checksum16(s)` | 16-bit reduction of `string_hash` |
| `hash_int(x)` | hash of one `Int32` |
| `hash_pair(a, b)` | order-sensitive hash of two `Int32` values |
| `hash_list_int(xs)` | order-sensitive hash of a `List[Int32]` |

Equal inputs always hash equally. Collisions are possible and easy to force;
do not use these hashes for security.

Tests: `python3 -m threadon --run-tests compiler/stdlib/hash/test.th`.
