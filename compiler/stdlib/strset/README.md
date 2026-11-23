# strset

A functional set of `String` values, backed by a `List[String]` and wrapped
in a `StringSet` class. All operations return a **new** set; the input is
unchanged. Insertion order is preserved.

```threadon
import strset

def main() -> Int32
    a: strset.StringSet = strset.from_list(["red", "green", "blue"])
    b: strset.StringSet = strset.from_list(["blue", "yellow"])
    print(strset.size(strset.union(a, b)))              # 4
    print(strset.contains(a, "green"))                  # True
    print(strset.size(strset.intersection(a, b)))       # 1
    return 0
```

| Function | Result |
| --- | --- |
| `empty_set()` | a new empty set |
| `from_list(xs)` | set of the distinct strings in a `List[String]` |
| `to_list(s)` | the strings as a `List[String]` (insertion order) |
| `size(s)` | number of distinct strings |
| `contains(s, value)` | whether `value` is in the set |
| `add(s, value)`, `remove(s, value)` | new sets with the value added/removed |
| `union(a, b)`, `intersection(a, b)`, `difference(a, b)` | new sets |

The functional style is deliberate: Threadon passes classes and lists by
value, and methods receive a copy of `self`, so a mutating method would not
change the caller's set. Every operation copies the items it keeps.

Tests: `python3 -m threadon --run-tests compiler/stdlib/strset/test.th`.
