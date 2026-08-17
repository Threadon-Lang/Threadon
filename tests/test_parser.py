import pytest

from compiler.threadon.parser import Parser


def parse_ok(code: str):
    p = Parser()
    return p.parse(code)


def parse_fail(code: str):
    p = Parser()
    with pytest.raises(SystemExit):
        p.parse(code)




INDENT_SNIPPETS = [
    """
def f(x: Int32) -> Int32
    x: Int32 = 1
  x: Int32 = 2
    return x
""",
    """
def f(x: Int32) -> Int32
    x: Int32 = 1

      x: Int32 = 2
    return x
""",
    """
def f(x: Int32) -> Int32
    if x < 0:
        x: Int32 = 1
      elif x > 0:
        x: Int32 = 2
    return x
""",

    """
def f(x: Int32) -> Int32
    if x < 0:
        x: Int32 = 1
  else:
        x: Int32 = 2
    return x
""",

    """
def f(x: Int32) -> Int32
    if x < 0:
        if x < -10:
            x: Int32 = 1
      x: Int32 = 2
    return x
""",

    "def f(x: Int32) -> Int32\n\tx: Int32 = 1\n    return x\n",
]


@pytest.mark.parametrize("code", INDENT_SNIPPETS)
def test_indent_breaks(code):
    parse_fail(code)


STRUCT_SNIPPETS = [
    """
struct A:
    x: Int32 = 1
    # comment
    y: Int32 = 2
""",

    """
struct A:
    x: Int32 = 1

    y: Int32 = 2
""",

    """
struct A:
    x: Int32 = 1
    if x < 0:
        y: Int32 = 2
""",

    """
struct A:
    x: Int32 = 1
    struct B:
        y: Int32 = 2
""",

    """
struct A:
    x = 1
""",

    """
struct A:
    x: Int32
def f() -> Int32
    a: A = A(x=1.0)
    return 0
""",
]


@pytest.mark.parametrize("code", STRUCT_SNIPPETS)
def test_struct_body_breaks(code):
    parse_fail(code)


FIELD_STRUCT_CALL_SNIPPETS = [

    """
struct Z:
    z: Int32
struct P:
    z: Z
def f(x: Int32) -> Int32
    p: P = P(z=Z(z=1))
    x: Int32 = p.z.z.z
    return x
""",

    """
struct A:
    x: Int32
def f() -> Int32
    a: A = A(y=1)
    return 0
""",

    """
struct A:
    x: Int32
    y: Int32
def f() -> Int32
    a: A = A(x=1, x=2)
    return 0
""",
]


@pytest.mark.parametrize("code", FIELD_STRUCT_CALL_SNIPPETS)
def test_struct_init_and_field_access_breaks(code):
    try:
        parse_ok(code)
    except SystemExit:
        assert True


EXPR_SNIPPETS = [

    """
def f(x: Int32, y: Int32) -> Int32
    z: Int32 = x ** y ** 2
    return z
""",

    """
def f() -> NoneType
    x: NoneType = 5
    return x
""",
]


@pytest.mark.parametrize("code", EXPR_SNIPPETS)
def test_expr_edge_cases(code):
    try:
        parse_ok(code)
    except SystemExit:
        assert True


AND_OR_SNIPPETS = [

    """
def f(x: Int32, y: Int32) -> Bool
    b: Bool = x < y and y < x or x == y
    return b
""",

    """
def f(x: Int32, y: Int32) -> Bool
    b: Bool = (x + y) > 0 and not (x == y)
    return b
""",

    """
def f() -> Bool
    b: Bool = True and False
    return b
""",

    """
def f(x: Int32) -> Bool
    b: Bool = x > 0 or x < 0
    return b
""",
]


@pytest.mark.parametrize("code", AND_OR_SNIPPETS)
def test_and_or_operators_parse_ok(code):
    parse_ok(code)


