"""Exhaustive tests for the compile-time interpreter."""
import pytest

from compiler.threadon.comptime_eval import (
    BreakSignal,
    ComptimeError,
    ComptimeInterpreter,
    ComptimeListIterator,
    ContinueSignal,
    ReturnSignal,
    _cast_to_type,
    eval_comptime,
)
from compiler.threadon.lexer import Token, TokenType
from compiler.threadon.nodes import (
    Assign,
    BinaryExpr,
    BreakStmt,
    CallExpr,
    CastExpr,
    ComptimeStmt,
    ContinueStmt,
    DictLiteralExpr,
    ExprStmt,
    FieldAccessExpr,
    IfStmt,
    IndexExpr,
    InterpolatedStringExpr,
    ListLiteralExpr,
    LiteralExpr,
    MethodCallExpr,
    RefExpr,
    ReturnStmt,
    SliceExpr,
    StructInitExpr,
    ThreadNode,
    UnaryExpr,
    VarDecl,
    VarExpr,
    WhileStmt,
)


def lit(value, token_type=TokenType.NUMBER):
    return LiteralExpr(Token(token_type, value), "")


def num(value):
    return lit(str(value))


def boolean(value):
    return lit(value, TokenType.TRUE if value else TokenType.FALSE)


def var(name):
    return VarExpr(name)


def call(name, *args):
    return CallExpr(name, list(args))


def interp():
    return ComptimeInterpreter()


def expect_error(fn, needle):
    with pytest.raises(ComptimeError) as excinfo:
        fn()
    assert needle in str(excinfo.value)


def test_eval_dispatch_and_unknown_node():
    assert interp().eval(VarDecl("x", "Int32", num(3))) == 3
    expect_error(
        lambda: interp().eval(ThreadNode("t", boolean(True), [])),
        "Cannot evaluate ThreadNode",
    )


@pytest.mark.parametrize(
    "token_type,value,expected",
    [
        (TokenType.NUMBER, "3", 3),
        (TokenType.NUMBER, "3.5", 3.5),
        (TokenType.NUMBER, "1e3", 1000.0),
        (TokenType.NUMBER, "2E2", 200.0),
        (TokenType.TRUE, True, True),
        (TokenType.FALSE, False, False),
        (TokenType.STRING, "hi", "hi"),
        (TokenType.NONE, None, None),
        (TokenType.IDENT, "raw", "raw"),
    ],
)
def test_literal_values(token_type, value, expected):
    assert interp().eval(lit(value, token_type)) == expected


def test_variable_declaration_assignment_and_lookup_errors():
    i = interp()
    assert i.eval(VarDecl("x", "Int32", num(1))) == 1
    assert i.eval(VarDecl("y", "Int32", None)) is None
    assert i.eval(var("x")) == 1
    assert i.eval(Assign("x", num(2))) == 2
    assert i.eval(var("x")) == 2
    expect_error(lambda: i.eval(var("nope")), "Variable 'nope' not defined")
    expect_error(lambda: i.eval(Assign("nope", num(1))), "Variable 'nope' not declared")


def test_return_statement_raises_signal():
    i = interp()
    with pytest.raises(ReturnSignal) as excinfo:
        i.eval(ReturnStmt("Int32", num(7)))
    assert excinfo.value.value == 7
    with pytest.raises(ReturnSignal) as excinfo:
        i.eval(ReturnStmt("NoneType", None))
    assert excinfo.value.value is None


def test_if_branches():
    i = interp()
    i.eval(VarDecl("hit", "Int32", num(0)))
    i.eval(IfStmt(boolean(True), [Assign("hit", num(1))], [], None))
    assert i.variables["hit"][1] == 1
    i.eval(IfStmt(boolean(False), [], [(boolean(True), [Assign("hit", num(2))])], None))
    assert i.variables["hit"][1] == 2
    i.eval(IfStmt(boolean(False), [], [(boolean(False), [])], [Assign("hit", num(3))]))
    assert i.variables["hit"][1] == 3
    i.eval(IfStmt(boolean(False), [], [(boolean(False), [])], None))
    expect_error(lambda: i.eval(IfStmt(num(1), [], [], [])), "If condition must be bool")


