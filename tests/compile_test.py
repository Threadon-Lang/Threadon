import io
import re
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from compiler.threadon.checker import CombinedChecker
from compiler.threadon.compiler import compile_source
from compiler.threadon.importer import Importer
from compiler.threadon.optimalise_ir import IROptimizer
from compiler.threadon.parser import Parser
from compiler.threadon.to_high_ir import SSABuilder
from compiler.threadon.to_llvm_ir import LLVMIRCompiler

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


def run_llvm(llvm, input=None, loads=None):
    with tempfile.NamedTemporaryFile("w", suffix=".ll", delete=False) as f:
        f.write(llvm)
        path = f.name
    try:
        cmd = ["lli"]
        for so in (loads or []):
            cmd.append("-load")
            cmd.append(str(so))
        cmd.append(path)
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, input=input
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
    assert result.stdout == "x = 3\nsum = 7\nflag = True\n\ntext 5 2.500000 True\n"


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
    assert result.stdout == "hello world\n42\n3.140000\nTrue\n3\n1\n5.000000\nTrue\n"


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
    assert result.stdout == "123\n3.500000\nTrue\nFalse\nFalse\nEnter a number: 42\n"


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
        assert result.stdout == "7\n9\n2\n100\n0\nTrue\nFalse\nTrue\n6\n"


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


def test_float_inf_constant_errors_with_flag():
    source = """
def main() -> Int32
    x: Float64 = 1.0e400
    print(x)
    return 0
"""
    with pytest.raises(SystemExit):
        compile_source(source, importer=Importer(), debug_mode=True, flag_inf=True)


def test_float_inf_constant_allowed_without_flag():
    source = """
def main() -> Int32
    a: Float64 = 1.0e400
    b: Float32 = -1.0e400
    print(a, b)
    return 0
"""
    llvm = compile_source(source, importer=Importer(), debug_mode=True)
    assert "0x7FF0000000000000" in llvm
    result = run_llvm(llvm)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "inf -inf\n"


def test_float_inf_runtime_errors_with_flag():
    source = """
def main() -> Int32
    x: Float64 = Float64(input("n> "))
    print(x * 2.0)
    return 0
"""
    llvm = compile_source(
        source, importer=Importer(), debug_mode=True, flag_inf=True
    )
    result = run_llvm(llvm, input="1e308\n")
    assert result.returncode == 1, result.stdout
    assert "Non-finite float value" in result.stderr

    ok = compile_source(source, importer=Importer(), debug_mode=True)
    result = run_llvm(ok, input="1e308\n")
    assert result.returncode == 0, result.stderr
    assert result.stdout.endswith("inf\n")


def test_float_div_zero_not_folded():
    source = """
def main() -> Int32
    a: Float64 = 1.0
    b: Float64 = 0.0
    c: Float64 = a / b
    print(c)
    return 0
"""
    result = run_llvm(compile_source(source, importer=Importer(), debug_mode=True))
    assert result.returncode == 0, result.stderr
    assert result.stdout == "inf\n"


def test_none_type_variables():
    source = """
def noop() -> NoneType
    return None

def take(x: NoneType) -> NoneType
    return x

def main() -> Int32
    ab: NoneType = None
    cd: NoneType
    ef: NoneType = noop()
    if ab == None:
        ab = None
    cd = ef
    take(ab)
    take(ef)
    print(1)
    return 0
"""
    for threshold in (0, 10000):
        result = compile_stdlib_run(source, inline_threshold=threshold)
        assert result.returncode == 0, result.stderr
        assert result.stdout == "1\n"


def test_print_none_type():
    source = """
def noop() -> NoneType
    return None

def main() -> Int32
    ab: NoneType = None
    ac: NoneType = noop()
    print(ab, ac)
    print("x", ab, 5)
    return 0
"""
    for threshold in (0, 10000):
        result = compile_stdlib_run(source, inline_threshold=threshold)
        assert result.returncode == 0, result.stderr
        assert result.stdout == "None None\nx None 5\n"


