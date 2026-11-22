"""Edge-case tests for the individual AST checker passes."""
import io
from contextlib import redirect_stdout

import pytest

from compiler.threadon.checker import (
    AliasChecker,
    DeadStoreChecker,
    DuplicateChecker,
    MissingReturnChecker,
    ShadowChecker,
    UnreachableChecker,
    UnusedVariableChecker,
    PurityChecker,
    UnusedVariableChecker as Warnings,
)
from compiler.threadon.nodes import (
    Assign, ComptimeStmt, FunctionDef, IfStmt, LiteralExpr, RefExpr, ReturnStmt,
    ThreadNode, VarDecl, VarExpr, WhileStmt,
)
from compiler.threadon.lexer import Token, TokenType
from compiler.threadon.parser import Parser


def parse(source):
    return Parser().parse(source)


def num(value="1"):
    return LiteralExpr(Token(TokenType.NUMBER, value), "Int32")


def ok(checker, source):
    checker().check(parse(source) if isinstance(source, str) else source)


def ok_ast(checker, ast):
    checker().check(ast)


def fails(checker, source):
    with pytest.raises(SystemExit):
        with redirect_stdout(io.StringIO()):
            checker().check(parse(source))


# --- UnreachableChecker ---------------------------------------------------

def test_unreachable_cfg_elif_and_thread_paths():
    ok(UnreachableChecker, """
def f(x: Int32) -> Int32
    if x == 1:
        return 1
    elif x == 2:
        return 2
    elif x == 3:
        return 3
    else:
        return 0
""")
    fails(UnreachableChecker, """
def f(x: Int32) -> Int32
    if x == 1:
        return 1
    elif x == 2:
        return 2
    else:
        return 0
    x = 9
""")
    ok(UnreachableChecker, [
        FunctionDef("f", [("flag", "Bool", None)], "Int32", [
            ThreadNode("w", VarExpr("flag"), [VarDecl("x", "Int32", num())]),
            ReturnStmt("Int32", num()),
        ])
    ])


def test_unreachable_statement_flag_is_reported():
    """The CFG records statement liveness; a False flag is an AST error."""
    checker = UnreachableChecker()
    stmt = ReturnStmt("Int32", None)
    blocks = [
        checker.new_block("entry"),
        {"name": "dead", "stmts": [(stmt, False)], "succ": []},
    ]
    blocks[0]["succ"].append("dead")
    func = FunctionDef("f", [], "NoneType", [])

    # Reachability comes from the successor graph; inject a False flag directly
    # by patching the built CFG for this focused unit test.
    original = checker.build_cfg
    checker.build_cfg = lambda fn: blocks
    with pytest.raises(SystemExit):
        with redirect_stdout(io.StringIO()):
            checker.check_function(func)
    checker.build_cfg = original


# --- ShadowChecker / DuplicateChecker ------------------------------------

def test_shadow_checker_visits_comptime_body():
    ok(ShadowChecker, """
comptime base: Int32 = 2
comptime total: Int32:
    inner: Int32 = 3
    return inner
def f() -> Int32
    return total
""")


def test_duplicate_checker_comptime_and_assignment():
    ok(DuplicateChecker, """
comptime base: Int32 = 2
comptime total: Int32:
    inner: Int32 = 3
    return inner
def f() -> Int32
    x: Int32 = total
    x = x + 1
    return x
""")
    fails(DuplicateChecker, """
def f() -> Int32
    x = 1
    return x
""")


# --- UnusedVariableChecker -----------------------------------------------

def test_unused_variable_checker_module_thread_and_comptime(capsys):
    ok(Warnings, """
comptime total: Int32:
    inner: Int32 = 3
    return inner
flag: Bool = True
thread w() on flag:
    flag = False
def f() -> Int32
    return total
""")
    output = capsys.readouterr().out
    assert "declared but never used" not in output


def test_unused_variable_checker_tracks_thread_body_reads(capsys):
    ok(Warnings, """
flag: Bool = True
thread w() on flag:
    flag = False
def main() -> NoneType
    return
""")
    assert "declared but never used" not in capsys.readouterr().out


# --- DeadStoreChecker -----------------------------------------------------

def test_dead_store_checker_thread_and_comptime_in_function():
    func = FunctionDef("f", [("flag", "Bool", None)], "Int32", [
        ComptimeStmt("c", "Int32", [VarDecl("t", "Int32", num("2"))], None),
        VarDecl("a", "Int32", num()),
        ThreadNode("w", VarExpr("flag"), [
            Assign("a", VarExpr("a")),
        ]),
        ReturnStmt("Int32", VarExpr("a")),
    ])
    ok_ast(DeadStoreChecker, [func])


# --- MissingReturnChecker -------------------------------------------------

