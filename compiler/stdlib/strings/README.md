# strings

Everyday string helpers built on top of the language's concatenation, indexing
and slicing. Every function returns a new string; strings are immutable.

```threadon
import strings

def main() -> Int32
    s: String = strings.trim("  Hello, World!  ")
    print(strings.upper(s))                   # HELLO, WORLD!
    parts: List[String] = strings.split(s, ", ")
    print(strings.join(parts, " | "))         # Hello | World!
    return 0
```

| Function | Result |
| --- | --- |
| `length(s)` | length as `Int64` (same as the built-in `len`) |
| `ord(c)` | byte value of a single-byte string, or `-1` |
| `upper(s)` / `lower(s)` | ASCII case conversion |
| `trim(s)` / `ltrim(s)` / `rtrim(s)` | remove surrounding spaces, tabs and newlines |
| `index_of(s, needle)` / `last_index_of(s, needle)` | first/last match, or `-1` |
| `contains(s, needle)` | `Bool` |
| `starts_with(s, prefix)` / `ends_with(s, suffix)` | `Bool` |
| `count(s, needle)` | number of non-overlapping matches |
| `replace(s, old, new)` | replace all occurrences |
| `split(s, sep)` | `List[String]`; an empty separator yields `[s]` |
| `join(parts, sep)` | join a `List[String]` |
| `reverse(s)` / `repeat(s, n)` | reversed / repeated text |
| `pad_left(s, width, pad)` / `pad_right(...)` | pad with the first byte of `pad` |
| `is_digit(s)` / `is_alpha(s)` / `is_alnum(s)` | whole-string character tests |

Only ASCII case conversion is provided; Threadon strings are byte strings.

Tests: `python3 -m threadon --run-tests compiler/stdlib/strings/test.th`.
