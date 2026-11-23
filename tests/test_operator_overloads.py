"""End-to-end tests for class operator overloads (dunder methods)."""
import io
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from compile_test import compile_stdlib_run
from compiler.threadon.compiler import compile_source
from compiler.threadon.importer import Importer
from compiler.threadon.nodes import BinaryExpr, UnaryExpr, VarExpr
from compiler.threadon.parser import Parser


def compile_error(source, needle):
    """Assert a Threadon source is rejected with the expected message."""
    with pytest.raises(Exception) as exc:
        compile_source(source, importer=Importer())
    message = str(exc.value).replace("\x1b", "")
    assert needle in message, message


def run(source):
    result = compile_stdlib_run(source)
    assert result.returncode == 0, result.stderr
    return result.stdout


POINT_OPS = """
class Point:
    x: Int32
    y: Int32

    def __init__(self: Point, x: Int32, y: Int32)
        self.x = x
        self.y = y

    puredef __eq__(self: Point, other: Point) -> Bool
        return self.x == other.x and self.y == other.y

    def __add__(self: Point, other: Point) -> Point
        return Point(self.x + other.x, self.y + other.y)

    def __getitem__(self: Point, i: Int32) -> Int32
        if i == 0:
            return self.x
        return self.y

    def __setitem__(self: Point, i: Int32, v: Int32) -> Point
        if i == 0:
            self.x = v
        else:
            self.y = v
        return self
"""


def test_eq_add_and_index_read_write():
    result = run(POINT_OPS + """
def main() -> Int32
    a: Point = Point(1, 2)
    b: Point = Point(1, 2)
    c: Point = Point(10, 20)
    if a == b:
        print("equal")
    d: Point = a + c
    print(d.x, d.y)
    print(a[0], a[1])
    a[0] = 7
    a[1] = 8
    print(a.x, a.y)
    return 0
""")
    assert result == "equal\n11 22\n1 2\n7 8\n"


def test_all_comparison_overloads():
    result = run("""
class N:
    v: Int32
    def __init__(self: N, v: Int32)
        self.v = v
    puredef __eq__(self: N, other: N) -> Bool
        return self.v == other.v
    def __ne__(self: N, other: N) -> Bool
        return self.v != other.v
    def __lt__(self: N, other: N) -> Bool
        return self.v < other.v
    def __gt__(self: N, other: N) -> Bool
        return self.v > other.v
    def __le__(self: N, other: N) -> Bool
        return self.v <= other.v
    def __ge__(self: N, other: N) -> Bool
        return self.v >= other.v

def main() -> Int32
    a: N = N(5)
    b: N = N(3)
    c: N = N(5)
    print(a == c, a == b, a != b, a != c)
    print(a < b, a > b, a <= c, a >= c)
    return 0
""")
    assert result == "True False True False\nFalse True True True\n"


def test_all_arithmetic_overloads():
    result = run("""
class N:
    v: Int32
    def __init__(self: N, v: Int32)
        self.v = v
    def __add__(self: N, other: N) -> N
        return N(self.v + other.v)
    def __sub__(self: N, other: N) -> N
        return N(self.v - other.v)
    def __mul__(self: N, other: N) -> N
        return N(self.v * other.v)
    def __truediv__(self: N, other: N) -> N
        return N(Int32(self.v / other.v))
    def __floordiv__(self: N, other: N) -> N
        return N(self.v // other.v)
    def __mod__(self: N, other: N) -> N
        return N(self.v % other.v)

def main() -> Int32
    a: N = N(7)
    b: N = N(3)
    print((a + b).v, (a - b).v, (a * b).v)
    print((a / b).v, (a // b).v, (a % b).v)
    return 0
""")
    assert result == "10 4 21\n2 2 1\n"


def test_unary_negate_and_bool_overloads():
    result = run("""
class N:
    v: Int32
    def __init__(self: N, v: Int32)
        self.v = v
    def __neg__(self: N) -> N
        return N(-self.v)
    def __bool__(self: N) -> Bool
        return self.v != 0

def main() -> Int32
    a: N = N(4)
    z: N = N(0)
    print((-a).v, not a, not z)
    return 0
""")
    assert result == "-4 True False\n"


def test_getitem_may_return_any_type():
    result = run("""
class Bag:
    def __getitem__(self: Bag, key: String) -> List[Int32]
        return [1, 2, 3]

def main() -> Int32
    bag: Bag = Bag()
    xs: List[Int32] = bag["x"]
    print(xs[1])
    return 0
""")
    assert result == "2\n"


def test_setitem_through_field_persists():
    result = run("""
class Cell:
    v: Int32
    def __init__(self: Cell, v: Int32)
        self.v = v
    def __setitem__(self: Cell, i: Int32, x: Int32) -> Cell
        self.v = x + i
        return self

class Holder:
    cell: Cell
    def __init__(self: Holder, c: Cell)
        self.cell = c

def main() -> Int32
    h: Holder = Holder(Cell(10))
    h.cell[2] = 40
    print(h.cell.v)
    return 0
""")
    assert result == "42\n"


def test_augmented_assignment_uses_add():
    result = run("""
class N:
    v: Int32
    def __init__(self: N, v: Int32)
        self.v = v
    def __add__(self: N, other: N) -> N
        return N(self.v + other.v)

def main() -> Int32
    a: N = N(1)
    b: N = N(4)
    a += b
    print(a.v)
    return 0
""")
    assert result == "5\n"


