# fraction

Rational numbers stored as reduced `Int64` numerator/denominator pairs.
`Fraction` is a struct with value semantics, so every operation returns a new
value. `make` moves the sign to the numerator, reduces by the greatest common
divisor, and substitutes `1` for a zero denominator.

```threadon
import fraction

def main() -> Int32
    a: fraction.Fraction = fraction.make(1, 2)
    b: fraction.Fraction = fraction.make(1, 3)
    sum_ab: fraction.Fraction = fraction.add(a, b)
    print(fraction.to_string(sum_ab))       # 5/6
    print(fraction.to_string(fraction.mul(a, b)))  # 1/6
    print(fraction.to_float(sum_ab))        # 0.833333
    return 0
```

| Function | Result |
| --- | --- |
| `make(n, d)` | reduced `n/d`, sign in the numerator; `d == 0` becomes `1` |
| `add(a, b)` | sum, reduced |
| `sub(a, b)` | difference, reduced |
| `mul(a, b)` | product, reduced |
| `div(a, b)` | quotient, reduced; dividing by zero returns `0/1` |
| `to_float(a)` | `Float64` approximation of `a` |
| `to_string(a)` | `"n/d"`, or just `"n"` when the denominator is `1` |
| `gcd64(a, b)` | non-negative `Int64` greatest common divisor (helper) |
| `abs64(n)` | `Int64` absolute value (helper) |

Caveats:

- Arithmetic uses fixed-width `Int64` intermediates without overflow checks.
  Cross-multiplication in `add`, `sub`, `mul` and `div` can overflow and wrap
  for large operands; keep numerators and denominators small.
- `Int64` negation of the minimum representable value also overflows.
- Division by a zero fraction yields `0/1` rather than an error.
- `Float64` results are approximate; use `unittest.assert_approx` in tests.

Tests: `python3 -m threadon --run-tests compiler/stdlib/fraction/test.th`.
