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
    python3 -m threadon --run-tests                       # run every test.th suite
    python3 -m threadon --run-tests path/to/test.th       # or a specific suite
    python3 -m threadon --run-tests -k test_addition      # or only matching tests
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import sysconfig
import shlex 

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from . import project
from .compiler import compile_file
from .errors import report_error, tool_error
from .importer import Importer
from .test_harness import find_test_functions

def _python_includes():
    """Include flags needed when compiling a Python-bridge module."""
    include_dir = sysconfig.get_paths().get("include")
    if include_dir:
        return [f"-I{include_dir}"]
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

def require_main(llvm):
    """Check that the compiled module has the program entry point.

    Threadon always starts at ``main``; the compiler emits it directly, so no
    extra harness is needed.
    """
    if not re.search(r"define\s+[^\s(]+\s+@main\(", llvm):
        tool_error("no function 'main' found in the compiled module")


def patch_llvm(llvm):
    llvm = re.sub(
        r"declare i32 @llvm\.pow\.i32\(i32, i32\) #\d+\n",
        POW_I32_IMPL + "\n",
        llvm,
    )
    return llvm


def dedupe_decls(llvm):
    """Remove duplicate ``declare`` lines by symbol name.

    The GC runtime is emitted before the backend's C-runtime declarations and
    may already declare ``printf`` (for ``THREADON_GC_STATS``) or ``malloc``
    with a slightly different signature. LLVM rejects a second declaration of
    the same symbol even when the types differ, so keep the first one.
    """
    seen = set()
    out = []
    for line in llvm.splitlines():
        if line.startswith("declare "):
            match = re.search(r"@([^\s(]+)", line)
            key = match.group(0) if match else line
            if key in seen:
                continue
            seen.add(key)
        out.append(line)
    return "\n".join(out)


def _run_tool(cmd, **kwargs):
    """Run an external tool, turning a missing binary into a clean diagnostic."""
    try:
        return subprocess.run(cmd, **kwargs)
    except FileNotFoundError:
        tool_error(
            f"'{cmd[0]}' was not found. Install the LLVM toolchain "
            "(lli, llc, opt) and a C compiler (gcc) to use this feature."
        )


def run_llvm(llvm, capture=False, loads=None, library_dirs=None):
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        ir_path = td / "main.ll"
        ir_path.write_text(llvm)
        opt_cmd = shutil.which("opt") or shutil.which("opt-19")
        run_path = ir_path
        if opt_cmd:
            opt_path = td / "main.opt.ll"
            r = _run_tool(
                [opt_cmd, "-O2", "-S", str(ir_path), "-o", str(opt_path)],
                capture_output=True,
                text=True,
            )
            if r.returncode == 0 and opt_path.exists():
                run_path = opt_path
        kwargs = {"capture_output": True, "text": True} if capture else {}
        env = os.environ.copy()
        if library_dirs:
            prev = env.get("LD_LIBRARY_PATH", "")
            env["LD_LIBRARY_PATH"] = ":".join(library_dirs) + (f":{prev}" if prev else "")
        cmd = ["lli", "-O2"]
        for so in (loads or []):
            cmd.append("-load")
            cmd.append(str(so))
        # automatically load libatomic for __atomic_* symbols
        import ctypes.util
        libatomic = ctypes.util.find_library("atomic")
        if libatomic:
            cmd.append("-load")
            cmd.append(libatomic)
        cmd.append(str(run_path))
        return _run_tool(cmd, env=env, **kwargs)


def native_library_dirs(modules):
    dirs = []
    for mod in modules:
        for link in mod.links or []:
            link = os.path.expandvars(link)
            if link.startswith("-L"):
                dirs.append(link[2:])
    return dirs


def native_modules(importer):
    return [m for m in importer.modules() if m.is_native]

