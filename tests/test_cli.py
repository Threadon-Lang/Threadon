"""Unit tests for the command-line driver (no real lli/llc/gcc needed)."""
import argparse
import ctypes.util
import io
import os
import subprocess
import sys
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from types import SimpleNamespace

import pytest

from compiler.threadon import __main__ as cli
from compiler.threadon.importer import Importer


class FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def make_mod(name="m", *, native=False, toolchain=None, source=None,
             manifest_dir=None, links=None, flags=None, extra_sources=None):
    return SimpleNamespace(
        name=name,
        is_native=native,
        toolchain=toolchain,
        native_source=source,
        manifest_dir=manifest_dir,
        links=links,
        flags=flags,
        extra_sources=extra_sources,
    )


def fake_toolchain(name="c", cxx=False):
    return SimpleNamespace(
        name=name,
        compiler="gcc",
        shared_args=["-shared", "-fPIC"],
        object_args=["-c"],
        object_ext="o",
        cxx=cxx,
    )


# --- small helpers ---------------------------------------------------------

def test_python_includes_and_link_flags(monkeypatch):
    monkeypatch.setattr(cli.sysconfig, "get_paths", lambda: {"include": ""})
    assert cli._python_includes() == []
    monkeypatch.setattr(cli.sysconfig, "get_paths", lambda: {"include": "/py/include"})
    assert cli._python_includes() == ["-I/py/include"]


@pytest.mark.parametrize("embed_ok,plain_ok,expected", [
    (True, True, ["-lembed"]),
    (False, True, ["-lplain"]),
    (False, False, []),
])
def test_python_link_flags_fallbacks(monkeypatch, embed_ok, plain_ok, expected):
    seen = []

    def fake_check_output(cmd, **kwargs):
        seen.append(cmd)
        if cmd[1] == "--embed":
            if embed_ok:
                return "-lembed"
            raise subprocess.CalledProcessError(1, cmd)
        if plain_ok:
            return "-lplain"
        raise FileNotFoundError

    monkeypatch.setattr(cli.subprocess, "check_output", fake_check_output)
    # The module defines _python_link_flags twice; the second definition wins.
    assert cli._python_link_flags() == expected
    assert seen[0] == ["python3-config", "--embed", "--ldflags"]


def test_require_main_and_patch_llvm_and_dedupe():
    with pytest.raises(SystemExit, match="no function 'main' found"):
        cli.require_main("define i32 @helper() { ret i32 0 }")
    cli.require_main("define i32 @main() { ret i32 0 }")
    assert "define i32 @llvm.pow.i32" in cli.patch_llvm(
        "declare i32 @llvm.pow.i32(i32, i32) #1\n"
    )
    deduped = cli.dedupe_decls(
        "declare i32 @printf(i8*, ...)\n"
        "declare i32 @printf(i8*)\n"
        "define i32 @main() {\n  ret i32 0\n}\n"
    )
    assert deduped.count("declare i32 @printf") == 1
    assert "@main" in deduped
    assert cli.dedupe_decls("") == ""


def test_run_llvm_builds_command_and_sets_env(monkeypatch):
    calls = []
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return FakeCompleted(returncode=3)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    monkeypatch.setattr(cli.os, "environ", {"PATH": "/bin", "LD_LIBRARY_PATH": "/old"})
    result = cli.run_llvm(
        "ir", capture=True, loads=["/tmp/a.so"], library_dirs=["/lib1", "$HOME/lib"]
    )
    assert result.returncode == 3
    cmd, kwargs = calls[0]
    assert cmd[:5] == ["lli", "-O2", "-load", "/tmp/a.so", "-load"]
    assert cmd[-1].endswith(".ll")
    assert kwargs["capture_output"] is True and kwargs["text"] is True
    env = kwargs["env"]
    assert env["LD_LIBRARY_PATH"].startswith("/lib1:$HOME/lib:/old")
    assert not Path(cmd[-1]).exists()  # cleaned up in finally


