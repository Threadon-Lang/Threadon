"""Regression tests for compiler, CLI and tooling bugs fixed in Threadon.

Each test names a concrete failure mode that used to produce invalid IR,
silent misbehaviour or a poor command-line experience.
"""
import itertools
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from compiler.threadon import __main__ as cli
from compiler.threadon import errors as error_module
from compiler.threadon.checker import CombinedChecker, UnreachableChecker
from compiler.threadon.compiler import compile_source
from compiler.threadon.importer import Importer
from compiler.threadon.optimalise_ir import IROptimizer
from compiler.threadon.parser import Parser
from compiler.threadon.to_high_ir import (
    IRBlock,
    IRFunction,
    IRInstr,
    SSAValue,
    SSABuilder,
)
from compiler.threadon.to_llvm_ir import LLVMIRCompiler

ROOT = Path(__file__).resolve().parents[1]

_counter = itertools.count()


def new_value(type_="Int32"):
    return SSAValue(f"%reg{next(_counter)}", type_)


def const(value, type_="Int32"):
    return IRInstr("const", [value], result=new_value(type_))


def instr(op, args, type_="Int32"):
    return IRInstr(op, list(args), result=new_value(type_))


def block(label, instructions=(), terminator=None):
    result = IRBlock(label)
    for item in instructions:
        result.add_instr(item)
    if terminator is not None:
        result.set_terminator(terminator)
    return result


def function(*blocks, name="f", return_type="Int32"):
    result = IRFunction(name, [], return_type)
    for item in blocks:
        result.add_block(item)
    return result


def compile_ir(source, **kwargs):
    return compile_source(source, importer=Importer(), **kwargs)


def build_module(source):
    ast = Parser().parse(source)
    CombinedChecker().run_all(ast)
    return SSABuilder().build_from_ast(ast)


def entry_ops(module):
    return [i.op for i in module.funcs[0].blocks[0].instructions]


# --- list.pop() on an empty list --------------------------------------------

POP_SOURCE = """\
def main() -> Int32
    xs: List[Int32] = []
    xs.pop()
    return 0
"""


@pytest.mark.parametrize("debug_mode", [False, True])
def test_pop_on_empty_list_is_checked_in_every_build(debug_mode):
    ir = compile_ir(POP_SOURCE, debug_mode=debug_mode)
    assert "@__threadon_debug_error" in ir
    oob_line = next(line for line in ir.splitlines() if "_oobc = icmp eq i64" in line)
    assert ", 0" in oob_line
    branch = next(line for line in ir.splitlines() if "br i1" in line and "_oobc" in line)
    assert "_oob" in branch and "_ok" in branch


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("lli") is None, reason="lli not available")
def test_pop_on_empty_list_exits_with_runtime_error():
    from compile_test import run_llvm

    result = run_llvm(compile_ir(POP_SOURCE))
    assert result.returncode == 1
    assert "pop on empty list" in result.stderr


# --- thread handle table ----------------------------------------------------

THREAD_SOURCE = """\
counter: Int8 = 0
thread T() on True:
    counter += 1
def main() -> Int32
    return 0
"""


def test_thread_registration_checks_the_fixed_handle_table_size():
    ir = compile_ir(THREAD_SOURCE)
    assert "@__threadon_thread_handles = internal global [1024 x i64]" in ir
    assert "%full = icmp uge i64 %old, 1024" in ir
    assert "too_many_threads:" in ir
    lines = ir.splitlines()
    guard = next(i for i, line in enumerate(lines) if "icmp uge i64 %old" in line)
    store = next(i for i, line in enumerate(lines) if "%idx = getelementptr" in line and "%old" in line)
    assert guard < store


# --- release plan failures --------------------------------------------------

def test_release_plan_failure_is_reported_instead_of_being_swallowed(monkeypatch):
    def broken_plan(self, func):
        raise RuntimeError("broken ownership graph")

    monkeypatch.setattr(LLVMIRCompiler, "_compute_release_plan", broken_plan)
    with pytest.raises(SystemExit, match="internal error while computing the release plan"):
        compile_ir("def main() -> Int32\n    return 0\n")


# --- optimizer traps --------------------------------------------------------

def test_trapping_arithmetic_is_not_treated_as_pure():
    opt = IROptimizer()
    for op in ("div", "floordiv", "mod", "pow"):
        assert opt._is_pure(op) is False, op
    for op in ("add", "sub", "mul"):
        assert opt._is_pure(op) is True, op


def test_unused_division_is_not_dead_code():
    module = build_module(
        """\
def f(x: Int32) -> Int32
    y: Int32 = 8 // x
    return 7
"""
    )
    IROptimizer().optimize(module)
    assert "floordiv" in entry_ops(module)


def test_if_conversion_keeps_a_trapping_branch():
    module = build_module(
        """\
def f(x: Int32) -> Int32
    if x > 0:
        r: Int32 = 10 // x
    else:
        r: Int32 = 20
    return r
"""
    )
    IROptimizer().optimize(module)
    func = module.funcs[0]
    assert func.blocks[0].terminator.op == "cond_br"
    assert any(i.op == "floordiv" for b in func.blocks for i in b.instructions)


def test_bitwise_reassociation_folds_with_bitwise_operators():
    x = new_value("UInt32")
    three = const(3, "UInt32")
    four = const(4, "UInt32")
    inner = instr("bit_and", [x, three.result], "UInt32")
    outer = instr("bit_and", [inner.result, four.result], "UInt32")
    func = function(block("entry", [three, four, inner, outer], IRInstr("ret", [outer.result])))
    opt = IROptimizer()
    opt.func = func

    assert opt._reassociation() is True
    folded = opt._get_const_value(outer.args[1])
    assert folded == 0  # 3 & 4, not 3 * 4
    assert outer.args[1].type == "UInt32"  # result type, not operand type


