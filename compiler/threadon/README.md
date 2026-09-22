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