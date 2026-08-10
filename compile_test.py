import io
import re
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from compiler.parser import Parser
from compiler.checker import CombinedChecker
from compiler.compiler import compile_source
from compiler.importer import Importer
from compiler.to_high_ir import SSABuilder
from compiler.optimalise_ir import IROptimizer
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
  %f = call double @average(double 1.5, double 2.5)
  %fmt2 = getelementptr inbounds [6 x i8], [6 x i8]* @.float_fmt, i64 0, i64 0
  %p2 = call i32 (i8*, ...) @printf(i8* %fmt2, double %f)
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
    llvm = compile_source(source, importer=Importer(), inline_threshold=inline_threshold)
    return run_llvm(llvm, input=input)


def test_builtin_print_and_conversions():
    result = compile_stdlib_run(
        """
def main() -> Int32
    print("hello world")
    print(42)
    print(3.14)
    print(True)
    print(to_int(3.7))
    print(to_int(True))
    print(to_float(5))
    print(to_bool(7))
    return 0
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "hello world\n42\n3.140000\n1\n3\n1\n5.000000\n1\n"


def test_builtin_input():
    result = compile_stdlib_run(
        """
def main() -> Int32
    n: Int32 = input("Give a number: ")
    print(n)
    return 0
""",
        input="21\n",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "Give a number: 21\n"


def test_expr_statement():
    result = compile_stdlib_run(
        """
def main() -> Int32
    print(to_int(2.5) + 1)
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


if __name__ == "__main__":
    test_complex_program_runs()
    test_complex_program_inlined()
    test_builtin_print_and_conversions()
    test_builtin_input()
    test_expr_statement()
    test_stdlib_helpers()
    print("compile_test OK")
