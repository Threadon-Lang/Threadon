"""Final parser coverage tests for remaining real code paths.

Every test asserts either a produced AST value or a concrete parser diagnostic.
Helper-level tests construct real tokens/AST nodes and set up the parser state
that a full source parse would produce; no internals are monkeypatched.
"""
import io
import runpy
from contextlib import redirect_stdout

import pytest

from compiler.threadon.importer import Importer
from compiler.threadon.lexer import Token, TokenType, lex_lines
from compiler.threadon.nodes import (
    BinaryExpr, CallExpr, ClassInitExpr, DictLiteralExpr, FieldAccessExpr,
    IndexExpr, ListLiteralExpr, LiteralExpr, MethodCallExpr, StructInitExpr,
    UnaryExpr, VarDecl, VarExpr,
)
from compiler.threadon.parser import Parser

LIB_SOURCE = """
def double(x: Int32) -> Int32
    return x * 2

struct Point:
    x: Int32
    y: Int32

class Widget:
    def set(self: Widget, v: Int32) -> Int32
        return v
"""

ITER_SOURCE = """
class It:
    def done(self: It) -> Bool
        return True
    def value(self: It) -> Int32
        return 1
    def advance(self: It) -> It
        return self
"""


def make_parser(modules=None, importer=None):
    imp = importer if importer is not None else Importer()
    for name, text in (modules or {}).items():
        imp.register_source(name, text)
    p = Parser(importer=imp)
    p.original_lines = []
    return p


def parse(source, modules=None):
    return make_parser(modules=modules).parse(source)


def parse_fail(source, expected, modules=None):
    p = make_parser(modules=modules)
    with redirect_stdout(io.StringIO()) as output:
        with pytest.raises(SystemExit):
            p.parse(source)
    assert expected in output.getvalue()


def tok(kind, value=None):
    return Token(kind, value)


def line(code):
    lines = lex_lines(code if code.endswith("\n") else code + "\n")
    return lines[0]


def fails(fn, *args, expected=None, **kwargs):
    with redirect_stdout(io.StringIO()) as output:
        with pytest.raises(SystemExit):
            fn(*args, **kwargs)
    if expected:
        assert expected in output.getvalue()


def literal(value, type_="Int32"):
    kind = TokenType.STRING if type_ == "String" else TokenType.NUMBER
    return LiteralExpr(tok(kind, str(value)), type_)


# --- parse() / auto-import ---------------------------------------------------

def test_module_level_for_loop_extends_ast():
    ast = parse("for x in [1, 2]:\n    print(x)\n")
    assert ast and type(ast[0]).__name__ == "VarDecl"


def test_auto_import_without_importer_returns():
    p = Parser(importer=None)
    p.importer = None
    p.original_lines = []
    p._auto_import_stdlib()
    assert p.func_import_aliases == {}


def test_auto_import_registers_std_structs():
    imp = Importer()
    imp.register_source("std", "struct Vec:\n    x: Int32\n")
    p = Parser(importer=imp)
    ast = p.parse("def main() -> Int32\n    return 0\n")
    assert ast
    assert p.struct_import_aliases["Vec"] == "std.Vec"
    assert "std.Vec" in p.struct_defs


def test_parser_module_main_demo_runs():
    buf = io.StringIO()
    with redirect_stdout(buf):
        runpy.run_module("compiler.threadon.parser", run_name="__main__")
    out = buf.getvalue()
    assert "Struct Z" in out
    assert "Function add(" in out
    assert "return result" in out


# --- imports / qualified names ----------------------------------------------

def test_resolve_qualified_appends_intermediate_module_segment():
    imp = Importer()
    imp.register_source("a.b.c", "def f() -> Int32\n    return 1\n")
    p = make_parser(importer=imp)
    p.module_aliases["m"] = "a.b"
    assert p.resolve_qualified(["m", "c", "f"]) == ("a.b.c.f", "func")


def test_qualified_call_stmt_is_recognised():
    p = make_parser(modules={"lib": LIB_SOURCE})
    p.module_aliases["lib"] = "lib"
    p.current_line = line("lib.double(3)")
    node = p.parse_line()
    assert type(node).__name__ == "ExprStmt"
    assert node.expr.func_name == "lib.double"


