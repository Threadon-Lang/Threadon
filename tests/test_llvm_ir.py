import io
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import compile_test as ct
import pytest

from compiler.checker import CombinedChecker
from compiler.optimalise_ir import IROptimizer
from compiler.parser import Parser
from compiler.to_high_ir import SSABuilder
from compiler.to_llvm_ir import LLVMIRCompiler

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
  %r = call float @run()
  %rd = fpext float %r to double
  %fmt1 = getelementptr inbounds [4 x i8], [4 x i8]* @.float_fmt, i64 0, i64 0
  %p1 = call i32 (i8*, ...) @printf(i8* %fmt1, double %rd)
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


def test_while_loop_runs():
    assert_run_output(
        """
def run() -> Int32
    i: Int32 = 0
    while i < 3:
        i += 1
    return i
""",
        "3\n",
    )


def test_inline_into_loop_runs():
    assert_run_output(
        """
def helper(x: Int32) -> Int32
    return x * 2

def run() -> Int32
    i: Int32 = 0
    s: Int32 = 0
    while i < 4:
        s += helper(i)
        i += 1
    return s
""",
        "12\n",
    )


def test_while_loop_debug_mode_runs():
    source = """
def run() -> Int32
    i: Int32 = 0
    while i < 3:
        i += 1
    return i
"""
    with redirect_stdout(io.StringIO()):
        ast = Parser().parse(source)
        CombinedChecker().run_all(ast)
        module = SSABuilder().build_from_ast(ast)
        IROptimizer(debug_mode=True).optimize(module)
    llvm = LLVMIRCompiler(debug_mode=True).compile(module)
    patched = patch_for_execution(llvm, INT_HARNESS)
    result = ct.run_llvm(patched)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "3\n"


def test_float_pow_intrinsic_emitted():
    llvm = compile_unoptimized("def run() -> Float32\n    return 2.0 ** 3.0\n")
    assert "@llvm.pow.f32" in llvm


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


def test_else_branch_execution():
    assert_run_output(
        """
def max2(a: Int32, b: Int32) -> Int32
    if a > b:
        r: Int32 = a
    else:
        r: Int32 = b
    return r
def run() -> Int32
    return max2(3, 7)
""",
        "7\n",
    )


def test_negative_literal_execution():
    assert_run_output("def run() -> Int32\n    return -5\n", "-5\n")


def test_modulo_operator_execution():
    assert_run_output("def run() -> Int32\n    return 10 % 3\n", "1\n")


def test_floordiv_operator_execution():
    assert_run_output("def run() -> Int32\n    return 10 // 3\n", "3\n")


def test_mul_optimized_to_shift_execution():
    assert_run_output(
        "def run() -> Int32\n    x: Int32 = 7\n    return x * 8\n", "56\n"
    )


def test_nested_struct_field_access_runtime():
    assert_run_output(
        """
struct Z:
    z: Int32
struct P:
    z: Z
def run() -> Int32
    p: P = P(z=Z(z=5))
    return p.z.z
""",
        "5\n",
    )


def test_elif_chain_runtime():
    assert_run_output(
        """
def clamp(n: Int32, lo: Int32, hi: Int32) -> Int32
    if n < lo:
        r: Int32 = lo
    elif n > hi:
        r: Int32 = hi
    else:
        r: Int32 = n
    return r
def run() -> Int32
    return clamp(150, 0, 100)
""",
        "100\n",
    )


def test_bool_variable_in_condition_runtime():
    assert_run_output(
        """
def run() -> Int32
    b: Bool = 2 < 3
    if b:
        r: Int32 = 1
    else:
        r: Int32 = 0
    return r
""",
        "1\n",
    )


def test_float_addition_execution():
    assert_float_output(
        "def run() -> Float32\n    a: Float32 = 1.5 + 2.5\n    return a\n",
        "4.000000\n",
    )


