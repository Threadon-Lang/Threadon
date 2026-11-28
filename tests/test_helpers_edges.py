"""Small helper modules: exhaustive edge tests."""
import importlib.util
import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from compiler.threadon import builtins as b
from compiler.threadon.compiler import compile_source
from compiler.threadon.importer import Importer, Module
from compiler.threadon.lexer import Lexer, Token, TokenType
from compiler.threadon.nodes import FunctionDef
from compiler.threadon.test_harness import generate_test_harness


# --- builtins type helpers ------------------------------------------------

def test_is_list_and_dict_type_reject_non_strings():
    assert b.is_list_type(None) is False
    assert b.is_dict_type(42) is False
    assert b.is_list_type("List[Int32]") is True
    assert b.is_dict_type("Dict[String,Int32]") is True


def test_dict_kv_types():
    assert b.dict_kv_types("Dict[String,Int32]") == ("String", "Int32")
    assert b.dict_kv_types("Dict[String,List[Int32]]") == (
        "String", "List[Int32]"
    )
    assert b.dict_kv_types("Dict[Int32]") == ("Int32", "Unknown")


def test_union_and_expand_type():
    assert b.union_members("Union[]") == ()
    assert b.is_union_type("Union[]") is True
    assert b.union_members("Int32") is None
    assert b.expand_type("Int") == tuple(b.GROUP_DEFS["Int"])
    assert b.expand_type("Union[Int64|Int32]") == ("Int32", "Int64")
    assert b.expand_type("Int32") == ("Int32",)


def test_common_numeric_type():
    assert b.common_numeric_type("Int32", "Int32") == "Int32"
    assert b.common_numeric_type("Int32", "Int64") == "Int64"
    assert b.common_numeric_type("Int32", "UInt32") == "UInt32"
    assert b.common_numeric_type("UInt32", "Int32") == "UInt32"
    assert b.common_numeric_type("Float32", "Float64") == "Float64"
    assert b.common_numeric_type("Float64", "Float16") == "Float64"
    assert b.common_numeric_type("Int32", "Float32") == "Float32"
    assert b.common_numeric_type("Float64", "Int32") == "Float64"
    assert b.common_numeric_type("Int32", "Bool") is None


def test_printable_with_aggregates_and_nested_dict_without_comma():
    assert b._is_printable("Point", {"Point"}) is True
    assert b._is_printable("Union[Int32|String]") is True
    assert b._is_printable("List[Int32]") is True
    assert b._is_printable("Dict[String,List[Int32]]") is True
    assert b._is_printable("Dict[Int32]") is False  # 'Unknown' value type
    assert b._is_printable("Point") is False


@pytest.mark.parametrize("func,args,needle", [
    ("len", [], "expects 1 argument, got 0"),
    ("dict_key", ["Int32"], "expects 2 arguments, got 1"),
    ("chr", [42], "expects type Int32, got 42"),
    ("print", ["Point"], "cannot print a value of type Point"),
    ("len", ["Bool"], "expects a String, List or Dict, got Bool"),
    ("dict_key", ["List[Int32]", "Int64"], "expects a Dict, got List"),
])
def test_builtin_signature_errors(func, args, needle):
    with pytest.raises(ValueError, match=needle):
        b.builtin_return_type(func, args)


def test_builtin_return_types():
    assert b.builtin_return_type("len", ["String"]) == "Int64"
    assert b.builtin_return_type("dict_key", ["Dict[String,Int32]", "Int64"]) == "String"
    assert b.builtin_return_type("collect", []) == "NoneType"


# --- nodes ----------------------------------------------------------------

def test_function_def_repr():
    func = FunctionDef("f", [("x", "Int32", None)], "Int32", [], pure=True)
    text = repr(func)
    assert "FunctionDef(name=f" in text
    assert "params=[('x', 'Int32', None)]" in text
    assert "return_type=Int32" in text
    assert "pure=True" in text
    assert "body_len=0" in text


# --- lexer ---------------------------------------------------------------

def lex(src):
    lexer = Lexer(src)
    out = []
    while True:
        token = lexer.next_token()
        out.append((token.type, token.value))
        if token.type == TokenType.EOF:
            return out


def test_lexer_blank_indented_line_and_comments():
    tokens = lex("def f():\n    # comment\n\n    return 1")
    assert (TokenType.RETURN, "return") in tokens
    assert (TokenType.NUMBER, "1") in tokens