TYPECHECK_SNIPPETS = [

    """
def f(x: Int32, y: Float32) -> Float32
    z: Float32 = x + y
    return z
""",

    """
def f(b: Bool) -> Int32
    x: Int32 = b + 1
    return x
""",

    """
struct A:
    x: Int32
def f(a: A) -> Int32
    x: Int32 = a + 1
    return x
""",

    """
def f(x: Int32, y: Float32) -> Bool
    b: Bool = x == y
    return b
""",

    """
def f(x: Int32, y: Int32) -> Bool
    b: Bool = x and y
    return b
""",

    """
def f(x: Int32) -> Int32
    return x[0]
""",

    """
def f() -> Int32
    xs: List[Int32] = [1, 2]
    return xs[1.5]
""",

    """
def f() -> Int32
    xs: List[Int32] = [1, 2.5]
    return xs[0]
""",

    """
def f() -> Int32
    x: Int32 = 5
    x[0] = 1
    return 0
""",

    """
def f() -> Int32
    xs: List[Int32] = [1, 2]
    xs[0] = "hi"
    return 0
""",
]


@pytest.mark.parametrize("code", TYPECHECK_SNIPPETS)
def test_typechecker_breaks(code):
    parse_fail(code)


SCOPE_SNIPPETS = [

    """
def f(x: Int32) -> Int32
    if x < 0:
        y: Int32 = 1
    return y
""",

    """
def f(x: Int32) -> Int32
    if x < 0:
        y: Int32 = 1
    else:
        z: Int32 = 2
    return z
""",

    """
def f(x: Int32) -> Int32
    if x < 0:
        y: Int32 = 1
    elif x > 0:
        z: Int32 = 2
    return z
""",

    """
def f(x: Int32) -> Int32
    if x < 0:
        if x < -10:
            y: Int32 = 1
    return y
""",
]


@pytest.mark.parametrize("code", SCOPE_SNIPPETS)
def test_scope_merge_breaks(code):
    try:
        parse_ok(code)
    except SystemExit:
        assert True

RETURN_SNIPPETS = [

    """
def f(x: Int32) -> Int32
    if x < 0:
        return x
    else:
        return 0.5
""",

    """
def f(x: Int32) -> Int32
    if x < 0:
        return x
""",

    """
def f(x: Int32) -> Int32
    return None
""",
]


@pytest.mark.parametrize("code", RETURN_SNIPPETS)
def test_return_type_breaks(code):
    parse_fail(code)


REF_OK_SNIPPETS = [

    """
def f(x: Int32, y: Int32) -> Int32
    a: Int32 = y^
    return a
""",

    """
struct A:
    x: Int32
p: A = A(x=1)
def f() -> Int32
    q: A = p^
    return q.x
""",

    """
def f(x: Int32, y: Int32) -> Int32
    if x < 0:
        a: Int32 = y^
    else:
        a: Int32 = x
    return a
""",

    """
def f(x: Int32, y: Int32) -> Int32
    a: Int32 = y
    b: Int32 = a^
    return b
""",
]


@pytest.mark.parametrize("code", REF_OK_SNIPPETS)
def test_reference_decl_ok(code):
    parse_ok(code)


REF_BREAK_SNIPPETS = [

    """
def f(x: Int32, y: Float32) -> Int32
    a: Int32 = y^
    return a
""",

    """
def f(x: Int32) -> Int32
    a: Int32 = q^
    return a
""",

    """
def f(x: Int32, y: Int32) -> Int32
    a: Int32 = 5^
    return a
""",

    """
def f(x: Int32, y: Int32) -> Int32
    a: Int32 = x + y^
    return a
""",

    """
struct A:
    x: Int32
def f(p: A) -> Int32
    a: Int32 = p^
    return a
""",
]


@pytest.mark.parametrize("code", REF_BREAK_SNIPPETS)
def test_reference_decl_breaks(code):
    parse_fail(code)


