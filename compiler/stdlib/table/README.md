# table

Plain-text table and progress-bar helpers. `table()` measures every column,
renders a header separator and returns the whole grid as one String; the
building blocks (`pad_cell`, `row`, `separator`, `bar`) are useful on their own.
No argument is mutated.

```threadon
import table

def main() -> Int32
    rows: List[List[String]] = [["name", "qty"], ["apple", "3"]]
    print(table.table(rows))
    print(table.bar(3, 4, 5, ""))
    return 0
```

| Function | Result |
| --- | --- |
| `pad_cell(s, width)` | left-aligned cell; too-long values end in `..` |
| `row(cells, widths)` | `| a | b |` with one space of padding |
| `separator(widths)` | `+---+---+` for the same widths |
| `bar(value, maximum, width, ch)` | fixed-width bar; `ch` defaults to `#` |
| `table(rows)` | full grid, with a separator after row 0 |

Widths are byte counts. Short rows get empty cells; extra cells are ignored.
`table()` returns `""` for an empty row list.

Tests: `python3 -m threadon --run-tests compiler/stdlib/table/test.th`.