def build_native_shared_libs(modules, output_dir):
    output_dir = Path(output_dir)
    libs = []
    for mod in modules:
        if mod.toolchain is None:
            tool_error(f"module '{mod.name}' has no registered toolchain")
        if mod.native_source is None or not mod.native_source.is_file():
            tool_error(f"native module '{mod.name}' has no source file")
        existing = Path(mod.manifest_dir) / f"{mod.name}.so"
        sources = [mod.native_source] + list(mod.extra_sources or [])
        if existing.is_file() and all(
            source.is_file() and source.stat().st_mtime <= existing.stat().st_mtime
            for source in sources
        ):
            libs.append(existing)
            continue
        tc = mod.toolchain
        so = output_dir / f"lib{mod.name}.so"
        flags = mod.flags or []
        is_python = tc.name == "python"
        includes = _python_includes() if is_python else []
        link_extra = _python_link_flags() if is_python else []
        sources = [str(mod.native_source)] + [str(s) for s in (mod.extra_sources or [])]
        result = _run_tool(
            [tc.compiler, *tc.shared_args, *includes, *flags,
             "-o", str(so), *sources, *link_extra],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            tool_error(
                f"{tc.compiler} failed compiling {mod.name} ({tc.name}):\n{result.stderr}"
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
        opt_ir = td / "main.opt.ll"
        obj = td / "main.o"
        ir.write_text(llvm)
        opt_cmd = shutil.which("opt") or shutil.which("opt-19")
        if opt_cmd:
            result = _run_tool(
                [opt_cmd, "-O2", "-S", str(ir), "-o", str(opt_ir)],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and opt_ir.exists():
                ir = opt_ir
        result = _run_tool(
            [llc, "-O2", "-filetype=obj", "-o", str(obj), str(ir)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            tool_error(f"{llc} failed:\n{result.stderr}")
        objs = [str(obj)]
        link_flags = []
        linker = cc
        link_extra = []
        for mod in native:
                    if mod.toolchain is None:
                        tool_error(f"module '{mod.name}' has no registered toolchain")
                    for lib in mod.links or []:
                        link_flags.append(f"-l{lib}")
                    if mod.native_source is None or not mod.native_source.is_file():
                        tool_error(f"native module '{mod.name}' has no source file")
                    tc = mod.toolchain
                    if tc.cxx:
                        linker = "g++"
                    mod_obj = td / f"{mod.name}.{tc.object_ext}"
                    flags = mod.flags or []
                    includes = _python_includes() if tc.name == "python" else []
                    link_extra = _python_link_flags() if tc.name == "python" else []
                    sources = [str(mod.native_source)] + [
                        str(extra) for extra in (mod.extra_sources or [])
                    ]
                    result = _run_tool(
                        [tc.compiler, *tc.object_args, *includes, *flags, "-o", str(mod_obj), *sources],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode != 0:
                        tool_error(
                            f"{tc.compiler} failed compiling {mod.name} ({tc.name}):\n{result.stderr}"
                        )
                    objs.append(str(mod_obj))
        result = _run_tool(
            [linker, *objs, "-o", str(out_path), "-no-pie", "-lm", *link_flags, *link_extra],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            tool_error(f"{linker} failed:\n{result.stderr}")


_PROJECT_MARKERS = (
    project.CONFIG_FILENAME,
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "MANIFEST.in",
    ".git",
    ".hg",
)

_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    "build",
    "dist",
    "target",
}


def _is_skipped_dir(path, root):
    """Skip matches inside heavy/vendored directories during discovery."""
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False
    return any(part in _SKIP_DIRS for part in rel.parts[:-1])


def project_root(start):
    """Nearest ancestor of ``start`` that looks like a project (or ``start``).

    Never climbs into the home directory, so an accidental ``~/.git`` cannot
    cause a scan of the whole home tree.
    """
    start = Path(start).resolve()
    home = str(Path.home())
    for cand in [start, *start.parents]:
        if cand == cand.parent:
            break
        if str(cand) == home:
            break
        if any((cand / m).exists() for m in _PROJECT_MARKERS):
            return cand
    return start


def discover_test_files(targets, cwd, include_paths):
    """Locate every ``test.th`` suite to run.

    With explicit ``targets`` (files or directories) only those are used.
    Otherwise the project root above ``cwd`` (the nearest ancestor holding a
    pyproject.toml/setup.py/.git/... marker), the ``-I`` include dirs and the
    stdlib are scanned for ``test.th`` files -- never just the compiler
    directory, no matter where the command was invoked from.
    """
    importer = Importer()
    for inc in include_paths:
        importer.add_search_path(inc)

    files = {}

    def add(path):
        path = Path(path)
        if path.is_file():
            files.setdefault(str(path.resolve()), path)
        elif path.is_dir():
            for sub in sorted(path.rglob("test.th")):
                if _is_skipped_dir(sub, path):
                    continue
                if sub.is_file():
                    files.setdefault(str(sub.resolve()), sub)

    if targets:
        for t in targets:
            add(t)
    else:
        add(project_root(cwd))
        for search in importer.search_paths:
            add(search)
    return list(files.values())


def run_one_test_file(path, include_paths, inline_threshold, debug_mode, flag_inf, test_filter=None):
    """Compile and run a single ``test.th``.

    Returns ``(returncode, stdout, stderr)`` on success, or
    ``(None, "", error_text)`` if it could not be compiled.
    """
    if test_filter:
        try:
            names = find_test_functions(path.read_text(errors="replace"))
        except OSError:
            names = []
        if not any(test_filter in n for n in names):
            return 0, "", f"(no tests match '{test_filter}')"
    importer = Importer()
    importer.add_search_path(path.parent)
    for inc in include_paths:
        importer.add_search_path(inc)
    try:
        llvm = compile_file(
            path,
            importer=importer,
            inline_threshold=inline_threshold,
            debug_mode=debug_mode,
            flag_inf=flag_inf,
            test_filter=test_filter,
        )
    except BaseException as e:
        return None, "", f"{type(e).__name__}: {e}"
    require_main(llvm)
    final = dedupe_decls(patch_llvm(llvm))
    mods = native_modules(importer)
    try:
        if mods:
            with tempfile.TemporaryDirectory() as td:
                libs = build_native_shared_libs(mods, output_dir=td)
                result = run_llvm(
                    final, capture=True, loads=libs,
                    library_dirs=native_library_dirs(mods),
                )
        else:
            result = run_llvm(final, capture=True)
    except SystemExit as e:
        return None, "", f"SystemExit: {e}"
    return result.returncode, result.stdout, result.stderr


def run_test_suite(targets, include_paths, cwd, inline_threshold, debug_mode, flag_inf, test_filter=None):
    """Run every discovered test suite, pytest-style, and return the exit code."""
    files = discover_test_files(targets, cwd, include_paths)
    if not files:
        print("no test.th files found", flush=True)
        return 1

    n_files = 0
    n_skipped = 0
    n_failed = 0
    for path in files:
        n_files += 1
        print(f"===== {path} =====", flush=True)
        rc, stdout, stderr = run_one_test_file(
            path, include_paths, inline_threshold, debug_mode, flag_inf,
            test_filter=test_filter,
        )
        if stderr.startswith("(no tests match"):
            n_skipped += 1
            print(stderr, flush=True)
            continue
        if rc is None:
            print(f"COLLECTION ERROR: {path}", flush=True)
            if stderr:
                print(stderr, flush=True)
            n_failed += 1
            continue
        if stdout:
            sys.stdout.write(stdout)
            sys.stdout.flush()
        if stderr:
            sys.stderr.write(stderr)
        if rc != 0:
            n_failed += 1
    print(flush=True)
    print(f"{n_files} test file(s), {n_failed} failed", flush=True)
    if test_filter and n_files == n_skipped:
        print(f"note: no test_* function matched '{test_filter}'", flush=True)
    return 1 if n_failed else 0


PROJECT_COMMANDS = {
    "init", "add", "build", "run", "test", "clean", "cache",
}


def _add_project_compile_args(parser):
    parser.add_argument("file", metavar="FILE.th", nargs="*")
    parser.add_argument("-o", "--output", metavar="FILE")
    parser.add_argument("--exe", metavar="FILE")
    parser.add_argument("-I", "--include", action="append", default=[], metavar="DIR")
    parser.add_argument("-O", "--inline-threshold", type=int, default=0, metavar="N")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--flag-inf", action="store_true")
    parser.add_argument("-k", "--test-name", metavar="PATTERN")


def _project_command_parser(command):
    parser = argparse.ArgumentParser(
        prog=f"threadon {command}",
        description=f"Threadon project command: {command}",
    )
    if command == "init":
        parser.add_argument("name", nargs="?", help="project name (default: directory name)")
        parser.add_argument("--force", action="store_true", help="overwrite threadon.toml")
        parser.add_argument("--dir", default=".", metavar="DIR", help="parent directory for the new project")
        parser.add_argument("--here", action="store_true", help="initialize in the current directory instead of a NAME/ subdirectory")
    elif command == "add":
        parser.add_argument("name", help="dependency name")
        parser.add_argument("path", help="local directory containing the dependency")
    elif command in ("build", "run"):
        _add_project_compile_args(parser)
    elif command == "test":
        parser.add_argument("file", metavar="FILE.th", nargs="*")
        parser.add_argument("-I", "--include", action="append", default=[], metavar="DIR")
        parser.add_argument("-O", "--inline-threshold", type=int, default=0, metavar="N")
        parser.add_argument("-k", "--test-name", metavar="PATTERN")
        parser.add_argument("--debug", action="store_true")
        parser.add_argument("--flag-inf", action="store_true")
    elif command == "clean":
        parser.add_argument("--modules", action="store_true", help="also clear the user module cache")
    elif command == "cache":
        parser.add_argument("action", choices=("path", "list", "clear"))
    else:  # pragma: no cover - guarded by PROJECT_COMMANDS
        parser.error(f"unknown project command '{command}'")
    return parser


def _report_project_failure(exc):
    if getattr(exc, "printed", False):
        return 1
    message = str(exc)
    if message.startswith("compiler error:\n"):
        message = message[len("compiler error:\n"):]
    if not message.strip():
        message = str(exc.__cause__ or exc)
    report_error(message, file=sys.stderr)
    return 1


def _project_context(cwd, extra_includes=None):
    config = project.load_project(cwd, required=True)
    includes = project.importer_paths(config, [Path(p) for p in (extra_includes or [])])
    return config, includes


def _project_compile_options(source, args, test_filter=None):
    return {
        "source": str(Path(source).resolve()),
        "inline_threshold": args.inline_threshold,
        "debug": args.debug,
        "flag_inf": args.flag_inf,
        "test_filter": test_filter,
    }


def _project_importer(config, includes):
    importer = Importer()
    project.apply_to_importer(config, importer, includes)
    return importer


def _compile_project_source(config, source, includes, options, test_filter=None):
    """Compile (or reuse cached) LLVM IR for a project source file."""
    key = project.compile_key([source, *includes], options)
    cached_llvm = project.load_compile_cache(config.root, config.name, key)
    importer = _project_importer(config, includes)
    if cached_llvm is not None:
        return cached_llvm, importer, True

    llvm = compile_file(
        source,
        importer=importer,
        inline_threshold=options.get("inline_threshold", 0),
        debug_mode=options.get("debug", False),
        flag_inf=options.get("flag_inf", False),
        test_filter=test_filter,
    )
    mods = native_modules(importer)
    if mods:
        # Native modules are built outside the IR cache; stale IR must not be
        # reused when a project switches to (or away from) native modules.
        llvm_path, meta_path = project.compile_cache_files(config.root, config.name)
        for path in (llvm_path, meta_path):
            if path.exists():
                path.unlink()
    else:
        project.save_compile_cache(config.root, config.name, key, llvm)
    return llvm, importer, False


def _run_project_llvm(llvm, importer, from_cache):
    require_main(llvm)
    final = dedupe_decls(patch_llvm(llvm))
    mods = [] if from_cache else native_modules(importer)
    if mods:
        with tempfile.TemporaryDirectory() as td:
            libs = build_native_shared_libs(mods, output_dir=td)
            result = run_llvm(
                final, loads=libs, library_dirs=native_library_dirs(mods)
            )
    else:
        result = run_llvm(final)
    return result.returncode


def _project_main(argv):
    """Dispatch ``threadon <project-command>`` before the compiler CLI."""
    command = argv[0]
    args = _project_command_parser(command).parse_args(argv[1:])

    try:
        if command == "init":
            # ``init NAME`` creates ./NAME so that the documented
            # ``python -m threadon init myapp && cd myapp`` flow works.
            # ``--here`` keeps the older in-place behaviour available.
            parent = Path(args.dir).expanduser().resolve()
            root = parent / args.name if args.name and not args.here else parent
            config = project.init_project(root, args.name, force=args.force)
            print(f"initialized {config.name} in {config.root}")
            print(f"config: {config.root / project.CONFIG_FILENAME}")
            return 0

        if command == "add":
            config = project.load_project(Path.cwd(), required=True)
            config, cached = project.add_dependency(config, args.name, Path(args.path))
            print(f"added dependency {args.name} -> {config.dependencies[args.name]}")
            print(f"cached at {cached}")
            return 0

        if command in ("build", "run"):
            config, includes = _project_context(Path.cwd(), args.include)
            source = Path(args.file[0]).resolve() if args.file else config.main_path
            if not source.is_file():
                raise project.ProjectError(f"source file not found: {source}")
            options = _project_compile_options(source, args, args.test_name)
            llvm, importer, from_cache = _compile_project_source(
                config, source, includes, options, test_filter=args.test_name
            )
            cache_path, _ = project.compile_cache_files(config.root, config.name)

            if command == "run":
                return _run_project_llvm(llvm, importer, from_cache)

            if args.output:
                Path(args.output).write_text(llvm)
                print(f"wrote {args.output}")
            if from_cache:
                print(f"cached {cache_path}")
            elif native_modules(importer):
                print(f"built {source} (native modules, IR cache skipped)")
            else:
                print(f"built {cache_path}")
            if args.exe:
                require_main(llvm)
                final = dedupe_decls(patch_llvm(llvm))
                build_executable(
                    final, args.exe,
                    native=[] if from_cache else native_modules(importer),
                )
                print(f"executable: {args.exe}")
            return 0

        if command == "test":
            config, includes = _project_context(Path.cwd(), args.include)
            targets = [Path(f) for f in args.file] or config.test_paths
            return run_test_suite(
                targets, includes, Path.cwd(), args.inline_threshold,
                args.debug, args.flag_inf, test_filter=args.test_name,
            )

        if command == "clean":
            config = project.load_project(Path.cwd(), required=True)
            removed = project.clear_compile_cache(config.root)
            base = project.build_cache_dir(config.root)
            print(f"cleaned {base}" if removed else f"nothing to clean in {base}")
            if args.modules:
                module_removed = project.clear_module_cache()
                module_base = project.module_cache_dir()
                print(
                    f"cleaned {module_base}" if module_removed
                    else f"nothing to clean in {module_base}"
                )
            return 0

        if command == "cache":
            if args.action == "path":
                print(project.module_cache_dir())
            elif args.action == "list":
                entries = project.list_cached_modules()
                if not entries:
                    print("(empty)")
                else:
                    for entry in entries:
                        print(f"{entry['name']} {entry.get('source', '')}")
            else:
                removed = project.clear_module_cache()
                base = project.module_cache_dir()
                print(f"cleaned {base}" if removed else f"nothing to clean in {base}")
            return 0
    except Exception as exc:
        return _report_project_failure(exc)

    return 1  # pragma: no cover - all commands are handled above


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in PROJECT_COMMANDS:
        return _project_main(argv)

    parser = argparse.ArgumentParser(
        prog="threadon",
        description="Compile a Threadon (.th) file (with its imports) to LLVM IR.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "project commands:\n"
            "  init NAME       create a new project in ./NAME\n"
            "  add NAME PATH   add a local dependency\n"
            "  build | run     compile / compile and run the project\n"
            "  test            run the project's test.th suites\n"
            "  clean           remove compile caches (--modules for module cache)\n"
            "  cache           path | list | clear the module cache\n\n"
            "Use 'threadon <command> --help' for command-specific options."
        ),
    )
    parser.add_argument("file", metavar="FILE.th", nargs="*", help="the Threadon source file (or one or more test files/dirs with --run-tests)")
    parser.add_argument(
        "-o", "--output", metavar="FILE", help="write LLVM IR to FILE (default: stdout)"
    )
    parser.add_argument(
        "--run", action="store_true", help="execute the module with lli after compiling"
    )
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="build and run every test.th suite (project root, -I paths and "
        "stdlib; optionally a specific FILE or DIR)",
    )
    parser.add_argument(
        "-k",
        "--test-name",
        metavar="PATTERN",
        help="with --run-tests/--run on a test.th: only run test_* functions "
        "whose name contains PATTERN",
    )
    parser.add_argument(
        "--exe",
        metavar="FILE",
        help="build a native executable to FILE (via llc + gcc)",
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

    try:
        config = project.load_project(Path.cwd(), required=False)
    except Exception as exc:
        return _report_project_failure(exc)

    if config is not None:
        includes = project.importer_paths(config, [Path(p) for p in args.include])
    else:
        includes = list(args.include)

    if args.run_tests:
        targets = [Path(f) for f in args.file]
        if not targets and config is not None:
            targets = config.test_paths
        return run_test_suite(
            targets, includes, Path.cwd(),
            args.inline_threshold, args.debug, args.flag_inf,
            test_filter=args.test_name,
        )

    if not args.file:
        parser.error("FILE.th is required (or use --run-tests)")
    if len(args.file) > 1:
        parser.error("only one FILE.th may be compiled (use --run-tests for multiple)")

    path = Path(args.file[0])
    if not path.is_file():
        parser.error(f"file not found: {path}")

    try:
        source_config = project.load_project(path.parent, required=False)
    except Exception as exc:
        return _report_project_failure(exc)
    config = source_config
    if config is not None:
        includes = project.importer_paths(
            config, [Path(p) for p in args.include]
        )
    else:
        includes = list(args.include)

    importer = Importer()
    if config is not None:
        project.apply_to_importer(config, importer, includes)
    else:
        for include in includes:
            importer.add_search_path(include)
    importer.add_search_path(path.parent)

    try:
        llvm = compile_file(
            path,
            importer=importer,
            inline_threshold=args.inline_threshold,
            debug_mode=args.debug,
            flag_inf=args.flag_inf,
            test_filter=args.test_name,
        )
    except Exception as e:
        if getattr(e, "printed", False):
            return 1
        msg = str(e)
        if msg.startswith("compiler error:\n"):
            msg = msg[len("compiler error:\n"):]
        if not msg.strip():
            msg = str(e.__cause__ or e)
        report_error(msg, file=sys.stderr)
        return 1

    if args.output:
        Path(args.output).write_text(llvm)

    if args.run:
        require_main(llvm)
        final = dedupe_decls(patch_llvm(llvm))
        mods = native_modules(importer)
        if mods:
            with tempfile.TemporaryDirectory() as td:
                libs = build_native_shared_libs(mods, output_dir=td)
                result = run_llvm(final, loads=libs, library_dirs=native_library_dirs(mods))
        else:
            result = run_llvm(final)
        sys.exit(result.returncode)

    if args.exe:
        require_main(llvm)
        final = dedupe_decls(patch_llvm(llvm))
        build_executable(final, args.exe, native=native_modules(importer))
        return 0

    if not args.output:
        sys.stdout.write(llvm)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