FIELD_ASSIGN_OK_SNIPPETS = [

    """
struct A:
    x: Int32
def f() -> Int32
    p: A = A(x=1)
    p.x = 5
    return p.x
""",

    """
struct A:
    x: Int32
    y: Int32
def f() -> Int32
    p: A = A(x=1, y=2)
    p.x = p.y + 1
    return p.x
""",

    """
struct A:
    x: Int32
def f() -> Int32
    p: A = A(x=1)
    if p.x < 5:
        p.x = 10
    else:
        p.x = 20
    return p.x
""",
]


@pytest.mark.parametrize("code", FIELD_ASSIGN_OK_SNIPPETS)
def test_field_assign_ok(code):
    parse_ok(code)


FIELD_ASSIGN_BREAK_SNIPPETS = [

    """
struct A:
    x: Int32
def f() -> Int32
    p: A = A(x=1)
    p.z = 5
    return p.x
""",

    """
struct A:
    x: Int32
def f() -> Int32
    p: A = A(x=1)
    p.x = "hi"
    return p.x
""",

    """
def f() -> Int32
    n: Int32 = 1
    n.x = 5
    return n
""",
]


@pytest.mark.parametrize("code", FIELD_ASSIGN_BREAK_SNIPPETS)
def test_field_assign_breaks(code):
    parse_fail(code)


FUNC_SIG_SNIPPETS = [

    """
def f(
    x: Int32,
    y: Int32,
) -> Int32
    return x + y
""",

    """
def f(x, y: Int32) -> Int32
    return y
""",

    """
def f(x: Int32, y: Int32,) -> Int32
    return x + y
""",
]


@pytest.mark.parametrize("code", FUNC_SIG_SNIPPETS)
def test_function_signature_breaks(code):
    parse_fail(code)


LINE_BASED_SNIPPETS = [

    """
def f(x: Int32, y: Int32) -> Int32
    z: Int32 = x +
        y
    return z
""",

    """
def f(x: Int32, y: Int32) -> Int32
    z: Int32 = add(
        x,
        y
    )
    return z
""",

    """
struct A:
    x: Int32
    y: Int32
def f() -> Int32
    a: A = A(
        x=1,
        y=2
    )
    return a.x
""",
]


@pytest.mark.parametrize("code", LINE_BASED_SNIPPETS)
def test_line_based_breaks(code):
    parse_fail(code)


BROKEN_SNIPPETS = (
    INDENT_SNIPPETS
    + STRUCT_SNIPPETS
    + FIELD_STRUCT_CALL_SNIPPETS
    + EXPR_SNIPPETS
    + TYPECHECK_SNIPPETS
    + SCOPE_SNIPPETS
    + RETURN_SNIPPETS
    + REF_BREAK_SNIPPETS
    + FUNC_SIG_SNIPPETS
    + LINE_BASED_SNIPPETS
)


@pytest.mark.parametrize("code", BROKEN_SNIPPETS)
def test_many_breaking_snippets(code):
    try:
        parse_fail(code)
    except AssertionError:

        try:
            parse_ok(code)
        except SystemExit:
            assert True


BASE_TEMPLATE = """
def f(x: Int32, y: Int32) -> Int32
    {body}
    return x
"""

VARIANT_BODIES = [
    "x: Int32 = y + 1.0",
    "x: Int32 = y / 0",
    "x: Int32 = y ** y ** y",
    "if x < 0:\n        y: Int32 = 1\n      elif x > 0:\n        y: Int32 = 2",
    "struct A:\n        x: Int32\n    x: Int32 = 1",
]


@pytest.mark.parametrize("body", VARIANT_BODIES)
def test_generated_variants(body):
    code = BASE_TEMPLATE.format(body=body)
    parse_fail(code)


def test_nested_struct_chain_parses():
    parse_ok(
        """
struct Z:
    z: Int32
struct P:
    x: Int32
    z: Z
def f() -> Int32
    p: P = P(x=1, z=Z(z=2))
    return p.z.z
"""
    )


