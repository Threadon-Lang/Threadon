# stats

Descriptive statistics for lists, built on the `lists` and `math` modules.

```threadon
import stats

def main() -> Int32
    xs: List[Int32] = [2, 4, 4, 4, 5, 5, 7, 9]
    print(stats.mean_int(xs))     # 5.000000
    print(stats.stddev_int(xs))   # 2.000000
    return 0
```

| Int32 | Float64 | Result |
| --- | --- | --- |
| `mean_int(xs)` | `mean_float(xs)` | arithmetic mean |
| `median_int(xs)` | — | median (average of the two middle values for even lengths) |
| `variance_int(xs)` | `variance_float(xs)` | population variance (divide by N) |
| `stddev_int(xs)` | `stddev_float(xs)` | square root of the variance |
| `range_int(xs)` | — | largest minus smallest, as `Int32` |
| — | `sum_float(xs)`, `min_float(xs)`, `max_float(xs)` | sum / extremes |

Every function returns `0` (or `0.0`) for an empty list.

Tests: `python3 -m threadon --run-tests compiler/stdlib/stats/test.th`.
