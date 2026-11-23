# units

Small conversion helpers for length, mass, temperature, time and binary byte
units. All conversions are pure Threadon with no `std` auto-import.

```threadon
import units

def main() -> Int32
    print(units.km_to_miles(10.0))             # 6.213712
    print(units.c_to_f(100.0))                 # 212.000000
    print(units.seconds_to_hms(3661))          # 1:01:01
    print(units.mib_to_bytes(1.5))             # 1572864
    return 0
```

| Function | Result |
| --- | --- |
| `km_to_miles(v)`, `miles_to_km(v)` | convert using 1 mi = 1.609344 km |
| `cm_to_inches(v)` | convert using 1 in = 2.54 cm |
| `kg_to_pounds(v)`, `pounds_to_kg(v)` | convert using 1 lb = 0.45359237 kg |
| `c_to_f(v)`, `f_to_c(v)` | Celsius/Fahrenheit conversion |
| `seconds_to_hms(seconds)` | `H:MM:SS` text for an `Int32` duration |
| `mib_to_bytes(v)` | `Float64` MiB to `Int64` bytes |
| `bytes_to_mib(v)` | `Int64` bytes to `Float64` MiB |

Length, mass and temperature conversions use exact definition constants and
plain `Float64` arithmetic; results are not pre-rounded. `seconds_to_hms`
divides with integer arithmetic, pads minutes and seconds to two digits,
leaves hours unpadded, and prefixes a `-` for negative input (the smallest
`Int32` cannot be negated safely).

`mib_to_bytes` truncates the scaled value **toward zero** (for example,
`1.9` MiB gives 1992294 bytes, not 1992295); `bytes_to_mib` returns the
full-precision quotient. Threadon prints `Float64` values with six decimals.

Tests: `python3 -m threadon --run-tests compiler/stdlib/units/test.th`.