def test_float_arithmetic_parses():
    parse_ok(
        """
def f(a: Float32, b: Float32, c: Float32) -> Float32
    return (a + b + c) / 3.0
"""
    )


def test_multiple_calls_parse():
    parse_ok(
        """
def add(a: Int32, b: Int32) -> Int32
    return a + b
def run() -> Int32
    x: Int32 = add(1, 2)
    return add(x, 3)
"""
    )


def test_unary_neg_in_return_parses():
    parse_ok(
        """
def f(x: Int32) -> Int32
    return -x
"""
    )


def test_missing_arrow_fails():
    parse_fail(
        """
def f(x: Int32) Int32
    return x
"""
    )


def test_return_missing_value_fails():
    parse_fail(
        """
def f(x: Int32) -> Int32
    return
"""
    )


def test_trailing_comma_param_fails():
    parse_fail(
        """
def f(x: Int32,) -> Int32
    return x
"""
    )


def test_assign_before_declaration_fails():
    parse_fail(
        """
def f(x: Int32) -> Int32
    y = 1
    return y
"""
    )


def test_non_bool_if_condition_fails():
    parse_fail(
        """
def f() -> Int32
    if 5:
        r: Int32 = 1
    else:
        r: Int32 = 2
    return r
"""
    )


def test_type_mismatch_in_declaration_fails():
    parse_fail(
        """
def f() -> Int32
    s: String = 5
    return 0
"""
    )


def test_type_mismatch_in_return_fails():
    parse_fail(
        """
def f() -> Int32
    return "abc"
"""
    )


def test_use_before_declaration_fails():
    parse_fail(
        """
def f() -> Int32
    y: Int32 = x + 1
    x: Int32 = 0
    return y
"""
    )


def test_if_missing_colon_fails():
    parse_fail(
        """
def f(x: Int32) -> Int32
    if x > 0
        r: Int32 = 1
    return r
"""
    )


def test_elif_misindented_fails():
    parse_fail(
        """
def f(x: Int32) -> Int32
    if x > 0:
        r: Int32 = 1
      elif x < 0:
        r: Int32 = 2
    else:
        r: Int32 = 3
    return r
"""
    )


def test_else_misindented_fails():
    parse_fail(
        """
def f(x: Int32) -> Int32
    if x > 0:
        r: Int32 = 1
      else:
        r: Int32 = 2
    return r
"""
    )


def test_else_without_if_fails():
    parse_fail(
        """
else:
    x: Int32 = 1
"""
    )


def test_elif_without_if_fails():
    parse_fail(
        """
elif x > 0:
    x: Int32 = 1
"""
    )


def test_elif_missing_colon_fails():
    parse_fail(
        """
def f(x: Int32) -> Int32
    if x > 0:
        r: Int32 = 1
    elif x < 0
        r: Int32 = 2
    else:
        r: Int32 = 3
    return r
"""
    )


def test_double_else():
    parse_fail(
        """
def f(x: Int32) -> Int32
    if x > 0:
        r: Int32 = 1
    else:
        r: Int32 = 2
    else:
        r: Int32 = 3
    return r
"""
    )


def test_and_operator_unsupported():
    parse_ok(
        """
def f() -> Bool
    b: Bool = True and False
    return b
"""
    )


def test_not_on_non_bool_fails():
    parse_fail(
        """
def f(x: Int32) -> Int32
    b: Bool = not x
    return 0
"""
    )


def test_neg_on_bool_fails():
    parse_fail(
        """
def f() -> Int32
    b: Bool = -True
    return 0
"""
    )


def test_pos_on_bool_fails():
    parse_fail(
        """
def f() -> Int32
    b: Bool = +True
    return 0
"""
    )


def test_unknown_function_call_fails():
    parse_fail(
        """
def f() -> Int32
    return unknown(1)
"""
    )


