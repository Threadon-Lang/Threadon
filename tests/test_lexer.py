import pytest
from compiler.lexer import TokenType, lex



def test_identifiers():
    tokens = lex("hello world")
    assert tokens[0].type == TokenType.IDENT
    assert tokens[0].value == "hello"
    assert tokens[1].type == TokenType.IDENT
    assert tokens[1].value == "world"


def test_numbers():
    tokens = lex("123 3.14 1_000 1e5")
    assert tokens[0].type == TokenType.NUMBER
    assert tokens[0].value == "123"
    assert tokens[1].value == "3.14"
    assert tokens[2].value == "1_000"
    assert tokens[3].value == "1e5"


def test_strings():
    tokens = lex('"hello" "world"')
    assert tokens[0].type == TokenType.STRING
    assert tokens[0].value == "hello"
    assert tokens[1].value == "world"



@pytest.mark.parametrize("kw,token", [
    ("def", TokenType.DEF),
    ("if", TokenType.IF),
    ("elif", TokenType.ELIF),
    ("else", TokenType.ELSE),
    ("while", TokenType.WHILE),
    ("for", TokenType.FOR),
    ("return", TokenType.RETURN),
    ("and", TokenType.AND),
    ("or", TokenType.OR),
    ("not", TokenType.NOT),
    ("None", TokenType.NONE),
    ("class", TokenType.CLASS),
    ("struct", TokenType.STRUCT),
    ("True", TokenType.TRUE),
    ("False", TokenType.FALSE),
    ("import", TokenType.IMPORT),
    ("from", TokenType.FROM),
])
def test_keywords(kw, token):
    tokens = lex(kw)
    assert tokens[0].type == token



@pytest.mark.parametrize("typ", [
    "Int8", "Int16", "Int32",
    "Float16", "Float32",
    "Boolean", "String"
])
def test_types(typ):
    tokens = lex(typ)
    assert tokens[0].type == TokenType.TYPE
    assert tokens[0].value == typ



@pytest.mark.parametrize("op,token", [
    ("+", TokenType.PLUS),
    ("-", TokenType.MINUS),
    ("*", TokenType.MUL),
    ("/", TokenType.DIV),
    ("%", TokenType.MOD),
    ("==", TokenType.EQ),
    ("!=", TokenType.NEQ),
    ("<", TokenType.LT),
    (">", TokenType.GT),
    ("<=", TokenType.LE),
    (">=", TokenType.GE),
    ("=", TokenType.ASSIGN),
    ("->", TokenType.ARROW),
    ("^", TokenType.CARET),
])
def test_operators(op, token):
    tokens = lex(op)
    assert tokens[0].type == token



def test_comment():
    tokens = lex("# dit is commentaar\n123")
    assert tokens[0].type == TokenType.NEWLINE
    assert tokens[1].type == TokenType.NUMBER



def test_indent_dedent():
    code = "a: Int32 = 5\n    b: Int32 = 10\nc: Int32 = 3"
    tokens = lex(code)

    types = [t.type for t in tokens]

    assert TokenType.INDENT in types
    assert TokenType.DEDENT in types



def test_function_signature():
    code = "def func(x: Int8, y: Int32) -> Boolean\n    return True"
    tokens = lex(code)

    types = [t.type for t in tokens]

    assert TokenType.DEF in types
    assert TokenType.IDENT in types
    assert TokenType.TYPE in types
    assert TokenType.ARROW in types
    assert TokenType.RETURN in types
    assert TokenType.TRUE in types



def test_class_struct():
    code = "class Test\n    x: Int32 = 5\nstruct Data\n    y: Float32 = 3.14"
    tokens = lex(code)

    types = [t.type for t in tokens]

    assert TokenType.CLASS in types
    assert TokenType.STRUCT in types
    assert TokenType.TYPE in types



def test_import():
    tokens = lex("import math")
    assert tokens[0].type == TokenType.IMPORT
    assert tokens[1].type == TokenType.IDENT


def test_from_import():
    tokens = lex("from math import sqrt")
    assert tokens[0].type == TokenType.FROM
    assert tokens[1].type == TokenType.IDENT
    assert tokens[2].type == TokenType.IMPORT
    assert tokens[3].type == TokenType.IDENT



def test_eof():
    tokens = lex("")
    assert tokens[-1].type == TokenType.EOF
def test_multiple_nested_indent_dedent():
    code = (
        "a: Int32 = 5\n"
        "    b: Int32 = 10\n"
        "        c: Int32 = 20\n"
        "    d: Int32 = 30\n"
        "e: Int32 = 40"
    )
    tokens = lex(code)
    types = [t.type for t in tokens]

    assert types.count(TokenType.INDENT) == 2
    assert types.count(TokenType.DEDENT) == 2


def test_indent_after_comment():
    code = (
        "# comment\n"
        "    x: Int32 = 5\n"
        "y: Int32 = 10"
    )
    tokens = lex(code)
    types = [t.type for t in tokens]

    assert TokenType.INDENT in types
    assert TokenType.DEDENT in types


def test_empty_lines_do_not_affect_indent():
    code = (
        "a: Int32 = 5\n"
        "\n"
        "    b: Int32 = 10\n"
        "\n"
        "c: Int32 = 3"
    )
    tokens = lex(code)
    types = [t.type for t in tokens]

    assert TokenType.INDENT in types
    assert TokenType.DEDENT in types
def test_string_with_escapes():
    tokens = lex('"hello\\nworld"')
    assert tokens[0].type == TokenType.STRING
    assert tokens[0].value == "hello\nworld"


