import io
import re
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from compiler.checker import CombinedChecker
from compiler.compiler import compile_source
from compiler.importer import Importer
from compiler.optimalise_ir import IROptimizer
from compiler.parser import Parser
from compiler.to_high_ir import SSABuilder
from compiler.to_llvm_ir import LLVMIRCompiler

COMPLEX_SOURCE = """
struct Z:
    z: Int32

struct Point:
    x: Int32
    y: Int32
    z: Z

def clamp(n: Int32, lo: Int32, hi: Int32) -> Int32
    if n < lo:
        result: Int32 = lo
    elif n > hi:
        result: Int32 = hi
    else:
        result: Int32 = n
    return result

def poly(v: Int32) -> Int32
    result: Int32 = v * v * 3 - v * 5 + 7
    return result

def average(a: Float32, b: Float32) -> Float32
    s: Float32 = (a + b) ** 2.0 / 2.0
    return s

def run() -> Int32
    a: Int32 = 10
    b: Int32 = 87
    p: Point = Point(x=a, y=b, z=Z(z=3))
    c: Int32 = clamp(p.y, 0, 100)
    d: Int32 = poly(c)
    e: Int32 = d // 2
    f: Int32 = e % 1000
    g: Int32 = -f + p.z.z * 2
    ref: Int32 = g^
    h: Bool = ref > 0
    if h:
        i: Int32 = ref + 1
    else:
        i: Int32 = ref - 1
    return i
"""

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
HARNESS_MAIN = """
declare i32 @printf(i8*, ...)

@.int_fmt = private unnamed_addr constant [4 x i8] c"%d\n\0"
@.float_fmt = private unnamed_addr constant [4 x i8] c"%f\n\0"

define i32 @main() {
  %r = call i32 @run()
  %fmt1 = getelementptr inbounds [4 x i8], [4 x i8]* @.int_fmt, i64 0, i64 0
  %p1 = call i32 (i8*, ...) @printf(i8* %fmt1, i32 %r)
  %f = call float @average(float 1.5, float 2.5)
  %fd = fpext float %f to double
  %fmt2 = getelementptr inbounds [6 x i8], [6 x i8]* @.float_fmt, i64 0, i64 0
  %p2 = call i32 (i8*, ...) @printf(i8* %fmt2, double %fd)
  ret i32 0
}
"""


def compile_program(source, inline_threshold=0):
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            parser = Parser()
            ast = parser.parse(source)
            CombinedChecker().run_all(ast)
            module = SSABuilder().build_from_ast(ast)
            IROptimizer(inline_threshold=inline_threshold).optimize(module)
    except BaseException as e:
        raise RuntimeError(f"compiler error:\n{buf.getvalue()}") from e
    return LLVMIRCompiler().compile(module)


def patch_llvm(llvm):
    llvm = re.sub(
        r"declare i32 @llvm\.pow\.i32\(i32, i32\) #\d+\n",
        POW_I32_IMPL + "\n",
        llvm,
    )
    return llvm + "\n" + HARNESS_MAIN + "\n"


def run_llvm(llvm, input=None):
    with tempfile.NamedTemporaryFile("w", suffix=".ll", delete=False) as f:
        f.write(llvm)
        path = f.name
    try:
        result = subprocess.run(
            ["lli", path], capture_output=True, text=True, timeout=60, input=input
        )
    finally:
        Path(path).unlink(missing_ok=True)
    return result


def compile_and_run(inline_threshold):
    llvm = compile_program(COMPLEX_SOURCE, inline_threshold=inline_threshold)
    llvm = patch_llvm(llvm)
    return run_llvm(llvm)


def test_complex_program_runs():
    result = compile_and_run(inline_threshold=0)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "-134\n8.000000\n"


def test_complex_program_inlined():
    result = compile_and_run(inline_threshold=10000)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "-134\n8.000000\n"


def compile_stdlib_run(source, inline_threshold=0, input=None):
    llvm = compile_source(source, importer=Importer(), inline_threshold=inline_threshold,debug_mode=True)
    return run_llvm(llvm, input=input)