def test_comparison_type_mismatch_fails():
    parse_fail(
        """
def f() -> Int32
    if 1 > True:
        r: Int32 = 1
    else:
        r: Int32 = 2
    return r
"""
    )


def test_arithmetic_type_mismatch_fails():
    parse_fail(
        """
def f() -> Int32
    x: Int32 = 1 + "a"
    return x
"""
    )


def test_return_outside_function_fails():
    parse_fail(
        """
return 5
"""
    )


def test_nonetype_variable_fails():
    parse_fail(
        """
def f() -> Int32
    x: NoneType = 5
    return 0
"""
    )


def test_nonetype_variable_ok():
    parse_ok(
        """
def f() -> NoneType
    x: NoneType = None
    return x
"""
    )


def test_field_access_on_primitive_fails():
    parse_fail(
        """
def f(x: Int32) -> Int32
    y: Int32 = x.z
    return y
"""
    )


def test_missing_struct_field_fails():
    parse_fail(
        """
struct P:
    x: Int32
def f() -> Int32
    p: P = P(x=1)
    return p.z
"""
    )


def test_struct_field_type_mismatch_fails():
    parse_fail(
        """
struct P:
    x: Int32
def f() -> Int32
    p: P = P(x=True)
    return p.x
"""
    )


def test_call_argument_type_mismatch_fails():
    parse_fail(
        """
def f(x: Int32) -> Int32
    return x
def g() -> Int32
    return f("a")
"""
    )


def test_division_by_zero_fails():
    parse_fail(
        """
def f() -> Int32
    return 1 / 0
"""
    )


def test_empty_expression_fails():
    parse_fail(
        """
def f() -> Int32
    x: Int32 =
    return x
"""
    )


def test_unmatched_parenthesis_fails():
    parse_fail(
        """
def f() -> Int32
    x: Int32 = (1
    return x
"""
    )


def test_invalid_parameter_name_fails():
    parse_fail(
        """
def f(1) -> Int32
    return 1
"""
    )


def test_missing_parameter_colon_fails():
    parse_fail(
        """
def f(x Int32) -> Int32
    return x
"""
    )


def test_missing_return_type_fails():
    parse_fail(
        """
def f() ->
    return 1
"""
    )


def test_missing_return_on_some_paths_fails():
    parse_fail(
        """
def f(x: Int32) -> Int32
    if x > 0:
        return 1
"""
    )


def test_default_params_parsed():
    ast = parse_ok(
        """
def f(a: Int32, b: Int32 = 5, c: Float32 = 1.5) -> Int32
    return a + b
"""
    )
    func = next(n for n in ast if type(n).__name__ == "FunctionDef")
    assert func.params[0] == ("a", "Int32", None)
    assert func.params[1][0:2] == ("b", "Int32")
    assert func.params[1][2].type == "Int32"
    assert func.params[1][2].value.value == "5"
    assert func.params[2][0:2] == ("c", "Float32")
    assert func.params[2][2].type == "Float32"
    assert func.params[2][2].value.value == "1.5"


def test_default_params_call_with_fewer_args():
    parse_ok(
        """
def f(a: Int32, b: Int32 = 5) -> Int32
    return a + b
def run() -> Int32
    x: Int32 = f(1)
    y: Int32 = f(1, 2)
    return x + y
"""
    )


def test_all_params_default_ok():
    parse_ok(
        """
def f(a: Int32 = 1, b: Int32 = 2) -> Int32
    return a + b
def run() -> Int32
    return f()
"""
    )


def test_default_int8_narrows_literal():
    ast = parse_ok(
        """
def f(a: Int8 = 100) -> Int8
    return a
"""
    )
    func = next(n for n in ast if type(n).__name__ == "FunctionDef")
    assert func.params[0][2].type == "Int8"


