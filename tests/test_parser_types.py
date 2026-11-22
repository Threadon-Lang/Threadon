"""Direct tests for the parser's type-inference and constant-folding helpers.

These are reached from many parse paths, but several error branches are easier
(and clearer) to verify by calling the helpers with hand-built expressions.
"""
import io
from contextlib import redirect_stdout

import pytest

from compiler.threadon.lexer import Token, TokenType
from compiler.threadon.nodes import (
    BinaryExpr,
    CallExpr,
    CastExpr,
    ClassInitExpr,
    DictLiteralExpr,
    FieldAccessExpr,
    IndexExpr,
    InterpolatedStringExpr,
    ListLiteralExpr,
    LiteralExpr,
    MethodCallExpr,
    RefExpr,
    SliceExpr,
    StructInitExpr,
    UnaryExpr,
    VarDecl,
    VarExpr,
)
from compiler.threadon.parser import Parser


def lit(value="1", type_="Int32"):
    return LiteralExpr(Token(TokenType.NUMBER if type_ != "String" else TokenType.STRING,
                             value), type_)


def var(name):
    return VarExpr(name)


def parser():
    p = Parser()
    p.original_lines = []
    return p


def error(expr, *args):
    with pytest.raises(SystemExit):
        with redirect_stdout(io.StringIO()):
            expr(*args)


# --- _const_eval -----------------------------------------------------------

def test_const_eval_literals():
    p = parser()
    assert p._const_eval(lit("12")) == (12, "Int32")
    assert p._const_eval(lit("1.5", "Float64")) == (1.5, "Float64")
    assert p._const_eval(lit("true", "Bool")) is None
    assert p._const_eval(var("x")) is None


def test_const_eval_unary_operators():
    p = parser()
    assert p._const_eval(UnaryExpr("-", lit("3"))) == (-3, "Int32")
    assert p._const_eval(UnaryExpr("+", lit("3"))) == (3, "Int32")
    assert p._const_eval(UnaryExpr("not", lit("3"))) is None
    assert p._const_eval(UnaryExpr("-", var("x"))) is None


def test_const_eval_binary_operators():
    p = parser()
    for op, expected in (
        ("+", 6), ("-", 2), ("*", 8), ("/", 3.0), ("//", 2), ("%", 0),
        ("**", 16),
    ):
        right = lit("2") if op != "/" else lit("2.0", "Float64")
        left = lit("4.0", "Float64") if op == "/" else lit("4")
        result = p._const_eval(BinaryExpr(left, op, right))
        if op == "/":
            assert result == (2.0, "Float64")
        else:
            assert result == (expected, "Int32")


def test_const_eval_binary_short_circuits():
    p = parser()
    assert p._const_eval(BinaryExpr(var("x"), "+", lit("1"))) is None
    assert p._const_eval(BinaryExpr(lit("1"), "+", var("x"))) is None
    assert p._const_eval(BinaryExpr(lit("1", "Bool"), "+", lit("2"))) is None
    assert p._const_eval(BinaryExpr(lit("1"), "&", lit("2"))) is None


@pytest.mark.parametrize("op", ["/", "//", "%"])
def test_const_eval_rejects_division_by_zero(op):
    p = parser()
    error(p._const_eval, BinaryExpr(lit("1"), op, lit("0")))


# --- detect_expr_type: collections and indexing ---------------------------

def test_detect_type_interpolated_ref_and_lists():
    p = parser()
    assert p.detect_expr_type(InterpolatedStringExpr("f", [])) == "String"
    p.scopes[-1]["n"] = "Int32"
    assert p.detect_expr_type(RefExpr(var("n"))) == "Int32"
    empty = ListLiteralExpr([])
    assert p.detect_expr_type(empty) == "List[Unknown]"
    typed = ListLiteralExpr([lit("1")])
    typed.type = "List[Int64]"
    assert p.detect_expr_type(typed) == "List[Int64]"
    assert p.detect_expr_type(ListLiteralExpr([lit("1"), lit("2")])) == "List[Int32]"
    # A literal can be adapted to the first element's type.
    assert p.detect_expr_type(ListLiteralExpr([lit("1", "Int64"), lit("2")])) == \
        "List[Int64]"
    error(p.detect_expr_type, ListLiteralExpr([lit("1"), lit("x", "String")]))


def test_detect_type_dicts():
    p = parser()
    assert p.detect_expr_type(DictLiteralExpr([], [])) == "Dict[Unknown,Unknown]"
    typed = DictLiteralExpr([lit("1")], [lit("2")])
    typed.type = "Dict[Int32,Int32]"
    assert p.detect_expr_type(typed) == "Dict[Int32,Int32]"
    assert p.detect_expr_type(DictLiteralExpr([lit("1")], [lit("2")])) == \
        "Dict[Int32,Int32]"
    assert p.detect_expr_type(DictLiteralExpr(
        [lit("1", "Int64"), lit("2")], [lit("3", "Int64"), lit("4")]
    )) == "Dict[Int64,Int64]"
    error(p.detect_expr_type, DictLiteralExpr(
        [lit("1"), lit("x", "String")], [lit("2")]))
    error(p.detect_expr_type, DictLiteralExpr(
        [lit("1"), lit("2")], [lit("3"), lit("x", "String")]))


