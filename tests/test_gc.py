"""Explicit garbage collector: API, runtime inclusion and diagnostics."""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from compile_test import run_llvm
from compiler.threadon.compiler import compile_source
from compiler.threadon.importer import Importer


def compile_and_run(source, env=None):
    return run_llvm(compile_source(source, importer=Importer()), env=env)


def test_collect_returns_none_type():
    result = compile_and_run(
        """
def main() -> Int32
    result: NoneType = collect()
    return 0
"""
    )
    assert result.returncode == 0, result.stderr


def test_can_collect_was_removed():
    with pytest.raises(RuntimeError) as excinfo:
        compile_source(
            """
def main() -> Int32
    can_collect()
    return 0
""",
            importer=Importer(),
        )
    assert "Unknown function 'can_collect'" in str(excinfo.value)


def test_gc_threshold_environment_variable_is_ignored():
    result = compile_and_run(
        """
def main() -> Int32
    s: String = ""
    i: Int64 = 0
    while i < 500:
        s = s + "abcdefghij"
        i += 1
    print(len(s))
    return 0
""",
        env={"THREADON_GC_STATS": "1", "THREADON_GC_THRESHOLD": "1"},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "5000\n[gc] collections=0 snapshots=0 snapshot_max=0us snapshot_avg=0us mark_max=0us sweep_max=0us collector_total=0.0ms\n"


def test_gc_stats_line_has_all_timings():
    result = compile_and_run(
        """
def main() -> Int32
    s: String = ""
    i: Int64 = 0
    while i < 100:
        s = s + "abcdefghij"
        i += 1
    collect()
    collect()
    return 0
""",
        env={"THREADON_GC_STATS": "1"},
    )
    assert result.returncode == 0, result.stderr
    line = next(line for line in result.stdout.splitlines() if line.startswith("[gc] "))
    assert re.fullmatch(
        r"\[gc\] collections=2 snapshots=\d+ "
        r"snapshot_max=\d+us snapshot_avg=\d+us "
        r"mark_max=\d+us sweep_max=\d+us "
        r"collector_total=\d+\.\dms",
        line,
    )


def test_collect_keeps_live_lists_and_dicts():
    result = compile_and_run(
        """
def main() -> Int32
    xs: List[String] = []
    d: Dict[String, Int64] = {"a": 1}
    i: Int64 = 0
    while i < 200:
        xs.append("x" + String(i))
        d["k" + String(i)] = i
        i += 1
    collect()
    collect()
    collect()
    print(len(xs))
    print(d["a"])
    return 0
""",
        env={"THREADON_GC_STATS": "1"},
    )
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[:2] == ["200", "1"]
    assert "[gc] collections=3 " in lines[2]


def test_gc_runtime_is_only_emitted_when_needed():
    simple = compile_source(
        """
def main() -> Int32
    return 0
""",
        importer=Importer(),
    )
    with_collect = compile_source(
        """
def main() -> Int32
    collect()
    return 0
""",
        importer=Importer(),
    )
    assert "manual garbage collector runtime" not in simple
    assert "__threadon_gc_collect" not in simple
    assert "manual garbage collector runtime" in with_collect
    assert "__threadon_gc_collect" in with_collect


def test_puredef_cannot_call_collect():
    with pytest.raises(RuntimeError) as excinfo:
        compile_source(
            """
puredef f() -> NoneType
    collect()
    return
def main() -> Int32
    return 0
""",
            importer=Importer(),
        )
    assert "may not call non-pure function 'collect'" in str(excinfo.value)