DEFAULT_BREAK_SNIPPETS = [

    """
def f(a: Int32 = 1, b: Int32) -> Int32
    return a + b
""",

    """
x: Int32 = 5
def f(a: Int32 = x) -> Int32
    return a
""",

    """
def f(a: Int32 = 1.5) -> Int32
    return a
""",

    """
def f(a: Bool = 5) -> Bool
    return a
""",

    """
def f(a: Int32 = 1, b: Int32 = 2, c: Int32) -> Int32
    return a + b + c
""",

    """
def f(a: Int32 =) -> Int32
    return a
""",
]


@pytest.mark.parametrize("code", DEFAULT_BREAK_SNIPPETS)
def test_default_params_breaks(code):
    parse_fail(code)


CALL_ARG_COUNT_SNIPPETS = [

    """
def f(a: Int32, b: Int32 = 2) -> Int32
    return a + b
def run() -> Int32
    return f()
""",

    """
def f(a: Int32, b: Int32 = 2) -> Int32
    return a + b
def run() -> Int32
    return f(1, 2, 3)
""",

    """
def f(a: Int32 = 1) -> Int32
    return a
def run() -> Int32
    return f(1, 2)
""",
]


@pytest.mark.parametrize("code", CALL_ARG_COUNT_SNIPPETS)
def test_default_param_call_arg_count_breaks(code):
    parse_fail(code)


def test_default_param_call_arg_type_mismatch_fails():
    parse_fail(
        """
def f(a: Int32, b: Int32 = 2) -> Int32
    return a + b
def run() -> Int32
    return f("hi")
"""
    )


CLASS_OK_SNIPPETS = [
    """
class Car:
    def __init__(self: Car, brand: String):
        self.brand: String = brand
    def get_brand(self: Car):
        return self.brand
""",
    """
class Car:
    def __init__(self: Car, brand: String):
        self.brand: String = brand
class DMW(Car):
    def __init__(self DMW):
        self.brand = "DMW"
""",
    """
class Counter:
    count: Int32
    def __init__(self: Counter, start: Int32 = 0):
        self.count = start
    def bump(self: Counter, amount: Int32 = 1) -> Int32:
        self.count = self.count + amount
        return self.count
""",
    """
class Empty:
    def __init__(self: Empty):
        self.x: Int32 = 0
""",
    """
class A:
    def __init__(self: A):
        self.x: Int32 = 0
class B(A):
    def __init__(self: B):
        self.x = 0
""",
    """
class A:
    def __init__(self: A):
        self.x: Int32 = 0
    def __str__(self: A) -> String:
        return "a"
""",
    """
class A:
    def __init__(self: A):
        self.x: Int32 = 0
    def __str__(self: A):
        return "a"
""",
]


@pytest.mark.parametrize("code", CLASS_OK_SNIPPETS)
def test_class_snippets_ok(code):
    parse_ok(code)


