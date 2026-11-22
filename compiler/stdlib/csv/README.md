# csv

A small CSV reader and writer for strings. Threadon has no file I/O, so the
input usually comes from `input()` or a string literal.

```threadon
import csv

def main() -> Int32
    row: String = "name,score"
    fields: List[String] = csv.parse_line("\"Doe, Jane\",10")
    print(fields[0])                       # Doe, Jane
    print(csv.encode_line(fields))         # "Doe, Jane",10
    return 0
```

| Function | Result |
| --- | --- |
| `parse_line(line)` | `List[String]` of fields; quotes may contain commas |
| `encode_field(s)` | one field, quoted only when it contains a comma, quote or newline |
| `encode_line(fields)` | join encoded fields with commas |
| `split_lines(text)` | `List[String]` of lines (`\n` separated) |
| `get_field(line, index)` | one field by index, or `""` when out of range |

Quotes inside quoted fields are doubled, following RFC 4180.

Tests: `python3 -m threadon --run-tests compiler/stdlib/csv/test.th`.