def test_run_llvm_without_capture_and_no_libs(monkeypatch):
    calls = []
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return FakeCompleted()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    monkeypatch.setattr(cli.os, "environ", {"PATH": "/bin"})
    monkeypatch.setattr(ctypes.util, "find_library", lambda name: None)
    cli.run_llvm("ir", loads=None, library_dirs=None)
    cmd, kwargs = calls[0]
    assert cmd[0] == "lli"
    assert "-load" not in cmd
    assert "capture_output" not in kwargs
    assert "LD_LIBRARY_PATH" not in kwargs["env"]


def test_native_helpers(monkeypatch, tmp_path):
    mods = [make_mod(links=["-L/opt/lib", "-L$HOME/x", "-lm"])]
    assert cli.native_library_dirs(mods) == ["/opt/lib", os.path.expandvars("$HOME/x")]

    importer = Importer()
    importer.cache["plain"] = make_mod("plain")
    importer.cache["native"] = make_mod("native", native=True)
    assert [m.name for m in cli.native_modules(importer)] == ["native"]


def test_build_native_shared_libs_uses_existing_and_compiles(monkeypatch, tmp_path):
    existing_mod = make_mod(
        "existing", toolchain=fake_toolchain(), source=tmp_path / "x.c",
        manifest_dir=tmp_path,
    )
    (tmp_path / "x.c").write_text("//")
    (tmp_path / "existing.so").write_bytes(b"so")
    src = tmp_path / "new.c"
    src.write_text("int x;")
    new_mod = make_mod(
        "new", toolchain=fake_toolchain(), source=src,
        manifest_dir=tmp_path, flags=["-O2"], extra_sources=[tmp_path / "extra.c"],
    )
    calls = []
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd, **kw: (
        calls.append(cmd) or FakeCompleted()
    ))
    monkeypatch.setattr(cli, "_python_includes", lambda: [])
    monkeypatch.setattr(cli, "_python_link_flags", lambda: [])
    libs = cli.build_native_shared_libs([existing_mod, new_mod], output_dir=tmp_path)
    assert libs[0] == tmp_path / "existing.so"
    assert libs[1] == tmp_path / "libnew.so"
    assert calls[0][0] == "gcc"
    assert "-O2" in calls[0]
    assert str(src) in calls[0]


def test_build_native_shared_libs_python_and_errors(monkeypatch, tmp_path):
    src = tmp_path / "py.cpp"
    src.write_text("//")
    mod = make_mod("py", toolchain=fake_toolchain("python", cxx=True), source=src,
                   manifest_dir=tmp_path)
    calls = []
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd, **kw: (
        calls.append(cmd) or FakeCompleted()
    ))
    monkeypatch.setattr(cli, "_python_includes", lambda: ["-I/py"])
    monkeypatch.setattr(cli, "_python_link_flags", lambda: ["-lpython3.13"])
    cli.build_native_shared_libs([mod], output_dir=tmp_path)
    cmd = calls[0]
    assert "-I/py" in cmd and "-lpython3.13" in cmd

    with pytest.raises(SystemExit, match="no registered toolchain"):
        cli.build_native_shared_libs([make_mod("x")], output_dir=tmp_path)
    with pytest.raises(SystemExit, match="has no source file"):
        cli.build_native_shared_libs(
            [make_mod("x", toolchain=fake_toolchain())], output_dir=tmp_path
        )

    monkeypatch.setattr(cli.subprocess, "run", lambda cmd, **kw: FakeCompleted(
        returncode=1, stderr="boom"
    ))
    with pytest.raises(SystemExit, match="gcc failed compiling"):
        cli.build_native_shared_libs(
            [make_mod("x", toolchain=fake_toolchain(), source=src,
                      manifest_dir=tmp_path)],
            output_dir=tmp_path,
        )


def test_build_executable_full_path(monkeypatch, tmp_path):
    src = tmp_path / "native.cpp"
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    src.write_text("//")
    native = make_mod(
        "native", toolchain=fake_toolchain("cpp", cxx=True), source=src,
        manifest_dir=tmp_path, links=["m"], flags=["-std=c++17"],
    )
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return FakeCompleted()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    monkeypatch.setattr(cli, "_python_includes", lambda: [])
    monkeypatch.setattr(cli, "_python_link_flags", lambda: [])
    out = tmp_path / "prog"
    cli.build_executable("ir", out, native=[native])
    assert calls[0][0] == "llc"
    assert calls[1][0] == "gcc"  # toolchain compiler builds the object
    assert calls[-1][0] == "g++"  # cxx toolchain switches linker
    assert "-lm" in calls[-1] and "-lnative" not in calls[-1]  # links -> -lm
    assert "-std=c++17" in calls[1]