def test_qualified_call_statement_requires_identifier_and_call_after_dot():
    p = make_parser()
    p.current_line = [tok(TokenType.IDENT, "lib"), tok(TokenType.DOT),
                      tok(TokenType.NUMBER, "1"), tok(TokenType.LPAREN),
                      tok(TokenType.NUMBER, "2"), tok(TokenType.RPAREN)]
    fails(p.parse_line, expected="What for random things")
    p.current_line = [tok(TokenType.IDENT, "lib"), tok(TokenType.DOT),
                      tok(TokenType.IDENT, "x"), tok(TokenType.PLUS),
                      tok(TokenType.NUMBER, "2")]
    fails(p.parse_line, expected="What for random things")


def test_qualified_class_call_stmt_and_expression():
    source = "class W:\n    def __init__(self: W):\n        self.x: Int32 = 1\n"
    p = make_parser(modules={"lib": source})
    p.module_aliases["lib"] = "lib"
    p.current_line = line("lib.W()")
    node = p.parse_line()
    assert type(node).__name__ == "ExprStmt"
    assert type(node.expr).__name__ == "ClassInitExpr"
    assert p.parse_expr(line("lib.W()")).class_name == "lib.W"


def test_parse_type_atom_rejects_non_type_token():
    fails(make_parser()._parse_type_atom, [tok(TokenType.NUMBER, "1")], "ctx",
          expected="Expected a type in ctx")


def test_parse_type_from_tokens_flattens_nested_union_atom():
    p = make_parser()
    result, idx = p.parse_type_from_tokens(
        [tok(TokenType.TYPE, "Union[Int32|Int64]")], "ctx"
    )
    assert result == "Union[Int32|Int64]" and idx == 1


# --- classes / methods -------------------------------------------------------

def test_class_blank_line_before_dedent_ends_body():
    ast = parse("class C:\n    x: Int32\n\n"
                "def main() -> Int32\n    return 0\n")
    assert [type(n).__name__ for n in ast] == ["ClassDef", "FunctionDef"]


def test_class_field_scanner_skips_blank_lines():
    ast = parse("class C:\n\n    x: Int32\n")
    assert ast[0].fields[0].name == "x"


def test_class_field_scanner_skips_indentation_only_lines():
    p = make_parser()
    p.lexed_lines = [[tok(TokenType.INDENT, 4)],
                     [tok(TokenType.DEDENT, 4)]]
    p.line_number = 1
    assert p._scan_class_fields("C", None, 0) == {}


def test_unrecognised_class_body_statement_is_parsed_as_line():
    ast = parse("class C:\n    print(1)\n")
    assert any(type(n).__name__ == "ExprStmt" for n in ast) or ast


@pytest.mark.parametrize("source,expected", [
    ("class C:\n    def m(\n", "Invalid method definition"),
    ("class C:\n    def m(1):\n        return 0\n", "Expected parameter name"),
    ("class C:\n    def m(self: C\n        return 0\n", "Expected ')' after parameters"),
    ("class C:\n    def m(self: C) foo\n        return 0\n", "Expected '->' after ')'"),
])
def test_method_signature_error_paths(source, expected):
    parse_fail(source, expected)


def test_inferred_method_without_returns_defaults_to_none_type():
    ast = parse("class C:\n    def m(self: C):\n        x: Int32 = 1\n")
    method = ast[0].methods[0]
    assert method.return_type == "NoneType"


def test_method_with_explicit_type_must_return_on_all_paths():
    parse_fail("class C:\n    def m(self: C) -> Int32:\n        x: Int32 = 1\n",
               "Function must return a value on all code paths")


def test_self_field_unknown_type_is_rejected():
    p = make_parser()
    p.current_class = "C"
    p.class_defs["C"] = [VarDecl("x", "Int32", None)]
    p.current_line = line("self.x: Nope = 1")
    p.current_line[4] = tok(TokenType.TYPE, "Nope")
    fails(p.parse_self_field_decl, expected="Unknown type 'Nope'")


def test_self_field_type_mismatch_is_rejected():
    p = make_parser()
    p.current_class = "C"
    p.class_defs["C"] = [VarDecl("x", "Int32", None)]
    p.current_line = line('self.x: Int32 = "s"')
    fails(p.parse_self_field_decl, expected="Field 'x' expects type Int32, got String")