def test_while_loop_with_body_and_step():
    i = interp()
    i.eval(VarDecl("i", "Int32", num(0)))
    i.eval(VarDecl("sum", "Int32", num(0)))
    i.eval(
        WhileStmt(
            BinaryExpr(var("i"), "<", num(3)),
            [Assign("sum", BinaryExpr(var("sum"), "+", var("i")))],
            [Assign("i", BinaryExpr(var("i"), "+", num(1)))],
        )
    )
    assert i.variables["sum"][1] == 3


def test_while_requires_bool_condition():
    expect_error(
        lambda: interp().eval(WhileStmt(num(1), [], None)),
        "While condition must be bool",
    )


def test_while_iteration_cap():
    expect_error(
        lambda: interp().eval(WhileStmt(boolean(True), [], None)),
        "Comptime loop exceeded maximum iterations",
    )


def test_expression_statement_and_control_signals():
    i = interp()
    assert i.eval(ExprStmt(num(5))) == 5
    with pytest.raises(BreakSignal):
        i.eval(BreakStmt())
    with pytest.raises(ContinueSignal):
        i.eval(ContinueStmt())


@pytest.mark.parametrize(
    "op,left,right,expected",
    [
        ("+", 2, 3, 5),
        ("-", 2, 3, -1),
        ("*", 2, 3, 6),
        ("/", 3, 2, 1.5),
        ("//", 7, 2, 3),
        ("%", 7, 3, 1),
        ("**", 2, 3, 8),
        ("==", 2, 2, True),
        ("!=", 2, 3, True),
        ("<", 2, 3, True),
        (">", 2, 3, False),
        ("<=", 2, 2, True),
        (">=", 2, 3, False),
        ("and", 2, 3, 3),
        ("or", 0, 3, 3),
    ],
)
def test_binary_operators(op, left, right, expected):
    assert interp().eval(BinaryExpr(num(left), op, num(right))) == expected


@pytest.mark.parametrize("op", ["/", "//"])
def test_binary_division_by_zero(op):
    expect_error(
        lambda: interp().eval(BinaryExpr(num(1), op, num(0))),
        "Division by zero",
    )


def test_unknown_binary_operator():
    expect_error(
        lambda: interp().eval(BinaryExpr(num(1), "??", num(2))),
        "Unknown binary operator: ??",
    )


@pytest.mark.parametrize(
    "op,value,expected",
    [("-", 5, -5), ("not", True, False), ("not", False, True)],
)
def test_unary_operators(op, value, expected):
    node = UnaryExpr(op, boolean(value) if op == "not" else num(value))
    assert interp().eval(node) == expected


def test_unknown_unary_operator():
    expect_error(
        lambda: interp().eval(UnaryExpr("~", num(1))),
        "Unknown unary operator: ~",
    )


def test_len_call():
    i = interp()
    assert i.eval(call("len", ListLiteralExpr([num(1), num(2)]))) == 2
    assert i.eval(call("len", lit("abc", TokenType.STRING))) == 3
    assert i.eval(call("len", DictLiteralExpr([num(1)], [num(2)]))) == 1
    expect_error(lambda: i.eval(call("len", num(1))), "len() not supported")


def test_print_call(capsys):
    assert interp().eval(call("print", num(1), lit("x", TokenType.STRING))) is None
    assert capsys.readouterr().out == "1 x\n"


def test_range_call():
    i = interp()
    assert i.eval(call("range", num(3)))._lst == [0, 1, 2]
    assert i.eval(call("range", num(2), num(5)))._lst == [2, 3, 4]
    assert i.eval(call("range", num(0), num(6), num(2)))._lst == [0, 2, 4]
    expect_error(
        lambda: i.eval(call("range", num(1), num(2), num(3), num(4))),
        "range() expects 1-3 arguments",
    )