def test_list_literal_get_set_print():
    result = compile_stdlib_run(
        """
def main() -> Int32
    xs: List[Int32] = [1, 2, 3, 4]
    xs[3] = 2
    print(xs)
    print(xs[0] + xs[1])
    return 0
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "[1, 2, 3, 2]\n3\n"


def test_list_float_string_bool_none():
    result = compile_stdlib_run(
        """
def main() -> Int32
    fs: List[Float64] = [1.5, 2.5]
    print(fs)
    ss: List[String] = ["a", "bb"]
    print(ss)
    bs: List[Bool] = [True, False]
    print(bs)
    ns: List[NoneType] = [None, None]
    print(ns)
    return 0
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        "[1.500000, 2.500000]\n[a, bb]\n[true, false]\n[None, None]\n"
    )


def test_list_empty_and_reassign():
    result = compile_stdlib_run(
        """
def main() -> Int32
    xs: List[Int32] = []
    print(xs)
    xs = [1, 2]
    print(xs)
    return 0
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "[]\n[1, 2]\n"


def test_list_type_adapts_literals():
    result = compile_stdlib_run(
        """
def main() -> Int32
    xs: List[Int64] = [1, 2, 3]
    print(xs)
    return 0
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "[1, 2, 3]\n"


def test_list_as_function_param_and_return():
    result = compile_stdlib_run(
        """
def first(xs: List[Int32]) -> Int32
    return xs[0]

def sum2(xs: List[Int32]) -> Int32
    return xs[0] + xs[1]

def make() -> List[Int32]
    return [7, 8, 9]

def main() -> Int32
    xs: List[Int32] = [10, 20, 30]
    print(first(xs))
    print(first(make()))
    print(sum2([5, 6]))
    return 0
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "10\n7\n11\n"


def test_list_in_struct():
    result = compile_stdlib_run(
        """
struct Bag:
    items: List[Int32]

def main() -> Int32
    b: Bag = Bag(items=[1, 2, 3])
    b.items[1] = 7
    print(b.items)
    print(b.items[0] + b.items[1] + b.items[2])
    return 0
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "[1, 7, 3]\n11\n"


def test_list_index_types():
    result = compile_stdlib_run(
        """
def main() -> Int32
    xs: List[Int32] = [10, 20, 30]
    i8: Int8 = 2
    ui: UInt64 = 0
    print(xs[i8])
    print(xs[ui])
    return 0
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "30\n10\n"


def test_list_index_out_of_bounds_errors():
    for src in (
        """
def main() -> Int32
    xs: List[Int32] = [1, 2]
    print(xs[5])
    return 0
""",
        """
def main() -> Int32
    xs: List[Int32] = [1, 2]
    print(xs[-1])
    return 0
""",
    ):
        result = compile_stdlib_run(src)
        assert result.returncode != 0
        assert "List index out of bounds" in result.stderr


def test_index_assign_uses_values():
    result = compile_stdlib_run(
        """
def main() -> Int32
    xs: List[Int32] = [1, 2, 3]
    i: Int32 = 1
    xs[i] = xs[0] + xs[2]
    print(xs)
    return 0
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "[1, 4, 3]\n"


def test_nested_list_chained_index():
    result = compile_stdlib_run(
        """
def main() -> Int32
    xd: List[List[Int32]] = [[1, 2], [3, 4]]
    xd[0][1] = 9
    print(xd)
    print(xd[1][0])
    return 0
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "[[1, 9], [3, 4]]\n3\n"


def test_deeply_nested_list_print():
    result = compile_stdlib_run(
        """
def main() -> Int32
    xdd: List[List[List[Int32]]] = [[[1, 3]]]
    print(xdd)
    xdd[0][0][1] = 7
    print(xdd)
    return 0
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "[[[1, 3]]]\n[[[1, 7]]]\n"


def test_nested_list_struct_field():
    result = compile_stdlib_run(
        """
struct Grid:
    rows: List[List[Int32]]

def main() -> Int32
    g: Grid = Grid(rows=[[1, 2], [3, 4]])
    g.rows[1][0] = 8
    print(g.rows)
    return 0
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "[[1, 2], [8, 4]]\n"


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
    test_float_inf_constant_errors_with_flag()
    test_float_inf_constant_allowed_without_flag()
    test_float_inf_runtime_errors_with_flag()
    test_float_div_zero_not_folded()
    test_none_type_variables()
    test_print_none_type()
    test_list_literal_get_set_print()
    test_list_float_string_bool_none()
    test_list_empty_and_reassign()
    test_list_type_adapts_literals()
    test_list_as_function_param_and_return()
    test_list_in_struct()
    test_list_index_types()
    test_list_index_out_of_bounds_errors()
    test_index_assign_uses_values()
    test_nested_list_chained_index()
    test_deeply_nested_list_print()
    test_nested_list_struct_field()
    print("compile_test OK")


CLASS_INHERITANCE_SOURCE = """
class Car:
    def __init__(self: Car, brand: String):
        self.brand: String = brand
    def get_brand(self: Car):
        return self.brand
    def mileage(self: Car) -> Int32:
        return 0

class DMW(Car):
    def __init__(self DMW):
        self.brand = "DMW"
    def mileage(self: DMW) -> Int32:
        return 100

def main() -> Int32
    c: Car = Car("BMW")
    d: DMW = DMW()
    print(c.get_brand())
    print(d.get_brand())
    print(c.mileage() + d.mileage())
    return 0
"""


def test_class_inheritance_and_override():
    result = compile_stdlib_run(CLASS_INHERITANCE_SOURCE)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "BMW\nDMW\n100\n"


def test_class_inheritance_inlined():
    result = compile_stdlib_run(CLASS_INHERITANCE_SOURCE, inline_threshold=10000)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "BMW\nDMW\n100\n"


CLASS_COUNTER_SOURCE = """
class Counter:
    def __init__(self: Counter, start: Int32 = 5):
        self.count: Int32 = start
    def bump(self: Counter, amount: Int32 = 1) -> Int32:
        self.count = self.count + amount
        return self.count
    def get(self: Counter) -> Int32:
        return self.count

def main() -> Int32
    c: Counter = Counter()
    c.bump()
    n: Int32 = c.bump(2)
    print(n)
    print(c.get())
    return 0
"""


def test_class_methods_default_args_and_value_semantics():
    result = compile_stdlib_run(CLASS_COUNTER_SOURCE)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "7\n5\n"


CLASS_STRUCT_FIELD_SOURCE = """
class Vec2:
    def __init__(self: Vec2, x: Int32, y: Int32):
        self.x: Int32 = x
        self.y: Int32 = y
    def sum(self: Vec2) -> Int32:
        return self.x + self.y

struct Pair:
    a: Vec2
    b: Vec2

def main() -> Int32
    p: Pair = Pair(a=Vec2(1, 2), b=Vec2(3, 4))
    print(p.a.sum() + p.b.sum())
    return 0
"""


def test_class_inside_struct_multiple_field_decls():
    result = compile_stdlib_run(CLASS_STRUCT_FIELD_SOURCE)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "10\n"


def test_class_field_assign():
    result = compile_stdlib_run(
        """
class Car:
    def __init__(self: Car, brand: String):
        self.brand: String = brand
    def get_brand(self: Car):
        return self.brand
def main() -> Int32
    c: Car = Car("BMW")
    c.brand = "Audi"
    print(c.get_brand())
    return 0
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "Audi\n"


def test_class_without_constructor():
    result = compile_stdlib_run(
        """
class Tag:
    def label(self: Tag):
        return "tag"
def main() -> Int32
    t: Tag = Tag()
    print(t.label())
    return 0
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "tag\n"


def test_class_method_returns_class():
    result = compile_stdlib_run(
        """
class Vec2:
    def __init__(self: Vec2, x: Int32):
        self.x: Int32 = x
    def scaled(self: Vec2, k: Int32) -> Vec2:
        r: Vec2 = Vec2(self.x * k)
        return r
    def get(self: Vec2) -> Int32:
        return self.x
def main() -> Int32
    v: Vec2 = Vec2(3)
    w: Vec2 = v.scaled(4)
    print(w.get())
    return 0
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "12\n"


def test_class_chained_method_call():
    result = compile_stdlib_run(
        """
class Vec2:
    def __init__(self: Vec2, x: Int32):
        self.x: Int32 = x
    def get(self: Vec2) -> Int32:
        return self.x
class Holder:
    def __init__(self: Holder, v: Vec2):
        self.v: Vec2 = v
    def inner(self: Holder) -> Vec2:
        return self.v
def main() -> Int32
    h: Holder = Holder(Vec2(9))
    print(h.inner().get())
    return 0
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "9\n"


def test_print_struct():
    result = compile_stdlib_run(
        """
struct Point:
    x: Int32
    y: Int32

struct Line:
    a: Point
    b: Point

def main() -> Int32
    p: Point = Point(x=3, y=4)
    l: Line = Line(a=Point(x=1, y=2), b=Point(x=3, y=4))
    print(p)
    print(l)
    return 0
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "{x: 3, y: 4}\n{a: {x: 1, y: 2}, b: {x: 3, y: 4}}\n"


def test_print_struct_field_types():
    result = compile_stdlib_run(
        """
struct Empty:

struct Mix:
    s: String
    n: NoneType
    f: Float64
    big: Int256
    flag: Bool

def main() -> Int32
    e: Empty = Empty()
    m: Mix = Mix(s="hi", n=None, f=2.25, big=123456789012345678901234567890, flag=True)
    print(e)
    print(m)
    return 0
"""
    )
    assert result.returncode == 0, result.stderr
    assert (
        result.stdout
        == "{}\n{s: hi, n: None, f: 2.250000, big: 123456789012345678901234567890, flag: true}\n"
    )


def test_print_list_of_structs():
    result = compile_stdlib_run(
        """
struct Vec:
    x: Float32
    y: Bool

def main() -> Int32
    v: Vec = Vec(x=1.5, y=True)
    l: List[Vec] = [Vec(x=0.0, y=False), v]
    print(l)
    return 0
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "[{x: 0.000000, y: false}, {x: 1.500000, y: true}]\n"


def test_print_class_without_str():
    result = compile_stdlib_run(
        """
class Car:
    def __init__(self: Car, brand: String):
        self.brand: String = brand

def main() -> Int32
    c: Car = Car("BMW")
    print(c)
    return 0
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "{brand: BMW}\n"


def test_print_class_with_str():
    result = compile_stdlib_run(
        """
class Bike:
    def __init__(self: Bike, brand: String):
        self.brand: String = brand
    def __str__(self: Bike) -> String:
        return f"Bike({self.brand})"

def main() -> Int32
    b: Bike = Bike("Gazelle")
    print(b)
    return 0
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "Bike(Gazelle)\n"


def test_print_class_with_str_no_field_use():
    result = compile_stdlib_run(
        """
class Thing:
    def __init__(self: Thing, n: Int32):
        self.n: Int32 = n
    def __str__(self: Thing) -> String:
        return f"Thing({self.n})"

def main() -> Int32
    t: Thing = Thing(7)
    print(t)
    print(t.__str__())
    return 0
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "Thing(7)\nThing(7)\n"


def test_string_alignment_tagged_pointers():
    result = compile_stdlib_run(
        """
class Car:
    def __init__(self: Car, brand: String):
        self.brand: String = brand
    def get_brand(self: Car):
        return self.brand
class DMW(Car):
    def __init__(self: DMW):
        self.brand = "DMW"
def main() -> Int32
    du: DMW = DMW()
    b: String = du.get_brand()
    print(b)
    s: String = f"brand={b}"
    print(s)
    return 0
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "DMW\nbrand=DMW\n"


def test_print_inherited_str():
    result = compile_stdlib_run(
        """
class Car:
    def __init__(self: Car, brand: String):
        self.brand: String = brand
    def __str__(self: Car) -> String:
        return f"Car(brand={self.brand})"
class DMW(Car):
    def __init__(self: DMW):
        self.brand = "DMW"
def main() -> Int32
    du: DMW = DMW()
    print(du)
    return 0
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "Car(brand=DMW)\n"


def test_print_inherited_str_extra_fields():
    result = compile_stdlib_run(
        """
class Car:
    def __init__(self: Car, brand: String):
        self.brand: String = brand
    def __str__(self: Car) -> String:
        return f"Car(brand={self.brand})"
class Truck(Car):
    def __init__(self: Truck, brand: String, capacity: Int32):
        self.brand = brand
        self.capacity: Int32 = capacity
def main() -> Int32
    t: Truck = Truck("Volvo", 5000)
    print(t)
    return 0
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "Car(brand=Volvo)\n"


def test_print_overridden_str():
    result = compile_stdlib_run(
        """
class Car:
    def __init__(self: Car, brand: String):
        self.brand: String = brand
    def __str__(self: Car) -> String:
        return f"Car(brand={self.brand})"
class Boat(Car):
    def __init__(self: Boat, brand: String):
        self.brand = brand
    def __str__(self: Boat) -> String:
        return f"Boat(brand={self.brand})"
def main() -> Int32
    b: Boat = Boat("Sunseeker")
    print(b)
    return 0
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "Boat(brand=Sunseeker)\n"
