"""Tests for the textual representations of ASTs and SSA IR.

These helpers are used by ``--dump-ast``/``--dump-ir`` and by optimizer
diagnostics.  Every branch is exercised with hand-built values so the
formatting is checked independently of the parser.
"""
from compiler.threadon.lexer import Token, TokenType
from compiler.threadon.nodes import (
    Assign,
    BinaryExpr,
    CallExpr,
    ClassDef,
    ClassInitExpr,
    FieldAccessExpr,
    FieldAssign,
    FunctionDef,
    IfStmt,
    IndexAssign,
    IndexExpr,
    ListLiteralExpr,
    LiteralExpr,
    MethodCallExpr,
    RefExpr,
    ReturnStmt,
    SliceExpr,
    StructDef,
    UnaryExpr,
    VarDecl,
    VarExpr,
    WhileStmt,
)
from compiler.threadon.parser import print_ast, print_expr
from compiler.threadon.to_high_ir import (
    IRBlock,
    IRFunction,
    IRInstr,
    IRModule,
    IRPhi,
    SSAValue,
)


def lit(value, type_="Int32"):
    return LiteralExpr(Token(TokenType.NUMBER, value), type_)


# --- parser.print_expr -----------------------------------------------------

def test_print_expr_covers_every_expression_kind():
    x = VarExpr("x")
    assert print_expr(lit("7")) == "7"
    assert print_expr(x) == "x"
    assert print_expr(CallExpr("f", [x, lit("2")])) == "f(x, 2)"
    assert print_expr(FieldAccessExpr(x, "field")) == "x.field"
    assert print_expr(MethodCallExpr(x, "m", [lit("1")])) == "x.m(1)"
    assert print_expr(ClassInitExpr("Point", [lit("1")])) == "Point(1)"
    assert print_expr(BinaryExpr(x, "+", lit("1"))) == "x + 1"
    assert print_expr(UnaryExpr("-", x)) == "-x"
    assert print_expr(RefExpr(x)) == "x^"
    assert print_expr(ListLiteralExpr([lit("1"), x])) == "[1, x]"
    assert print_expr(IndexExpr(x, lit("0"))) == "x[0]"
    assert print_expr(SliceExpr(x, lit("1"), lit("3"))) == "x[1:3]"
    assert print_expr(SliceExpr(x, None, lit("3"))) == "x[:3]"
    assert print_expr(SliceExpr(x, lit("1"), None)) == "x[1:]"
    assert print_expr(SliceExpr(x, None, None)) == "x[:]"


def test_print_expr_unknown_node():
    assert print_expr(object()) == "<unknown expr>"


# --- parser.print_ast ------------------------------------------------------

def test_print_ast_covers_every_statement_kind(capsys):
    x = VarExpr("x")
    ast = [
        FunctionDef("f", [("a", "Int32", lit("1")), ("b", "Int32", None)],
                    "Int32", [
                        VarDecl("v", "Int32", None),
                        VarDecl("w", "Int32", lit("2")),
                        Assign("v", lit("3")),
                        IndexAssign(x, lit("0"), lit("4")),
                        FieldAssign("p", "x", lit("5")),
                        ReturnStmt("Int32", None),
                        ReturnStmt("Int32", lit("6")),
                    ]),
        IfStmt(x, [Assign("v", lit("1"))],
               [(lit("2"), [Assign("v", lit("2"))])],
               [Assign("v", lit("3"))]),
        IfStmt(x, [], [], None),
        WhileStmt(x, [Assign("v", lit("1"))]),
        StructDef("S", [VarDecl("f", "Int32", None)]),
        ClassDef("C", "Base", [], [FunctionDef("m", [], "NoneType", [])],
                 [VarDecl("g", "Int32", None)]),
        ClassDef("D", None, [], [], []),
        object(),
    ]
    print_ast(ast)
    text = capsys.readouterr().out
    for expected in (
        "Function f(", "param a: Int32 = 1", "param b: Int32",
        "VarDecl v: Int32", "VarDecl w: Int32 = 2", "Assign v = 3",
        "IndexAssign x[0] = 4", "FieldAssign p.x = 5", "return",
        "return 6", "If x:", "Elif 2:", "Else:", "While x:",
        "Struct S", "Class C(Base)", "Class D", "<Unknown node object>",
    ):
        assert expected in text


# --- to_high_ir formatting -------------------------------------------------

def test_ssa_value_str():
    assert str(SSAValue("t1", "Int32")) == "t1: Int32"