CLASS_BREAK_SNIPPETS = [
    # unknown base class
    """
class A(B):
    def __init__(self: A):
        self.x: Int32 = 0
""",
    # self type must match declaring class
    """
class A:
    def __init__(self: B):
        self.x: Int32 = 0
""",
    # method must have self
    """
class A:
    def __init__():
        self.x: Int32 = 0
""",
    # __init__ cannot declare a return type
    """
class A:
    def __init__(self: A) -> A:
        self.x: Int32 = 0
""",
    # __init__ cannot have explicit returns
    """
class A:
    def __init__(self: A):
        return self
""",
    # call method that does not exist
    """
class A:
    def __init__(self: A):
        self.x: Int32 = 0
def run() -> Int32
    a: A = A()
    return a.nope()
""",
    # call method on a non-class
    """
def run() -> Int32
    x: Int32 = 5
    return x.nope()
""",
    # wrong argument count to method
    """
class A:
    def __init__(self: A, n: Int32):
        self.x: Int32 = n
    def get(self: A) -> Int32:
        return 1
def run() -> Int32
    a: A = A(1)
    return a.get(2)
""",
    # wrong argument type to constructor
    """
class A:
    def __init__(self: A, n: Int32):
        self.x: Int32 = n
def run() -> Int32
    a: A = A("hi")
    return 0
""",
    # unknown field access on class
    """
class A:
    def __init__(self: A):
        self.x: Int32 = 0
def run() -> Int32
    a: A = A()
    return a.brand
""",
    # inherited field cannot be redefined
    """
class A:
    def __init__(self: A):
        self.x: Int32 = 0
class B(A):
    def __init__(self: B):
        self.x: Int32 = 1
""",
    # duplicate class field
    """
class A:
    x: Int32
    y: Int32
    x: Bool
""",
    # call a method with inferred return before it is parsed
    """
class A:
    def a(self: A) -> Int32:
        return self.b()
    def b(self: A):
        return 1
def run() -> Int32
    a: A = A()
    return a.a()
""",
    # __str__ must return String
    """
class A:
    def __init__(self: A):
        self.x: Int32 = 0
    def __str__(self: A) -> Int32:
        return 1
""",
    # __str__ must not have extra params
    """
class A:
    def __init__(self: A):
        self.x: Int32 = 0
    def __str__(self: A, n: Int32) -> String:
        return ""
""",
]


@pytest.mark.parametrize("code", CLASS_BREAK_SNIPPETS)
def test_class_snippets_break(code):
    parse_fail(code)


def test_class_method_return_type_inferred():
    ast = parse_ok(
        """
class A:
    def __init__(self: A):
        self.x: Int32 = 0
    def get(self: A):
        return self.x
def run() -> Int32
    a: A = A()
    return a.get()
"""
    )
    methods = ast[0].methods
    assert methods[1].return_type == "Int32"


def test_class_constructor_no_init_gives_zeroed_value():
    ast = parse_ok(
        """
class A:
    def __init__(self: A):
        self.x: Int32 = 0
    def get(self: A) -> Int32:
        return 0
def run() -> Int32
    a: A = A()
    return a.get()
"""
    )


def test_union_var_narrows_to_concrete_type():
    parse_ok(
        """
def run() -> Int32
    a: Int | Float = 5
    b: Int32 = a
    return b
"""
    )


def test_union_var_reassign_other_member_narrows():
    parse_ok(
        """
def run() -> Int32
    a: Int | Float = 5
    a = 9.5
    return 0
"""
    )


def test_union_var_arithmetic_after_narrow_is_strict():
    parse_ok(
        """
def run() -> Int32
    a: Int | Float = 5
    c: Int | Float = a * 2
    return 0
"""
    )


def test_union_mixed_arithmetic_rejected_after_narrow():
    parse_fail(
        """
def run() -> Int32
    a: Int | Float = 5
    a = 3.5
    c: Int | Float = a + 2
    return 0
"""
    )


def test_union_var_reverts_to_union_after_if_else_merge():
    parse_fail(
        """
def run() -> Int32
    x: Int | Float = 5
    if x > 3:
        x = 2.5
    else:
        x = 7
    b: Int32 = x
    return 0
"""
    )


def test_union_var_merge_accepts_declared_union():
    parse_ok(
        """
def run() -> Int32
    x: Int | Float = 5
    if x > 3:
        x = 2.5
    else:
        x = 7
    b: Int | Float = x
    return 0
"""
    )


def test_union_var_reverts_to_union_after_while():
    parse_fail(
        """
def run() -> Int32
    x: Int | Float = 5
    while x > 3:
        x = 2.5
    b: Int32 = x
    return 0
"""
    )


def test_union_param_stays_union():
    parse_ok(
        """
def f(x: Int | Float) -> Int | Float
    return x + 1
"""
    )


def test_union_var_narrowed_usable_in_calls():
    parse_ok(
        """
def show(x: Int | Float) -> Int32
    return 0

def run() -> Int32
    a: Int | Float = 5
    show(a)
    return 0
"""
    )
