import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from compiler.threadon.compiler import compile_file, compile_source
from compiler.threadon.importer import Importer
from compiler.threadon.test_harness import find_test_functions, generate_test_harness

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPILER_DIR = REPO_ROOT / "compiler"


def run_llvm(llvm):
    with tempfile.NamedTemporaryFile("w", suffix=".ll", delete=False) as f:
        f.write(llvm)
        path = f.name
    try:
        cmd = ["lli"]
        import ctypes.util
        libatomic = ctypes.util.find_library("atomic")
        if libatomic:
            cmd.append("-load")
            cmd.append(libatomic)
        cmd.append(path)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    finally:
        Path(path).unlink(missing_ok=True)
    return result


def run_cli(args, *, cwd=None):
    env = os.environ.copy()
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(COMPILER_DIR) + (os.pathsep + prev if prev else "")
    return subprocess.run(
        [sys.executable, "-m", "threadon", *args],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=cwd or str(REPO_ROOT),
        env=env,
    )



PASSING_SUITE = """\
import unittest

def test_addition() -> Bool:
    return unittest.assert_true(1 + 1 == 2)

def test_subtraction() -> Bool:
    return unittest.assert_true(5 - 3 == 2)
"""


def test_find_test_functions():
    assert find_test_functions(PASSING_SUITE) == ["test_addition", "test_subtraction"]


def test_find_test_functions_ignores_indented_and_commented():
    src = (
        "# def test_hidden() -> Bool\n"
        "class Foo:\n"
        "    def test_method() -> Bool:\n"
        "        return True\n"
        "def test_visible() -> Bool:\n"
        "    return True\n"
    )
    assert find_test_functions(src) == ["test_visible"]


def test_generate_test_harness_calls_every_test():
    out = generate_test_harness(PASSING_SUITE)
    assert "def main() -> Int32" in out
    assert "test_addition()" in out
    assert "test_subtraction()" in out
    assert "[PASS]" in out
    assert "return __t_failed" in out


def test_generate_test_harness_skips_when_user_defines_main():
    src = PASSING_SUITE + "\ndef main() -> Int32:\n    return 0\n"
    assert generate_test_harness(src) == src


def test_generate_test_harness_filters_by_name():
    out = generate_test_harness(PASSING_SUITE, test_filter="addition")
    harness = out[out.index("def main() -> Int32"):]
    assert "test_addition()" in harness
    assert "test_subtraction()" not in harness


def test_generate_test_harness_setup_teardown():
    src = (
        PASSING_SUITE
        + "\ndef setup() -> Bool:\n    return True\n"
        + "\ndef teardown() -> Bool:\n    return True\n"
    )
    out = generate_test_harness(src)
    assert "__t_ok: Bool = setup()" in out
    assert "if not __t_ok:" in out
    assert "__t_ok = teardown()" in out
    assert 'print("[FAIL] teardown")' in out
    assert out.index("teardown()") > out.index("test_addition()")




def test_test_th_suite_passes(tmp_path):
    path = tmp_path / "test.th"
    path.write_text(PASSING_SUITE)
    llvm = compile_file(path)
    result = run_llvm(llvm)
    assert result.returncode == 0, result.stderr
    assert "[PASS] test_addition" in result.stdout
    assert "[PASS] test_subtraction" in result.stdout


def test_test_th_suite_failure_exit_code(tmp_path):
    path = tmp_path / "test.th"
    path.write_text(
        "import unittest\n\n"
        "def test_wrong() -> Bool:\n"
        "    return unittest.assert_true(2 + 2 == 5)\n"
    )
    llvm = compile_file(path)
    result = run_llvm(llvm)
    assert result.returncode == 1
    assert "[FAIL] test_wrong" in result.stdout
    assert "1 tests 1 failed" in result.stdout


def test_non_test_file_untouched(tmp_path):
    path = tmp_path / "main.th"
    path.write_text(
        "def main() -> Int32:\n"
        "    return 0\n"
    )
    llvm = compile_file(path)
    assert "define i32 @main" in llvm


