"""Direct tests for small parser helpers used during type checking."""
import io
from contextlib import redirect_stdout

import pytest

from compiler.threadon.lexer import Token, TokenType
from compiler.threadon.nodes import (
    BinaryExpr, DictLiteralExpr, ListLiteralExpr, LiteralExpr, UnaryExpr, VarExpr,
)
from compiler.threadon.parser import Parser


def lit(value="1", type_="Int32"):
    return LiteralExpr(Token(TokenType.NUMBER, value), type_)


def parser():
    p = Parser()
    p.original_lines = []
    return p


def fails(fn, *args):
    with pytest.raises(SystemExit):
        with redirect_stdout(io.StringIO()):
            fn(*args)


# --- line bookkeeping ------------------------------------------------------

def test_peek_read_line_and_nonempty_level_at_eof():
    p = parser()
    p.lexed_lines = []
    assert p.peek_raw() is None
    assert p.next_nonempty_level() is None
    assert p.read_line() is None
    p.lexed_lines = [[], [Token(TokenType.IDENT, "x")]]
    assert p.next_nonempty_level() == p.current_indent


def test_apply_indent_uses_current_column_when_none():
    p = parser()
    p.current_indent_col = 4
    p.indent_stack = [0]
    p.apply_indent(1, 0)
    assert p.indent_stack == [0, 4]


def test_scope_helpers_merge_and_lookup():
    p = parser()
    p.push_scope()
    p.declare_var("x", "Int32")
    p.scopes[0]["parent"] = "Bool"
    p.var_declared_stack[0]["parent"] = "Bool"
    p.modified_stack[0].add("parent")
    p.pop_scope_merge()
    assert p.scopes[-1] == {"x": "Int32", "parent": "Bool"}
    assert p.var_declared_stack[-1] == {"x": "Int32", "parent": "Bool"}
    assert "parent" in p.modified_stack[-1]
    p.pop_scope()
    assert p._lookup_declared("missing") is None
    p.push_scope()
    p.var_declared_stack[-1]["x"] = "Int64"
    assert p._lookup_declared("x") == "Int64"


def test_narrow_var_uses_declared_type_or_fallback():
    p = parser()
    p.push_scope()
    p.var_declared_stack[-1]["x"] = "Union[Int32|Int64]"
    p._narrow_var("x", "Int32")
    assert p.scopes[-1]["x"] == "Int32"
    p._narrow_var("y", "Int32")
    assert p.scopes[-1]["y"] == "Int32"


# --- type validity ---------------------------------------------------------

def test_is_valid_type_covers_every_category():
    p = parser()
    p.struct_defs["Point"] = []
    p.struct_import_aliases["other"] = "math.Point"
    p.class_defs["Widget"] = []
    p.class_import_aliases["other"] = "mod.Widget"
    for t in ("Int", "Union[Int32|Int64]", "Bool", "Point", "math.Point",
              "Widget", "mod.Widget", "List[List[Int32]]",
              "Dict[Dict[String,Int32],Int32]",
              "List[Int32]*", "Union[Point|Int32]"):
        assert p._is_valid_type(t), t
    assert not p._is_valid_type("DoesNotExist")
    # A Dict without a comma has no valid value type.
    assert not p._is_valid_type("Dict[Int32]")


def test_dict_parse_inner_handles_nested_brackets_and_bad_input():
    p = parser()
    assert p._dict_parse_inner("Dict[Dict[String,Int32],Int32]") == \
        ("Dict[String,Int32]", "Int32")
    assert p._dict_parse_inner("Dict[Int32]") is None
    assert p._dict_parse_inner("List[Int32]") is None


# --- literal adaptation ----------------------------------------------------

def test_try_adapt_literal_inner_rejects_non_literal_collections():
    p = parser()
    assert not p._try_adapt_literal(VarExpr("x"), "List[Int32]", "List[Int64]")
    assert not p._try_adapt_literal(VarExpr("x"), "Dict[Int32,Int32]",
                                    "Dict[Int64,Int64]")
    assert not p._try_adapt_literal_inner(
        lit("1"), "Int32", "Float64", promote_num=False)


def test_try_adapt_literal_inner_adapts_nested_collections():
    p = parser()
    lst = ListLiteralExpr([lit("1", "Int64"), lit("2")])
    assert p._try_adapt_literal(lst, "List[Int64]", "List[Float64]")
    assert lst.type == "List[Float64]"

    d = DictLiteralExpr([lit("1", "Int64")], [lit("2")])
    assert p._try_adapt_literal(d, "Dict[Int64,Int32]", "Dict[Float64,Float64]")
    assert d.type == "Dict[Float64,Float64]"


def test_try_adapt_literal_inner_rejects_incompatible_elements():
    p = parser()
    assert not p._try_adapt_literal(
        ListLiteralExpr([lit("x", "String")]), "List[String]", "List[Int32]")
    assert not p._try_adapt_literal(
        DictLiteralExpr([lit("1")], [lit("x", "String")]),
        "Dict[Int32,String]", "Dict[Int64,Int64]")


def test_try_adapt_literal_inner_rejects_unknown_dict_value_types():
    p = parser()
    d = DictLiteralExpr([lit("1")], [lit("2", "Int64")])
    assert not p._try_adapt_literal(d, "Dict[Int32,Int64]",
                                    "Dict[Int32,Builtin]")


# --- assignment and literal ranges ----------------------------------------

def test_check_assign_handles_union_targets():
    p = parser()
    target = "Union[Int32|Int64]"
    assert p._check_assign(lit(), "Int32", target, "Variable") is True
    assert p._check_assign(lit(), target, target, "Variable") is True
    wider = "Union[Int32|Int64|String]"
    assert p._check_assign(lit(), target, wider, "Variable") is True
    fails(p._check_assign, lit("x", "String"), "String", target, "Variable")
    fails(p._check_assign, lit(), target, "Int32", "Variable")
    assert p._check_assign(lit(), "Int32", "Int32", "Variable") is False


def test_const_expr_recognises_constant_arithmetic():
    p = parser()
    assert p._is_const_expr(BinaryExpr(lit(), "+", lit("2")))
    assert p._is_const_expr(UnaryExpr("-", lit()))
    assert not p._is_const_expr(VarExpr("x"))


def test_check_literal_range_and_set_expr_type():
    p = parser()
    assert p._check_literal_range(lit("1.5", "Float64"), "Int8") is None
    assert p._check_literal_range(lit("1"), "Float64") is None
    p._check_literal_range(lit("1"), "Int32")
    fails(p._check_literal_range, lit("300"), "Int8")
    expr = lit("1")
    p._set_expr_type(expr, "Int64")
    assert expr.type == "Int64"
    fails(p._set_expr_type, lit("300"), "Int8")


def test_const_eval_non_zero_division_returns_none():
    p = parser()
    assert p._const_eval(BinaryExpr(lit("1", "Bool"), "%", lit("2"))) is None
