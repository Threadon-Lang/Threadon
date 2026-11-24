#!/usr/bin/env python3
"""Benchmark Threadon against C++ and Python on the same numeric workloads.

Each benchmark case lives in ``cases/<name>/`` and provides the same program in
Threadon (``<name>.th``), C++ (``<name>.cpp``) and Python (``<name>.py``). The
programs print a checksum, which the runner uses to verify that every
implementation computed the same answer.

Compilation time and execution time are reported separately. Execution times
are wall-clock medians over several fresh processes, so Threadon's JIT startup
is included in the ``JIT/lli`` numbers, just as it is in a normal
``python3 -m threadon ... --run`` invocation.
"""

from __future__ import annotations

import argparse
import ctypes.util
import os
import shutil
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

BENCH_ROOT = Path(__file__).resolve().parent
REPO_ROOT = BENCH_ROOT.parent
CASES_DIR = BENCH_ROOT / "cases"
COMPILER_DIR = REPO_ROOT / "compiler"
DEFAULT_BUILD_DIR = BENCH_ROOT / "build"


class BenchmarkError(RuntimeError):
    pass


@dataclass(frozen=True)
class Implementation:
    key: str
    name: str
    needs: tuple[str, ...] = ()


IMPLEMENTATIONS = (
    Implementation("cpp", "C++ (g++ -O2)", ("g++",)),
    Implementation("threadon-jit", "Threadon (JIT/lli)", ("lli",)),
    Implementation("threadon-native", "Threadon (native exe)", ("llc", "gcc")),
    Implementation("python", "Python 3", ()),
)


@dataclass
class Result:
    impl: Implementation
    compile_time: float | None
    median: float
    best: float
    output: str


def discover_cases() -> list[str]:
    cases = []
    for path in sorted(CASES_DIR.iterdir()):
        if not path.is_dir():
            continue
        required = (f"{path.name}.th", f"{path.name}.cpp", f"{path.name}.py")
        if all((path / name).is_file() for name in required):
            cases.append(path.name)
    return cases


def threadon_env(use_installed: bool) -> dict[str, str]:
    env = os.environ.copy()
    if not use_installed:
        previous = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(COMPILER_DIR) + (
            os.pathsep + previous if previous else ""
        )
    return env


def lli_command(ir_path: Path) -> list[str]:
    cmd = ["lli", "-O2"]
    libatomic = ctypes.util.find_library("atomic")
    if libatomic:
        cmd += ["-load", libatomic]
    cmd.append(str(ir_path))
    return cmd


def build_plan(
    impl: Implementation,
    case: str,
    build_dir: Path,
    use_installed: bool,
    inline_threshold: int,
) -> tuple[list[list[str]], list[str], dict[str, str] | None]:
    """Return (build commands, run command, environment) for an implementation."""
    source_dir = CASES_DIR / case
    base = source_dir / case
    env = threadon_env(use_installed)
    threadon_cmd = [sys.executable, "-m", "threadon", "-O", str(inline_threshold)]

    if impl.key == "cpp":
        exe = build_dir / f"{case}_cpp"
        return (
            [["g++", "-O2", "-std=c++17", str(base) + ".cpp", "-o", str(exe)]],
            [str(exe)],
            None,
        )

    if impl.key == "python":
        return [], [sys.executable, str(base) + ".py"], None

    if impl.key == "threadon-jit":
        ir = build_dir / f"{case}.ll"
        opt_ir = build_dir / f"{case}.opt.ll"
        build_cmds = [threadon_cmd + [str(base) + ".th", "-o", str(ir)]]
        opt_cmd = shutil.which("opt") or shutil.which("opt-19")
        run_ir = ir
        if opt_cmd:
            build_cmds.append([opt_cmd, "-O2", "-S", str(ir), "-o", str(opt_ir)])
            run_ir = opt_ir
        return (build_cmds, lli_command(run_ir), env)

    if impl.key == "threadon-native":
        exe = build_dir / f"{case}_threadon"
        return (
            [threadon_cmd + ["--exe", str(exe), str(base) + ".th"]],
            [str(exe)],
            env,
        )

    raise BenchmarkError(f"unknown implementation: {impl.key}")


