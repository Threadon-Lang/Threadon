"""Real compiler tests for *args and **kwargs support."""
import io
import subprocess
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from compiler.threadon.compiler import compile_source
from compiler.threadon.importer import Importer
from compiler.threadon.parser import Parser


def run_ir(llvm, expected):
    with tempfile.NamedTemporaryFile("w", suffix=".ll", delete=False) as f:
        f.write(llvm)
        path = f.name
    try:
        result = subprocess.run(["lli", path], capture_output=True, text=True, timeout=60)
    finally:
        Path(path).unlink(missing_ok=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == expected


def parse_fail(source, expected):
    p = Parser()
    with redirect_stdout(io.StringIO()) as output:
        with pytest.raises(SystemExit):
            p.parse(source)
    assert expected in output.getvalue()


def test_function_args_and_kwargs_run():
    source = """
def total(a: Int32, *rest: List[Int32], **opts: Dict[String, Int32]) -> Int32
    s: Int32 = a
    for x in rest:
        s += x
    for k in opts:
        s += opts[k]
    return s

def main() -> Int32
    print(total(1, 2, 3, x=4, y=5))
    return 0
"""
    run_ir(compile_source(source), "15\n")


def test_args_with_defaults_and_empty_containers_run():
    source = """
def total(a: Int32 = 10, *rest: List[Int32], **opts: Dict[String, Int32]) -> Int32
    s: Int32 = a
    for x in rest:
        s += x
    for k in opts:
        s += opts[k]
    return s

def main() -> Int32
    print(total())
    print(total(1, *[], **{}))
    print(total(1, 2, **{}))
    return 0
"""
    run_ir(compile_source(source), "10\n1\n3\n")


def test_star_and_starstar_spread_containers_run():
    source = """
def total(a: Int32, *rest: List[Int32], **opts: Dict[String, Int32]) -> Int32
    s: Int32 = a
    for x in rest:
        s += x
    for k in opts:
        s += opts[k]
    return s

def main() -> Int32
    xs: List[Int32] = [2, 3]
    opts: Dict[String, Int32] = {"a": 4, "b": 5}
    print(total(1, *xs, **opts))
    return 0
"""
    run_ir(compile_source(source), "15\n")


def test_kwargs_only_runs():
    source = """
def total(a: Int32, **opts: Dict[String, Int32]) -> Int32
    s: Int32 = a
    for k in opts:
        s += opts[k]
    return s

def main() -> Int32
    print(total(1, x=2, y=3))
    return 0
"""
    run_ir(compile_source(source), "6\n")


def test_method_and_constructor_variadics_run():
    source = """
class Acc:
    total: Int32
    def __init__(self: Acc, start: Int32, **opts: Dict[String, Int32])
        self.total = start
        for k in opts:
            v: Int32 = opts[k]
            self.total = self.total + v
    def add(self: Acc, *xs: List[Int32]) -> Int32
        for x in xs:
            self.total = self.total + x
        return self.total

def main() -> Int32
    a: Acc = Acc(1, x=2, y=3)
    print(a.add(4, 5))
    return 0
"""
    run_ir(compile_source(source), "15\n")


def test_variadic_call_survives_inlining():
    source = """
def total(*xs: List[Int32]) -> Int32
    s: Int32 = 0
    for x in xs:
        s += x
    return s

def main() -> Int32
    print(total(1, 2, 3))
    return 0
"""
    run_ir(compile_source(source, inline_threshold=100), "6\n")


def test_imported_variadic_function_runs():
    importer = Importer()
    importer.register_source("lib", """
def total(*xs: List[Int32]) -> Int32
    s: Int32 = 0
    for x in xs:
        s += x
    return s
""")
    source = """
import lib

def main() -> Int32
    print(lib.total(2, 3, 4))
    return 0
"""
    run_ir(compile_source(source, importer=importer), "9\n")


def test_lazy_imported_variadic_function_runs():
    importer = Importer()
    importer.register_source("lib", """
def total(*xs: List[Int32]) -> Int32
    s: Int32 = 0
    for x in xs:
        s += x
    return s
""")
    source = """
lazyimport lib

def main() -> Int32
    print(lib.total(2, 3))
    return 0
"""
    run_ir(compile_source(source, importer=importer), "5\n")


@pytest.mark.parametrize("source, expected", [
    ("def f(*xs: Int32) -> NoneType\n    return\n", "*args parameter must have type List[T]"),
    ("def f(**xs: List[Int32]) -> NoneType\n    return\n", "**kwargs parameter must have type Dict[String, T]"),
    ("def f(**xs: Dict[Int32, Int32]) -> NoneType\n    return\n", "**kwargs parameter must have type Dict[String, T]"),
    ("def f(*a: List[Int32], *b: List[Int32]) -> NoneType\n    return\n", "Variadic parameters must come last"),
    ("def f(**a: Dict[String, Int32], **b: Dict[String, Int32]) -> NoneType\n    return\n", "Variadic parameters must come last"),
    ("def f(*a: List[Int32], b: Int32) -> NoneType\n    return\n", "Variadic parameters must come last"),
    ("def f(*a: List[Int32] = []) -> NoneType\n    return\n", "cannot have a default value"),
    ("def f(**a: Dict[String, Int32] = {}) -> NoneType\n    return\n", "cannot have a default value"),
])
def test_invalid_variadic_signatures_are_rejected(source, expected):
    parse_fail(source, expected)


@pytest.mark.parametrize("signature, expected", [
    ("*xs: List[Int32], y: Int32", "Variadic parameters must come last"),
    ("*a: List[Int32], *b: List[Int32]", "Variadic parameters must come last"),
    ("**a: Dict[String, Int32], **b: Dict[String, Int32]",
     "Variadic parameters must come last"),
    ("*xs: List[Int32] = []", "cannot have a default value"),
])
def test_invalid_variadic_method_signatures_are_rejected(signature, expected):
    source = f"""class C:
    x: Int32
    def f(self: C, {signature}) -> NoneType
        return
"""
    parse_fail(source, expected)


@pytest.mark.parametrize("call, expected", [
    ("f(1, z=3)", "unexpected keyword argument 'z'"),
    ("f(1, a=2)", "multiple values for argument 'a'"),
    ("f(a=1, a=2)", "multiple values for argument 'a'"),
    ("f(*[1])", "does not accept *arguments"),
    ("f(**{})", "does not accept **keyword arguments"),
])
def test_invalid_variadic_calls_without_specs_are_rejected(call, expected):
    source = f"""
def f(a: Int32) -> Int32
    return a

def main() -> Int32
    return {call}
"""
    parse_fail(source, expected)


@pytest.mark.parametrize("call, expected", [
    ("f(1, *[2], 3)", "cannot mix extra positional arguments with *arguments"),
    ("f(1, **{}, z=3)", "cannot mix keyword arguments with **keyword arguments"),
    ("f(1, *[2], *[3])", "at most one *arguments value"),
    ("f(1, **{}, **{})", "at most one **keyword arguments value"),
    ("f(1, z=2, z=3)", "multiple values for keyword 'z'"),
])
def test_invalid_variadic_call_combinations_are_rejected(call, expected):
    source = f"""
def f(a: Int32, *rest: List[Int32], **opts: Dict[String, Int32]) -> Int32
    return a

def main() -> Int32
    return {call}
"""
    parse_fail(source, expected)


def test_builtin_spread_arguments_are_rejected():
    parse_fail("def main() -> NoneType\n    print(*[1])\n    return\n",
               "Builtin 'print' does not accept keyword or spread arguments")


def test_list_method_spread_arguments_are_rejected():
    parse_fail(
        "def main() -> NoneType\n    xs: List[Int32] = []\n    xs.append(*[1])\n    return\n",
        "List method 'append' does not accept keyword or spread arguments",
    )


def test_range_spread_arguments_are_rejected():
    parse_fail("def main() -> NoneType\n    for i in range(*[2]):\n        pass\n    return\n",
               "range() does not accept keyword or spread arguments")


def test_class_without_init_rejects_variadic_arguments():
    parse_fail(
        "class C:\n    x: Int32\n\ndef main() -> NoneType\n    c: C = C(**{})\n    return\n",
        "has no '__init__' taking arguments",
    )