def test_build_executable_errors(monkeypatch, tmp_path):
    def failing(cmd, **kw):
        return FakeCompleted(returncode=1, stderr="fail")

    monkeypatch.setattr(cli.subprocess, "run", failing)
    with pytest.raises(SystemExit, match="llc failed"):
        cli.build_executable("ir", tmp_path / "p")

    calls = [0]

    def llc_ok(cmd, **kw):
        calls[0] += 1
        return FakeCompleted()

    monkeypatch.setattr(cli, "_python_includes", lambda: [])
    monkeypatch.setattr(cli, "_python_link_flags", lambda: [])
    monkeypatch.setattr(cli.subprocess, "run", llc_ok)
    with pytest.raises(SystemExit, match="no registered toolchain"):
        cli.build_executable("ir", tmp_path / "p", native=[make_mod("x")])
    with pytest.raises(SystemExit, match="has no source file"):
        cli.build_executable(
            "ir", tmp_path / "p", native=[
                make_mod("x", toolchain=fake_toolchain(), links=[])
            ]
        )

    src = tmp_path / "x.c"
    src.write_text("//")
    mod = make_mod("x", toolchain=fake_toolchain(), source=src, manifest_dir=tmp_path,
                   links=[])
    def fail_native_compile(cmd, **kw):
        calls[0] += 1
        if cmd[0] == "gcc" and "-c" in cmd:
            return FakeCompleted(returncode=1, stderr="bad")
        return FakeCompleted()

    monkeypatch.setattr(cli.subprocess, "run", fail_native_compile)
    with pytest.raises(SystemExit, match="gcc failed compiling"):
        cli.build_executable("ir", tmp_path / "p", native=[mod])

    calls[0] = 1

    def fail_link(cmd, **kw):
        calls[0] += 1
        if cmd[0] == "gcc" and "-no-pie" in cmd:
            return FakeCompleted(returncode=1, stderr="link")
        return FakeCompleted()

    monkeypatch.setattr(cli.subprocess, "run", fail_link)
    with pytest.raises(SystemExit, match="gcc failed"):
        cli.build_executable("ir", tmp_path / "p")


def test_is_skipped_dir_and_project_root(tmp_path):
    inside = tmp_path / "node_modules" / "test.th"
    assert cli._is_skipped_dir(inside, tmp_path) is True
    assert cli._is_skipped_dir(tmp_path / "test.th", tmp_path) is False
    assert cli._is_skipped_dir(tmp_path.parent / "x" / "test.th", tmp_path) is False

    (tmp_path / "pyproject.toml").write_text("")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert cli.project_root(nested) == tmp_path
    assert cli.project_root(tmp_path.parent) == tmp_path.parent
    monkeypatch_home = Path.home()
    assert cli.project_root(monkeypatch_home) == monkeypatch_home


def test_discover_test_files(tmp_path):
    kept = tmp_path / "proj" / "test.th"
    kept.parent.mkdir()
    kept.write_text("")
    skipped = tmp_path / "proj" / "venv" / "test.th"
    skipped.parent.mkdir()
    skipped.write_text("")
    other = tmp_path / "inc" / "test.th"
    other.parent.mkdir()
    other.write_text("")
    assert cli.discover_test_files([kept], tmp_path, []) == [kept]
    found = cli.discover_test_files([], tmp_path / "proj", [tmp_path / "inc"])
    assert kept in found and other in found and skipped not in found


