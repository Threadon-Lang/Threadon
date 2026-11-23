"""Deep parser tests for remaining statement, expression and type-check paths.

The snippets are real (mostly deliberately malformed) Threadon programs.  Every
test asserts either the produced AST or the parser's diagnostic, so the tests
verify behavior rather than merely executing lines.
"""
import io
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
g: Int32 = 7

def double(x: Int32) -> Int32
    return x * 2

struct Point:
    x: Int32
    y: Int32

class Widget:
    self.label: String
    def set(self: Widget, v: Int32) -> Int32
        return v

class Child(Widget):
    def reset(self: Child) -> Int32
        return 0
"""


def new_parser(source="", modules=None, module_name=""):
    imp = Importer()
    for name, text in (modules or {}).items():
        imp.register_source(name, text)
    p = Parser(importer=imp, module_name=module_name)
    p.parse(source) if source else None
    p.original_lines = source.splitlines()
    return p


def parse(source, modules=None):
    return new_parser(source="", modules=modules).parse(source)


def parse_fail(source, expected, modules=None):
    p = new_parser(modules=modules)
    with redirect_stdout(io.StringIO()) as output:
        with pytest.raises(SystemExit):
            p.parse(source)
    assert expected in output.getvalue()


def tok(kind, value=None):
    return Token(kind, value)


def lit(value="1", type_="Int32"):
    kind = TokenType.STRING if type_ == "String" else TokenType.NUMBER
    return LiteralExpr(tok(kind, value), type_)


def fails(fn, *args, expected=None, **kwargs):
    with redirect_stdout(io.StringIO()) as output:
        with pytest.raises(SystemExit):
            fn(*args, **kwargs)
    if expected:
        assert expected in output.getvalue()


# --- parse_line and imports -------------------------------------------------

def test_qualified_expression_statement():
    ast = parse("class C:\n    def m(self: C) -> Int32\n        return 1\n"
                "def main() -> Int32\n    c: C = C()\n    c.m()\n    return 0\n")
    assert ast[-1].name == "main"


def test_unrecognised_statement_is_rejected():
    parse_fail("1 2\n", "What for random things where you doing there")


def test_from_import_class_copies_inheritance_chain():
    p = new_parser(modules={"lib": LIB_SOURCE})
    p.parse("from lib import Child\ndef main() -> Int32\n"
            "    c: Child\n    return 0\n")
    assert "lib.Child" in p.class_defs
    assert "lib.Widget" in p.class_defs  # base was copied recursively
    assert p.class_import_aliases["Child"] == "lib.Child"


def test_import_alias_trailing_tokens_error():
    parse_fail("import lib as m x\n", "Unexpected token at end of import statement",
               {"lib": LIB_SOURCE})


def test_lazy_function_resolution_rejects_types_and_missing_members():
    p = new_parser(modules={"lib": LIB_SOURCE})
    p.lazy_imports["Point"] = ("lib", "Point")
    fails(p.resolve_func_name, "Point",
          expected="'Point' is a type, not a function")
    p.lazy_imports["missing"] = ("lib", "missing")
    fails(p.resolve_func_name, "missing",
          expected="Module 'lib' has no member 'missing'")


def test_qualified_module_not_imported_error():
    p = new_parser()
    fails(p.resolve_qualified, ["other", "thing"], expected="Module 'other' is not imported")


def test_lexical_error_is_reported_with_position():
    parse_fail("x = @\n", "Lexical error")


def test_parse_returns_flattened_node_lists():
    # A function returning a list of nodes is extended rather than appended.
    p = new_parser()
    ast = p.parse("struct S:\n    x: Int32\n")
    assert any(type(node).__name__ == "StructDef" for node in ast)


# --- type atoms -------------------------------------------------------------

def test_parse_type_atom_empty_tokens():
    fails(new_parser()._parse_type_atom, [], "ctx", expected="Expected a type in ctx")


def test_dict_type_with_nested_key_bracket_tracks_depth():
    p = new_parser()
    L, B, R, C = TokenType.IDENT, TokenType.LBRACKET, TokenType.RBRACKET, TokenType.COMMA
    tokens = [tok(L, "Dict"), tok(B), tok(L, "List"), tok(B),
              tok(TokenType.TYPE, "Int32"), tok(R), tok(C),
              tok(TokenType.TYPE, "String"), tok(R)]
    assert p._parse_type_atom(tokens, "ctx") == ("Dict[List[Int32],String]", 9)


def test_parse_type_from_tokens_expands_group_member():
    p = new_parser()
    result, idx = p.parse_type_from_tokens([tok(TokenType.TYPE, "Int")], "ctx")
    assert result.startswith("Union[")
    assert idx == 1


def test_import_member_missing_module_member():
    p = new_parser(modules={"lib": LIB_SOURCE})
    with redirect_stdout(io.StringIO()) as output:
        with pytest.raises(SystemExit):
            p.import_member("lib", "missing")
    assert "has no member 'missing'" in output.getvalue()


# --- class fields and self field declarations -------------------------------

def test_class_field_declaration_error_paths():
    parse_fail("class C:\n    x: Int32 = 1\n",
               "cannot have an initializer at class body level")
    parse_fail("class C:\n    x: Int32\n    x: String\n", "Duplicate field 'x'")


def test_self_field_declaration_errors():
    parse_fail("def f() -> Int32\n    self.x: Int32 = 1\n    return 0\n",
               "'self' can only be used inside a class method")
    parse_fail("class C:\n    def __init__(self: C):\n"
               "        self.x: Int32 1\n", "Expected '=' in self field declaration")
    parse_fail("class C:\n    x: Int32\n    def __init__(self: C):\n"
               "        self.x: Int32 = \"str\"\n",
               "Field 'x' expects type Int32, got String")


def test_self_field_decl_without_initializer():
    p = new_parser()
    p.current_class = "C"
    p.class_defs["C"] = [VarDecl("x", "Int32", None)]
    p.current_line = [tok(TokenType.IDENT, "self"), tok(TokenType.DOT),
                      tok(TokenType.IDENT, "x"), tok(TokenType.COLON),
                      tok(TokenType.TYPE, "Int32")]
    decl = p.parse_self_field_decl()
    assert decl.field == "x" and decl.expr is None
    p.class_defs["C"] = []
    fails(p.parse_self_field_decl, expected="has no field 'x'")


# --- control flow errors ----------------------------------------------------

def test_if_elif_and_else_error_paths():
    parse_fail("def f() -> Int32\n    if:\n        return 1\n    return 0\n",
               "Empty expression")
    parse_fail("def f(x: Bool) -> Int32\n    if x:\n        return 1\n"
               "  elif x:\n        return 2\n    return 0\n",
               "same column as its 'if'")
    parse_fail("def f(x: Bool) -> Int32\n    if x:\n        return 1\n"
               "    elif 1:\n        return 2\n    return 0\n",
               "Elif condition must be Bool")
    parse_fail("def f(x: Bool) -> Int32\n    if x:\n        return 1\n"
               "  else:\n        return 2\n", "same column as its 'if'")
    parse_fail("def f(x: Bool) -> Int32\n    if x:\n        return 1\n"
               "    elif x:\n        return 2\n  else:\n        return 3\n",
               "same column as its 'if'")

def test_while_and_thread_error_paths():
    parse_fail("def f() -> Int32\n    while:\n        return 1\n    return 0\n",
               "Empty expression")
    parse_fail("def f() -> Int32\n    thread w() on True:\n"
               "        print(1)\n    return 0\n",
               "only allowed at module level")


def test_thread_with_blank_line_in_body():
    ast = parse("thread w() on True:\n\n    print(1)\n")
    assert any(type(node).__name__ == "ThreadNode" for node in ast)


# --- comptime ---------------------------------------------------------------

def test_comptime_evaluation_error_paths():
    parse_fail("comptime x: Int32 = 1 / 0\n", "Error evaluating comptime 'x'")
    parse_fail("comptime x: Int32 = missing()\n", "Error evaluating comptime 'x'")
    parse_fail("comptime x: Int32 = 1 / 0\ndef main() -> Int32\n    return 0\n",
               "Error evaluating comptime 'x'")


def test_comptime_statement_syntax_errors():
    parse_fail("comptime x: Int32 foo = 1\n", "Expected ':' or '=' in comptime statement")
    parse_fail("comptime x:\n    return 1\n", "Invalid comptime statement")


def test_comptime_block_with_eval_error():
    parse_fail("comptime x: Int32:\n    return 1 / 0\n", "Division by zero")


# --- for loops --------------------------------------------------------------

def test_for_statement_error_paths():
    parse_fail("def f() -> Int32\n    for x in:\n        print(x)\n    return 0\n",
               "Expected an iterable in 'for' statement")
    parse_fail("class C:\n    def m(self: C) -> Int32\n        return 0\n"
               "def f() -> Int32\n    for x in C():\n        print(x)\n    return 0\n",
               "missing method 'done()'")
    parse_fail("def f() -> Int32\n    x: String = \"a\"\n"
               "    for x in [1,2]:\n        print(x)\n    return 0\n",
               "cannot reuse it as 'Int32'")
    parse_fail("def f() -> Int32\n    for x in range(1,2:\n"
               "        print(x)\n    return 0\n", "Unmatched '(' in range() call")
    parse_fail("def f() -> Int32\n    for x in range(1,2,3,4):\n"
               "        print(x)\n    return 0\n", "range() expects 1 to 3 arguments")


# --- interpolated strings ---------------------------------------------------

def test_interpolated_string_escape_and_nested_braces():
    p = new_parser()
    tokens = lex_lines('f"a\\zb{ {1:2} }c"')
    result = p.parse_interpolated_string(tokens[0][0])
    assert result.parts[0] == ("lit", "azb")
    assert any(kind == "expr" for kind, _ in result.parts)


def test_interpolated_string_trailing_backslash():
    p = new_parser()
    result = p.parse_interpolated_string(tok(TokenType.FSTRING, "abc\\"))
    assert ("lit", "abc\\") in result.parts


def test_interpolated_string_error_paths():
    p = new_parser()
    for value, expected in (
        ("{x", "Unterminated '{' in interpolated string"),
        ("{}", "Empty interpolation in interpolated string"),
        ("{ }", "Empty interpolation in interpolated string"),
    ):
        fails(p.parse_interpolated_string, tok(TokenType.FSTRING, value),
              expected=expected)


# --- expression parsing -----------------------------------------------------

def test_field_access_chain_and_unmatched_calls():
    p = new_parser(modules={"lib": LIB_SOURCE})
    assert isinstance(p.parse_expr(lex_lines("a.b.c")[0]), FieldAccessExpr)
    p.module_aliases["lib"] = "lib"
    fails(p.parse_expr, lex_lines("lib.double(1")[0],
          expected="Unmatched '(' in call")
    fails(p.parse_expr, lex_lines("Int32(1")[0], expected="Unmatched '(' in cast")


def test_module_alias_without_call_is_not_an_expression():
    p = new_parser()
    p.module_aliases["m"] = "m"
    fails(p.parse_expr, lex_lines("m.x")[0], expected="Invalid expression")


def test_list_and_dict_literal_error_paths():
    p = new_parser()
    fails(p.parse_expr, lex_lines("[")[0], expected="Unmatched '[' in list literal")
    fails(p.parse_expr, lex_lines("[,1]")[0], expected="Empty element in list literal")
    fails(p.parse_expr, lex_lines("{")[0], expected="Unmatched '{' in dict literal")
    fails(p.parse_expr, lex_lines("{1 2}")[0],
          expected="Dict literal entries must be 'key: value' pairs")
    fails(p.parse_expr, lex_lines("{:1}")[0],
          expected="Dict literal entry cannot have empty key or value")


def test_dict_literal_nested_colon_uses_depth():
    p = new_parser()
    expr = p.parse_expr(lex_lines('{"a": {"b": 1}}')[0])
    assert isinstance(expr, DictLiteralExpr)


def test_postfix_error_paths():
    p = new_parser()
    fails(p.parse_expr, lex_lines("x.m(")[0], expected="Unmatched '(' in method call")
    fails(p.parse_expr, lex_lines("x[")[0], expected="Unmatched '[' in index expression")
    fails(p.parse_expr, lex_lines("x[]")[0], expected="Empty index expression")
    fails(p.parse_expr, lex_lines("x[1:2:3]")[0], expected="Slice step is not supported")
    fails(p.parse_expr, lex_lines("x[0] y")[0],
          expected="Unexpected tokens after index expression")
    fails(p.parse_expr, lex_lines("x.m() y")[0],
          expected="Unexpected tokens after index expression")


def test_nested_index_depth_is_tracked():
    p = new_parser()
    p.scopes[-1]["x"] = "List[List[Int32]]"
    expr = p.parse_expr(lex_lines("x[0][1]")[0])
    assert isinstance(expr, IndexExpr)
