# Threadon benchmarks

Small, self-contained workloads compiled and run in several languages so you
can compare Threadon with C++ and Python on the **same algorithm**.

## Running

```bash
python3 benchmark/run.py
```

By default this benchmarks every case in `benchmark/cases/` with:

- **C++ (g++ -O2)** — compiled native baseline
- **Threadon (JIT/lli)** — `python3 -m threadon FILE.th -o FILE.ll`, then `lli FILE.ll`
- **Threadon (native exe)** — `python3 -m threadon --exe ... FILE.th`
- **Python 3** — interpreted reference

The runner uses the compiler sources in this repository (`compiler/` on
`PYTHONPATH`). Add `--installed` to benchmark the installed `threadon` package
instead.

Useful options:

```bash
python3 benchmark/run.py --list                     # list available cases
python3 benchmark/run.py --cases mandelbrot         # one case
python3 benchmark/run.py --langs cpp threadon-jit   # selected implementations
python3 benchmark/run.py --runs 10                  # more timing samples
python3 benchmark/run.py --installed                # benchmark installed package
```

## What is measured

| Column | Meaning |
| --- | --- |
| `compile` | Wall time to build the artefact (once). `-` for interpreted Python. |
| `median` | Median wall time over `--runs` fresh process launches. |
| `best` | Fastest of those runs. |
| `result` | Checksum printed by the program. All implementations must agree. |
| `vs C++` | `median / C++ median`; values above 1 mean slower than C++. |

Fresh processes are timed deliberately: JIT startup and dynamic linking are
part of the cost a user pays when running a program. Compilation is reported
separately so it does not pollute the execution numbers. Each program is
deterministic and prints a checksum, which makes it easy to spot a bad port.

## Cases

- **mandelbrot** — 256×256 escape-time count, max 255 iterations (floating point).
- **primes** — count primes below 20,000 by trial division (integer arithmetic).

Each case directory contains the same program as `<name>.th`, `<name>.cpp` and
`<name>.py`.

## Adding a case

1. Create `benchmark/cases/<name>/`.
2. Add `<name>.th`, `<name>.cpp` and `<name>.py` with identical algorithms and
   a single-line checksum on stdout.
3. Run `python3 benchmark/run.py --cases <name>` to verify the checksums agree.

Build artefacts go to `benchmark/build/` (git-ignored). Toolchains that are not
installed are skipped with a message rather than failing the whole run.