@pytest.mark.parametrize(
    "name,args,expected",
    [
        ("abs", (num(-3),), 3),
        ("std.abs", (num(-4),), 4),
        ("max", (num(2), num(5)), 5),
        ("std.max", (num(6), num(1)), 6),
        ("min", (num(2), num(5)), 2),
        ("std.min", (num(6), num(1)), 1),
        ("clamp", (num(9), num(0), num(5)), 5),
        ("std.clamp", (num(-1), num(0), num(5)), 0),
        ("clamp", (num(3), num(0), num(5)), 3),
        ("is_even", (num(4),), True),
        ("std.is_even", (num(3),), False),
        ("is_odd", (num(3),), True),
        ("std.is_odd", (num(4),), False),
    ],
)
def test_std_library_calls(name, args, expected):
    assert interp().eval(call(name, *args)) == expected


@pytest.mark.parametrize(
    "name,count",
    [("abs", 2), ("max", 1), ("min", 3), ("clamp", 2), ("is_even", 2), ("is_odd", 0)],
)
def test_std_library_call_argument_counts(name, count):
    expect_error(
        lambda: interp().eval(call(name, *([num(1)] * count))),
        f"{name}() expects",
    )


@pytest.mark.parametrize(
    "name,args",
    [
        ("abs", (lit("x", TokenType.STRING),)),
        ("max", (num(1), lit("x", TokenType.STRING))),
        ("min", (lit("x", TokenType.STRING), num(1))),
        ("clamp", (num(1), lit("x", TokenType.STRING), num(2))),
        ("is_even", (lit("x", TokenType.STRING),)),
        ("is_odd", (lit("x", TokenType.STRING),)),
    ],
)
def test_std_library_calls_reject_unsupported_types(name, args):
    expect_error(
        lambda: interp().eval(call(name, *args)),
        "not supported",
    )


def test_unknown_function():
    expect_error(
        lambda: interp().eval(call("nope")),
        "Function 'nope' not available at compile time",
    )


def test_list_literal_index_and_unsupported_indexing():
    i = interp()
    xs = i.eval(ListLiteralExpr([num(1), num(2)]))
    assert xs == [1, 2]
    i.variables["xs"] = ("List", xs)
    assert i.eval(IndexExpr(var("xs"), num(1))) == 2
    expect_error(
        lambda: i.eval(IndexExpr(num(1), num(0))),
        "Indexing not supported",
    )


def test_slice_list_string_and_unsupported_slicing():
    i = interp()
    i.variables["xs"] = ("List", [0, 1, 2, 3])
    assert i.eval(SliceExpr(var("xs"), num(1), num(3))) == [1, 2]
    assert i.eval(SliceExpr(var("xs"), None, num(2))) == [0, 1]
    i.variables["s"] = ("String", "abcd")
    assert i.eval(SliceExpr(var("s"), num(1), None)) == "bcd"
    expect_error(
        lambda: i.eval(SliceExpr(num(1), None, None)),
        "Slicing not supported",
    )


def test_dict_literal_and_field_access():
    i = interp()
    d = i.eval(DictLiteralExpr([lit("a", TokenType.STRING)], [num(1)]))
    assert d == {"a": 1}
    i.variables["d"] = ("Dict", d)
    assert i.eval(FieldAccessExpr(var("d"), "a")) == 1
    assert i.eval(FieldAccessExpr(var("d"), "missing")) is None
    expect_error(
        lambda: i.eval(FieldAccessExpr(num(1), "a")),
        "Field access not supported",
    )


def test_struct_init():
    fields = interp().eval(StructInitExpr("Point", {"x": num(1)}))
    assert fields == {"x": 1}


def test_interpolated_string():
    node = InterpolatedStringExpr("f", [("lit", "n="), ("expr", num(4))])
    assert interp().eval(node) == "n=4"


@pytest.mark.parametrize(
    "target,value,expected",
    [
        ("Int8", 3.9, 3),
        ("UInt64", 3, 3),
        ("Float32", 3, 3.0),
        ("Bool", 0, False),
        ("String", 3, "3"),
    ],
)
def test_cast_expression(target, value, expected):
    assert interp().eval(CastExpr(target, num(value))) == expected