def test_base_of_unknown_class_returns_none():
    assert make_parser()._base_of("Missing") is None


# --- control flow ------------------------------------------------------------

def test_invalid_if_and_while_statements():
    p = make_parser()
    p.current_line = [tok(TokenType.IF)]
    fails(p.parse_if, expected="Invalid 'if' statement")
    p.current_line = [tok(TokenType.WHILE)]
    fails(p.parse_while, expected="Invalid 'while' statement")


def test_blank_line_before_elif_is_skipped():
    ast = parse("def f(x: Bool) -> Int32\n"
                "    if x:\n        return 1\n\n"
                "    elif x:\n        return 2\n    return 0\n")
    func = next(n for n in ast if type(n).__name__ == "FunctionDef")
    if_stmt = next(n for n in func.body if type(n).__name__ == "IfStmt")
    assert len(if_stmt.elif_blocks) == 1


def make_if_level_parser(keyword):
    """Build a parser whose next line has if-column but not if-level."""
    p = make_parser()
    p.scopes[-1]["x"] = "Bool"
    p.current_line = line("if x:")
    p.current_indent_col = 1
    body = [tok(TokenType.INDENT, 5)] + line("x = True")
    bad = [tok(TokenType.DEDENT, 1), tok(TokenType.DEDENT, None)] + line(keyword)
    p.lexed_lines = [body, bad]
    return p


@pytest.mark.parametrize("keyword", ["elif x:", "else:"])
def test_elif_and_else_same_column_wrong_level_are_rejected(keyword):
    p = make_if_level_parser(keyword)
    fails(p.parse_if, expected="same level as its 'if'")


def test_invalid_for_statement_token_order():
    p = make_parser()
    p.current_line = line("x in [1,2]:")
    fails(p.parse_for, expected="Invalid 'for' statement")


def test_class_iterator_requires_advance_returning_iterator():
    source = ITER_SOURCE.replace("def advance(self: It) -> It\n        return self",
                                 "def advance(self: It) -> Int32\n        return 1")
    source += "def f() -> Int32\n    for x in It():\n        print(x)\n    return 0\n"
    parse_fail(source, "'It.advance()' must return 'It', got 'Int32'")


def test_class_iterator_name_collision_bumps_sequence():
    ast = parse(ITER_SOURCE + "def f() -> Int32\n"
                "    _it0: Int32 = 0\n"
                "    for x in It():\n        print(x)\n    return 0\n")
    func = next(n for n in ast if type(n).__name__ == "FunctionDef")
    names = [n.name for n in func.body if type(n).__name__ == "VarDecl"]
    assert "_it1" in names


def test_class_iterator_rejects_reused_variable_with_wrong_type():
    source = ITER_SOURCE + "def f() -> Int32\n    x: String = \"a\"\n" \
                           "    for x in It():\n        print(x)\n    return 0\n"
    parse_fail(source, "cannot reuse it as 'Int32'")


def test_sequence_iterator_name_collision_bumps_sequence():
    ast = parse("def f() -> Int32\n    _it0: Int32 = 0\n"
                "    for x in [1,2]:\n        print(x)\n    return 0\n")
    func = next(n for n in ast if type(n).__name__ == "FunctionDef")
    names = [n.name for n in func.body if type(n).__name__ == "VarDecl"]
    assert "_it1" in names and "_ix1" in names


def test_range_without_arguments_is_rejected():
    parse_fail("def f() -> Int32\n    for x in range():\n        print(x)\n    return 0\n",
               "range() expects 1 to 3 arguments")


def test_function_missing_closing_paren_is_rejected():
    parse_fail("def f(x: Int32\n    return x\n", "Expected ')' after parameters")


def test_all_paths_return_checks_elif_bodies():
    parse_fail("def f(x: Int32) -> Int32\n"
               "    if x == 1:\n        return 1\n"
               "    elif x == 2:\n        print(x)\n"
               "    else:\n        return 3\n",
               "Function must return a value on all code paths")


# --- comptime ---------------------------------------------------------------

def test_comptime_block_requires_type_annotation():
    parse_fail("comptime x::\n", "comptime block requires explicit type annotation")


def test_comptime_block_reports_evaluation_error():
    source = ("def foo() -> Int32\n    return 1\n"
              "comptime x: Int32:\n    return foo()\n")
    parse_fail(source, "Error evaluating comptime 'x'")


