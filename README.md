

CLI
===

the command-line compiler

Usage
-----

Threadon is a Python module that drives LLVM. From the project root:

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

`-e NAME`

Use NAME as the entry point instead of `main`.

`-I DIR`

Add an import search path. Repeatable.

`-O N`

Optimizer inline threshold. Default `0` = no inlining.

`--debug`


`--flag-inf`

Flag infinite (`inf`) and `NaN` float values: non-finite constants are a compile-time error and values that become non-finite at runtime raise a runtime error. Independent of `--debug`. Without it, non-finite values are allowed silently.

Choosing the entry point
------------------------

By default the program starts at `main`, and its return value becomes the exit code. Use `-e` to start somewhere else:

    python3 -m threadon --run -e greet file.th

Two conditions hold:

*   The named function must exist. Otherwise: _"no function 'greet' found in the compiled module"_.
*   The file must not also define `main`. Otherwise: _"the module already defines a 'main' function"_.

The entry function's return value becomes the exit code, like `main`. If it returns `NoneType`, the exit code is 0.

Building an executable
----------------------

`--exe` runs the IR through `llc` and links with `gcc`, so both need to be installed:

    python3 -m threadon --exe hello examples/01_hello/main.th
    ./hello
full docs on https://threadon-lang.github.io/

Threadon 3.0 · If something here disagrees with the compiler, the compiler wins.