def test_unknown_cast_target():
    expect_error(
        lambda: interp().eval(CastExpr("Custom", num(3))),
        "Cannot cast to Custom at compile time",
    )


def test_method_calls_on_iterator():
    i = interp()
    i.variables["it"] = ("Iterator", i.eval(call("range", num(2))))
    assert i.eval(MethodCallExpr(var("it"), "done", [])) is False
    assert i.eval(MethodCallExpr(var("it"), "value", [])) == 0
    assert i.eval(MethodCallExpr(var("it"), "advance", [])) is i.variables["it"][1]
    assert i.eval(MethodCallExpr(var("it"), "value", [])) == 1
    assert i.eval(MethodCallExpr(var("it"), "advance", [])) is i.variables["it"][1]
    assert i.eval(MethodCallExpr(var("it"), "done", [])) is True
    assert i.eval(MethodCallExpr(var("it"), "append", [num(2)])) is i.variables["it"][1]
    assert i.eval(MethodCallExpr(var("it"), "pop", [])) == 2
    assert i.eval(MethodCallExpr(var("it"), "len", [])) == 2


def test_method_calls_on_plain_list_and_dict():
    i = interp()
    i.variables["xs"] = ("List", [1, 2])
    assert i.eval(MethodCallExpr(var("xs"), "append", [num(3)])) is not None
    assert i.eval(MethodCallExpr(var("xs"), "len", [])) == 3
    assert i.eval(MethodCallExpr(var("xs"), "pop", [])) == 3
    assert i.eval(MethodCallExpr(var("xs"), "done", [])) is False
    assert i.eval(MethodCallExpr(var("xs"), "value", [])) == 1
    assert i.eval(MethodCallExpr(var("xs"), "advance", [])) is not None
    i.variables["d"] = ("Dict", {"a": 1})
    assert i.eval(MethodCallExpr(var("d"), "len", [])) == 1
    expect_error(
        lambda: i.eval(MethodCallExpr(var("d"), "append", [num(1)])),
        "Method 'append' not available at compile time",
    )


def test_comptime_list_iterator_protocol():
    it = ComptimeListIterator([10, 20])
    assert it.done() is False
    assert it.value() == 10
    assert it.advance() is it
    assert it.value() == 20
    assert it.advance() is it
    assert it.done() is True
    empty = ComptimeListIterator([])
    assert empty.done() is True
    assert empty.value() is None
    assert it.append(30) is it
    assert it.pop() == 30
    assert len(it) == 2
    assert it[0] == 10
    it[0] = 11
    assert it[0] == 11
    assert it.get("_done") is True
    assert it.get("_value") == 20
    assert it.get("_idx") == 1
    assert it.get("missing") is None
    assert it.get("missing", "fallback") == "fallback"


def test_ref_expr():
    assert interp().eval(RefExpr(num(4))) == 4


def test_eval_comptime_with_return_expression():
    node = ComptimeStmt(
        "x",
        "Int32",
        [VarDecl("y", "Int32", num(2))],
        BinaryExpr(var("y"), "+", num(3)),
    )
    assert eval_comptime(node, {}, {}, {}) == 5


def test_eval_comptime_with_return_statement():
    node = ComptimeStmt("x", "Int32", [ReturnStmt("Int32", num(9))], None)
    assert eval_comptime(node, {}, {}, {}) == 9


def test_eval_comptime_without_return():
    node = ComptimeStmt(
        "x",
        "Int32",
        [VarDecl("z", "Int32", num(1)), ExprStmt(Assign("z", num(1)))],
        None,
    )
    assert eval_comptime(node, {}, {}, {}) is None


@pytest.mark.parametrize(
    "target,value,expected",
    [
        ("Int32", None, None),
        ("Int8", 2.9, 2),
        ("UInt8", 2, 2),
        ("Float64", 2, 2.0),
        ("Bool", 1, True),
        ("String", 1, "1"),
        ("Unknown", 1, 1),
    ],
)
def test_cast_to_type(target, value, expected):
    assert _cast_to_type(value, target) == expected
