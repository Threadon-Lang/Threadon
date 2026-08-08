from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    IDENT = auto()
    TYPE = auto()
    NUMBER = auto()
    STRING = auto()
    NEWLINE = auto()
    INDENT = auto()
    DEDENT = auto()
    EOF = auto()

    DEF = auto()
    IF = auto()
    ELIF = auto()
    ELSE = auto()
    WHILE = auto()
    FOR = auto()
    RETURN = auto()
    AND = auto()
    OR = auto()
    NOT = auto()
    NONE = auto()
    CLASS = auto()
    STRUCT = auto()
    TRUE = auto()
    FALSE = auto()

    COLON = auto()
    COMMA = auto()
    LPAREN = auto()
    RPAREN = auto()
    ASSIGN = auto()
    ARROW = auto()

    POWER = auto()
    PLUS = auto()
    MINUS = auto()
    MUL = auto()
    DIV = auto()
    MOD = auto()
    EQ = auto()
    NEQ = auto()
    LT = auto()
    GT = auto()
    LE = auto()
    GE = auto()

    PLUS_ASSIGN = auto()
    MINUS_ASSIGN = auto()
    MUL_ASSIGN = auto()
    DIV_ASSIGN = auto()
    MOD_ASSIGN = auto()
    FLOORDIV = auto()
    FLOORDIV_ASSIGN = auto()


    IMPORT = auto()
    FROM = auto()

    DOT = auto()
    CARET = auto()


@dataclass
class Token:
    type: TokenType
    value: str | None = None
    line: int = 0
    col: int = 0


KEYWORDS = {
    "def": TokenType.DEF,
    "if": TokenType.IF,
    "elif": TokenType.ELIF,
    "else": TokenType.ELSE,
    "while": TokenType.WHILE,
    "for": TokenType.FOR,
    "return": TokenType.RETURN,
    "and": TokenType.AND,
    "or": TokenType.OR,
    "not": TokenType.NOT,
    "None": TokenType.NONE,
    "class": TokenType.CLASS,
    "struct": TokenType.STRUCT,
    "True": TokenType.TRUE,
    "False": TokenType.FALSE,
    "import": TokenType.IMPORT,
    "from": TokenType.FROM,
}

TYPES = {
    "Int8", "Int16", "Int32",
    "Float16", "Float32",
    "Boolean", "Bool", "String",
    "NoneType"
}