def test_prefixed_strings_with_escapes_and_nested_quotes():
    tokens = lex('f"a \\"b\\" {x}"')
    assert any(t[0] == TokenType.FSTRING and "\\" in t[1] for t in tokens)
    tokens = lex('f"outer {"inner"} end"')
    assert any(t[0] == TokenType.FSTRING and "inner" in t[1] for t in tokens)


# --- test harness --------------------------------------------------------

def test_harness_without_test_functions():
    source = generate_test_harness("x: Int32 = 1\n")
    assert "(no test functions found)" in source


# --- importer leftovers --------------------------------------------------

def test_module_repr_and_missing_manifest():
    assert repr(Module("m", "")) == "Module('m')"
    importer = Importer()
    assert importer._load_manifest("does.not.exist") is None


# --- compiler: native class definitions ---------------------------------

def test_compile_source_with_native_class_defs():
    """Native class definitions are forwarded to the SSA builder."""
    importer = Importer()
    field = type("F", (), {"name": "__handle", "var_type": "String"})()
    mod = Module("native", None, None)
    mod.is_native = True
    mod.class_defs = {"native.Box": [field]}
    importer.cache["native"] = mod
    ir = compile_source(
        "def main() -> NoneType:\n    return\n", importer=importer
    )
    assert "define" in ir and "@main" in ir


# --- gen_docs syntax highlighting and entry point ------------------------

GEN_DOCS_PATH = Path(__file__).resolve().parents[2] / "gen_docs.py"
if not GEN_DOCS_PATH.is_file():
    pytest.skip("docs generator fixture (../gen_docs.py) is not available", allow_module_level=True)
SPEC = importlib.util.spec_from_file_location("threadon_gen_docs_edges", GEN_DOCS_PATH)
gen_docs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gen_docs)


def test_code_highlighting_covers_every_token_class():
    html = gen_docs.code('# note\nx: Int32 = 12\nmsg = "hi"\nif x: pass\n')
    for cls in ("tok-cm", "tok-str", "tok-kw", "tok-type", "tok-num", "tok-fn"):
        assert f'class="{cls}"' in html
    assert gen_docs.code("<>") == "&lt;&gt;"


def test_module_entry_point_calls_main():
    called = []
    namespace = dict(vars(gen_docs))
    namespace["__name__"] = "__main__"
    namespace["record"] = lambda: called.append(True)
    # Replace only the call, keeping the line number so this exercises the
    # actual `if __name__ == "__main__": main()` entry point without writing.
    source = GEN_DOCS_PATH.read_text().replace("\n    main()\n", "\n    record()\n")
    exec(compile(source, str(GEN_DOCS_PATH), "exec"), namespace)
    assert called == [True]


def test_shared_nav_loader_renders_full_bar_without_fetch():
    script = gen_docs.nav_loader_js()
    full_markup = gen_docs.nav_fragment()
    assert f"render({json.dumps(full_markup)});" in script
    assert 'fetch("nav.html")' in script
    assert "Keeping embedded navigation" in script
    assert "<a href=\"index.html\">Home</a>" in full_markup
    assert "<a href=\"threads.html\">Threads</a>" in full_markup


def test_nested_bracket_parsing_in_dict_types():
    """Commas inside a nested Dict must not split the outer key/value pair."""
    nested = "Dict[Dict[String,Int32],Int32]"
    assert b.dict_kv_types(nested) == ("Dict[String,Int32]", "Int32")
    assert b._is_printable(nested) is True


def test_lexer_blank_indented_line_is_ignored():
    """A whitespace-only line emits no indent token."""
    kinds = [t[0] for t in lex("x = 1\n    \ny = 2")]
    assert TokenType.INDENT not in kinds
    assert kinds.count(TokenType.NEWLINE) == 2


def test_lexer_escaped_quote_inside_fstring_expression():
    """Escaped quotes inside a nested string in {...} stay in the token."""
    tokens = lex('f"{\\"a\\"}"')
    fstrings = [v for t, v in tokens if t == TokenType.FSTRING]
    assert len(fstrings) == 1
    assert "a" in fstrings[0] and fstrings[0].startswith("{")


def test_lexer_escape_inside_nested_fstring_expression_string():
    """An escaped character in a string nested in {...} keeps both chars."""
    for prefix, kind in (("f", TokenType.FSTRING), ("t", TokenType.TSTRING)):
        tokens = lex(prefix + '"{"a\\"b"}"')
        values = [v for t, v in tokens if t == kind]
        assert values == ['{"a\\"b"}']