def test_augmented_assignment_execution():
    assert_run_output(
        "def run() -> Int32\n    x: Int32 = 5\n    x += 3\n    return x\n", "8\n"
    )


def test_not_operator_execution():
    assert_run_output(
        """
def run() -> Int32
    b: Bool = not (2 > 3)
    if b:
        r: Int32 = 1
    else:
        r: Int32 = 0
    return r
""",
        "1\n",
    )


def test_eq_comparison_execution():
    assert_run_output(
        """
def run() -> Int32
    if 2 == 2:
        r: Int32 = 1
    else:
        r: Int32 = 0
    return r
""",
        "1\n",
    )


def test_ne_comparison_execution():
    assert_run_output(
        """
def run() -> Int32
    if 2 != 3:
        r: Int32 = 1
    else:
        r: Int32 = 0
    return r
""",
        "1\n",
    )


def test_le_comparison_execution():
    assert_run_output(
        """
def run() -> Int32
    if 2 <= 2:
        r: Int32 = 1
    else:
        r: Int32 = 0
    return r
""",
        "1\n",
    )


def test_ge_comparison_execution():
    assert_run_output(
        """
def run() -> Int32
    if 3 >= 3:
        r: Int32 = 1
    else:
        r: Int32 = 0
    return r
""",
        "1\n",
    )


def test_float_division_execution():
    assert_float_output(
        "def run() -> Float32\n    a: Float32 = 6.0 / 4.0\n    return a\n",
        "1.500000\n",
    )


def test_float_comparison_execution():
    assert_run_output(
        """
def run() -> Int32
    if 1.5 > 1.0:
        r: Int32 = 1
    else:
        r: Int32 = 0
    return r
""",
        "1\n",
    )


def test_float_multiplication_execution():
    assert_float_output(
        "def run() -> Float32\n    a: Float32 = 1.5 * 2.0\n    return a\n",
        "3.000000\n",
    )


def test_float_subtraction_execution():
    assert_float_output(
        "def run() -> Float32\n    a: Float32 = 5.5 - 2.0\n    return a\n",
        "3.500000\n",
    )


def test_float_negation_execution():
    assert_float_output(
        "def run() -> Float32\n    return -1.5\n", "-1.500000\n"
    )


def test_float_modulo_execution():
    assert_float_output(
        "def run() -> Float32\n    return 5.5 % 2.0\n", "1.500000\n"
    )


def test_float_floordiv_execution():
    assert_float_output(
        "def run() -> Float32\n    return 5.0 // 2.0\n", "2.000000\n"
    )


def test_float_pow_execution():
    assert_float_output(
        "def run() -> Float32\n    return 2.0 ** 3.0\n", "8.000000\n"
    )


def test_float_unary_plus_execution():
    assert_float_output(
        "def run() -> Float32\n    return +2.5\n", "2.500000\n"
    )


from compiler.compiler import compile_file, compile_source
from compiler.importer import Importer

MATH_SOURCE = """
def abs(x: Int32) -> Int32
    result: Int32 = x
    if x < 0:
        result *= -1
    return result

def mean(a: Float32, b: Float32) -> Float32
    return (a + b) / 2.0
"""

STRUCT_SOURCE = """
struct Point:
    x: Int32
    y: Int32

def dot(a: Point, b: Point) -> Int32
    return a.x * b.x + a.y * b.y

def origin() -> Point
    return Point(x=1, y=2)
"""


def compile_imported(source, module_sources, inline_threshold=0):
    imp = Importer()
    for name, src in module_sources.items():
        imp.register_source(name, src)
    return compile_source(source, importer=imp, inline_threshold=inline_threshold)


def assert_imported_output(source, module_sources, expected, harness=INT_HARNESS):
    llvm = compile_imported(source, module_sources)
    patched = patch_for_execution(llvm, harness)
    result = ct.run_llvm(patched)
    assert result.returncode == 0, result.stderr
    assert result.stdout == expected