def test_missing_return_error_and_thread():
    fails(MissingReturnChecker, """
def f() -> Int32
    x: Int32 = 1
""")
    ok_ast(MissingReturnChecker, [
        FunctionDef("f", [("flag", "Bool", None)], "Int32", [
            ThreadNode("w", VarExpr("flag"), [VarDecl("x", "Int32", num())]),
            ReturnStmt("Int32", num("3")),
        ])
    ])


# --- AliasChecker ---------------------------------------------------------

def test_alias_checker_visits_thread_body():
    func = FunctionDef("f", [("flag", "Bool", None)], "Int32", [
        VarDecl("x", "Int32", num()),
        ThreadNode("w", VarExpr("flag"), [
            VarDecl("r", "Ref Int32", RefExpr(VarExpr("x"))),
        ]),
        ReturnStmt("Int32", VarExpr("x")),
    ])
    ok_ast(AliasChecker, [func])


# --- PurityChecker --------------------------------------------------------

def test_purity_checker_index_assign_and_elif():
    ok(PurityChecker, """
puredef f(xs: List[Int32], n: Int32) -> Int32
    xs[0] = n
    if n > 2:
        return 1
    elif n > 1:
        return 2
    else:
        return 0
""")


# --- error paths that the parser rejects before a checker sees them --------

def test_unreachable_disconnected_block_and_dead_statement():
    """A block with no predecessor and a dead statement are both AST errors."""
    checker = UnreachableChecker()
    dead = checker.new_block("dead")
    checker.build_cfg = lambda fn: [checker.new_block("entry"), dead]
    with pytest.raises(SystemExit):
        with redirect_stdout(io.StringIO()):
            checker.check_function(FunctionDef("f", [], "NoneType", []))

    checker = UnreachableChecker()
    dead = checker.new_block("dead")
    checker.build_cfg = lambda fn: [checker.new_block("entry"), dead]
    messages = []
    checker.error = messages.append
    checker.check_function(FunctionDef("f", [], "NoneType", []))
    assert any("block" in m.lower() for m in messages)

    checker = UnreachableChecker()
    entry = checker.new_block("entry")
    entry["stmts"].append((ReturnStmt("Int32", num()), False))
    checker.build_cfg = lambda fn: [entry]
    messages = []
    checker.error = messages.append
    checker.check_function(FunctionDef("f", [], "NoneType", []))
    assert any("statement" in m.lower() for m in messages)


def test_unreachable_checker_while_body_that_returns():
    """A return inside a while body ends the current CFG path."""
    func = FunctionDef("f", [], "Int32", [
        WhileStmt(VarExpr("flag"), [ReturnStmt("Int32", num())]),
    ])
    ok_ast(UnreachableChecker, [func])


def test_duplicate_checker_assignment_before_declaration():
    """The parser rejects this first, so feed the checker a hand-built AST."""
    func = FunctionDef("f", [], "Int32", [
        Assign("x", [num()]),
        ReturnStmt("Int32", VarExpr("x")),
    ])
    with pytest.raises(SystemExit):
        with redirect_stdout(io.StringIO()):
            DuplicateChecker().check([func])


def test_unused_variable_checker_thread_inside_function():
    """A thread statement nested in a function body visits its body."""
    func = FunctionDef("f", [("flag", "Bool", None)], "Int32", [
        ThreadNode("w", VarExpr("flag"), [VarDecl("x", "Int32", num())]),
        ReturnStmt("Int32", num()),
    ])
    ok_ast(Warnings, [func])


def test_missing_return_checker_error_on_raw_ast():
    """The parser rejects this first, so feed the checker a hand-built AST."""
    func = FunctionDef("f", [], "Int32", [VarDecl("x", "Int32", num())])
    with pytest.raises(SystemExit):
        with redirect_stdout(io.StringIO()):
            MissingReturnChecker().check([func])


def test_alias_checker_reference_declaration_errors():
    def ref(inner):
        return FunctionDef("f", [], "NoneType", [
            VarDecl("x", "Int32", num()),
            VarDecl("r", "Ref Int32", RefExpr(inner)),
        ])

    cases = [
        ref(num()),             # not a variable
        ref(VarExpr("missing")),  # unknown target
    ]
    for ast in cases:
        with pytest.raises(SystemExit):
            with redirect_stdout(io.StringIO()):
                AliasChecker().check([ast])

    duplicate = FunctionDef("f", [], "NoneType", [
        VarDecl("x", "Int32", num()),
        VarDecl("r", "Ref Int32", RefExpr(VarExpr("x"))),
        VarDecl("r", "Ref Int32", RefExpr(VarExpr("x"))),
    ])
    with pytest.raises(SystemExit):
        with redirect_stdout(io.StringIO()):
            AliasChecker().check([duplicate])
