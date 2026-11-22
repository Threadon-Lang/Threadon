"""Tests for SSABuilder's read/write analysis helpers.

They are the small pure walkers used for phi insertion and alias handling;
testing them directly keeps the analysis independent of full IR lowering.
"""
import pytest

from compiler.threadon.lexer import Token, TokenType
from compiler.threadon.nodes import (
    Assign,
    AttrDecl,
    BinaryExpr,
    CallExpr,
    CastExpr,
    ClassInitExpr,
    DictLiteralExpr,
    ExprStmt,
    FieldAccessExpr,
    FieldAssign,
    IfStmt,
    IndexAssign,
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
from compiler.threadon.to_high_ir import IRBlock, SSABuilder


def lit(value="1"):
    return LiteralExpr(Token(TokenType.NUMBER, value), "Int32")


def x(name="x"):
    return VarExpr(name)


def builder():
    return SSABuilder()


def test_walk_stmt_reads_covers_every_statement_kind():
    b = builder()
    calls = [
        VarDecl("a", "Int32", x("b")),
        VarDecl("c", "Int32", None),
        Assign("c", x("d")),
        FieldAssign("p", "f", x("e")),
        AttrDecl("p", "f", "Int32", x("g")),
        AttrDecl("p", "f", "Int32", None),
        IndexAssign(x("h"), lit("0"), x("i")),
        ExprStmt(x("j")),
        ReturnStmt("Int32", x("k")),
        ReturnStmt("Int32", None),
        IfStmt(x("l"), [Assign("m", lit())],
               [(x("n"), [Assign("o", lit())])],
               [Assign("p", lit())]),
        IfStmt(x("q"), [], [], None),
        WhileStmt(x("r"), [Assign("s", lit())]),
        ThreadNode("t", x("u"), [Assign("v", lit())]),
    ]
    reads, defs = set(), set()
    for stmt in calls:
        b._walk_stmt_reads(stmt, reads, defs)
    assert reads == set("bcdeghijklmnopqrsuv")  # Assign also reads its target
    assert "a" in defs and "c" in defs


def test_walk_expr_reads_covers_every_expression_kind():
    b = builder()
    exprs = [
        None,
        x("a"),
        BinaryExpr(x("b"), "+", x("c")),
        CastExpr("Int64", x("d")),
        UnaryExpr("-", x("e")),
        RefExpr(x("f")),
        CallExpr("g", [x("h")]),
        InterpolatedStringExpr("f", [("expr", x("i")), ("text", "plain")]),
        FieldAccessExpr(x("j"), "f"),
        IndexExpr(x("k"), x("l")),
        SliceExpr(x("m"), x("n"), x("o")),
        SliceExpr(x("p"), None, None),
        ListLiteralExpr([x("q")]),
        DictLiteralExpr([x("r")], [x("s")]),
        StructInitExpr("S", {"f": x("t")}),
        MethodCallExpr(x("u"), "m", [x("v")]),
        ClassInitExpr("C", [x("w")]),
        lit(),
    ]
    reads, defs = set(), set()
    for expr in exprs:
        b._walk_expr_reads(expr, reads, defs)
    assert reads == set("abcdefhijklmnopqrstuvw")  # call names are not reads


def test_collect_assigned_covers_all_targets_and_nesting():
    b = builder()
    stmts = [
        Assign("a", lit()),
        FieldAssign("b", "f", lit()),
        AttrDecl("c", "f", "Int32", lit()),
        IndexAssign(x("d"), lit(), lit()),
        ExprStmt(MethodCallExpr(x("e"), "append", [lit()],
                                obj_type="List[Int32]")),
        ExprStmt(x("ignored")),
        VarDecl("f", "Int32", lit()),
        IfStmt(lit(), [Assign("g", lit())],
               [(lit(), [Assign("h", lit())])],
               [Assign("i", lit())]),
        WhileStmt(lit(), [Assign("j", lit())], [Assign("k", lit())]),
    ]
    out = set()
    b._collect_assigned(stmts, out)
    assert out == set("abcdefghijk")


def test_collect_target_names_recurses_through_index_and_field():
    b = builder()
    out = set()
    b._collect_target_names(IndexExpr(FieldAccessExpr(x("base"), "f"), lit()), out)
    assert out == {"base"}
    b._collect_target_names(lit(), out)
    assert out == {"base"}


def test_var_names_covers_all_expression_shapes():
    b = builder()
    assert b._var_names(x("a")) == ["a"]
    assert b._var_names(lit()) == []
    assert b._var_names(BinaryExpr(x("b"), "+", x("c"))) == ["b", "c"]
    assert b._var_names(RefExpr(x("d"))) == ["d"]
    assert b._var_names(CallExpr("f", [x("e")])) == ["e"]
    assert b._var_names(ListLiteralExpr([x("g")])) == ["g"]
    assert b._var_names(StructInitExpr("S", {"f": x("h"), "g": lit()})) == ["h"]
    assert b._var_names(StructInitExpr("S", [("f", x("i")), lit()])) == ["i"]
    assert b._var_names(InterpolatedStringExpr("f", [
        ("expr", x("j")), ("text", "plain"),
    ])) == ["j"]


def test_is_expr_node_and_safe_env_lookup():
    b = builder()
    assert b._is_expr_node(x())
    assert b._is_expr_node(CastExpr("Int32", x()))
    assert not b._is_expr_node(object())
    assert not b._is_expr_node(None)
    assert b._safe_env_lookup({"a": 1}, "a", IRBlock("entry")) == 1
    with pytest.raises(Exception, match="no value on back-edge"):
        b._safe_env_lookup({}, "a", IRBlock("entry"))
