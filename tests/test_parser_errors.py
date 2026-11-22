"""Error-path tests for the parser.

Each snippet below is a malformed but lexically valid program; the parser must
reject it with a diagnostic rather than producing an AST.  Checking the
message keeps these from being vacuous "raises SystemExit" tests.
"""
import io
from contextlib import redirect_stdout

import pytest

from compiler.threadon.parser import Parser


def parse_fail(code, expected):
    p = Parser()
    with redirect_stdout(io.StringIO()) as output:
        with pytest.raises(SystemExit):
            p.parse(code)
    assert expected in output.getvalue()


@pytest.mark.parametrize("code,expected", [
    ("def f() -> Int32\n    if true\n        return 1\n    return 0\n",
     "Expected ':' after 'if' condition"),
    ("def f() -> Int32\n    if 1:\n        return 1\n    return 0\n",
     "If condition must be Bool"),
    ("def f(x: Bool) -> Int32\n    if x:\n        return 1\n    else\n        return 2\n",
     "Expected ':' after 'else'"),
    ("def f(x: Bool) -> Int32\n    while x\n        x = false\n    return 0\n",
     "Expected ':' after 'while' condition"),
    ("def f() -> Int32\n    while 1:\n        x = 1\n    return 0\n",
     "While condition must be Bool"),
    ("def f() -> Int32\n    for x xs:\n        print(x)\n    return 0\n",
     "Expected 'in' after the loop variable"),
    ("def f() -> Int32\n    for x in\n        print(x)\n    return 0\n",
     "Invalid 'for' statement"),
    ("def f() -> Int32\n    for in xs:\n        print(x)\n    return 0\n",
     "Expected a loop variable after 'for'"),
    ("def f() -> Int32\n    for x in 1:\n        print(x)\n    return 0\n",
     "is not iterable"),
    ("import\n", "Invalid import statement"),
    ("import .\n", "Expected module name in import"),
    ("import foo bar\n", "Unexpected token after module name"),
    ("from math import *\n", "Wildcard imports (*) are not allowed"),
    ("from math import\n", "Expected at least one name to import"),
    ("import math as\n", "Expected alias name after 'as'"),
    ("import math,\n", "Unexpected token after module name"),
    ("def f() -> Int32\n    class C\n        pass\n    return 0\n",
     "Class must be declared at the top level"),
    ("class\n    x: Int32 = 1\n", "Class must have a name"),
    ("class C(A, B)\n    x: Int32 = 1\n",
     "Expected a single base class name in parentheses"),
    ("class C = 1\n", "Unexpected token in class declaration"),
    ("struct\n    x: Int32\n", "Struct must have a name"),
])
def test_rejected_declarations_and_statements(code, expected):
    parse_fail(code, expected)


@pytest.mark.parametrize("code,expected", [
    ("def f() -> Int32\n    comptime x: Int32 = 1\n    return 0\n",
     "comptime statements are only allowed at module level"),
    ("comptime\n", "Invalid comptime statement"),
    ("comptime : Int32 = 1\n", "Expected variable name after 'comptime'"),
    ("comptime x Int32 = 1\n", "Expected ':' after variable name in comptime"),
    ("comptime x:\n    return 1\n", "Invalid comptime statement"),
    ("thread w:\n    print(1)\n", "Expected 'thread <name>() on <condition>:'"),
    ("thread w() on True\n    print(1)\n", "Expected ':' after 'thread' condition"),
    ("thread w() on 1:\n    print(1)\n", "Thread condition must be Bool"),
    ("def f() -> Int32\n    for x in range(1,2,3,4):\n        print(x)\n    return 0\n",
     "range() expects 1 to 3 arguments"),
])
def test_rejected_comptime_threads_and_ranges(code, expected):
    parse_fail(code, expected)


@pytest.mark.parametrize("code", [
    "def f() -> Int32\n    if True:\n        return 1\n    return 0\n",
    "def f(x: Int32) -> Int32\n    while x > 0:\n        x = x - 1\n    return x\n",
    "import math as m\n",
    "class Point\n    x: Int32\n",
])
def test_valid_control_flow_and_declarations_parse(code):
    assert Parser().parse(code)