def test_ir_instr_str_for_collection_ops():
    a, b, c = SSAValue("%a", "Int32"), SSAValue("%b", "Int32"), SSAValue("%c", "Int32")
    r = SSAValue("%r", "Int32")
    assert str(IRInstr("struct_init", ["Point", "x", a], result=r)) == \
        "%r: Int32 = struct_init %Point(x=%a)"
    assert str(IRInstr("struct_init", ["Point", "x", a])) == \
        "struct_init %Point(x=%a)"
    assert str(IRInstr("list_init", ["Int32", a, b], result=r)) == \
        "%r: Int32 = list_init Int32 [%a, %b]"
    assert str(IRInstr("list_init", ["Int32"])) == "list_init Int32 []"
    assert str(IRInstr("list_get", [a, b], result=r)) == \
        "%r: Int32 = list_get %a[%b]"
    assert str(IRInstr("list_get", [a, b])) == "list_get %a[%b]"
    assert str(IRInstr("list_set", [a, b, c], result=r)) == \
        "%r: Int32 = list_set %a[%b] = %c"
    assert str(IRInstr("list_set", [a, b, c])) == "list_set %a[%b] = %c"
    assert str(IRInstr("dict_init", ["Int32", "Int32", a, b], result=r)) == \
        "%r: Int32 = dict_init Int32,Int32 {%a: %b}"
    assert str(IRInstr("dict_init", ["Int32", "Int32"])) == "dict_init Int32,Int32 {}"
    assert str(IRInstr("dict_get", [a, b], result=r)) == \
        "%r: Int32 = dict_get %a[%b]"
    assert str(IRInstr("dict_get", [a, b])) == "dict_get %a[%b]"
    assert str(IRInstr("dict_set", [a, b, c], result=r)) == \
        "%r: Int32 = dict_set %a[%b] = %c"
    assert str(IRInstr("dict_set", [a, b, c])) == "dict_set %a[%b] = %c"


def test_ir_instr_str_generic_form():
    a, b = SSAValue("%a", "Int32"), SSAValue("%b", "Int32")
    r = SSAValue("%r", "Int32")
    assert str(IRInstr("add", [a, b], result=r)) == "%r: Int32 = add %a: Int32, %b: Int32"
    assert str(IRInstr("br", ["entry"])) == "br entry"


def test_ir_phi_str():
    a, b, r = SSAValue("%a", "Int32"), SSAValue("%b", "Int32"), SSAValue("%r", "Int32")
    assert str(IRPhi(r, [("entry", a), ("loop", b)])) == \
        "%r: Int32 = phi entry: %a, loop: %b"


def test_ir_block_str_and_terminator_guard():
    a, r = SSAValue("%a", "Int32"), SSAValue("%r", "Int32")
    block = IRBlock("entry")
    assert str(block) == "entry:"
    block.add_instr(IRInstr("const", ["1"], result=r))
    block.set_terminator(IRInstr("br", ["exit"]))
    assert str(block) == "entry:\n  %r: Int32 = const 1\n  br exit"
    try:
        block.set_terminator(IRInstr("ret_void", []))
    except Exception as exc:
        assert "already has a terminator" in str(exc)
    else:
        raise AssertionError("a second terminator must be rejected")


def test_ir_function_str_reports_cfg_and_analysis():
    func = IRFunction("f", [("a", "Int32", None)], "Int32")
    entry = IRBlock("entry")
    exit_ = IRBlock("exit")
    a, r = SSAValue("%a", "Int32"), SSAValue("%r", "Int32")
    entry.add_instr(IRInstr("add", [a, a], result=r))
    entry.set_terminator(IRInstr("br", ["exit"]))
    exit_.set_terminator(IRInstr("ret", [r]))
    func.add_block(entry)
    func.add_block(exit_)
    text = str(func)
    assert text.startswith("func f(a: Int32) -> Int32")
    for part in ("entry:", "exit:", "preds: []", "succs: ['exit']",
                 "dominators:", "live_in:", "live_out:"):
        assert part in text
    try:
        func.add_block(IRBlock("entry"))
    except Exception as exc:
        assert "Duplicate block label" in str(exc)
    else:
        raise AssertionError("duplicate block labels must be rejected")


def test_ir_function_cfg_rejects_unknown_targets():
    for terminator, message in (
        (IRInstr("br", ["missing"]), "missing"),
        (IRInstr("cond_br", ["%c", "missing", "entry"]), "missing"),
        (IRInstr("cond_br", ["%c", "entry", "missing"]), "missing"),
    ):
        func = IRFunction("f", [], "Int32")
        entry = IRBlock("entry")
        entry.set_terminator(terminator)
        func.add_block(entry)
        try:
            func.build_cfg()
        except Exception as exc:
            assert message in str(exc)
        else:
            raise AssertionError("unknown branch targets must be rejected")


def test_ir_module_str():
    module = IRModule()
    module.add_type("Point", [("x", "Int32"), ("y", "Int32")])
    func = IRFunction("f", [], "Int32")
    block = IRBlock("entry")
    block.set_terminator(IRInstr("ret", [SSAValue("%r", "Int32")]))
    func.add_block(block)
    module.add_func(func)
    text = str(module)
    assert text.startswith("module:")
    assert "type %Point = { x: Int32, y: Int32 }" in text
    assert "func f() -> Int32" in text