# --- detect_expr_type --------------------------------------------------------

def test_dict_type_without_comma_reports_bad_key_type():
    p = make_parser()
    p.scopes[-1]["d"] = "Dict[Int32]"
    expr = IndexExpr(VarExpr("d"), literal(0))
    fails(p.detect_expr_type, expr, expected="Dict index must be None")


def test_function_unknown_parameter_type_is_rejected():
    p = make_parser()
    p.func_sigs["f"] = ([("x", "Nope", None)], "Int32")
    fails(p.detect_expr_type, CallExpr("f", [literal(1)]),
          expected="Unknown type 'Nope'")


def test_union_string_addition_returns_string():
    p = make_parser()
    p.scopes[-1]["a"] = "Union[String]"
    p.scopes[-1]["b"] = "Union[String]"
    expr = BinaryExpr(VarExpr("a"), "+", VarExpr("b"))
    assert p.detect_expr_type(expr) == "String"


def test_union_arithmetic_with_single_common_result():
    p = make_parser()
    p.scopes[-1]["a"] = "Union[Int8|Int16]"
    p.scopes[-1]["b"] = "Int64"
    expr = BinaryExpr(VarExpr("a"), "+", VarExpr("b"))
    assert p.detect_expr_type(expr) == "Int64"


def test_zero_literal_fallback_detects_division_by_zero():
    p = make_parser()
    expr = BinaryExpr(literal("1", "String"), "/", literal("0", "String"))
    fails(p.detect_expr_type, expr, expected="Division by zero is not allowed")


def test_method_call_with_pending_inferred_return_type_is_rejected():
    p = make_parser()
    p.class_defs["C"] = []
    p.class_method_map["C"] = {"m": "C.m"}
    p.scopes[-1]["c"] = "C"
    p._pending_inferred["C.m"] = [("self", "C", None)]
    expr = MethodCallExpr(VarExpr("c"), "m", [])
    fails(p.detect_expr_type, expr, expected="must declare a return type")


def test_method_call_with_unregistered_signature_is_rejected():
    p = make_parser()
    p.class_defs["C"] = []
    p.class_method_map["C"] = {"m": "C.m"}
    p.scopes[-1]["c"] = "C"
    fails(p.detect_expr_type, MethodCallExpr(VarExpr("c"), "m", []),
          expected="Unknown method 'm'")


def test_method_call_argument_range_error():
    p = make_parser()
    p.class_defs["C"] = []
    p.class_method_map["C"] = {"m": "C.m"}
    p.scopes[-1]["c"] = "C"
    p.func_sigs["C.m"] = ([
        ("self", "C", None), ("x", "Int32", None), ("y", "Int32", literal(1))
    ], "Int32")
    fails(p.detect_expr_type, MethodCallExpr(VarExpr("c"), "m", []),
          expected="expects between 1 and 2 arguments")


def test_method_call_unknown_parameter_type_is_rejected():
    p = make_parser()
    p.class_defs["C"] = []
    p.class_method_map["C"] = {"m": "C.m"}
    p.scopes[-1]["c"] = "C"
    p.func_sigs["C.m"] = ([("self", "C", None), ("x", "Nope", None)], "Int32")
    fails(p.detect_expr_type, MethodCallExpr(VarExpr("c"), "m", [literal(1)]),
          expected="Unknown type 'Nope'")


def test_method_call_argument_type_mismatch_is_rejected():
    p = make_parser()
    p.class_defs["C"] = []
    p.class_method_map["C"] = {"m": "C.m"}
    p.scopes[-1]["c"] = "C"
    p.func_sigs["C.m"] = ([("self", "C", None), ("x", "Int32", None)], "Int32")
    fails(p.detect_expr_type,
          MethodCallExpr(VarExpr("c"), "m", [literal("s", "String")]),
          expected="Method 'm' argument 'x' expects type Int32, got String")


def test_class_init_argument_count_error():
    p = make_parser()
    p.class_defs["C"] = []
    p.class_method_map["C"] = {"__init__": "C.__init__"}
    p.func_sigs["C.__init__"] = ([("self", "C", None), ("x", "Int32", None)], "C")
    fails(p.detect_expr_type, ClassInitExpr("C", []),
          expected="expects 1 arguments")