# --- entry point and checker ------------------------------------------------

MAIN_WITH_PARAMS = """\
def main(x: Int32) -> Int32
    return x
"""


def test_main_with_parameters_is_rejected_by_checker_and_compiler():
    with pytest.raises(SystemExit, match="cannot take parameters"):
        CombinedChecker().run_all(Parser().parse(MAIN_WITH_PARAMS))
    with pytest.raises(Exception, match="cannot take parameters"):
        compile_ir(MAIN_WITH_PARAMS)


def test_unreachable_checker_handles_duplicate_statements():
    func = Parser().parse(
        """\
def f(x: Int32) -> Int32
    print("same")
    print("same")
    return 0
"""
    )[0]
    blocks = UnreachableChecker().build_cfg(func)
    entry = blocks[0]
    assert len(entry["stmts"]) == 3
    assert all(reachable for _, reachable in entry["stmts"])
    assert not any(block["name"] != "entry" for block in blocks)


def test_keyboard_interrupt_is_not_rewrapped_as_a_compiler_error(monkeypatch):
    importer = Importer()

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(importer, "load_main", interrupt)
    with pytest.raises(KeyboardInterrupt):
        compile_source("def main() -> Int32\n    return 0\n", importer=importer)


# --- CLI experience ---------------------------------------------------------

def test_help_lists_project_commands(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    for needle in ("project commands:", "init NAME", "add NAME PATH", "cache"):
        assert needle in out


def test_init_creates_a_project_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["init", "demo"]) == 0
    assert (tmp_path / "demo" / "threadon.toml").is_file()
    assert (tmp_path / "demo" / "src" / "main.th").is_file()

    here = tmp_path / "here"
    here.mkdir()
    monkeypatch.chdir(here)
    assert cli.main(["init", "local", "--here"]) == 0
    assert (here / "threadon.toml").is_file()


def test_missing_external_tool_gets_a_clean_diagnostic(monkeypatch):
    def missing(cmd, **kwargs):
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    monkeypatch.setattr(cli.subprocess, "run", missing)
    with pytest.raises(SystemExit, match="'lli' was not found"):
        cli.run_llvm("define i32 @main() { ret i32 0 }")
    with pytest.raises(SystemExit, match="'llc' was not found"):
        cli.build_executable("define i32 @main() { ret i32 0 }", "prog")


def test_build_executable_compiles_extra_native_sources(monkeypatch, tmp_path):
    source = tmp_path / "native.c"
    extra = tmp_path / "bridge.cpp"
    source.write_text("//")
    extra.write_text("//")
    toolchain = SimpleNamespace(
        name="c", compiler="gcc", object_args=["-c"], object_ext="o", cxx=False,
    )
    mod = SimpleNamespace(
        name="native", is_native=True, toolchain=toolchain, native_source=source,
        manifest_dir=tmp_path, links=[], flags=[], extra_sources=[extra],
    )
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    cli.build_executable("ir", tmp_path / "prog", native=[mod])
    compile_cmd = next(cmd for cmd in calls if "-c" in cmd)
    assert str(source) in compile_cmd
    assert str(extra) in compile_cmd


def test_native_shared_library_is_rebuilt_when_sources_change(monkeypatch, tmp_path):
    import os
    import time

    source = tmp_path / "m.c"
    source.write_text("int x;")
    cached = tmp_path / "m.so"
    cached.write_bytes(b"so")
    old = time.time() - 3600
    os.utime(cached, (old, old))
    toolchain = SimpleNamespace(
        name="c", compiler="gcc", shared_args=["-shared", "-fPIC"],
        object_args=["-c"], object_ext="o", cxx=False,
    )
    mod = SimpleNamespace(
        name="m", is_native=True, toolchain=toolchain, native_source=source,
        manifest_dir=tmp_path, links=[], flags=[], extra_sources=[],
    )
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    libs = cli.build_native_shared_libs([mod], output_dir=tmp_path)
    assert calls, "a stale .so must be rebuilt"
    assert libs[0] == tmp_path / "libm.so"

    os.utime(source, (old, old))
    calls.clear()
    libs = cli.build_native_shared_libs([mod], output_dir=tmp_path)
    assert calls == [], "an up-to-date .so must be reused"
    assert libs[0] == cached


def test_no_color_is_honoured_and_colors_default_to_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    stderr = SimpleNamespace(isatty=lambda: False)
    monkeypatch.setattr(error_module.sys, "stderr", stderr)
    assert error_module.use_color() is False

    stderr.isatty = lambda: True
    assert error_module.use_color() is True

    monkeypatch.setenv("NO_COLOR", "1")
    assert error_module.use_color() is False

    monkeypatch.delenv("NO_COLOR")
    monkeypatch.setenv("FORCE_COLOR", "1")
    stderr.isatty = lambda: False
    assert error_module.use_color() is True


# --- CI configuration -------------------------------------------------------

def test_ci_runs_pytest_from_the_checkout_and_preflights_llvm():
    workflow = (ROOT / ".github/workflows/python-package.yml").read_text()
    assert "python -m pytest" in workflow
    assert "command -v lli" in workflow
    pyproject = (ROOT / "pyproject.toml").read_text()
    assert 'pythonpath = ["."]' in pyproject