class Lexer:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.line = 1
        self.col = 1
        self.current_char = text[0] if text else None

        self.indent_stack = [0]
        self.previous_was_newline = True
        self.pending_dedents = 0


    def advance(self):
        if self.current_char == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1

        self.pos += 1
        self.current_char = self.text[self.pos] if self.pos < len(self.text) else None


    def peek(self):
        nxt = self.pos + 1
        return self.text[nxt] if nxt < len(self.text) else None


    def skip_comment(self):
        while self.current_char is not None and self.current_char != "\n":
            self.advance()


    def skip_whitespace(self):
        while self.current_char == " ":
            self.advance()

    def lex_indent(self):
        count = 0

        while self.current_char == " ":
            count += 1
            self.advance()

        if self.current_char == "\n" or self.current_char is None:
            return None

        if self.current_char == "#":
            self.skip_comment()
            return None

        if count > self.indent_stack[-1]:
            self.indent_stack.append(count)
            self.previous_was_newline = False
            return Token(TokenType.INDENT, count, self.line, self.col)

        while count < self.indent_stack[-1]:
            self.indent_stack.pop()
            self.pending_dedents += 1

        self.previous_was_newline = False

        if self.pending_dedents:
            self.pending_dedents -= 1
            return Token(TokenType.DEDENT, count, self.line, self.col)

        return None


    def string(self):
        start_line, start_col = self.line, self.col
        self.advance()
        result = ""

        while self.current_char is not None and self.current_char != '"':
            if self.current_char == "\\":
                self.advance()
                escapes = {"n": "\n", "t": "\t", '"': '"'}
                result += escapes.get(self.current_char, self.current_char)
            else:
                result += self.current_char
            self.advance()

        self.advance()
        return Token(TokenType.STRING, result, start_line, start_col)

    def number(self):
        start_line, start_col = self.line, self.col
        result = ""

        has_dot = False
        has_exp = False

        while self.current_char is not None and self.current_char.isdigit():
            result += self.current_char
            self.advance()

        while self.current_char is not None:
            ch = self.current_char

            if ch == "_":
                if not (result[-1].isdigit() and self.peek() and self.peek().isdigit()):
                    raise SyntaxError(f"Invalid number literal at line {start_line}, col {start_col}")

                result += ch
                self.advance()

                while self.current_char is not None and self.current_char.isdigit():
                    result += self.current_char
                    self.advance()

                continue

            if ch == ".":
                if has_dot or has_exp:
                    raise SyntaxError(f"Invalid number literal at line {start_line}, col {start_col}")
                has_dot = True
                result += ch
                self.advance()

                if self.current_char is None or not self.current_char.isdigit():
                    raise SyntaxError(f"Invalid number literal at line {start_line}, col {start_col}")

                while self.current_char is not None and self.current_char.isdigit():
                    result += self.current_char
                    self.advance()

                continue

            if ch in "eE":
                if has_exp:
                    raise SyntaxError(f"Invalid number literal at line {start_line}, col {start_col}")
                has_exp = True
                result += ch
                self.advance()

                if self.current_char is None or not self.current_char.isdigit():
                    raise SyntaxError(f"Invalid number literal at line {start_line}, col {start_col}")

                while self.current_char is not None and self.current_char.isdigit():
                    result += self.current_char
                    self.advance()

                continue

            if ch.isalpha():
                raise SyntaxError(f"Invalid number literal at line {start_line}, col {start_col}")

            break

        return Token(TokenType.NUMBER, result, start_line, start_col)

    def identifier(self):
        start_line, start_col = self.line, self.col
        result = ""

        while self.current_char is not None and (
            self.current_char.isalnum() or self.current_char in "_"
        ):
            result += self.current_char
            self.advance()

        if result in KEYWORDS:
            return Token(KEYWORDS[result], result, start_line, start_col)

        if result in TYPES:
            return Token(TokenType.TYPE, result, start_line, start_col)

        return Token(TokenType.IDENT, result, start_line, start_col)
    def next_token(self):
        while self.current_char is not None:

            if self.pending_dedents:
                self.pending_dedents -= 1
                return Token(TokenType.DEDENT, None, self.line, self.col)

            if self.current_char == "\n":
                self.advance()
                self.previous_was_newline = True
                return Token(TokenType.NEWLINE, None, self.line, self.col)

            if self.col == 1 and self.previous_was_newline:
                indent_token = self.lex_indent()

                if indent_token is not None:
                    return indent_token

                continue

            if self.current_char == "#":
                self.skip_comment()
                self.previous_was_newline = True
                continue

            if self.current_char.isspace() and self.col != 1:
                self.skip_whitespace()
                continue

            if self.current_char == '"':
                self.previous_was_newline = False
                return self.string()

            if self.current_char.isdigit():
                self.previous_was_newline = False
                return self.number()

            if self.current_char.isalpha() or self.current_char == "_":
                self.previous_was_newline = False
                return self.identifier()

            if self.current_char == ".":
                self.advance()
                return Token(TokenType.DOT, ".", self.line, self.col)

            if self.current_char == ":":
                self.advance()
                return Token(TokenType.COLON, ":")

            if self.current_char == ",":
                self.advance()
                return Token(TokenType.COMMA, ",")

            if self.current_char == "(":
                self.advance()
                return Token(TokenType.LPAREN, "(")
            if self.current_char == ")":
                self.advance()
                return Token(TokenType.RPAREN, ")")

            if self.current_char == "=":
                if self.peek() == "=":
                    self.advance()
                    self.advance()
                    return Token(TokenType.EQ, "==")
                self.advance()
                return Token(TokenType.ASSIGN, "=")

            if self.current_char == "-":
                if self.peek() == "=":
                    self.advance()
                    self.advance()
                    return Token(TokenType.MINUS_ASSIGN, "-=", self.line, self.col)
                if self.peek() == ">":
                    self.advance()
                    self.advance()
                    return Token(TokenType.ARROW, "->", self.line, self.col)
                self.advance()
                return Token(TokenType.MINUS, "-")

            if self.current_char == "+":
                if self.peek() == "=":
                    self.advance()
                    self.advance()
                    return Token(TokenType.PLUS_ASSIGN, "+=", self.line, self.col)
                self.advance()
                return Token(TokenType.PLUS, "+")

            if self.current_char == "*":
                if self.peek() == "*":
                    self.advance()
                    self.advance()
                    return Token(TokenType.POWER, "**", self.line, self.col)

                if self.peek() == "=":
                    self.advance()
                    self.advance()
                    return Token(TokenType.MUL_ASSIGN, "*=", self.line, self.col)

                self.advance()
                return Token(TokenType.MUL, "*", self.line, self.col)


            if self.current_char == "/":
                nxt = self.peek()

                if nxt == "/":
                    if self.pos + 2 < len(self.text) and self.text[self.pos+2] == "=":
                        self.advance()
                        self.advance()
                        self.advance()
                        return Token(TokenType.FLOORDIV_ASSIGN, "//=", self.line, self.col)

                    self.advance()
                    self.advance()
                    return Token(TokenType.FLOORDIV, "//", self.line, self.col)

                if nxt == "=":
                    self.advance()
                    self.advance()
                    return Token(TokenType.DIV_ASSIGN, "/=", self.line, self.col)

                self.advance()
                return Token(TokenType.DIV, "/", self.line, self.col)

            if self.current_char == "%":
                if self.peek() == "=":
                    self.advance()
                    self.advance()
                    return Token(TokenType.MOD_ASSIGN, "%=", self.line, self.col)
                self.advance()
                return Token(TokenType.MOD, "%")

            if self.current_char == "<":
                if self.peek() == "=":
                    self.advance()
                    self.advance()
                    return Token(TokenType.LE, "<=")
                self.advance()
                return Token(TokenType.LT, "<")

            if self.current_char == ">":
                if self.peek() == "=":
                    self.advance()
                    self.advance()
                    return Token(TokenType.GE, ">=")
                self.advance()
                return Token(TokenType.GT, ">")

            if self.current_char == "!":
                if self.peek() == "=":
                    self.advance()
                    self.advance()
                    return Token(TokenType.NEQ, "!=")

            if self.current_char == "^":
                self.advance()
                return Token(TokenType.CARET, "^")

            raise SyntaxError(f"Unrecognized token: {self.current_char}")

        return Token(TokenType.EOF, None)

def lex(code: str):

    lx = Lexer(code)
    tokens = []
    while True:
        tok = lx.next_token()
        tokens.append(tok)
        if tok.type == TokenType.EOF:
            break
    return tokens
def lex_lines(code: str):
    tokens = lex(code)
    lines = []
    current = []

    for tok in tokens:
        if tok.type == TokenType.NEWLINE:
            lines.append(current)
            current = []
        elif tok.type == TokenType.EOF:
            if current:
                lines.append(current)
            break
        else:
            current.append(tok)

    return lines