def test_run_one_test_file_filter_compile_and_run(monkeypatch, tmp_path):
    path = tmp_path / "test.th"
    path.write_text("def test_foo():\n    pass\n")
    monkeypatch.setattr(cli, "compile_file", lambda *a, **kw: "define i32 @main() {}")
    run = []

    def fake_run_llvm(llvm, **kwargs):
        run.append(kwargs)
        return FakeCompleted(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(cli, "run_llvm", fake_run_llvm)
    rc, out, err = cli.run_one_test_file(path, [], 0, False, False, test_filter="missing")
    assert (rc, out, err) == (0, "", "(no tests match 'missing')")
    assert not run
    rc, out, err = cli.run_one_test_file(path, [], 0, False, False, test_filter="foo")
    assert (rc, out, err) == (0, "ok", "")
    assert run[0]["capture"] is True

    monkeypatch.setattr(cli, "compile_file", lambda *a, **kw: (_ for _ in ()).throw(
        ValueError("bad")
    ))
    rc, out, err = cli.run_one_test_file(path, [], 0, False, False)
    assert rc is None and "ValueError: bad" == err

    monkeypatch.setattr(cli, "require_main", cli.require_main)
    monkeypatch.setattr(cli, "compile_file", lambda *a, **kw: "no main here")
    with pytest.raises(SystemExit, match="no function 'main'"):
        cli.run_one_test_file(path, [], 0, False, False)


def test_run_one_test_file_unreadable_filter_and_includes(monkeypatch, tmp_path):
    """An unreadable source still proceeds to compilation with no name filter."""
    path = tmp_path / "test.th"
    path.mkdir()  # read_text raises IsADirectoryError (an OSError)
    seen = []
    monkeypatch.setattr(cli, "compile_file", lambda *a, **kw: "define i32 @main() {}")
    monkeypatch.setattr(cli, "run_llvm", lambda llvm, **kw: (
        seen.append(kw) or FakeCompleted(returncode=0)
    ))
    rc, _, err = cli.run_one_test_file(path, [], 0, False, False,
                                       test_filter="test_x")
    assert rc == 0 and err == "(no tests match 'test_x')"
    assert not seen

    readable = tmp_path / "real.th"
    readable.write_text("def test_x():\n    return 1\n")
    rc, _, _ = cli.run_one_test_file(readable, [str(tmp_path)], 0, False, False,
                                     test_filter="test_x")
    assert rc == 0
    assert seen


def test_module_entry_point(monkeypatch, tmp_path):
    """The `if __name__ == '__main__'` guard exits with main()'s result."""
    source = (Path(cli.__file__).read_text()
              .replace("\n    raise SystemExit(main())\n", "\n    raise SystemExit(record())\n"))
    namespace = dict(vars(cli))
    namespace["__name__"] = "__main__"
    called = []
    namespace["record"] = lambda: called.append(True) or 3
    with pytest.raises(SystemExit) as excinfo:
        exec(compile(source, cli.__file__, "exec"), namespace)
    assert excinfo.value.code == 3
    assert called == [True]


def test_run_one_test_file_native_and_systemexit(monkeypatch, tmp_path):
    path = tmp_path / "test.th"
    path.write_text("//")
    monkeypatch.setattr(cli, "compile_file", lambda *a, **kw: "define i32 @main() {}")
    monkeypatch.setattr(cli, "native_modules", lambda importer: [make_mod("native")])
    monkeypatch.setattr(cli, "build_native_shared_libs", lambda mods, output_dir: [
        tmp_path / "native.so"
    ])
    monkeypatch.setattr(cli, "native_library_dirs", lambda mods: ["/lib"])
    seen = []

    def fake_run_llvm(llvm, **kwargs):
        seen.append(kwargs)
        return FakeCompleted(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(cli, "run_llvm", fake_run_llvm)
    assert cli.run_one_test_file(path, [], 0, False, False)[0] == 0
    assert seen[0]["loads"] == [tmp_path / "native.so"]
    assert seen[0]["library_dirs"] == ["/lib"]

    def bad_build(mods, output_dir):
        raise SystemExit("compile failed")

    monkeypatch.setattr(cli, "build_native_shared_libs", bad_build)
    rc, out, err = cli.run_one_test_file(path, [], 0, False, False)
    assert rc is None and err == "SystemExit: compile failed"


def test_run_test_suite_branches(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "discover_test_files", lambda *a: [])
    assert cli.run_test_suite([], [], tmp_path, 0, False, False) == 1
    assert "no test.th files found" in capsys.readouterr().out

    monkeypatch.setattr(cli, "discover_test_files", lambda *a: [
        tmp_path / "a.th", tmp_path / "b.th", tmp_path / "c.th"
    ])
    results = [
        (0, "out", ""),
        (None, "", "collection error"),
        (1, "bad", "err"),
    ]
    monkeypatch.setattr(cli, "run_one_test_file", lambda *a, **kw: results.pop(0))
    rc = cli.run_test_suite([], [], tmp_path, 0, False, False)
    out = capsys.readouterr().out
    assert rc == 1
    assert "COLLECTION ERROR" in out
    assert "3 test file(s), 2 failed" in out
    assert "out" in out

    monkeypatch.setattr(cli, "discover_test_files", lambda *a: [tmp_path / "a.th"])
    monkeypatch.setattr(cli, "run_one_test_file", lambda *a, **kw: (
        0, "", "(no tests match 'x')"
    ))
    rc = cli.run_test_suite([], [], tmp_path, 0, False, False, test_filter="x")
    out = capsys.readouterr().out
    assert rc == 0
    assert "note: no test_* function matched 'x'" in out


# --- main() argument handling ---------------------------------------------

def write_source(tmp_path):
    source = tmp_path / "main.th"
    source.write_text("def main() -> NoneType:\n    return\n")
    return source


def test_main_compile_output_and_stdout(monkeypatch, tmp_path, capsys):
    source = write_source(tmp_path)
    monkeypatch.setattr(cli, "compile_file", lambda *a, **kw: "ir-text")
    assert cli.main([str(source)]) == 0
    assert capsys.readouterr().out == "ir-text"

    out = tmp_path / "out.ll"
    assert cli.main(["-o", str(out), "-I", str(tmp_path), "-O", "3",
                     "--debug", "--flag-inf", str(source)]) == 0
    assert out.read_text() == "ir-text"
    assert capsys.readouterr().out == ""


def test_main_argument_validation(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "compile_file", lambda *a, **kw: "ir")
    with pytest.raises(SystemExit):
        with redirect_stderr(io.StringIO()) as err:
            cli.main([])
    assert "FILE.th is required" in err.getvalue()
    with pytest.raises(SystemExit):
        with redirect_stderr(io.StringIO()) as err:
            cli.main(["a.th", "b.th"])
    assert "only one FILE.th" in err.getvalue()
    with pytest.raises(SystemExit):
        with redirect_stderr(io.StringIO()) as err:
            cli.main(["missing.th"])
    assert "file not found" in err.getvalue()


def test_main_run_and_exe_with_native(monkeypatch, tmp_path):
    source = write_source(tmp_path)
    monkeypatch.setattr(cli, "compile_file", lambda *a, **kw: "ir")
    monkeypatch.setattr(cli, "require_main", lambda llvm: None)
    seen = []

    def fake_run_llvm(llvm, **kwargs):
        seen.append(kwargs)
        return FakeCompleted(returncode=0)

    monkeypatch.setattr(cli, "run_llvm", fake_run_llvm)
    monkeypatch.setattr(cli, "native_modules", lambda importer: [make_mod("native")])
    monkeypatch.setattr(cli, "build_native_shared_libs", lambda mods, output_dir: [
        tmp_path / "native.so"
    ])
    monkeypatch.setattr(cli, "native_library_dirs", lambda mods: ["/lib"])
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--run", str(source)])
    assert excinfo.value.code == 0
    assert seen[0]["loads"] == [tmp_path / "native.so"]

    monkeypatch.setattr(cli, "native_modules", lambda importer: [])
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--run", str(source)])
    assert excinfo.value.code == 0

    built = []
    monkeypatch.setattr(cli, "build_executable", lambda *a, **kw: built.append((a, kw)))
    assert cli.main(["--exe", "prog", str(source)]) == 0
    assert built[0][0][1] == "prog"


def test_main_run_tests_delegates(monkeypatch, tmp_path):
    called = []

    def fake_suite(targets, includes, cwd, inline, debug, flag_inf, test_filter=None):
        called.append((targets, includes, cwd, inline, debug, flag_inf, test_filter))
        return 7

    monkeypatch.setattr(cli, "run_test_suite", fake_suite)
    assert cli.main(["--run-tests", "-k", "foo", "-I", "inc", "-O", "2",
                     "--debug", "--flag-inf", str(tmp_path)]) == 7
    args = called[0]
    assert args[0] == [tmp_path]
    assert args[1] == ["inc"]
    assert args[3:] == (2, True, True, "foo")
