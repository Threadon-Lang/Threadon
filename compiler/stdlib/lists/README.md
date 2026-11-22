# lists

Search, sort and aggregate helpers for Threadon lists. Pure Threadon.

```threadon
import lists

def main() -> Int32
    xs: List[Int32] = [5, 1, 4, 1, 3]
    print(lists.sort_int(xs))     # [1, 1, 3, 4, 5]
    print(lists.sum_int(xs))      # 14
    print(lists.unique_int(xs))   # [5, 1, 4, 3]
    return 0
```

There is no overloading in Threadon, so the suffix selects the element type:
`_int` means `List[Int32]`, `_str` means `List[String]`.

| Int32 | String | Result |
| --- | --- | --- |
| `sum_int(xs)` | — | sum as `Int64` |
| `min_int(xs)`, `max_int(xs)` | — | smallest/largest, or `0` for an empty list |
| `contains_int(xs, v)`, `index_int(xs, v)` | `contains_str`, `index_str` | search; `index_*` returns `-1` if missing |
| `count_int(xs, v)` | `count_str` | number of matches |
| `sort_int(xs)` | `sort_str(xs)` | new sorted list (ascending, stable insertion sort) |
| `reverse_int(xs)` | `reverse_str(xs)` | new reversed list |
| `unique_int(xs)` | — | first copy of each value |
| `extend_int(xs, more)` | — | new list with all items of `more` appended |
| `join_int(xs, sep)` | — | text like `1-2-3` |
| `range_list(n)` | — | `[0, 1, ..., n-1]` |

Tests: `python3 -m threadon --run-tests compiler/stdlib/lists/test.th`.
