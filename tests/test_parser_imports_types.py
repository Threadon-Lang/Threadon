"""Parser tests for imports, type annotations and class member validation.

The snippets use the importer's in-memory source registry so that module
resolution is exercised with real parser/importer cooperation instead of fakes.
"""
import io
from contextlib import redirect_stdout

import pytest

from compiler.threadon.importer import Importer
from compiler.threadon.lexer import Token, TokenType
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
"""


def make_parser(source="", modules=None):
    imp = Importer()
    for name, mod_source in (modules or {}).items():
        imp.register_source(name, mod_source)
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


def fails(fn, *args, expected=None, **kwargs):
    with redirect_stdout(io.StringIO()) as output:
        with pytest.raises(SystemExit):
            fn(*args, **kwargs)
    if expected:
        assert expected in output.getvalue()


# --- eager and lazy import resolution --------------------------------------

def test_lazy_from_import_resolves_function_on_use():
    p = make_parser(modules={"lib": LIB_SOURCE})
    p.parse("lazyfrom lib import double\ndef main() -> Int32\n    return double(3)\n")
    assert p.func_import_aliases["double"] == "lib.double"
    assert "double" not in p.lazy_imports


def test_lazy_from_import_resolves_struct_as_type():
    p = make_parser(modules={"lib": LIB_SOURCE})
    p.parse("lazyfrom lib import Point\ndef main() -> Int32\n"
            "    p: Point\n    return p.x\n")
    assert p.struct_import_aliases["Point"] == "lib.Point"
    assert "Point" not in p.lazy_imports


def test_lazy_from_import_resolves_class_as_type():
    p = make_parser(modules={"lib": LIB_SOURCE})
    p.parse("lazyfrom lib import Widget\ndef main() -> Int32\n"
            "    w: Widget\n    return 0\n")
    assert p.class_import_aliases["Widget"] == "lib.Widget"
    assert "Widget" not in p.lazy_imports


def test_lazy_from_import_function_used_as_type_is_an_error():
    parse_fail(
        "lazyfrom lib import double\ndef main() -> Int32\n"
        "    x: double\n    return 0\n",
        "'double' is a function, not a type",
        {"lib": LIB_SOURCE},
    )
    p = make_parser(modules={"lib": LIB_SOURCE})
    assert p.resolve_type("double", strict=False) == "double"


def test_lazy_from_import_unknown_member_is_an_error():
    parse_fail(
        "lazyfrom lib import missing\ndef main() -> Int32\n"
        "    return missing()\n",
        "Module 'lib' has no member 'missing'",
        {"lib": LIB_SOURCE},
    )


def test_lazy_from_import_unknown_type_member_is_an_error():
    parse_fail(
        "lazyfrom lib import missing\ndef main() -> Int32\n"
        "    x: missing\n    return 0\n",
        "Module 'lib' has no member 'missing'",
        {"lib": LIB_SOURCE},
    )


@pytest.mark.parametrize("typ,expected", [
    ("Point", "lib.Point"),
    ("Widget", "lib.Widget"),
])
def test_lazy_module_qualifier_resolves_types(typ, expected):
    source = (f"lazyimport lib\ndef main() -> Int32\n"
              f"    x: lib.{typ}\n    return 0\n")
    p = make_parser(modules={"lib": LIB_SOURCE})
    p.parse(source)
    assert p.module_aliases["lib"] == "lib"
    assert expected in p.struct_defs or expected in p.class_defs


def test_lazy_module_qualifier_resolves_function():
    p = make_parser(modules={"lib": LIB_SOURCE})
    p.parse("lazyimport lib\ndef main() -> Int32\n    return lib.double(3)\n")
    assert "lib.double" in p.func_sigs


def test_lazy_module_qualifier_function_as_type_is_an_error():
    parse_fail(
        "lazyimport lib\ndef main() -> Int32\n    x: lib.double\n    return 0\n",
        "'lib.double' is a function, not a type",
        {"lib": LIB_SOURCE},
    )
    p = make_parser(modules={"lib": LIB_SOURCE})
    p.module_aliases["lib"] = "lib"
    assert p.resolve_type("lib.double", strict=False) == "lib.double"


def test_lazy_module_qualifier_unknown_member_is_an_error():
    parse_fail(
        "lazyimport lib\ndef main() -> Int32\n    return lib.missing()\n",
        "Module 'lib' has no member 'missing'",
        {"lib": LIB_SOURCE},
    )


def test_import_variable_is_rejected():
    parse_fail("from lib import g\n", "Cannot import variable 'g'", {"lib": LIB_SOURCE})


def test_import_unknown_member_is_rejected():
    parse_fail("from lib import missing\n", "Module 'lib' has no member 'missing'",
               {"lib": LIB_SOURCE})


def test_import_variable_via_qualified_member_is_rejected():
    parse_fail(
        "import lib\ndef main() -> Int32\n    x: lib.g\n    return 0\n",
        "Module 'lib' has no function or type 'g'",
        {"lib": LIB_SOURCE},
    )


def test_dotted_module_path_with_alias():
    p = make_parser(modules={"lib.sub": "def f() -> Int32\n    return 1\n"})
    p.parse("import lib.sub as s\ndef main() -> Int32\n    return s.f()\n")
    assert p.module_aliases["s"] == "lib.sub"


def test_from_import_alias():
    p = make_parser(modules={"lib": LIB_SOURCE})
    p.parse("from lib import double as twice\ndef main() -> Int32\n"
            "    return twice(1)\n")
    assert p.func_import_aliases["twice"] == "lib.double"


@pytest.mark.parametrize("source,expected", [
    ("import lib.\n", "Expected module name after '.'"),
    ("from lib x double\n", "Expected 'import' after module name"),
    ("from lib import 1\n", "Expected name to import"),
    ("from lib import double double\n", "Unexpected token in import statement"),
    ("from lib import double,\n", "Trailing comma in import is not allowed"),
    ("import lib as\n", "Expected alias name after 'as'"),
    ("import lib as 1\n", "Expected alias name after 'as'"),
    ("import lib extra\n", "Unexpected token after module name"),
    ("from lib import double as\n", "Expected alias name after 'as'"),
])
def test_import_syntax_errors(source, expected):
    parse_fail(source, expected, {"lib": LIB_SOURCE})


# --- type token and type atom parsing --------------------------------------

def test_parse_type_token():
    p = make_parser()
    assert p.parse_type_token(tok(TokenType.TYPE, "Int32"), "test") == "Int32"
    p.struct_defs["Point"] = []
    assert p.parse_type_token(tok(TokenType.IDENT, "Point"), "test") == "Point"
    fails(p.parse_type_token, None, "test", expected="Expected a type in test")
    fails(p.parse_type_token, tok(TokenType.IDENT, "Missing"), "test",
          expected="Unknown type 'Missing' in test")
    fails(p.parse_type_token, tok(TokenType.NUMBER, "1"), "test",
          expected="Expected a type in test")


def test_parse_type_atom_list_and_dict():
    p = make_parser()
    L, LB, RB, C = TokenType.IDENT, TokenType.LBRACKET, TokenType.RBRACKET, TokenType.COMMA
    assert p._parse_type_atom([tok(L, "List"), tok(LB), tok(TokenType.TYPE, "Int32"),
                               tok(RB)], "test") == ("List[Int32]", 4)
    assert p._parse_type_atom([
        tok(L, "Dict"), tok(LB), tok(TokenType.TYPE, "String"), tok(C),
        tok(L, "List"), tok(LB), tok(TokenType.TYPE, "Int32"), tok(RB), tok(RB),
    ], "test") == ("Dict[String,List[Int32]]", 9)
    assert p._parse_type_atom([tok(TokenType.TYPE, "Bool")], "test") == ("Bool", 1)


@pytest.mark.parametrize("tokens,expected", [
    ([tok(TokenType.IDENT, "List")], "Expected '[' after 'List' in type"),
    ([tok(TokenType.IDENT, "List"), tok(TokenType.LBRACKET),
      tok(TokenType.TYPE, "Int32")], "Unmatched '[' in type"),
    ([tok(TokenType.IDENT, "List"), tok(TokenType.LBRACKET),
      tok(TokenType.TYPE, "Builtin"), tok(TokenType.RBRACKET)],
     "List element type cannot be a type group or union"),
    ([tok(TokenType.IDENT, "Dict")], "Expected '[' after 'Dict' in type"),
    ([tok(TokenType.IDENT, "Dict"), tok(TokenType.LBRACKET),
      tok(TokenType.TYPE, "Int32")], "Unmatched '[' in type"),
    ([tok(TokenType.IDENT, "Dict"), tok(TokenType.LBRACKET),
      tok(TokenType.TYPE, "Int32"), tok(TokenType.RBRACKET)],
     "Dict type requires two type parameters"),
])
def test_parse_type_atom_errors(tokens, expected):
    fails(make_parser()._parse_type_atom, tokens, "test", expected=expected)


def test_parse_type_from_tokens_union_and_group():
    p = make_parser()
    T, P = TokenType.TYPE, TokenType.PIPE
    assert p.parse_type_from_tokens([tok(T, "Int32"), tok(P), tok(T, "String")],
                                    "test") == ("Union[Int32|String]", 3)
    fails(p.parse_type_from_tokens, [tok(T, "Int32"), tok(P), tok(T, "String")],
          "test", 0, False, expected="Union types are not allowed here")
    fails(p.parse_type_from_tokens, [tok(T, "Int32"), tok(P)], "test",
          expected="Expected a type after '|' in test")
    fails(p.parse_type_from_tokens, [], "test", expected="Expected a type in test")


def test_normalize_union_deduplicates_and_validates():
    p = make_parser()
    p.struct_defs["Point"] = []
    assert p._normalize_union(["Int32", "Int32", "Point"], "test") == \
        ["Int32", "Point"]
    assert p._normalize_union(["Int32", "String"], "test") == ["Int32", "String"]
    fails(p._normalize_union, [], "test", expected="Expected a type in test")
    fails(p._normalize_union, ["Nope"], "test", expected="Unknown type 'Nope' in test")


# --- class fields and methods ----------------------------------------------

def test_class_field_conflicting_types():
    parse_fail(
        "class C:\n    self.x: Int32\n    self.x: String\n",
        "declared with conflicting types",
    )


def test_class_field_star_expression_and_blank_lines_are_skipped():
    ast = parse("class C:\n\n    self.x: Int32\n\n    def m(self: C):\n"
                "        return 0\n")
    assert ast and ast[0].name == "C"


@pytest.mark.parametrize("method,expected", [
    ("def m(x: Int32):\n        return 0\n", "Method must have a 'self' parameter"),
    ("def m(self: String):\n        return 0\n",
     "'self' parameter of method 'm' must be of type 'C'"),
    ("def m(self C):\n        return 0\n", None),
    ("def m(self: C, ):\n        return 0\n",
     "Trailing comma in parameter list is not allowed"),
    ("def m(self: C, x):\n        return 0\n", "Expected ':' after parameter name"),
    ("def m(self: C, x: Int32 = ):\n        return 0\n",
     "Expected default value after '='"),
    ("def m(self)\n        return 0\n", "Expected ':' after 'self'"),
    ("def __init__(self: C) -> Int32:\n        return 0\n",
     "'__init__' cannot have a return type"),
])
def test_method_signature_paths(method, expected):
    source = "class C:\n" + "".join("    " + line + "\n" for line in method.splitlines())
    if expected:
        parse_fail(source, expected)
    else:
        assert parse(source)


def test_pure_method_and_default_parameter():
    ast = parse("class C:\n    puredef m(self: C, x: Int32 = 1) -> Int32:\n"
                "        return x\n")
    assert ast[0].methods[0].pure is True
    assert ast[0].methods[0].params[1][2] is not None


@pytest.mark.parametrize("default,type_,expected", [
    ("1", "Int32", None),
    ("1", "Int64", None),
    ("1.5", "Float64", None),
    ("1.5", "Int32", "must have type Int32"),
    ("get()", "Int32", "must be a constant expression"),
])
def test_parameter_default_validation(default, type_, expected):
    source = ("class C:\n    def m(self: C, x: " + type_ + " = " + default +
              "):\n        return 0\n")
    if expected:
        parse_fail(source, expected)
    else:
        assert parse(source)


def test_parameter_without_default_after_default_is_rejected():
    parse_fail("class C:\n    def m(self: C, a: Int32 = 1, b: Int32):\n"
               "        return 0\n",
               "cannot follow a parameter with a default value")


@pytest.mark.parametrize("source,expected", [
    ("def f(x: Int32 = 1, y: Int32) -> Int32\n    return x\n",
     "cannot follow a parameter with a default value"),
    ("def f(x: Int32 = foo()) -> Int32\n    return x\n",
     "must be a constant expression"),
])
def test_function_parameter_default_validation(source, expected):
    parse_fail(source, expected)