def test_import_function_runtime():
    assert_imported_output(
        "from std.math import abs\ndef run() -> Int32\n    return abs(-5)\n",
        {"std.math": MATH_SOURCE},
        "5\n",
    )


def test_import_qualified_call_runtime():
    assert_imported_output(
        (
            "import std.math\n"
            "def run() -> Int32\n"
            "    return std.math.abs(-5)\n"
        ),
        {"std.math": MATH_SOURCE},
        "5\n",
    )


def test_import_from_alias_runtime():
    assert_imported_output(
        (
            "from std.math import abs as absolute\n"
            "def run() -> Int32\n"
            "    return absolute(-9)\n"
        ),
        {"std.math": MATH_SOURCE},
        "9\n",
    )


def test_import_qualified_alias_runtime():
    assert_imported_output(
        (
            "import std.math as m\n"
            "def run() -> Int32\n"
            "    return m.abs(-9)\n"
        ),
        {"std.math": MATH_SOURCE},
        "9\n",
    )


def test_import_struct_runtime():
    assert_imported_output(
        (
            "from std.math import Point, dot, origin\n"
            "def run() -> Int32\n"
            "    p: Point = origin()\n"
            "    q: Point = Point(x=3, y=4)\n"
            "    return dot(p, q)\n"
        ),
        {"std.math": STRUCT_SOURCE},
        "11\n",
    )


def test_import_struct_qualified_runtime():
    assert_imported_output(
        (
            "import std.math\n"
            "def run() -> Int32\n"
            "    q: std.math.Point = std.math.Point(x=3, y=4)\n"
            "    return q.x + q.y\n"
        ),
        {"std.math": STRUCT_SOURCE},
        "7\n",
    )


def test_lazy_import_never_used_does_not_load():
    source = (
        "lazyfrom no.such.module import missing\n"
        "def run() -> Int32\n"
        "    return 42\n"
    )
    llvm = compile_source(source, importer=Importer())
    assert "define i32 @run()" in llvm


def test_lazy_import_qualified_type_annotation():
    source = (
        "lazyimport geom\n"
        "def run() -> Int32\n"
        "    p: geom.Point\n"
        "    q: geom.Point = geom.Point(x=3, y=4)\n"
        "    return q.x\n"
    )
    imp = Importer()
    imp.register_source(
        "geom",
        "struct Point:\n    x: Int32\n    y: Int32\n",
    )
    llvm = compile_source(source, importer=imp)
    assert "%struct.geom.Point = type { i32, i32 }" in llvm
    assert "define i32 @run()" in llvm


def test_lazy_import_loaded_when_used():
    source = (
        "lazyfrom std.math import abs\n"
        "def run() -> Int32\n"
        "    return abs(-5)\n"
    )
    imp = Importer()
    imp.register_source("std.math", MATH_SOURCE)
    llvm = compile_source(source, importer=imp)
    assert "define i32 @std.math.abs(i32" in llvm


def test_import_qualified_function_emitted():
    llvm = compile_imported(
        "from std.math import abs\ndef run() -> Int32\n    return abs(-5)\n",
        {"std.math": MATH_SOURCE},
    )
    assert "define i32 @std.math.abs(i32" in llvm


def test_import_struct_types_in_llvm():
    llvm = compile_imported(
        (
            "from std.math import Point, dot\n"
            "def run() -> Int32\n"
            "    p: Point = Point(x=1, y=2)\n"
            "    return dot(p, p)\n"
        ),
        {"std.math": STRUCT_SOURCE},
    )
    assert "%struct.std.math.Point = type { i32, i32 }" in llvm
    assert "define i32 @std.math.dot(%struct.std.math.Point" in llvm
    assert "define %struct.std.math.Point @std.math.origin()" in llvm


