# path

POSIX-style path string helpers, built on the `strings` module. No filesystem
access: these functions never check whether a path exists.

```threadon
import path

def main() -> Int32
    p: String = "/home/user/notes.txt"
    print(path.basename(p))    # notes.txt
    print(path.extension(p))   # .txt
    print(path.join("a", "b")) # a/b
    return 0
```

| Function | Result |
| --- | --- |
| `basename(p)` | last component |
| `dirname(p)` | everything before the last slash (`.` when there is none) |
| `extension(p)` | suffix including the dot, or `""` |
| `stem(p)` | file name without its extension |
| `with_extension(p, ext)` | replace the extension |
| `join(a, b)` | join with one slash; an absolute `b` replaces `a` |
| `is_absolute(p)` | does `p` start with `/`? |
| `normalize(p)` | collapse repeated slashes and drop a trailing slash |

Tests: `python3 -m threadon --run-tests compiler/stdlib/path/test.th`.
