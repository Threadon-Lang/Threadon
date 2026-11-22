"""Exhaustive checks for compile-time ``puredef`` enforcement."""
import io
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from compiler.threadon.checker import PurityChecker
from compiler.threadon.importer import Importer
from compiler.threadon.lexer import Token, TokenType
from compiler.threadon.nodes import (
    Assign,
    BinaryExpr,
    CallExpr,
    CastExpr,
    ClassDef,
    ClassInitExpr,
    ComptimeStmt,
    DictLiteralExpr,
    ExprStmt,
    FieldAccessExpr,
    FieldAssign,
    FunctionDef,
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


def literal(value="0"):
    return LiteralExpr(Token(TokenType.NUMBER, value), "Int32")


def call(name, *args):
    return CallExpr(name, list(args))


def impure():
    return call("impure")


def func(name, body, pure=True):
    return FunctionDef(name, [], "Int32", body, pure=pure)


def purity_error(checker, ast):
    output = io.StringIO()
    with redirect_stdout(output):
        with pytest.raises(SystemExit):
            checker.check(ast)
    return output.getvalue()


def assert_pure_ok(ast, **kwargs):
    output = io.StringIO()
    with redirect_stdout(output):
        PurityChecker(**kwargs).check(ast)
    assert "AST Error" not in output.getvalue()


@pytest.mark.parametrize("builtin", sorted(PurityChecker.PURE_BUILTINS))
def test_whitelisted_builtins_are_pure(builtin):
    assert_pure_ok([func("f", [ExprStmt(call(builtin))])])


@pytest.mark.parametrize(
    "builtin",
    ["print", "input", "collect", "thread_exit", "now", "can_collect"],
)
def test_other_builtins_are_not_pure(builtin):
    message = purity_error(
        PurityChecker(), [func("f", [ExprStmt(call(builtin))])]
    )
    assert f"may not call non-pure function '{builtin}'" in message


def test_native_function_rejection_wins_over_pure_declaration():
    ast = [
        func("time.now", [ReturnStmt("Int32", literal())]),
        func("f", [ExprStmt(call("time.now"))]),
    ]
    message = purity_error(PurityChecker(native_functions={"time.now"}), ast)
    assert "may not call native function 'time.now'" in message


def test_pure_calls_are_accepted_and_impure_calls_are_not():
    ast = [
        func("pure_helper", [ReturnStmt("Int32", literal())]),
        func("f", [ExprStmt(call("pure_helper"))]),
        func("g", [ExprStmt(call("impure"))]),
    ]
    assert_pure_ok(ast[:2])
    message = purity_error(PurityChecker(), ast[2:])
    assert "may not call non-pure function 'impure'" in message


EXPRESSION_CASES = {
    "call_argument": lambda: call("len", impure()),
    "method_argument": lambda: MethodCallExpr(VarExpr("x"), "m", [impure()]),
    "method_function_name": lambda: MethodCallExpr(
        VarExpr("x"), "m", [], func_name="impure"
    ),
    "global_list_mutator": lambda: MethodCallExpr(
        VarExpr("g"), "append", [literal()], obj_type="List[Int32]"
    ),
    "global_field_list_mutator": lambda: MethodCallExpr(
        FieldAccessExpr(VarExpr("g"), "items"),
        "append",
        [literal()],
        obj_type="List[Int32]",
    ),
    "local_list_mutator_argument": lambda: MethodCallExpr(
        VarExpr("x"), "append", [impure()], obj_type="List[Int32]"
    ),
    "class_init_name": lambda: ClassInitExpr("P", [], init_name="impure"),
    "class_init_argument": lambda: ClassInitExpr("P", [impure()]),
    "struct_init": lambda: StructInitExpr("S", {"a": impure()}),
    "binary_left": lambda: BinaryExpr(impure(), "+", literal()),
    "binary_right": lambda: BinaryExpr(literal(), "+", impure()),
    "unary": lambda: UnaryExpr("-", impure()),
    "cast": lambda: CastExpr("Int32", impure()),
    "field_access": lambda: FieldAccessExpr(impure(), "x"),
    "index_object": lambda: IndexExpr(impure(), literal()),
    "index_index": lambda: IndexExpr(VarExpr("x"), impure()),
    "slice_start": lambda: SliceExpr(VarExpr("s"), impure(), None),
    "slice_end": lambda: SliceExpr(VarExpr("s"), None, impure()),
    "list_literal": lambda: ListLiteralExpr([impure()]),
    "dict_key": lambda: DictLiteralExpr([impure()], [literal()]),
    "dict_value": lambda: DictLiteralExpr([literal()], [impure()]),
    "interpolated_string": lambda: InterpolatedStringExpr(
        "f", [("lit", "x"), ("expr", impure())]
    ),
    "ref": lambda: RefExpr(impure()),
    "list_fallback": lambda: [impure()],
}


@pytest.mark.parametrize("name", sorted(EXPRESSION_CASES))
def test_every_expression_shape_is_checked(name):
    expression = EXPRESSION_CASES[name]()
    message = purity_error(
        PurityChecker(global_vars={"g"}),
        [func("f", [ExprStmt(expression)])],
    )
    if name in {"global_list_mutator", "global_field_list_mutator"}:
        assert "may not write global variable 'g'" in message
    else:
        assert "may not call non-pure function 'impure'" in message


PURE_EXPRESSION_CASES = {
    "call": lambda: call("pure_helper"),
    "method": lambda: MethodCallExpr(
        VarExpr("x"), "m", [], func_name="pure_helper.m"
    ),
    "class_init": lambda: ClassInitExpr("P", [], init_name="P.__init__"),
    "struct_init": lambda: StructInitExpr("S", {"a": call("pure_helper")}),
    "binary": lambda: BinaryExpr(call("pure_helper"), "+", literal()),
    "unary": lambda: UnaryExpr("-", call("pure_helper")),
    "cast": lambda: CastExpr("Int32", call("pure_helper")),
    "field_access": lambda: FieldAccessExpr(call("pure_helper"), "x"),
    "index": lambda: IndexExpr(call("pure_helper"), literal()),
    "slice": lambda: SliceExpr(VarExpr("s"), call("pure_helper"), None),
    "list": lambda: ListLiteralExpr([call("pure_helper")]),
    "dict": lambda: DictLiteralExpr([literal()], [call("pure_helper")]),
    "interpolated_string": lambda: InterpolatedStringExpr(
        "f", [("expr", call("pure_helper"))]
    ),
    "ref": lambda: RefExpr(call("pure_helper")),
}


@pytest.mark.parametrize("name", sorted(PURE_EXPRESSION_CASES))
def test_pure_expression_shapes_are_accepted(name):
    ast = [
        func("pure_helper", [ReturnStmt("Int32", literal())]),
        func("pure_helper.m", [ReturnStmt("Int32", literal())]),
        func("P.__init__", [ReturnStmt("Int32", literal())]),
        func("f", [ExprStmt(PURE_EXPRESSION_CASES[name]())]),
    ]
    assert_pure_ok(ast)


@pytest.mark.parametrize(
    "statement,needle",
    [
        (VarDecl("x", "Int32", impure()), "non-pure function 'impure'"),
        (ReturnStmt("Int32", impure()), "non-pure function 'impure'"),
        (Assign("x", impure()), "non-pure function 'impure'"),
        (FieldAssign("x", "a", impure()), "non-pure function 'impure'"),
        (
            IndexAssign(VarExpr("x"), impure(), literal()),
            "non-pure function 'impure'",
        ),
        (ExprStmt(impure()), "non-pure function 'impure'"),
        (
            IfStmt(
                impure(),
                [ExprStmt(impure())],
                [(impure(), [ExprStmt(impure())])],
                [ExprStmt(impure())],
            ),
            "non-pure function 'impure'",
        ),
        (
            WhileStmt(
                impure(), [ExprStmt(impure())], [ExprStmt(impure())]
            ),
            "non-pure function 'impure'",
        ),
        (ThreadNode("t", literal(), []), "may not start threads"),
        (ComptimeStmt("x", "Int32", []), "may not run compile-time statements"),
    ],
)
def test_every_statement_kind_is_checked(statement, needle):
    message = purity_error(PurityChecker(), [func("f", [statement])])
    assert needle in message


GLOBAL_WRITE_CASES = {
    "assign": lambda: Assign("g", literal()),
    "field_assign": lambda: FieldAssign("g", "a", literal()),
    "index_assign": lambda: IndexAssign(
        IndexExpr(VarExpr("g"), literal()), literal(), literal()
    ),
    "imported_global": lambda: Assign("ext.counter", literal()),
}


@pytest.mark.parametrize("name", sorted(GLOBAL_WRITE_CASES))
def test_every_global_write_shape_is_rejected(name):
    globals_ = {"ext.counter"} if name == "imported_global" else {"g"}
    message = purity_error(
        PurityChecker(global_vars=globals_),
        [func("f", [GLOBAL_WRITE_CASES[name]()])],
    )
    target = "ext.counter" if name == "imported_global" else "g"
    assert f"may not write global variable '{target}'" in message


def test_module_level_global_is_detected_without_explicit_globals():
    message = purity_error(
        PurityChecker(),
        [VarDecl("g", "Int32", literal()), func("f", [Assign("g", literal())])],
    )
    assert "may not write global variable 'g'" in message


def test_local_shadowing_of_a_global_is_allowed():
    ast = [
        VarDecl("g", "Int32", literal()),
        func(
            "f",
            [VarDecl("g", "Int32", literal()), Assign("g", literal())],
        ),
    ]
    assert_pure_ok(ast)


def test_nested_local_declarations_are_collected():
    checker = PurityChecker()
    checker.locals = set()
    checker._collect_locals(
        IfStmt(literal(), [VarDecl("a", "Int32", literal())], [], [])
    )
    checker._collect_locals(
        WhileStmt(
            literal(),
            [VarDecl("b", "Int32", literal())],
            [VarDecl("c", "Int32", literal())],
        )
    )
    checker._collect_locals(ThreadNode("t", literal(), [VarDecl("d", "Int32", literal())]))
    checker._collect_locals(ComptimeStmt("e", "Int32", [VarDecl("e", "Int32", literal())]))
    assert {"a", "b", "c", "d", "e"} <= checker.locals


def test_pure_methods_and_constructors_are_checked():
    good = ClassDef(
        "P",
        None,
        [],
        [func("P.value", [ReturnStmt("Int32", literal())])],
        [],
    )
    bad = ClassDef("P", None, [], [func("P.value", [ExprStmt(impure())])], [])
    assert_pure_ok([good, func("f", [ExprStmt(call("P.value"))])])
    message = purity_error(
        PurityChecker(), [bad, func("f", [ExprStmt(call("P.value"))])]
    )
    assert "may not call non-pure function 'impure'" in message


STDLIB = Path(__file__).resolve().parents[1] / "compiler" / "stdlib"
STDLIB_MODULES = sorted(
    p.name for p in STDLIB.iterdir() if (p / "manifest").is_file()
)


@pytest.mark.parametrize("module", STDLIB_MODULES)
def test_every_shipped_puredef_stays_pure(module):
    importer = Importer()
    mod = importer.load(module)
    assert_pure_ok(
        mod.ast or [],
        native_functions=set(mod.func_sigs) if mod.is_native else set(),
    )