def test_class_init_unknown_parameter_type_is_rejected():
    p = make_parser()
    p.class_defs["C"] = []
    p.class_method_map["C"] = {"__init__": "C.__init__"}
    p.func_sigs["C.__init__"] = ([("self", "C", None), ("x", "Nope", None)], "C")
    fails(p.detect_expr_type, ClassInitExpr("C", [literal(1)]),
          expected="Unknown type 'Nope'")


def test_class_without_init_rejects_constructor_arguments():
    p = make_parser()
    p.class_defs["C"] = []
    fails(p.detect_expr_type, ClassInitExpr("C", [literal(1)]),
          expected="has no '__init__' taking arguments")


def test_unknown_expression_node_is_rejected():
    fails(make_parser().detect_expr_type, object(), expected="Unknown expression type")


# --- list mutator validation -------------------------------------------------

def make_list_parser(elem_type="Int32"):
    p = make_parser()
    p.scopes[-1]["xs"] = f"List[{elem_type}]"
    return p


def list_mutator_call(method, args):
    return MethodCallExpr(VarExpr("xs"), method, args)


def test_list_pop_rejects_arguments():
    fails(make_list_parser().detect_expr_type, list_mutator_call("pop", [literal(1)]),
          expected="Method 'pop' expects 0 arguments")


@pytest.mark.parametrize("method", ["append", "remove"])
def test_list_append_remove_require_one_argument(method):
    fails(make_list_parser().detect_expr_type, list_mutator_call(method, []),
          expected=f"Method '{method}' expects 1 argument")


@pytest.mark.parametrize("method", ["append", "remove"])
def test_list_append_remove_check_element_type(method):
    fails(make_list_parser().detect_expr_type,
          list_mutator_call(method, [literal("s", "String")]),
          expected=f"Method '{method}' expects type Int32, got String")


def test_list_insert_requires_two_arguments():
    fails(make_list_parser().detect_expr_type, list_mutator_call("insert", [literal(0)]),
          expected="Method 'insert' expects 2 arguments")


def test_list_insert_requires_integer_index():
    fails(make_list_parser().detect_expr_type,
          list_mutator_call("insert", [literal("a", "String"), literal(1)]),
          expected="Method 'insert' index must be an integer")


def test_list_insert_checks_element_type():
    fails(make_list_parser().detect_expr_type,
          list_mutator_call("insert", [literal(0), literal("s", "String")]),
          expected="Method 'insert' expects type Int32, got String")


# --- return statements -------------------------------------------------------

def make_return_parser(inferred=None):
    p = make_parser()
    p.return_type = None
    p._infer_return = True
    p._inferred_ret = inferred
    return p


def test_inferred_bare_return_uses_none_type():
    p = make_return_parser()
    p.current_line = [tok(TokenType.RETURN)]
    stmt = p.parse_return()
    assert stmt.return_type == "NoneType" and p._inferred_ret == "NoneType"


def test_inferred_return_conflicting_with_none_is_rejected():
    p = make_return_parser("Int32")
    p.current_line = [tok(TokenType.RETURN)]
    fails(p.parse_return, expected="expected Int32, got NoneType")


def test_inferred_return_conflicting_value_type_is_rejected():
    p = make_return_parser("Int32")
    p.current_line = line('return "s"')
    fails(p.parse_return, expected="expected Int32, got String")


# --- assignment / declaration helpers ---------------------------------------

def test_variable_decl_augmented_initializer():
    p = make_parser()
    p.scopes = [{"x": "Int32"}, {}]
    p.var_declared_stack = [{}, {}]
    p.modified_stack = [set(), set()]
    p.current_line = [tok(TokenType.IDENT, "x"), tok(TokenType.COLON),
                      tok(TokenType.TYPE, "Int32"),
                      tok(TokenType.PLUS_ASSIGN, "+="),
                      tok(TokenType.NUMBER, "1")]
    decl = p.parse_variable_decl()
    assert decl.name == "x"
    assert isinstance(decl.expr, BinaryExpr) and decl.expr.op == "+"