def test_setup_teardown_helpers_run(tmp_path):
    path = tmp_path / "test.th"
    path.write_text(
        "import unittest\n\n"
        "def setup() -> Bool:\n"
        "    return True\n\n"
        "def test_one() -> Bool:\n"
        "    return unittest.assert_true(True)\n\n"
        "def test_two() -> Bool:\n"
        "    return unittest.assert_true(True)\n\n"
        "def teardown() -> Bool:\n"
        "    return unittest.assert_true(True)\n"
    )
    llvm = compile_file(path)
    result = run_llvm(llvm)
    assert result.returncode == 0, result.stderr
    assert "2 tests 0 failed" in result.stdout


def test_advanced_assertion_helpers(tmp_path):
    path = tmp_path / "test.th"
    path.write_text(
        "import unittest\n\n"
        "def test_helpers() -> Bool:\n"
        "    return unittest.assert_eq(2 + 2, 4) and "
        "unittest.assert_approx(0.1 + 0.2, 0.3) and "
        "unittest.assert_contains(\"hello world\", \"wor\") and "
        "unittest.assert_starts_with(\"hello\", \"he\") and "
        "unittest.assert_ends_with(\"hello\", \"lo\")\n"
    )
    llvm = compile_file(path)
    result = run_llvm(llvm)
    assert result.returncode == 0, result.stderr
    assert "[PASS] test_helpers" in result.stdout


def test_tiny_float_literal_emits_valid_llvm():
    llvm = compile_source(
        "def main() -> Int32:\n"
        "    x: Float64 = 0.000001\n"
        "    y: Float64 = 1e-6\n"
        "    print(x + y)\n"
        "    return 0\n",
        importer=Importer(),
    )
    result = run_llvm(llvm)
    assert result.returncode == 0, result.stderr




def test_cli_run_tests_explicit_suite(tmp_path):
    suite = tmp_path / "test.th"
    suite.write_text(PASSING_SUITE)
    result = run_cli(["--run-tests", str(suite)])
    assert result.returncode == 0, result.stderr
    assert "[PASS] test_addition" in result.stdout
    assert "test file(s), 0 failed" in result.stdout


def test_cli_run_tests_failing_suite(tmp_path):
    suite = tmp_path / "test.th"
    suite.write_text(
        "import unittest\n\n"
        "def test_wrong() -> Bool:\n"
        "    return unittest.assert_true(1 == 2)\n"
    )
    result = run_cli(["--run-tests", str(suite)])
    assert result.returncode == 1
    assert "[FAIL] test_wrong" in result.stdout


def test_cli_run_tests_directory_discovery(tmp_path):
    (tmp_path / "test.th").write_text(PASSING_SUITE)
    result = run_cli(["--run-tests", str(tmp_path)])
    assert result.returncode == 0, result.stderr
    assert "1 test file(s), 0 failed" in result.stdout


def test_cli_run_tests_filter_single_test(tmp_path):
    (tmp_path / "test.th").write_text(PASSING_SUITE)
    result = run_cli(
        ["--run-tests", "-k", "addition", str(tmp_path)]
    )
    assert result.returncode == 0, result.stderr
    assert "[PASS] test_addition" in result.stdout
    assert "test_subtraction" not in result.stdout
    assert "1 tests 0 failed" in result.stdout


def test_cli_run_tests_filter_no_match_skips(tmp_path):
    (tmp_path / "test.th").write_text(PASSING_SUITE)
    result = run_cli(["--run-tests", "-k", "doesnotexist", str(tmp_path)])
    assert result.returncode == 0, result.stderr
    assert "no tests match 'doesnotexist'" in result.stdout


def test_cli_run_tests_scans_project_root_from_subdir(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    suite = tmp_path / "test.th"
    suite.write_text(PASSING_SUITE)
    deep = tmp_path / "nested" / "deep"
    deep.mkdir(parents=True)
    result = run_cli(["--run-tests"], cwd=str(deep))
    assert result.returncode == 0, result.stderr
    assert str(suite) in result.stdout
    assert "0 failed" in result.stdout


def test_cli_run_tests_no_targets_runs_stdlib_suites(tmp_path):
    result = run_cli(["--run-tests"], cwd=str(tmp_path))
    assert result.returncode == 0, result.stderr
    assert "compiler/stdlib/std/test.th" in result.stdout
    assert "compiler/stdlib/unittest/test.th" in result.stdout
    assert "test file(s), 0 failed" in result.stdout