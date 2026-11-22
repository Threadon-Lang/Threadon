# intset

A set of `Int32` values, backed by a `List[Int32]` and wrapped in an
`IntSet` class. All operations return a **new** set; the input is unchanged.

```threadon
import intset

def main() -> Int32
    a: intset.IntSet = intset.from_list([1, 2, 3])
    b: intset.IntSet = intset.from_list([3, 4])
    print(intset.size(intset.union(a, b)))        # 4
    print(intset.contains(a, 2))                 # True
    return 0
```

| Function | Result |
| --- | --- |
| `empty_set()` | a new empty set |
| `from_list(xs)` | set of the distinct values in a `List[Int32]` |
| `to_list(s)` | the values as a `List[Int32]` (insertion order) |
| `contains(s, v)`, `size(s)` | membership and size |
| `add(s, v)`, `remove(s, v)` | new sets with the value added/removed |
| `union(a, b)`, `intersection(a, b)`, `difference(a, b)` | new sets |

The functional style is deliberate: Threadon passes classes and lists by
value, and methods receive a copy of `self`, so a mutating method would not
change the caller's set.

Tests: `python3 -m threadon --run-tests compiler/stdlib/intset/test.th`.