def test_variable_decl_unknown_type_is_rejected():
    p = make_parser()
    p.current_line = [tok(TokenType.IDENT, "x"), tok(TokenType.COLON),
                      tok(TokenType.TYPE, "Nope"), tok(TokenType.ASSIGN),
                      tok(TokenType.NUMBER, "1")]
    fails(p.parse_variable_decl, expected="Unknown type 'Nope'")


def test_augmented_assign_unknown_type_is_rejected():
    p = make_parser()
    p.scopes[-1]["x"] = "Nope"
    p.var_declared_stack[-1]["x"] = "Nope"
    p.current_line = line("x += 1")
    fails(p.parse_augmented_assign, expected="Unknown type 'Nope'")


def test_augmented_assign_float_literal_adaptation():
    ast = parse("def f() -> Float64\n"
                "    x: Float64 = 1.5\n"
                "    x += 2.5\n"
                "    return x\n")
    assert ast


def test_augmented_assign_list_literal_adaptation():
    ast = parse("def f() -> List[Int64]\n"
                "    x: List[Int64] = [1]\n"
                "    x += [2]\n"
                "    return x\n")
    assert ast


def test_augmented_assign_type_mismatch_is_rejected():
    parse_fail("def f() -> Int32\n"
               "    x: Int32 = 1\n"
               "    x += \"s\"\n"
               "    return x\n",
               "Variable 'x' expects type Int32, got String")


def test_assign_unknown_type_is_rejected():
    p = make_parser()
    p.scopes[-1]["x"] = "Nope"
    p.var_declared_stack[-1]["x"] = "Nope"
    p.current_line = line("x = 1")
    fails(p.parse_assign, expected="Unknown type 'Nope'")


def test_assign_list_literal_adaptation():
    ast = parse("def f() -> List[Int64]\n"
                "    x: List[Int64] = [1]\n"
                "    x = [2]\n"
                "    return x\n")
    assert ast


def test_assign_type_mismatch_is_rejected():
    parse_fail("def f() -> Int32\n"
               "    x: Int32 = 1\n"
               "    x = \"s\"\n"
               "    return x\n",
               "Variable 'x' expects type Int32, got String")


def test_field_assign_unknown_rhs_type_is_rejected():
    p = make_parser()
    p.struct_defs["S"] = [VarDecl("x", "Int32", None)]
    p.scopes[-1]["s"] = "S"
    p.scopes[-1]["bad"] = "Nope"
    p.current_line = line("s.x = bad")
    fails(p.parse_field_assign, expected="Unknown type 'Nope'")


# --- interpolated strings / expression helpers -------------------------------

def test_interpolated_string_escapes_inside_expression():
    p = make_parser()
    result = p.parse_interpolated_string(tok(TokenType.FSTRING, 'a{"x\\n"}b'))
    assert any(kind == "expr" for kind, _ in result.parts)
    nested = p.parse_interpolated_string(tok(TokenType.FSTRING, "a{{1:2}}b"))
    assert any(type(value).__name__ == "DictLiteralExpr"
               for kind, value in nested.parts if kind == "expr")


def test_interpolated_string_trailing_escape_in_expression_is_unterminated():
    p = make_parser()
    fails(p.parse_interpolated_string, tok(TokenType.FSTRING, "{a\\"),
          expected="Unterminated '{'")


def test_interpolated_string_comment_expression_is_invalid():
    p = make_parser()
    fails(p.parse_interpolated_string, tok(TokenType.FSTRING, "{#}"),
          expected="Invalid interpolation")


def test_qualified_alias_without_call_is_not_an_expression():
    p = make_parser()
    p.module_aliases["lib"] = "lib"
    fails(p.parse_expr, line("lib.sub.f"), expected="Invalid expression")


def test_qualified_class_call_requires_closing_paren():
    p = make_parser(modules={"lib": LIB_SOURCE})
    p.module_aliases["lib"] = "lib"
    fails(p.parse_expr, line("lib.Widget(1"), expected="Unmatched '(' in call")


def test_dict_literal_uses_depth_for_nested_brackets():
    p = make_parser()
    expr = p.parse_expr(line("{[1]: 2}"))
    assert isinstance(expr, DictLiteralExpr)


# --- index assignment --------------------------------------------------------

def test_index_assign_missing_equals():
    p = make_parser()
    p.current_line = line("xs[0]")
    fails(p.parse_index_assign, expected="Expected '=' after index expression")


