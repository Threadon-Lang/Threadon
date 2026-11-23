# url

Percent-encoding and query-string helpers. `quote` escapes every byte outside
the RFC 3986 unreserved set; `unquote` decodes `%HH` triples; `encode_form` and
`parse_query` handle `application/x-www-form-urlencoded` style data.

```threadon
import url

def main() -> Int32
    s: String = url.quote("a b+c/~")   # a%20b%2Bc%2F~
    print(s)
    print(url.unquote(s))              # a b+c/~
    d: Dict[String, String] = {"name": "Ada Lovelace", "q": "x&y"}
    print(url.encode_form(d))          # name=Ada%20Lovelace&q=x%26y
    parts: Dict[String, String] = url.parse_query("name=Ada%20Lovelace&q=x%26y")
    print(parts["name"], parts["q"])
    return 0
```

| Function | Result |
| --- | --- |
| `quote(s)` | `s` with all bytes except `A-Z a-z 0-9 -._~` replaced by `%HH` (upper-case hex) |
| `unquote(s)` | `%HH` decoded to its byte; `+` stays `+`; malformed escapes are kept literally |
| `encode_form(d)` | `key=value&key=value` text from a `Dict[String, String]` |
| `parse_query(q)` | `Dict[String, String]` split on `&` then the first `=`; empty keys skipped |

Caveats:

- `encode_form` visits keys in `dict_key` insertion order; no sorting is done,
  so two dicts inserted in different orders encode differently.
- `parse_query` does not treat `+` as a space. Use `unquote` on individual
  values and translate `+` yourself if a form body requires that convention.
- Duplicate keys in a query keep the last value. Parts without `=` get the
  empty String as their value.
- Character codes come from `strings.ord`, which is a plain `def` (linear scan
  over 256 byte values), so these functions are plain `def`s too.
- Malformed escapes such as `%GZ`, `%2` or a trailing `%` are copied through
  unchanged. Threadon strings are byte strings, so decoded bytes above 127
  are returned as raw high-byte characters.

Tests: `python3 -m threadon --run-tests compiler/stdlib/url/test.th`.
