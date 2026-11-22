

Threadon
===
Installation
---
Install threadon using pip
```bash
sudo apt install llvm
pip3 install threadon
```


Usage
-----

Threadon is a Python module that drives LLVM

    python3 -m threadon FILE.th [options]

With no options, the compiler prints LLVM IR to standard output.

Flags
-----

Flag

Meaning

`-o FILE`

Write the LLVM IR to FILE instead of stdout.

`--run`

Execute the program with `lli` after compiling.

`--exe FILE`

Build a native executable via `llc` and `gcc`.

`-I DIR`

Add an import search path. Repeatable.

`-O N`

Optimizer inline threshold. Default `0` = no inlining.

`--debug`


`--flag-inf`

Flag infinite (`inf`) and `NaN` float values: non-finite constants are a compile-time error and values that become non-finite at runtime raise a runtime error. Independent of `--debug`. Without it, non-finite values are allowed silently.

Pure functions
--------------

Use `puredef` instead of `def` to declare that a function has no side effects:

```threadon
puredef abs(x: Int32) -> Int32
    if x < 0:
        return -x
    return x
```

The compiler enforces this at compile time. A pure function may only:

- call other `puredef` functions (and the pure builtins `len`, `chr`, `dict_key`);
- read global variables;
- change local variables, local containers and local `self` fields.

It may not:

- call a plain `def` function;
- write a global variable or mutate a global container;
- call a function or method from a native Python/C/C++/Rust module;
- print, read input, call `collect()`, start a thread or use `thread_exit`.

`puredef` works for methods too, including `__init__`, as long as the body stays side-effect free.

Entry point
-----------

Programs always start at `main`. Its return value becomes the exit code. A program without a `main` function cannot be run or built as an executable: `error: no function 'main' found in the compiled module`.

Building an executable
----------------------

`--exe` runs the IR through `llc` and links with `gcc`, so both need to be installed:

    python3 -m threadon --exe hello examples/01_hello/main.th
    ./hello
full docs on https://threadon-lang.github.io/

Threadon 3.0 · If something here disagrees with the compiler, the compiler wins.