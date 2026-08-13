#!/usr/bin/env python3
"""Command-line driver for the Threadon compiler.

Compiles a ``.th`` file (together with the modules it imports) to LLVM IR,
or executes it with ``lli``.

Examples::

    python3 -m compiler.main examples/01_hello/main.th
    python3 -m compiler.main --run examples/03_imports/main.th
    python3 -m compiler.main -o out.ll examples/02_structs/main.th
    python3 -m compiler.main --exe hello examples/01_hello/main.th
    python3 -m compiler.main --run -I ./lib examples/app/main.th
"""

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from compiler.compiler import compile_file
from compiler.importer import Importer

POW_I32_IMPL = """
define i32 @llvm.pow.i32(i32 %base, i32 %exp) {
entry:
  %res = alloca i32
  store i32 1, i32* %res
  %cnt = alloca i32
  store i32 0, i32* %cnt
  br label %loop

loop:
  %c = load i32, i32* %cnt
  %cmp = icmp slt i32 %c, %exp
  br i1 %cmp, label %body, label %done

body:
  %r0 = load i32, i32* %res
  %m = mul i32 %r0, %base
  store i32 %m, i32* %res
  %c1 = load i32, i32* %cnt
  %n = add i32 %c1, 1
  store i32 %n, i32* %cnt
  br label %loop

done:
  %r = load i32, i32* %res
  ret i32 %r
}
"""

def build_harness(llvm, entry="main"):
    """Generate a main() wrapper for a non-main entry point.

    A Threadon function named ``main`` is already the program's entry point,
    so no wrapper is needed and an empty string is returned. For any other
    entry the result is used as the process exit code (not printed).
    """
    match = re.search(
        rf"define\s+([^\s(]+)\s+@{re.escape(entry)}\(", llvm
    )
    if not match:
        raise SystemExit(
            f"error: no function '{entry}' found in the compiled module"
        )
    rtype = match.group(1)

    if entry == "main":
        return ""

    if re.search(r"define\s+i32\s+@main\(", llvm):
        raise SystemExit(
            f"error: the module already defines a 'main' function; "
            f"cannot use '{entry}' as the entry point"
        )

    if rtype == "void":
        return (
            f"define i32 @main() {{\n"
            f"  call void @{entry}()\n"
            + "  ret i32 0\n"
            + "}\n"
        )

    if rtype == "i32":
        return (
            f"define i32 @main() {{\n"
            f"  %r = call i32 @{entry}()\n"
            + "  ret i32 %r\n"
            + "}\n"
        )

    return (
        f"define i32 @main() {{\n"
        f"  %r = call {rtype} @{entry}()\n"
        + "  ret i32 0\n"
        + "}\n"
    )


def patch_llvm(llvm):
    llvm = re.sub(
        r"declare i32 @llvm\.pow\.i32\(i32, i32\) #\d+\n",
        POW_I32_IMPL + "\n",
        llvm,
    )
    return llvm


def dedupe_decls(llvm):
    """Remove duplicate ``declare`` lines (e.g. printf from backend + harness)."""
    seen = set()
    out = []
    for line in llvm.splitlines():
        if line.startswith("declare "):
            if line in seen:
                continue
            seen.add(line)
        out.append(line)
    return "\n".join(out)


def run_llvm(llvm, capture=False):
    with tempfile.NamedTemporaryFile("w", suffix=".ll", delete=False) as f:
        f.write(llvm)
        path = f.name
    try:
        kwargs = {"capture_output": True, "text": True} if capture else {}
        return subprocess.run(["lli", path], **kwargs)
    finally:
        Path(path).unlink(missing_ok=True)


def build_executable(llvm, out_path, llc="llc", cc="gcc"):
    """Compile the (patched, harnessed) LLVM IR to a native executable."""
    out_path = Path(out_path)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        ir = td / "main.ll"
        obj = td / "main.o"
        ir.write_text(llvm)
        result = subprocess.run(
            [llc, "-filetype=obj", "-o", str(obj), str(ir)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise SystemExit(f"error: {llc} failed:\n{result.stderr}")
        result = subprocess.run(
            [cc, str(obj), "-o", str(out_path), "-no-pie", "-lm"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise SystemExit(f"error: {cc} failed:\n{result.stderr}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="threadon",
        description="Compile a Threadon (.th) file (with its imports) to LLVM IR.",
    )
    parser.add_argument("file", metavar="FILE.th", help="the Threadon source file")
    parser.add_argument(
        "-o", "--output", metavar="FILE", help="write LLVM IR to FILE (default: stdout)"
    )
    parser.add_argument(
        "--run", action="store_true", help="execute the module with lli after compiling"
    )
    parser.add_argument(
        "--exe",
        metavar="FILE",
        help="build a native executable to FILE (via llc + gcc)",
    )
    parser.add_argument(
        "-e",
        "--entry",
        default="main",
        help="entry function for --run/--exe (default: main)",
    )
    parser.add_argument(
        "-I",
        "--include",
        action="append",
        default=[],
        metavar="DIR",
        help="add an import search path (repeatable)",
    )
    parser.add_argument(
        "-O",
        "--inline-threshold",
        type=int,
        default=0,
        metavar="N",
        help="optimizer inline threshold (default: 0 = no inlining)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug runtime checks")
    parser.add_argument(
        "--flag-inf",
        action="store_true",
        help="Flag non-finite float values (inf/NaN): constants error at compile time, "
        "runtime values raise a runtime error (independent of --debug)",
    )
    
    args = parser.parse_args(argv)

    path = Path(args.file)
    if not path.is_file():
        parser.error(f"file not found: {path}")

    importer = Importer()
    importer.add_search_path(path.parent)
    for include in args.include:
        importer.add_search_path(include)

    llvm = compile_file(
        path,
        importer=importer,
        inline_threshold=args.inline_threshold,
        debug_mode=args.debug,
        flag_inf=args.flag_inf,
    )

    if args.output:
        Path(args.output).write_text(llvm)

    if args.run:
        final = dedupe_decls(
            patch_llvm(llvm) + "\n" + build_harness(llvm, args.entry) + "\n"
        )
        result = run_llvm(final)
        sys.exit(result.returncode)

    if args.exe:
        final = dedupe_decls(
            patch_llvm(llvm) + "\n" + build_harness(llvm, args.entry) + "\n"
        )
        build_executable(final, args.exe)
        return 0

    if not args.output:
        sys.stdout.write(llvm)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