def test_compile_file_with_search_path(tmp_path):
    (tmp_path / "math.th").write_text(MATH_SOURCE)
    main = tmp_path / "main.th"
    main.write_text(
        "from math import abs\ndef run() -> Int32\n    return abs(-5)\n"
    )
    llvm = compile_file(str(main), importer=Importer())
    patched = patch_for_execution(llvm, INT_HARNESS)
    result = ct.run_llvm(patched)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "5\n"


def test_import_nested_module_path(tmp_path):
    mod_dir = tmp_path / "lib" / "util"
    mod_dir.mkdir(parents=True)
    (mod_dir / "helpers.th").write_text(MATH_SOURCE)
    main = tmp_path / "main.th"
    main.write_text(
        "from lib.util.helpers import abs\n"
        "def run() -> Int32\n"
        "    return abs(-5)\n"
    )
    llvm = compile_file(str(main), importer=Importer())
    assert "define i32 @lib.util.helpers.abs(i32" in llvm


def test_build_executable(tmp_path):
    import shutil
    import subprocess

    from compiler.main import build_executable, patch_llvm

    if not (shutil.which("llc") and shutil.which("gcc")):
        pytest.skip("llc/gcc not available")
    llvm = compile_source(
        "def main() -> Int32\n    return 6 * 7\n", importer=Importer()
    )
    final = patch_llvm(llvm)
    exe = tmp_path / "prog"
    build_executable(final, exe)
    result = subprocess.run([str(exe)], capture_output=True, text=True)
    assert result.returncode == 42, result.stderr
    assert result.stdout == ""


def test_default_params_emitted_in_signature():
    llvm = compile_unoptimized(
        """
def f(a: Int32, b: Int32 = 5) -> Int32
    return a + b
"""
    )
    assert "define i32 @f(i32 %t0, i32 %t1)" in llvm


def test_defaults_filled_at_call_site_in_llvm():
    llvm = compile_unoptimized(
        """
def f(a: Int32, b: Int32 = 5, c: Float32 = 1.5) -> Int32
    return a
def run() -> Int32
    return f(1)
"""
    )
    assert "define i32 @f(i32 %t0, i32 %t1, float %t2)" in llvm

    run_idx = llvm.index("define i32 @run")
    run = llvm[run_idx:]
    assert "call i32 @f(i32 %t0, i32 %t1, float %t2)" in run
    assert "add i32 0, 5" in run
    assert "fadd float 0.0" in run


def test_default_params_runtime():
    assert_run_output(
        """
def add(a: Int32, b: Int32 = 5, c: Int32 = 10) -> Int32
    return a + b + c
def run() -> Int32
    return add(1)
""",
        "16\n",
    )
    assert_run_output(
        """
def add(a: Int32, b: Int32 = 5, c: Int32 = 10) -> Int32
    return a + b + c
def run() -> Int32
    return add(1, 2)
""",
        "13\n",
    )
    assert_run_output(
        """
def add(a: Int32, b: Int32 = 5, c: Int32 = 10) -> Int32
    return a + b + c
def run() -> Int32
    return add(1, 2, 3)
""",
        "6\n",
    )


def test_default_params_runtime_inlined():
    assert_run_output(
        """
def add(a: Int32, b: Int32 = 5, c: Int32 = 10) -> Int32
    return a + b + c
def run() -> Int32
    return add(1)
""",
        "16\n",
        inline_threshold=10000,
    )


def test_default_bool_and_string_runtime():
    assert_run_output(
        """
def f(b: Bool = True) -> Int32
    if b:
        return 1
    return 0
def run() -> Int32
    return f() + f(False)
""",
        "1\n",
        inline_threshold=0,
    )


def test_default_float_runtime():
    llvm = compile_llvm(
        """
def f(a: Float32 = 2.5) -> Float32
    return a
def run() -> Float32
    return f()
"""
    )
    patched = patch_for_execution(llvm, FLOAT_HARNESS)
    result = ct.run_llvm(patched)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "2.500000\n"