def test_empty_string():
    tokens = lex('""')
    assert tokens[0].type == TokenType.STRING
    assert tokens[0].value == ""


def test_string_next_to_identifier():
    tokens = lex('name "John"')
    assert tokens[0].type == TokenType.IDENT
    assert tokens[1].type == TokenType.STRING
def test_float_with_exponent():
    tokens = lex("1.23e10")
    assert tokens[0].type == TokenType.NUMBER
    assert tokens[0].value == "1.23e10"


def test_number_with_multiple_underscores():
    tokens = lex("1_000_000")
    assert tokens[0].type == TokenType.NUMBER
    assert tokens[0].value == "1_000_000"

def test_number_followed_by_identifier():
    with pytest.raises(SyntaxError):
        lex("123abc")

def test_operator_sequence():
    tokens = lex("a==b!=c<=d>=e")
    types = [t.type for t in tokens]

    assert TokenType.EQ in types
    assert TokenType.NEQ in types
    assert TokenType.LE in types
    assert TokenType.GE in types


def test_mixed_operators_and_values():
    tokens = lex('x + 5 * y - "test"')
    types = [t.type for t in tokens]

    assert TokenType.PLUS in types
    assert TokenType.MUL in types
    assert TokenType.MINUS in types
    assert TokenType.STRING in types
def test_operator_sequence():
    tokens = lex("a==b!=c<=d>=e")
    types = [t.type for t in tokens]

    assert TokenType.EQ in types
    assert TokenType.NEQ in types
    assert TokenType.LE in types
    assert TokenType.GE in types


def test_mixed_operators_and_values():
    tokens = lex('x + 5 * y - "test"')
    types = [t.type for t in tokens]

    assert TokenType.PLUS in types
    assert TokenType.MUL in types
    assert TokenType.MINUS in types
    assert TokenType.STRING in types
def test_function_no_params():
    tokens = lex("def test() -> Boolean\n    return True")
    types = [t.type for t in tokens]

    assert TokenType.DEF in types
    assert TokenType.LPAREN in types
    assert TokenType.RPAREN in types
    assert TokenType.ARROW in types


def test_function_single_param():
    tokens = lex("def test(x: Int32) -> Boolean\n    return False")
    types = [t.type for t in tokens]

    assert TokenType.TYPE in types
    assert TokenType.IDENT in types


def test_function_many_params():
    tokens = lex("def test(a: Int8, b: Int16, c: Int32) -> Boolean\n    return True")
    types = [t.type for t in tokens]

    assert types.count(TokenType.TYPE) == 4
def test_class_nested():
    code = (
        "class Test\n"
        "    x: Int32 = 5\n"
        "    def method() -> None\n"
        "        return None\n"
        "y: Int32 = 10"
    )
    tokens = lex(code)
    types = [t.type for t in tokens]

    assert TokenType.CLASS in types
    assert TokenType.DEF in types
    assert TokenType.INDENT in types
    assert TokenType.DEDENT in types
def test_import_with_dots():
    tokens = lex("import compiler.lexer")
    assert tokens[0].type == TokenType.IMPORT
    assert tokens[1].type == TokenType.IDENT


def test_from_import_multiple():
    tokens = lex("from math import sin, cos, tan")
    types = [t.type for t in tokens]

    assert types.count(TokenType.IDENT) == 4
def test_multiple_newlines():
    tokens = lex("a: Int32 = 5\n\n\nb: Int32 = 10")
    types = [t.type for t in tokens]

    assert types.count(TokenType.NEWLINE) >= 3


def test_compound_assignment_tokens():
    code = "a += 1\nb -= 2\nc *= 3\nd /= 4\ne //= 5\nf %= 6"
    tokens = lex(code)
    types = [t.type for t in tokens]

    assert TokenType.PLUS_ASSIGN in types
    assert TokenType.MINUS_ASSIGN in types
    assert TokenType.MUL_ASSIGN in types
    assert TokenType.DIV_ASSIGN in types
    assert TokenType.FLOORDIV_ASSIGN in types
    assert TokenType.MOD_ASSIGN in types


def test_floordiv_token():
    tokens = lex("10 // 3")
    assert tokens[0].type == TokenType.NUMBER
    assert tokens[1].type == TokenType.FLOORDIV
    assert tokens[1].value == "//"


def test_power_token():
    tokens = lex("2 ** 8")
    assert tokens[1].type == TokenType.POWER
    assert tokens[1].value == "**"


def test_boolean_literals():
    tokens = lex("True False")
    assert tokens[0].type == TokenType.TRUE
    assert tokens[0].value == "True"
    assert tokens[1].type == TokenType.FALSE
    assert tokens[1].value == "False"


def test_arrow_and_caret():
    tokens = lex("a -> b ^ c")
    assert tokens[1].type == TokenType.ARROW
    assert tokens[3].type == TokenType.CARET


def test_string_tab_escape():
    tokens = lex('"tab\\tend"')
    assert tokens[0].type == TokenType.STRING
    assert tokens[0].value == "tab\tend"


def test_nonetype_token():
    tokens = lex("NoneType")
    assert tokens[0].type == TokenType.TYPE
    assert tokens[0].value == "NoneType"


def test_lex_lines_groups_tokens():
    from compiler.lexer import lex_lines

    lines = lex_lines("a: Int32 = 1\nb: Int32 = 2")
    assert len(lines) == 2
    assert [t.value for t in lines[0]] == ["a", ":", "Int32", "=", "1"]
    assert [t.value for t in lines[1]] == ["b", ":", "Int32", "=", "2"]
