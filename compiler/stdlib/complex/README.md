# complex

Complex numbers with `Float64` real and imaginary parts. `Complex` is a struct,
so it has value semantics: every operation returns a new value and leaves its
arguments untouched. Square roots come from the pure-Threadon `math` module.

```threadon
import complex

def main() -> Int32
    a: complex.Complex = complex.make(1.0, 2.0)
    b: complex.Complex = complex.make(3.0, -4.0)
    c: complex.Complex = complex.mul(a, b)
    print(complex.to_string(c))          # 11.0+2.0i
    print(complex.to_string(complex.conj(c)))  # 11.0-2.0i
    print(complex.abs(a))                # 2.236068
    return 0
```

| Function | Result |
| --- | --- |
| `make(re, im)` | a new `Complex(re=re, im=im)` |
| `add(a, b)` | component-wise sum |
| `sub(a, b)` | component-wise difference |
| `mul(a, b)` | complex product `(ar*br - ai*bi) + (ar*bi + ai*br)i` |
| `scale(a, k)` | multiply both parts by the `Float64` scalar `k` |
| `conj(a)` | complex conjugate `re - im*i` |
| `norm(a)` | squared magnitude `re*re + im*im` |
| `abs(a)` | magnitude `sqrt(norm(a))` |
| `to_string(a)` | `re+imi` or `re-imi`, e.g. `3.0-4.0i` |
| `float_text(x)` | helper: `String(x)` trimmed to one decimal, e.g. `"3.0"` |

Caveats:

- `norm` squares its components, so very large components may overflow to
  infinity; use `abs` for the magnitude.
- `float_text` reflects the compiler's `String(Float64)` conversion, which
  prints six decimals. Values needing more precision keep only what that
  conversion provides, and very large or very small values may print in
  scientific notation.
- `abs` shadows the built-in `abs` inside this module; call it as `complex.abs`
  (or import it explicitly) in your programs.

Tests: `python3 -m threadon --run-tests compiler/stdlib/complex/test.th`.