def test_detect_type_index_and_slice():
    p = parser()
    p.scopes[-1].update({
        "xs": "List[Int32]", "d": "Dict[String,Int32]",
        "nested": "Dict[Dict[String,Int32],Int32]", "s": "String",
        "n": "Int32", "b": "Bool", "i": "Int64",
    })
    assert p.detect_expr_type(IndexExpr(var("xs"), var("n"))) == "Int32"
    assert p.detect_expr_type(IndexExpr(var("d"), lit("k", "String"))) == "Int32"
    assert p.detect_expr_type(IndexExpr(var("nested"), var("d"))) == "Int32"
    assert p.detect_expr_type(IndexExpr(var("s"), var("n"))) == "String"
    assert p.detect_expr_type(SliceExpr(var("xs"), var("n"), var("i"))) == \
        "List[Int32]"
    assert p.detect_expr_type(SliceExpr(var("s"), None, None)) == "String"
    error(p.detect_expr_type, IndexExpr(var("xs"), var("b")))
    error(p.detect_expr_type, IndexExpr(var("d"), var("n")))
    error(p.detect_expr_type, IndexExpr(var("s"), var("b")))
    error(p.detect_expr_type, IndexExpr(var("n"), var("n")))
    error(p.detect_expr_type, SliceExpr(var("xs"), var("b"), None))
    error(p.detect_expr_type, SliceExpr(var("xs"), None, var("b")))
    error(p.detect_expr_type, SliceExpr(var("n"), None, None))


# --- detect_expr_type: variables, fields and structs ----------------------

def test_detect_type_vars_fields_and_struct_init():
    p = parser()
    p.scopes[-1]["n"] = "Int32"
    p.struct_defs["Point"] = [VarDecl("x", "Int32", None)]
    p.class_defs["Widget"] = [VarDecl("label", "String", None)]
    p.module_aliases["math"] = "math"
    p.func_sigs["f"] = ([], "Int32")
    assert p.detect_expr_type(var("n")) == "Int32"
    assert p.detect_expr_type(var("Point")) == "Point"
    assert p.detect_expr_type(var("Widget")) == "Widget"
    assert p.detect_expr_type(FieldAccessExpr(var("Point"), "x")) == "Int32"
    assert p.detect_expr_type(FieldAccessExpr(var("Widget"), "label")) == "String"
    assert p.detect_expr_type(StructInitExpr("Point", {"x": lit("1")})) == "Point"
    assert p.detect_expr_type(StructInitExpr("Point", {"x": lit("2", "Int64")})) == \
        "Point"
    error(p.detect_expr_type, var("math"))
    error(p.detect_expr_type, var("f"))
    error(p.detect_expr_type, var("missing"))
    error(p.detect_expr_type, FieldAccessExpr(var("n"), "x"))
    error(p.detect_expr_type, FieldAccessExpr(var("Point"), "missing"))
    error(p.detect_expr_type, StructInitExpr("Missing", {}))
    error(p.detect_expr_type, StructInitExpr("Point", {"missing": lit()}))
    error(p.detect_expr_type, StructInitExpr(
        "Point", {"x": InterpolatedStringExpr("f", [])}))


# --- detect_expr_type: operators and calls --------------------------------

def test_detect_type_unary_and_binary_operators():
    p = parser()
    p.scopes[-1].update({"b": "Bool", "n": "Int32", "s": "String",
                         "u": "Union[Int32|String]",
                         "nums": "Union[Int32|Int64]"})
    assert p.detect_expr_type(UnaryExpr("not", var("b"))) == "Bool"
    assert p.detect_expr_type(UnaryExpr("-", var("n"))) == "Int32"
    assert p.detect_expr_type(UnaryExpr("+", var("nums"))) == "Union[Int32|Int64]"
    assert p.detect_expr_type(BinaryExpr(var("n"), "<", var("n"))) == "Bool"
    assert p.detect_expr_type(BinaryExpr(var("b"), "and", var("b"))) == "Bool"
    assert p.detect_expr_type(BinaryExpr(var("s"), "+", var("s"))) == "String"
    assert p.detect_expr_type(BinaryExpr(var("n"), "+", var("n"))) == "Int32"
    assert p.detect_expr_type(BinaryExpr(lit("1", "Int32"), "+",
                                         lit("2", "Int64"))) == "Int64"
    error(p.detect_expr_type, UnaryExpr("not", var("n")))
    error(p.detect_expr_type, UnaryExpr("-", var("s")))
    error(p.detect_expr_type, UnaryExpr("-", var("u")))
    error(p.detect_expr_type, BinaryExpr(var("n"), "<", var("s")))
    error(p.detect_expr_type, BinaryExpr(var("n"), "and", var("n")))
    error(p.detect_expr_type, BinaryExpr(var("n"), "+", var("s")))
    error(p.detect_expr_type, BinaryExpr(var("n"), "/", lit("0")))
    error(p.detect_expr_type, BinaryExpr(var("n"), "??", var("n")))