def test_pure_function_can_use_eq_but_not_add():
    result = run("""
class N:
    v: Int32
    def __init__(self: N, v: Int32)
        self.v = v
    puredef __eq__(self: N, other: N) -> Bool
        return self.v == other.v
    def __add__(self: N, other: N) -> N
        return N(self.v + other.v)

puredef same(a: N, b: N) -> Bool
    return a == b

def main() -> Int32
    a: N = N(3)
    b: N = N(3)
    print(same(a, b))
    return 0
""")
    assert result == "True\n"
    compile_error("""
class N:
    v: Int32
    def __init__(self: N, v: Int32)
        self.v = v
    def __add__(self: N, other: N) -> N
        return N(self.v + other.v)

puredef combine(a: N, b: N) -> N
    return a + b

def main() -> Int32
    return 0
""", "may not call non-pure function 'N.__add__'")


def test_eq_must_be_pure_and_return_bool():
    compile_error("""
class A:
    v: Int32
    def __eq__(self: A, other: A) -> Bool
        return self.v == other.v

def main() -> Int32
    return 0
""", "Method '__eq__' must be declared with puredef")
    compile_error("""
class A:
    v: Int32
    puredef __eq__(self: A, other: A) -> Int32
        return self.v

def main() -> Int32
    return 0
""", "Method '__eq__' must return Bool")


def test_eq_purity_is_checked_inside_body():
    compile_error("""
side: Int32 = 0
class A:
    v: Int32
    puredef __eq__(self: A, other: A) -> Bool
        side = 1
        return self.v == other.v

def main() -> Int32
    return 0
""", "may not write global variable 'side'")
    compile_error("""
class A:
    v: Int32
    puredef __eq__(self: A, other: A) -> Bool
        print("side effect")
        return self.v == other.v

def main() -> Int32
    return 0
""", "may not call non-pure function 'print'")


def test_arithmetic_return_and_operand_rules():
    compile_error("""
class A:
    v: Int32
    def __init__(self: A, v: Int32)
        self.v = v
    def __add__(self: A, other: A) -> Int32
        return self.v

def main() -> Int32
    return 0
""", "Method '__add__' must return A")
    compile_error("""
class A:
    v: Int32
    def __init__(self: A, v: Int32)
        self.v = v
    def __add__(self: A, other: Int32) -> A
        return A(self.v + other)

def main() -> Int32
    return 0
""", "Method '__add__' operand must be A")
    compile_error("""
class A:
    v: Int32
    def __init__(self: A, v: Int32)
        self.v = v
    def __add__(self: A, other: A) -> A
        return A(self.v + other.v)
class B:
    w: Int32

def main() -> Int32
    a: A = A(1)
    b: B = B()
    c: A = a + b
    return 0
""", "Method '__add__' argument 'other' expects type A, got B")


def test_index_overload_signatures():
    compile_error("""
class A:
    def __getitem__(self: A) -> Int32
        return 1

def main() -> Int32
    return 0
""", "Method '__getitem__' must take 1 parameter")
    compile_error("""
class A:
    def __setitem__(self: A, i: Int32, v: Int32) -> NoneType
        return None

def main() -> Int32
    return 0
""", "Method '__setitem__' must return A")
    compile_error("""
class A:
    def __getitem__(self: A, i: Int32) -> Int32
        return i

def main() -> Int32
    a: A = A()
    a[0] = 3
    return 0
""", "has no method '__setitem__'")


def test_inherited_binary_and_negate_overloads_are_rejected():
    compile_error("""
class A:
    v: Int32
    def __init__(self: A, v: Int32)
        self.v = v
    def __add__(self: A, other: A) -> A
        return A(self.v + other.v)
class B(A):
    w: Int32
    def __init__(self: B, v: Int32, w: Int32)
        self.v = v
        self.w = w

def main() -> Int32
    a: B = B(1, 2)
    b: B = B(3, 4)
    c: B = a + b
    return 0
""", "inherits '__add__' from 'A'")
    compile_error("""
class A:
    v: Int32
    def __init__(self: A, v: Int32)
        self.v = v
    def __neg__(self: A) -> A
        return A(-self.v)
class B(A):
    w: Int32
    def __init__(self: B, v: Int32, w: Int32)
        self.v = v
        self.w = w

def main() -> Int32
    a: B = B(1, 2)
    b: B = -a
    return 0
""", "must return 'B', got 'A'")


def test_inherited_getitem_is_allowed():
    result = run("""
class A:
    v: Int32
    def __init__(self: A, v: Int32)
        self.v = v
    def __getitem__(self: A, i: Int32) -> Int32
        return self.v + i
class B(A):
    w: Int32
    def __init__(self: B, v: Int32, w: Int32)
        self.v = v
        self.w = w

def main() -> Int32
    b: B = B(10, 20)
    print(b[5])
    return 0
""")
    assert result == "15\n"


def test_parser_desugar_helper_handles_other_nodes():
    """The helper leaves nodes it does not handle untouched."""
    parser = Parser()
    parser.declare_var("x", "Int32")
    var = VarExpr("x")
    assert parser._desugar_operator(var) is var
    unknown_unary = UnaryExpr("?", var)
    assert parser._desugar_operator(unknown_unary) is unknown_unary
    boolean = BinaryExpr(var, "and", var)
    assert parser._desugar_operator(boolean) is boolean


def test_invalid_index_assignment_target():
    with pytest.raises(Exception) as exc:
        compile_source("""
def main() -> Int32
    xs: List[Int32] = [1, 2]
    xs[0:1] = [3]
    return 0
""", importer=Importer())
    assert "Invalid index assignment target" in str(exc.value)


def test_inherited_setitem_is_rejected():
    compile_error("""
class A:
    v: Int32
    def __setitem__(self: A, i: Int32, x: Int32) -> A
        self.v = x
        return self
class B(A):
    w: Int32

def main() -> Int32
    b: B = B()
    b[0] = 3
    return 0
""", "inherits '__setitem__' from 'A'")