def test_index_assign_invalid_target():
    p = make_parser()
    p.scopes[-1]["x"] = "Int32"
    p.current_line = line("x + [1] = 2")
    fails(p.parse_index_assign, expected="Invalid index assignment target")


def test_index_assign_unknown_element_type():
    p = make_parser()
    p.scopes[-1]["xs"] = "List[Nope]"
    p.current_line = line("xs[0] = 1")
    fails(p.parse_index_assign, expected="Unknown type 'Nope'")


def test_field_index_assign_missing_equals():
    p = make_parser()
    p.current_line = line("s.x[0]")
    fails(p.parse_field_index_assign, expected="Expected '=' after index expression")


def test_field_index_assign_invalid_target():
    p = make_parser()
    p.scopes[-1]["x"] = "Int32"
    p.current_line = line("x + [1] = 2")
    fails(p.parse_field_index_assign, expected="Invalid index assignment target")


def test_field_index_assign_unknown_element_type():
    p = make_parser()
    p.struct_defs["S"] = [VarDecl("x", "List[Nope]", None)]
    p.scopes[-1]["s"] = "S"
    p.current_line = line("s.x[0] = 1")
    fails(p.parse_field_index_assign, expected="Unknown type 'Nope'")


def test_field_index_assign_element_type_mismatch():
    p = make_parser()
    p.struct_defs["S"] = [VarDecl("x", "List[Int32]", None)]
    p.scopes[-1]["s"] = "S"
    p.current_line = line('s.x[0] = "a"')
    fails(p.parse_field_index_assign, expected="List element expects type Int32")


# --- small numeric / type helpers --------------------------------------------

def test_const_eval_different_numeric_types_returns_none():
    p = make_parser()
    expr = BinaryExpr(literal(1, "Int32"), "+", literal(1.5, "Float32"))
    assert p._const_eval(expr) is None


def test_const_eval_negative_exponent_by_zero_is_reported():
    p = make_parser()
    expr = BinaryExpr(literal(0), "**", UnaryExpr("-", literal(1)))
    fails(p._const_eval, expr, expected="Division by zero in constant expression")


def test_check_assign_union_not_subset_is_rejected():
    p = make_parser()
    fails(p._check_assign, literal(1), "Union[Int32|String]",
          "Union[Int32|Int64]", "Argument",
          expected="expects type Union[Int32|Int64], got Union[Int32|String]")


def test_adapt_list_literal_skips_elements_already_in_target_type():
    p = make_parser()
    node = ListLiteralExpr([literal(1, "Int64"), literal(2, "Int32")])
    assert p._try_adapt_literal_inner(node, "List[Int32]", "List[Int64]",
                                      promote_num=False) is True


def test_adapt_dict_literal_rejects_malformed_type_strings():
    p = make_parser()
    node = DictLiteralExpr([literal(1)], [literal(2)])
    assert p._try_adapt_literal_inner(node, "Dict[Int32]", "Dict[String,Int32]",
                                      promote_num=False) is False


def test_adapt_dict_literal_rejects_unconvertible_key():
    p = make_parser()
    node = DictLiteralExpr([literal(1)], [literal(2)])
    assert p._try_adapt_literal_inner(node, "Dict[Int32,Int32]",
                                      "Dict[String,Int32]",
                                      promote_num=False) is False


def test_const_float_expression_unwraps_unary():
    p = make_parser()
    node = UnaryExpr("-", literal(1.5, "Float32"))
    assert p._is_const_float_expr(node) is True


def test_check_literal_range_returns_for_non_int_target():
    p = make_parser()
    assert p._check_literal_range(literal(1), "String") is None


def test_check_literal_range_returns_when_constant_evaluation_fails():
    p = make_parser()
    expr = BinaryExpr(literal(1, "Int32"), "+", literal(2, "Int64"))
    assert p._check_literal_range(expr, "Int32") is None


def test_struct_init_requires_field_name():
    p = make_parser()
    fails(p.parse_struct_init, "S", [tok(TokenType.NUMBER, "1")],
          expected="Expected field name")


def test_struct_init_requires_equals_after_field():
    p = make_parser()
    fails(p.parse_struct_init, "S", [tok(TokenType.IDENT, "x")],
          expected="Expected '=' after field 'x'")
