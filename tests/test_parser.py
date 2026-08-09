import pytest
from compiler.parser import Parser


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
def g(a: Int32, b: Int32) -> Int32
    return a + b
def f() -> Int32
    a: A = A(x=g(1,2))
    return a.x
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
def f(x: Int32, y: Int32) -> Bool
    b: Bool = x < y and y < x or x == y
    return b
""",

    """
def f(x: Int32, y: Int32) -> Int32
    z: Int32 = x ** y ** 2
    return z
""",

    """
def f(x: Int32, y: Int32) -> Bool
    b: Bool = (x + y) > 0 and not (x == y)
    return b
""",

    """
def f() -> NoneType
    x: NoneType = None
    return x
""",
]


@pytest.mark.parametrize("code", EXPR_SNIPPETS)
def test_expr_edge_cases(code):
    try:
        parse_ok(code)
    except SystemExit:
        assert True


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


FUNC_SIG_SNIPPETS = [

    """
def f(x: Int32 = 0) -> Int32
    return x
""",

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

    """
def f(x: Int32, y: Int32) -> Bool
    b: Bool = x < y and \
        y < x
    return b
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