def test_detect_type_union_binary_paths():
    p = parser()
    p.scopes[-1].update({"u": "Union[Int32|String]",
                         "nums": "Union[Int32|Int64]", "n": "Int32",
                         "s": "String", "b": "Bool"})
    assert p.detect_expr_type(BinaryExpr(var("nums"), "<", lit("1"))) == "Bool"
    assert p.detect_expr_type(BinaryExpr(var("nums"), "+", lit("1"))) == "Union[Int32|Int64]"
    error(p.detect_expr_type, BinaryExpr(var("u"), "and", var("u")))
    error(p.detect_expr_type, BinaryExpr(var("u"), "<", var("s")))
    error(p.detect_expr_type, BinaryExpr(var("nums"), "+", var("b")))
    error(p.detect_expr_type, BinaryExpr(var("nums"), "&", var("n")))


def test_detect_type_call_expr():
    p = parser()
    p.scopes[-1].update({"n": "Int32", "s": "String"})
    p.func_sigs["one"] = ([("a", "Int32", None)], "Int32")
    p.func_sigs["opt"] = ([("a", "Int32", None), ("b", "Int32", lit("1"))], "Int32")
    assert p.detect_expr_type(CallExpr("len", [var("s")])) == "Int64"
    assert p.detect_expr_type(CallExpr("one", [lit("1")])) == "Int32"
    assert p.detect_expr_type(CallExpr("opt", [lit("1")])) == "Int32"
    assert p.detect_expr_type(CallExpr("opt", [lit("1"), lit("2")])) == "Int32"
    error(p.detect_expr_type, CallExpr("len", []))
    error(p.detect_expr_type, CallExpr("missing", []))
    error(p.detect_expr_type, CallExpr("one", []))
    error(p.detect_expr_type, CallExpr("opt", [lit("1"), lit("2"), lit("3")]))


def test_detect_type_cast_expr():
    p = parser()
    p.scopes[-1].update({"n": "Int32", "s": "String", "u": "Union[Int32|Bool]"})
    p.struct_defs["Point"] = [VarDecl("x", "Int32", None)]
    assert p.detect_expr_type(CastExpr("Float64", var("n"))) == "Float64"
    error(p.detect_expr_type, CastExpr("Int32", var("u")))
    error(p.detect_expr_type, CastExpr("Int32", var("Point")))
    error(p.detect_expr_type, CastExpr("Unknown", var("s")))


def test_detect_type_method_call_and_class_init():
    p = parser()
    p.scopes[-1].update({"xs": "List[Int32]", "n": "Int32",
                         "w": "Widget", "s": "String"})
    p.class_defs["Widget"] = [VarDecl("label", "String", None)]
    p.class_ast["Widget"] = type("Node", (), {"base": None})()
    p.class_method_map["Widget"] = {"set": "Widget_set", "__init__": "Widget_init"}
    p.func_sigs["Widget_set"] = ([("self", "Widget", None),
                                   ("v", "Int32", None)], "Int32")
    p.func_sigs["Widget_init"] = ([("self", "Widget", None),
                                    ("v", "Int32", lit("1"))], "NoneType")
    assert p.detect_expr_type(MethodCallExpr(var("xs"), "append", [lit("1")],
                                             obj_type="List[Int32]")) == "List[Int32]"
    assert p.detect_expr_type(MethodCallExpr(var("w"), "set", [lit("1")])) == "Int32"
    assert p.detect_expr_type(ClassInitExpr("Widget", [lit("1")])) == "Widget"
    assert p.detect_expr_type(ClassInitExpr("Widget", [])) == "Widget"
    error(p.detect_expr_type, MethodCallExpr(var("s"), "upper", []))
    error(p.detect_expr_type, MethodCallExpr(var("w"), "missing", []))
    error(p.detect_expr_type, MethodCallExpr(var("w"), "set", []))
    error(p.detect_expr_type, MethodCallExpr(var("w"), "set", [lit("1"), lit("2")]))
    error(p.detect_expr_type, ClassInitExpr("Missing", []))
    error(p.detect_expr_type, ClassInitExpr("Widget", [lit("1"), lit("2")]))
