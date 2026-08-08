import io
from contextlib import redirect_stdout
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from compiler.checker import CombinedChecker
from compiler.parser import Parser
from compiler.to_high_ir import SSABuilder
from compiler.to_llvm_ir import LLVMIRCompiler

import compile_test as ct

INT_HARNESS = """
declare i32 @printf(i8*, ...)

@.int_fmt = private unnamed_addr constant [4 x i8] c"%d\n\0"

define i32 @main() {
  %r = call i32 @run()
  %fmt1 = getelementptr inbounds [4 x i8], [4 x i8]* @.int_fmt, i64 0, i64 0
  %p1 = call i32 (i8*, ...) @printf(i8* %fmt1, i32 %r)
  ret i32 0
}
"""

FLOAT_HARNESS = """
declare i32 @printf(i8*, ...)

@.float_fmt = private unnamed_addr constant [4 x i8] c"%f\n\0"

define i32 @main() {
  %r = call double @run()
  %fmt1 = getelementptr inbounds [4 x i8], [4 x i8]* @.float_fmt, i64 0, i64 0
  %p1 = call i32 (i8*, ...) @printf(i8* %fmt1, double %r)
  ret i32 0
}
"""


def compile_llvm(source, inline_threshold=30):
    return ct.compile_program(source, inline_threshold=inline_threshold)


def compile_unoptimized(source):
    with redirect_stdout(io.StringIO()):
        ast = Parser().parse(source)
        CombinedChecker().run_all(ast)
        module = SSABuilder().build_from_ast(ast)
    return LLVMIRCompiler().compile(module)


def patch_for_execution(llvm, harness):
    llvm = re.sub(
        r"declare i32 @llvm\.pow\.i32\(i32, i32\) #\d+\n",
        ct.POW_I32_IMPL + "\n",
        llvm,
    )
    return llvm + "\n" + harness + "\n"


def assert_run_output(source, expected, inline_threshold=30):
    llvm = compile_llvm(source, inline_threshold=inline_threshold)
    patched = patch_for_execution(llvm, INT_HARNESS)
    result = ct.run_llvm(patched)
    assert result.returncode == 0, result.stderr
    assert result.stdout == expected


def assert_float_output(source, expected, inline_threshold=30):
    llvm = compile_llvm(source, inline_threshold=inline_threshold)
    patched = patch_for_execution(llvm, FLOAT_HARNESS)
    result = ct.run_llvm(patched)
    assert result.returncode == 0, result.stderr
    assert result.stdout == expected


# --- structural tests --------------------------------------------------------


def test_emit_target_declaration():
    llvm = compile_unoptimized("def run() -> Int32\n    return 2 ** 8\n")
    assert "declare i32 @llvm.pow.i32" in llvm


def test_struct_type_and_ops_emitted_unoptimized():
    llvm = compile_unoptimized(
        """
struct Point:
    x: Int32
    y: Int32
def run() -> Int32
    p: Point = Point(x=1, y=2)
    return p.x + p.y
"""
    )
    assert "%struct.Point = type { i32, i32 }" in llvm
    assert re.search(r"insertvalue %struct\.Point undef", llvm)
    assert re.search(r"extractvalue %struct\.Point", llvm)


def test_optimized_struct_access_survives():
    llvm = compile_llvm(
        """
struct Point:
    x: Int32
    y: Int32
def run() -> Int32
    p: Point = Point(x=1, y=2)
    return p.x + p.y
"""
    )
    assert "%struct.Point = type { i32, i32 }" in llvm


def test_phi_nodes_emitted():
    llvm = compile_llvm(
        """
def max2(a: Int32, b: Int32) -> Int32
    if a > b:
        r: Int32 = a
    else:
        r: Int32 = b
    return r
def run() -> Int32
    return max2(7, 3)
"""
    )
    assert "= phi i32 [" in llvm


def test_float_pow_intrinsic_emitted():
    llvm = compile_unoptimized("def run() -> Float32\n    return 2.0 ** 3.0\n")
    assert "@llvm.pow.f64" in llvm


# --- execution tests ---------------------------------------------------------


def test_arithmetic_expression():
    assert_run_output(
        "def run() -> Int32\n    a: Int32 = 2 + 3 * 4\n    return a\n",
        "14\n",
    )


def test_const_condition_folds():
    assert_run_output(
        """
def run() -> Int32
    a: Int32 = 10
    b: Int32 = 3
    if a > b:
        r: Int32 = a
    else:
        r: Int32 = b
    return r
""",
        "10\n",
    )


def test_if_else_from_params():
    assert_run_output(
        """
def max2(a: Int32, b: Int32) -> Int32
    if a > b:
        r: Int32 = a
    else:
        r: Int32 = b
    return r
def run() -> Int32
    return max2(7, 3)
""",
        "7\n",
    )


def test_struct_field_access():
    assert_run_output(
        """
struct Point:
    x: Int32
    y: Int32
def run() -> Int32
    p: Point = Point(x=3, y=5)
    return p.x + p.y
""",
        "8\n",
    )


def test_float_pow():
    assert_float_output(
        "def run() -> Float32\n    a: Float32 = (1.5 + 2.5) ** 2.0 / 2.0\n    return a\n",
        "8.000000\n",
    )


def test_int_pow():
    assert_run_output(
        """
def run() -> Int32
    a: Int32 = 2 ** 8
    return a
""",
        "256\n",
    )


def test_full_program_output():
    llvm = ct.compile_program(ct.COMPLEX_SOURCE, inline_threshold=30)
    patched = ct.patch_llvm(llvm)
    result = ct.run_llvm(patched)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "-134\n8.000000\n"
