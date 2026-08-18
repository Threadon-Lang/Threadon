#!/usr/bin/env python3
"""Command-line driver for the Threadon compiler.threadon.

Compiles a ``.th`` file (together with the modules it imports) to LLVM IR,
or executes it with ``lli``.

Examples::

    python3 -m threadon examples/01_hello/main.th
    python3 -m threadon --run examples/03_imports/main.th
    python3 -m threadon -o out.ll examples/02_structs/main.th
    python3 -m threadon --exe hello examples/01_hello/main.th
    python3 -m threadon --run -I ./lib examples/app/main.th
"""

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path
import sysconfig
import shlex 

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from .compiler import compile_file
from .importer import Importer

def _python_includes():
    """Include flags needed when compiling a Python-bridge module."""
    include_dir = sysconfig.get_paths().get("include")
    if include_dir:
        return [f"-I{include_dir}"]
    return []
def _python_link_flags():
    """Link flags needed to embed the Python interpreter (Py_Initialize etc.)."""
    try:
        out = subprocess.check_output(
            ["python3-config", "--embed", "--ldflags"], text=True
        ).strip()
        return shlex.split(out)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    try:
        out = subprocess.check_output(
            ["python3-config", "--ldflags"], text=True
        ).strip()
        return shlex.split(out)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

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


def run_llvm(llvm, capture=False, loads=None):
    with tempfile.NamedTemporaryFile("w", suffix=".ll", delete=False) as f:
        f.write(llvm)
        path = f.name
    try:
        kwargs = {"capture_output": True, "text": True} if capture else {}
        cmd = ["lli"]
        for so in (loads or []):
            cmd.append("-load")
            cmd.append(str(so))
        cmd.append(path)
        return subprocess.run(cmd, **kwargs)
    finally:
        Path(path).unlink(missing_ok=True)


def native_modules(importer):
    return [m for m in importer.modules() if m.is_native]

def build_native_shared_libs(modules, output_dir):
    output_dir = Path(output_dir)
    libs = []
    for mod in modules:
        if mod.toolchain is None:
            raise SystemExit(f"error: module '{mod.name}' has no registered toolchain")
        if mod.native_source is None or not mod.native_source.is_file():
            raise SystemExit(f"error: native module '{mod.name}' has no source file")
        tc = mod.toolchain
        so = output_dir / f"lib{mod.name}.so"
        flags = mod.flags or []
        is_python = tc.name == "python"
        includes = _python_includes() if is_python else []
        link_extra = _python_link_flags() if is_python else []
        sources = [str(mod.native_source)] + [str(s) for s in (mod.extra_sources or [])]
        result = subprocess.run(
            [tc.compiler, *tc.shared_args, *includes, *flags,
             "-o", str(so), *sources, *link_extra],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise SystemExit(
                f"error: {tc.compiler} failed compiling {mod.name} ({tc.name}):\n{result.stderr}"
            )
        libs.append(so)
    return libs
def _python_link_flags():
    """Link flags needed to embed the Python interpreter (Py_Initialize etc.)."""
    try:
        out = subprocess.check_output(
            ["python3-config", "--embed", "--ldflags"], text=True
        ).strip()
        return shlex.split(out)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    try:
        out = subprocess.check_output(
            ["python3-config", "--ldflags"], text=True
        ).strip()
        return shlex.split(out)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


def build_executable(llvm, out_path, llc="llc", cc="gcc", native=None):
    """Compile the (patched, harnessed) LLVM IR to a native executable."""
    out_path = Path(out_path)
    native = native or []
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
        objs = [str(obj)]
        link_flags = []
        linker = cc
        link_extra = []
        for mod in native:
                    if mod.toolchain is None:
                        raise SystemExit(f"error: module '{mod.name}' has no registered toolchain")
                    for lib in mod.links:
                        link_flags.append(f"-l{lib}")
                    if mod.native_source is None or not mod.native_source.is_file():
                        raise SystemExit(f"error: native module '{mod.name}' has no source file")
                    tc = mod.toolchain
                    if tc.cxx:
                        linker = "g++"
                    mod_obj = td / f"{mod.name}.{tc.object_ext}"
                    flags = mod.flags or []
                    includes = _python_includes() if tc.name == "python" else []
                    link_extra = _python_link_flags() if tc.name == "python" else []
                    result = subprocess.run(
                        [tc.compiler, *tc.object_args, *includes, *flags, "-o", str(mod_obj), str(mod.native_source)],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode != 0:
                        raise SystemExit(
                            f"error: {tc.compiler} failed compiling {mod.name} ({tc.name}):\n{result.stderr}"
                        )
                    objs.append(str(mod_obj))
        result = subprocess.run(
            [linker, *objs, "-o", str(out_path), "-no-pie", "-lm", *link_flags, *link_extra],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise SystemExit(f"error: {linker} failed:\n{result.stderr}")


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
        mods = native_modules(importer)
        if mods:
            with tempfile.TemporaryDirectory() as td:
                libs = build_native_shared_libs(mods, output_dir=td)
                result = run_llvm(final, loads=libs)
        else:
            result = run_llvm(final)
        sys.exit(result.returncode)

    if args.exe:
        final = dedupe_decls(
            patch_llvm(llvm) + "\n" + build_harness(llvm, args.entry) + "\n"
        )
        build_executable(final, args.exe, native=native_modules(importer))
        return 0

    if not args.output:
        sys.stdout.write(llvm)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