def test_multi_arg_print():
    result = compile_stdlib_run(
        """
struct Point:
    x: Int32
    y: Int32

def main() -> Int32
    p: Point = Point(x=3, y=4)
    print("x =", p.x)
    print("sum =", p.x + p.y)
    print("flag =", p.x < p.y)
    print()
    print("text", 5, 2.5, True)
    return 0
""",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "x = 3\nsum = 7\nflag = 1\n\ntext 5 2.500000 1\n"


def test_builtin_print_and_conversions():
    result = compile_stdlib_run(
        """
def main() -> Int32
    print("hello world")
    print(42)
    print(3.14)
    print(True)
    print(Int32(3.7))
    print(Int32(True))
    print(Float32(5))
    print(Bool(7))
    return 0
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "hello world\n42\n3.140000\n1\n3\n1\n5.000000\n1\n"


def test_string_conversions():
    result = compile_stdlib_run(
        """
def main() -> Int32
    print(Int32("123"))
    print(Float32("3.5"))
    print(Bool("true"))
    print(Bool("False"))
    print(Bool("0"))
    n: Int32 = Int32(input("Enter a number: "))
    print(n * 2)
    return 0
""",
        input="21\n",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "123\n3.500000\n1\n0\n0\nEnter a number: 42\n"


def test_string_conversion_invalid_errors():
    result = compile_stdlib_run(
        """
def main() -> Int32
    print(Int32("abc"))
    return 0
""",
    )
    assert result.returncode != 0
    assert "Invalid integer conversion" in result.stderr


def test_int_and_string_zero_constants_distinct():
    result = compile_stdlib_run(
        """
def main() -> Int32
    s: String = "0"
    n: Int32 = 0
    print(Int32(s) + 1)
    print(n)
    return 0
""",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "1\n0\n"


def test_builtin_input():
    result = compile_stdlib_run(
        """
def main() -> Int32
    n: String = input("Give a name: ")
    print("Hello,")
    print(n)
    return 0
""",
        input="Joep\n",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "Give a name: Hello,\nJoep\n"


def test_input_empty_on_eof():
    result = compile_stdlib_run(
        """
def main() -> Int32
    n: String = input("Give a name: ")
    print(n)
    return 0
""",
        input="",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "Give a name: \n"


def test_field_assign():
    result = compile_stdlib_run(
        """
struct Point:
    x: Int32
    y: Int32

def main() -> Int32
    p: Point = Point(x=0, y=0)
    print(p.x)
    print(p.y)
    p.x = 3
    p.y = p.x + 1
    print(p.x)
    print(p.y)
    if p.x < 5:
        p.x = 10
    print(p.x)
    print(p.y)
    return 0
""",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "0\n0\n3\n4\n10\n4\n"


def test_expr_statement():
    result = compile_stdlib_run(
        """
def main() -> Int32
    print(Int32(2.5) + 1)
    return 0
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "3\n"


def test_stdlib_helpers():
    source = """
def add(a: Int32, b: Int32) -> Int32
    return a + b

def main() -> Int32
    print(abs(-7))
    print(max(3, 9))
    print(min(2, 8))
    print(clamp(150, 0, 100))
    print(clamp(-5, 0, 100))
    print(is_even(4))
    print(is_even(5))
    print(is_odd(7))
    print(add(add(1, 2), 3))
    return 0
"""
    for threshold in (0, 10000):
        result = compile_stdlib_run(source, inline_threshold=threshold)
        assert result.returncode == 0, result.stderr
        assert result.stdout == "7\n9\n2\n100\n0\n1\n0\n1\n6\n"


def test_default_parameters_runtime():
    source = """
def add(a: Int32, b: Int32 = 5, c: Int32 = 10) -> Int32
    return a + b + c

def greet(name: String = "world") -> String
    return name

def main() -> Int32
    print(add(1))
    print(add(1, 2))
    print(add(1, 2, 3))
    print(greet())
    print(greet("threadon"))
    return 0
"""
    for threshold in (0, 10000):
        result = compile_stdlib_run(source, inline_threshold=threshold)
        assert result.returncode == 0, result.stderr
        assert result.stdout == "16\n13\n6\nworld\nthreadon\n"


def test_default_parameters_error_cases():
    with pytest.raises(RuntimeError) as excinfo:
        compile_source(
            """
def f(a: Int32, b: Int32 = 2) -> Int32
    return a + b
def main() -> Int32
    print(f())
    return 0
""",
            importer=Importer(),
        )
    assert "expects between 1 and 2 arguments, got 0" in str(excinfo.value)


if __name__ == "__main__":
    test_complex_program_runs()
    test_complex_program_inlined()
    test_builtin_print_and_conversions()
    test_multi_arg_print()
    test_string_conversions()
    test_string_conversion_invalid_errors()
    test_int_and_string_zero_constants_distinct()
    test_builtin_input()
    test_input_empty_on_eof()
    test_field_assign()
    test_expr_statement()
    test_stdlib_helpers()
    test_default_parameters_runtime()
    test_default_parameters_error_cases()
    print("compile_test OK")