def run_command(cmd: list[str], env: dict[str, str] | None) -> subprocess.CompletedProcess[str]:
    def _no_core():
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        except Exception:
            pass

    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=300,
            preexec_fn=_no_core,
        )
    except FileNotFoundError as exc:
        raise BenchmarkError(f"missing executable: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise BenchmarkError(f"timeout after {exc.timeout}s: {' '.join(cmd)}") from exc


def measure(
    impl: Implementation,
    case: str,
    build_dir: Path,
    runs: int,
    use_installed: bool,
    inline_threshold: int,
) -> Result:
    build_cmds, run_cmd, env = build_plan(
        impl, case, build_dir, use_installed, inline_threshold
    )

    compile_time = None
    for cmd in build_cmds:
        start = time.perf_counter()
        proc = run_command(cmd, env)
        elapsed = time.perf_counter() - start
        if proc.returncode != 0:
            raise BenchmarkError(
                f"build failed for {impl.name}:\n{proc.stderr.strip()}"
            )
        compile_time = elapsed if compile_time is None else compile_time + elapsed

    times: list[float] = []
    outputs: set[str] = set()
    for _ in range(runs):
        start = time.perf_counter()
        proc = run_command(run_cmd, env)
        times.append(time.perf_counter() - start)
        if proc.returncode != 0:
            raise BenchmarkError(
                f"run failed for {impl.name}:\n{proc.stderr.strip()}"
            )
        outputs.add(proc.stdout.strip())

    if len(outputs) != 1:
        raise BenchmarkError(f"{impl.name} gave inconsistent output: {outputs}")
    return Result(impl, compile_time, statistics.median(times), min(times), outputs.pop())


def report(case: str, results: list[Result]) -> None:
    cpp_median = next(
        (r.median for r in results if r.impl.key == "cpp" and r.median > 0),
        None,
    )

    header = (
        f"{'case':<12} {'implementation':<22} {'compile':>9} "
        f"{'median':>9} {'best':>9} {'result':>12} {'vs C++':>14}"
    )
    print(header)
    print("-" * len(header))
    for index, r in enumerate(results):
        compile_s = f"{r.compile_time:.3f}s" if r.compile_time is not None else "-"
        if cpp_median is not None:
            ratio = r.median / cpp_median
            ratio_s = f"{ratio:.2f}x {'slower' if ratio >= 1 else 'faster'}"
        else:
            ratio_s = "-"
        print(
            f"{case if index == 0 else '':<12} {r.impl.name:<22} {compile_s:>9} "
            f"{r.median:>8.3f}s {r.best:>8.3f}s {r.output:>12} {ratio_s:>14}"
        )

    outputs = {r.output for r in results}
    if len(outputs) == 1:
        print("\nAll implementations agree on the checksum.")
    else:
        print(f"\nWARNING: checksums disagree: {sorted(outputs)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases",
        nargs="*",
        help="Benchmark only these case names (default: all).",
    )
    parser.add_argument(
        "--langs",
        nargs="*",
        choices=[impl.key for impl in IMPLEMENTATIONS],
        help="Benchmark only these implementations (default: all available).",
    )
    parser.add_argument("--runs", type=int, default=5, help="Runs per case (default: 5).")
    parser.add_argument(
        "--inline-threshold",
        type=int,
        default=0,
        metavar="N",
        help="Threadon -O inline threshold (default: 0 = no inlining).",
    )
    parser.add_argument(
        "--build-dir",
        type=Path,
        default=DEFAULT_BUILD_DIR,
        help=f"Build artefacts directory (default: {DEFAULT_BUILD_DIR}).",
    )
    parser.add_argument(
        "--installed",
        action="store_true",
        help="Use the installed threadon package instead of this repo's compiler/.",
    )
    parser.add_argument("--list", action="store_true", help="List cases and exit.")
    args = parser.parse_args()

    cases = discover_cases()
    if not cases:
        print("No benchmark cases found.", file=sys.stderr)
        return 1
    if args.list:
        print("\n".join(cases))
        return 0

    if args.cases:
        unknown = set(args.cases) - set(cases)
        if unknown:
            print(f"Unknown case(s): {', '.join(sorted(unknown))}", file=sys.stderr)
            return 2
        cases = [c for c in cases if c in args.cases]
    if args.runs < 1:
        print("--runs must be at least 1", file=sys.stderr)
        return 2

    selected = IMPLEMENTATIONS
    if args.langs:
        selected = tuple(i for i in IMPLEMENTATIONS if i.key in args.langs)
    available = [
        impl
        for impl in selected
        if all(shutil.which(tool) for tool in impl.needs)
    ]
    skipped = [impl for impl in selected if impl not in available]

    args.build_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"Benchmarking {len(cases)} case(s), {args.runs} run(s) each; "
        f"compiler: {'installed package' if args.installed else 'repo compiler/'}; "
        f"-O {args.inline_threshold}"
    )
    if skipped:
        print("Skipping (toolchain unavailable): " + ", ".join(i.name for i in skipped))

    failed = False
    for case in cases:
        print(f"\n=== {case} ===")
        results = []
        for impl in available:
            try:
                results.append(
                    measure(
                        impl,
                        case,
                        args.build_dir,
                        args.runs,
                        args.installed,
                        args.inline_threshold,
                    )
                )
            except BenchmarkError as exc:
                failed = True
                print(f"  {impl.name}: FAILED: {exc}")
        if results:
            report(case, results)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
