# Threadon 3.0
a programming language with c like performance and python like syntax

You can use modules written in the languages **C**, **C++**, **Rust** and **Python**
(including classes from all four) through `manifest` files next to the module
source. See `examples/11_native_c`, `examples/14_python_example` and
`examples/16_python_classes`, and the Modules page in the documentation.

The standard library includes a `torch` module that wraps the C++ (libtorch)
implementation, exposing a `Tensor` class (constructed from a `List[Float64]`,
methods like `sum()`, `mean()`, `max()`, `min()`, `at(i)`, `item()`, `dim()`,
`numel()`) plus an `arange(end) -> List[Float64]` helper:

```threadon
import torch

def main() -> Int32:
    t: torch.Tensor = torch.Tensor([1.0, 2.0, 3.0, 4.0])
    print(t.sum())
    print(t.mean())
    xs: List[Float64] = torch.arange(5.0)
    print(xs[4])
    return 0
```

It needs a libtorch installation (e.g. the one shipped with PyTorch). The
include/lib paths in `stdlib/torch/manifest` use `$TORCH_ROOT`; if not set, the
torch install of the running Python is detected automatically.

## Unittests

Threadon has a pytest-like `unittest` standard-library module. Every module in
the standard library ships a `test.th` suite that uses it:

```threadon
import unittest

def setup() -> Bool:
    # optional: called once before the suite
    return True

def test_addition() -> Bool:
    return unittest.assert_true(1 + 1 == 2)

def test_subtraction() -> Bool:
    return unittest.assert_eq(5 - 3, 2)

def teardown() -> Bool:
    # optional: called once after the suite
    return True
```

A test function returns `Bool` — `True` means it passed — so the idiom is
`return unittest.assert_true(<condition>)`. Assertion helpers (all return
`Bool`, and are Int32-specific because the language has no overloading):
`assert_true`, `assert_false`, `fail`, `assert_eq`, `assert_ne`,
`assert_lt`, `assert_le`, `assert_gt`, `assert_ge`, `assert_approx`
(Float64), `assert_contains`, `assert_starts_with`, `assert_ends_with`
(String). For other types write `unittest.assert_true(a == b)`. See
`stdlib/unittest/unittest.th`.

The compiler automatically adds a `main` to any file named `test.th`: it runs
every module-level `def test_*()` function in source order (between the
optional `setup()` and `teardown()`), prints a `[PASS]`/`[FAIL]` line per test
plus a summary, and returns the number of failed tests as the exit code. So
`test.th` never defines `main` itself.

Run a single suite with `python3 -m threadon --run path/to/test.th`, only the
tests matching a name with `-k`:

```
python3 -m threadon --run-tests
python3 -m threadon --run-tests -k test_addition
```

`--run-tests` discovers every `test.th` under the project root (the nearest
ancestor with a `pyproject.toml`/`setup.py`/`.git`/... marker), the `-I`
include paths and the stdlib — from anywhere below the project, not just the
compiler directory. `pip install .` also compiles and runs the bundled
`stdlib` suites as a self-test (disable with `THREADON_SKIP_INSTALL_TESTS=1`).

## TODO's

### adding libraries:
- imports
- standard library
- the possibility to use libraries out of the languages C, C++, Rust and Python (done, see above)
- future: Java and Javascript
### Adding classes
- class inheterance
- \_\_init\_\_'s
- functions like \_\_add\_\_  and \_\_str\_\_
### proper documentation
### more unittests
### adding decorators