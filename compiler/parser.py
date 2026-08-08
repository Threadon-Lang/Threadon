from .lexer import lex_lines, TokenType, Token
from .nodes import *


def strip_indent_tokens(line_tokens):
    indent = 0
    dedent = 0

    for tok in line_tokens:
        if tok.type == TokenType.INDENT:
            indent += 1
        elif tok.type == TokenType.DEDENT:
            dedent += 1

    cleaned = [
        tok for tok in line_tokens
        if tok.type not in (TokenType.INDENT, TokenType.DEDENT)
    ]

    return indent, dedent, cleaned
def print_expr(expr):
    t = type(expr).__name__

    if t == "LiteralExpr":
        return expr.value.value

    if t == "VarExpr":
        return expr.name

    if t == "CallExpr":
        args = ", ".join(print_expr(a) for a in expr.args)
        return f"{expr.func_name}({args})"
    if t == "FieldAccessExpr":
        return f"{print_expr(expr.obj)}.{expr.field}"

    if t == "BinaryExpr":
        left = print_expr(expr.left)
        right = print_expr(expr.right)
        return f"{left} {expr.op} {right}"

    if t == "UnaryExpr":
        return f"{expr.op}{print_expr(expr.expr)}"

    if t == "RefExpr":
        return f"{print_expr(expr.inner)}^"

    return "<unknown expr>"
def print_ast(ast, indent=0):
    pad = "    " * indent

    for node in ast:
        t = type(node).__name__

        if t == "FunctionDef":
            print(f"{pad}Function {node.name}(")
            for pname, ptype in node.params:
                print(f"{pad}    param {pname}: {ptype}")
            print(f"{pad}) -> {node.return_type}")
            print(f"{pad}{{")
            print_ast(node.body, indent + 1)
            print(f"{pad}}}")
            continue

        if t == "VarDecl":
            if node.expr is None:
                print(f"{pad}VarDecl {node.name}: {node.var_type}")
            else:
                print(f"{pad}VarDecl {node.name}: {node.var_type} = {print_expr(node.expr)}")
            continue

        if t == "Assign":
            print(f"{pad}Assign {node.name} = {print_expr(node.expr)}")
            continue

        if t == "ReturnStmt":
            if node.value is None:
                print(f"{pad}return")
            else:
                print(f"{pad}return {print_expr(node.value)}")
            continue

        if t == "IfStmt":
            print(f"{pad}If {print_expr(node.condition)}:")
            print(f"{pad}{{")
            print_ast(node.body, indent + 1)
            print(f"{pad}}}")

            for cond, body in node.elif_blocks:
                print(f"{pad}Elif {print_expr(cond)}:")
                print(f"{pad}{{")
                print_ast(body, indent + 1)
                print(f"{pad}}}")

            if node.else_body is not None:
                print(f"{pad}Else:")
                print(f"{pad}{{")
                print_ast(node.else_body, indent + 1)
                print(f"{pad}}}")

            continue

        if t == "StructDef":
            print(f"{pad}Struct {node.name}")
            print(f"{pad}{{")
            print_ast(node.fields, indent + 1)
            print(f"{pad}}}")
            continue

        print(f"{pad}<Unknown node {t}>")


class Parser:
    def __init__(self):
        self.lexed_lines = []
        self.line_number = 1
        self.current_line_number = 0
        self.current_line = []
        self.current_indent = 0
        self.return_type = None
        self.ast = []
        self.scopes = []
        self.func_sigs = {}
        self.indent_stack = [0]
        self.struct_defs = {}
        self.current_indent_col = 0
        self.aliases = {}


    def give_error(self, msg, line_num=None):
        RED = "\033[91m"
        BOLD = "\033[1m"
        RESET = "\033[0m"

        print(f"{RED}{BOLD}Error:{RESET} {msg}",end="")

        if line_num is None:
            line_num = self.current_line_number or self.line_number
        print(f" at line {line_num}")

        if 0 <= line_num - 1 < len(self.original_lines):
            line = self.original_lines[line_num - 1]
            print(f"  {line}")

            caret_pos = len(line) - len(line.lstrip(" "))
            print("  " + " " * caret_pos + "^")

        raise SystemExit

    def apply_indent(self, indent, dedent, col=None):
        if col is None:
            col = self.current_indent_col

        for _ in range(min(dedent, len(self.indent_stack) - 1)):
            self.indent_stack.pop()

        for _ in range(indent):
            self.indent_stack.append(col)

        if col != self.indent_stack[-1]:
            self.give_error("Inconsistent indentation column")

        self.current_indent = len(self.indent_stack) - 1

    def peek_line(self):
        if self.line_number > len(self.lexed_lines):
            return None
        return strip_indent_tokens(self.lexed_lines[self.line_number - 1])

    def peek_raw(self):
        if self.line_number > len(self.lexed_lines):
            return None
        return self.lexed_lines[self.line_number - 1]

    def line_col(self, raw):
        for tok in raw:
            if tok.type in (TokenType.INDENT, TokenType.DEDENT):
                if tok.value is not None:
                    return tok.value
        return self.current_indent_col

    def read_line(self):
        raw = self.peek_raw()
        if raw is None:
            return None
        indent, dedent, cleaned = strip_indent_tokens(raw)
        col = self.line_col(raw)
        self.current_indent_col = col
        self.current_line_number = self.line_number
        self.apply_indent(indent, dedent, col)
        self.current_line = cleaned
        self.line_number += 1
        return cleaned

    def next_nonempty_level(self):
        i = self.line_number
        while i <= len(self.lexed_lines):
            raw = self.lexed_lines[i - 1]
            if raw:
                indent, dedent, _ = strip_indent_tokens(raw)
                return self.line_level(indent, dedent)
            i += 1
        return None

    def line_level(self, indent, dedent):
        return self.current_indent + indent - dedent

    def line_is_within_body(self, indent, dedent, parent_indent):
        return self.line_level(indent, dedent) > parent_indent

    def parse_block(self, parent_indent):
        block = []
        self.push_scope()

        while True:
            peeked = self.peek_line()
            if peeked is None:
                break

            indent, dedent, cleaned = peeked

            if not cleaned:
                self.read_line()
                continue

            if not self.line_is_within_body(indent, dedent, parent_indent):
                break

            self.read_line()
            node = self.parse_line()
            if node is not None:
                block.append(node)

        return block

    def pop_scope_merge(self):
        branch = self.scopes.pop()
        if self.scopes:
            self.scopes[-1].update(branch)

    def push_scope(self):
        self.scopes.append({})

    def pop_scope(self):
        self.scopes.pop()

    def declare_var(self, name, type_):
        if name in self.scopes[-1]:
            self.give_error(f"Variable '{name}' already declared in this scope")
        self.scopes[-1][name] = type_

    def lookup_var(self, name):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        self.give_error(f"Unknown variable '{name}'")

    def parse_line(self):
        if not self.current_line:
            return None

        first = self.current_line[0].type

        if first == TokenType.DEF:
            return self.parse_function()

        if first == TokenType.RETURN:
            return self.parse_return()
        if first == TokenType.IDENT and len(self.current_line) > 1 and self.current_line[1].type == TokenType.COLON:
            return self.parse_variable_decl()
        if first == TokenType.IF:
            return self.parse_if()
        if first == TokenType.STRUCT:
            return self.parse_struct()

        if first == TokenType.ELSE:
            return self.parse_else_error()

        if first == TokenType.ELIF:
            return self.parse_elif_error()
        if first == TokenType.IDENT and len(self.current_line) > 1:
            if self.current_line[1].type in (
                TokenType.PLUS_ASSIGN,
                TokenType.MINUS_ASSIGN,
                TokenType.MUL_ASSIGN,
                TokenType.DIV_ASSIGN,
                TokenType.MOD_ASSIGN,
                TokenType.FLOORDIV_ASSIGN,
            ):
                return self.parse_augmented_assign()

        self.give_error("What for random things where you doing there")
        return None

    def parse(self, code: str):
        self.line_number = 1
        self.current_line_number = 0
        self.current_indent = 0
        self.current_indent_col = 0
        self.ast = []
        self.original_lines = code.splitlines()
        self.indent_stack = [0]
        self.struct_defs = {}
        self.func_sigs = {}
        self.aliases = {}

        self.scopes = []
        self.push_scope()

        try:
            self.lexed_lines = lex_lines(code)
        except SyntaxError as e:
            self.give_error(f"Lexical error: {e}")

        while self.line_number <= len(self.lexed_lines):
            self.read_line()
            node = self.parse_line()
            if node is not None:
                self.ast.append(node)

        return self.ast
    def parse_struct(self):
        if self.return_type is not None:
            self.give_error("Struct must be declared at the top level")

        tokens = self.current_line

        if len(tokens) < 2:
            self.give_error("Struct must have a name")

        name = tokens[1].value
        parent_indent = self.current_indent

        fields = []
        self.push_scope()

        while True:
            peeked = self.peek_line()
            if peeked is None:
                break

            indent, dedent, cleaned = peeked

            if not cleaned:
                level = self.next_nonempty_level()
                if level is not None and level > parent_indent:
                    self.give_error("Struct body may only contain variable declarations", self.line_number)
                self.read_line()
                continue

            if not self.line_is_within_body(indent, dedent, parent_indent):
                break

            self.read_line()

            if cleaned[0].type == TokenType.IDENT and len(cleaned) > 1 and cleaned[1].type == TokenType.COLON:
                fields.append(self.parse_variable_decl())
            else:
                self.give_error("Struct body may only contain variable declarations")

        self.pop_scope()
        self.struct_defs[name] = fields

        return StructDef(name, fields)

    def parse_if(self):
        tokens = self.current_line

        if len(tokens) < 2:
            self.give_error("Invalid 'if' statement")

        parent_indent = self.current_indent
        if_col = self.current_indent_col
        cond_tokens = tokens[1:]

        if cond_tokens[-1].type != TokenType.COLON:
            self.give_error("Expected ':' after 'if' condition")

        cond_tokens = cond_tokens[:-1]

        condition = self.parse_expr(cond_tokens)

        cond_type = self.detect_expr_type(condition)
        if cond_type != "Bool":
            self.give_error(f"If condition must be Bool, got {cond_type}")

        body = self.parse_block(parent_indent)
        branch_scopes = [self.scopes.pop()]

        elif_blocks = []

        while True:
            peeked = self.peek_line()
            if peeked is None:
                break

            indent, dedent, cleaned = peeked

            if not cleaned:
                self.read_line()
                continue

            if cleaned[0].type != TokenType.ELIF:
                break

            if self.line_col(self.peek_raw()) != if_col:
                self.give_error("'elif' must be indented at the same column as its 'if'", self.line_number)

            if self.line_level(indent, dedent) != parent_indent:
                self.give_error("'elif' must be indented at the same level as its 'if'", self.line_number)

            self.read_line()

            cond_tokens = cleaned[1:]

            if cond_tokens[-1].type != TokenType.COLON:
                self.give_error("Expected ':' after 'elif' condition")

            cond_tokens = cond_tokens[:-1]

            cond = self.parse_expr(cond_tokens)
            cond_type = self.detect_expr_type(cond)
            if cond_type != "Bool":
                self.give_error("Elif condition must be Bool")

            elif_body = self.parse_block(parent_indent)
            branch_scopes.append(self.scopes.pop())
            elif_blocks.append((cond, elif_body))

        else_body = None
        has_else = False
        peeked = self.peek_line()

        if peeked is not None:
            indent, dedent, cleaned = peeked

            if cleaned and cleaned[0].type == TokenType.ELSE:
                if self.line_col(self.peek_raw()) != if_col:
                    self.give_error("'else' must be indented at the same column as its 'if'", self.line_number)

                if self.line_level(indent, dedent) != parent_indent:
                    self.give_error("'else' must be indented at the same level as its 'if'", self.line_number)

                if len(cleaned) != 2 or cleaned[1].type != TokenType.COLON:
                    self.give_error("Expected ':' after 'else'")

                self.read_line()

                else_body = self.parse_block(parent_indent)
                branch_scopes.append(self.scopes.pop())
                has_else = True

        if has_else:
            common = set(branch_scopes[0])
            for s in branch_scopes[1:]:
                common &= set(s)
            for name in common:
                self.scopes[-1][name] = branch_scopes[0][name]

        return IfStmt(condition, body, elif_blocks, else_body)

    def parse_else_error(self):
        self.give_error("'else' without matching 'if'")
    def parse_elif_error(self):
        self.give_error("'elif' without matching 'if'")

    def parse_function(self):
        tokens = self.current_line

        if len(tokens) < 4:
            self.give_error("Invalid function definition")

        parent_indent = self.current_indent
        func_name = tokens[1].value

        params = []
        i = 3

        while i < len(tokens) and tokens[i].type != TokenType.RPAREN:
            if tokens[i].type != TokenType.IDENT:
                self.give_error("Expected parameter name")
            param_name = tokens[i].value
            i += 1

            if tokens[i].type != TokenType.COLON:
                self.give_error("Expected ':' after parameter name")
            i += 1

            if tokens[i].type != TokenType.TYPE:
                self.give_error("Expected type after ':'")
            param_type = tokens[i].value
            i += 1

            params.append((param_name, param_type))

            if i < len(tokens) and tokens[i].type == TokenType.COMMA:
                i += 1
                if i < len(tokens) and tokens[i].type == TokenType.RPAREN:
                    self.give_error("Trailing comma in parameter list is not allowed")

        if i >= len(tokens) or tokens[i].type != TokenType.RPAREN:
            self.give_error("Expected ')' after parameters")
        i += 1

        if i >= len(tokens) or tokens[i].type != TokenType.ARROW:
            self.give_error("Expected '->' after ')'")
        i += 1

        if i >= len(tokens) or tokens[i].type != TokenType.TYPE:
            self.give_error("Expected return type after '->'")
        return_type = tokens[i].value

        self.func_sigs[func_name] = (params, return_type)

        self.push_scope()
        for pname, ptype in params:
            self.declare_var(pname, ptype)

        self.return_type = return_type
        func_body = self.parse_block(parent_indent)
        self.pop_scope()
        self.return_type = None

        if return_type != "NoneType" and not self.all_paths_return(func_body):
            self.give_error("Function must return a value on all code paths")

        return FunctionDef(func_name, params, return_type, func_body)

    def all_paths_return(self, stmts):
        if not stmts:
            return False
        last = stmts[-1]
        t = type(last).__name__
        if t == "ReturnStmt":
            return True
        if t == "IfStmt":
            if last.else_body is None:
                return False
            for cond, body in last.elif_blocks:
                if not self.all_paths_return(body):
                    return False
            return self.all_paths_return(last.body) and self.all_paths_return(last.else_body)
        return False


    def parse_expr(self, tokens):
        for tok in tokens:
            if tok.type in (TokenType.AND, TokenType.OR):
                self.give_error(f"Boolean operator '{tok.value}' is not supported")

        def find_op(ts, op_types, last=True, skip_prefix_unary=False):
            idx = None
            depth = 0
            start = 0
            if skip_prefix_unary and ts and ts[0].type in (TokenType.MINUS, TokenType.PLUS):
                start = 1
            for k, tok in enumerate(ts):
                if k < start:
                    continue
                if tok.type == TokenType.LPAREN:
                    depth += 1
                elif tok.type == TokenType.RPAREN:
                    depth -= 1
                elif depth == 0 and tok.type in op_types:
                    if last or idx is None:
                        idx = k
            return idx

        def parse_field_access(ts):
            if len(ts) < 3:
                return None

            for i in range(0, len(ts), 2):
                if ts[i].type != TokenType.IDENT:
                    return None
                if i + 1 < len(ts) and ts[i+1].type != TokenType.DOT:
                    return None

            expr = VarExpr(ts[0].value)

            i = 2
            while i < len(ts):
                field = ts[i].value
                expr = FieldAccessExpr(expr, field)
                i += 2

            return expr
        def factor(ts):
            fa = parse_field_access(ts)
            if fa is not None:
                return fa

            if not ts:
                self.give_error("Empty expression")
            if len(ts) >= 3 and ts[0].type == TokenType.IDENT and ts[1].type == TokenType.LPAREN:
                struct_name = ts[0].value

                if struct_name in self.struct_defs:
                    return self.parse_struct_init(struct_name, ts[2:-1])

            if ts[0].type == TokenType.LPAREN:
                depth = 0
                inner = []
                for tok in ts:
                    if tok.type == TokenType.LPAREN:
                        depth += 1
                        if depth > 1:
                            inner.append(tok)
                    elif tok.type == TokenType.RPAREN:
                        depth -= 1
                        if depth == 0:
                            return self.parse_expr(inner)
                        else:
                            inner.append(tok)
                    else:
                        if depth >= 1:
                            inner.append(tok)
                self.give_error("Unmatched '('")

            if len(ts) >= 3 and ts[0].type == TokenType.IDENT and ts[1].type == TokenType.LPAREN:
                func_name = ts[0].value
                args = []
                i = 2
                while i < len(ts) and ts[i].type != TokenType.RPAREN:
                    arg_tokens = []
                    while i < len(ts) and ts[i].type not in (TokenType.COMMA, TokenType.RPAREN):
                        arg_tokens.append(ts[i])
                        i += 1
                    args.append(self.parse_expr(arg_tokens))
                    if i < len(ts) and ts[i].type == TokenType.COMMA:
                        i += 1
                return CallExpr(func_name, args)

            if len(ts) == 1:
                tok = ts[0]
                if tok.type == TokenType.STRING:
                    return LiteralExpr(tok, "String")
                if tok.type == TokenType.NUMBER:
                    lit_type = "Float32" if "." in tok.value else "Int32"
                    return LiteralExpr(tok, lit_type)
                if tok.type in (TokenType.TRUE, TokenType.FALSE):
                    return LiteralExpr(tok, "Bool")
                if tok.type == TokenType.NONE:
                    return LiteralExpr(tok, "NoneType")
                if tok.type == TokenType.IDENT:
                    return VarExpr(tok.value)

            self.give_error("Invalid expression")

        def unary(ts):
            if ts and ts[0].type == TokenType.MINUS:
                return UnaryExpr("-", unary(ts[1:]))
            if ts and ts[0].type == TokenType.PLUS:
                return UnaryExpr("+", unary(ts[1:]))
            return power(ts)

        def comparison(ts):
            ops = {
                TokenType.LT: "<",
                TokenType.GT: ">",
                TokenType.LE: "<=",
                TokenType.GE: ">=",
                TokenType.EQ: "==",
                TokenType.NEQ: "!=",
            }
            i = find_op(ts, tuple(ops))
            if i is not None:
                left = add_sub(ts[:i])
                right = add_sub(ts[i+1:])
                return BinaryExpr(left, ops[ts[i].type], right)
            return add_sub(ts)

        def not_expr(ts):
            if ts and ts[0].type == TokenType.NOT:
                return UnaryExpr("not", not_expr(ts[1:]))
            return comparison(ts)

        def add_sub(ts):
            i = find_op(ts, (TokenType.PLUS, TokenType.MINUS), skip_prefix_unary=True)
            if i is not None:
                left = add_sub(ts[:i])
                right = mul_div(ts[i+1:])
                return BinaryExpr(left, ts[i].value, right)
            return mul_div(ts)

        def power(ts):
            i = find_op(ts, (TokenType.POWER,), last=False)
            if i is not None:
                left = unary(ts[:i])
                right = power(ts[i+1:])
                if type(right).__name__ == "BinaryExpr" and right.op == "**":
                    self.give_error("Chained '**' is not allowed")
                return BinaryExpr(left, "**", right)
            return factor(ts)

        def mul_div(ts):
            i = find_op(ts, (TokenType.MUL, TokenType.DIV, TokenType.MOD, TokenType.FLOORDIV))
            if i is not None:
                left = mul_div(ts[:i])
                right = unary(ts[i+1:])
                return BinaryExpr(left, ts[i].value, right)
            return unary(ts)

        def bool_ops(ts):
            i = find_op(ts, (TokenType.OR,))
            if i is not None:
                left = bool_ops(ts[:i])
                right = bool_ops(ts[i+1:])
                return BinaryExpr(left, "or", right)
            i = find_op(ts, (TokenType.AND,))
            if i is not None:
                left = bool_ops(ts[:i])
                right = bool_ops(ts[i+1:])
                return BinaryExpr(left, "and", right)
            return not_expr(ts)

        return bool_ops(tokens)

    def detect_expr_type(self, expr):
        t = type(expr).__name__

        if t == "LiteralExpr":
            return expr.type
        if t == "RefExpr":
            inner_type = self.detect_expr_type(expr.inner)
            return inner_type
        if t == "FieldAccessExpr":
            obj_type = self.detect_expr_type(expr.obj)

            if obj_type not in self.struct_defs:
                self.give_error(f"'{obj_type}' is not a struct, cannot access field '{expr.field}'")

            fields = self.struct_defs[obj_type]

            for field_decl in fields:
                if field_decl.name == expr.field:
                    return field_decl.var_type

            self.give_error(f"Struct '{obj_type}' has no field '{expr.field}'")
        if t == "StructInitExpr":
            struct_name = expr.struct_name

            if struct_name not in self.struct_defs:
                self.give_error(f"Unknown struct '{struct_name}'")

            struct_fields = self.struct_defs[struct_name]

            for fname, fexpr in expr.fields.items():
                found = False
                for decl in struct_fields:
                    if decl.name == fname:
                        found = True
                        expected = decl.var_type
                        actual = self.detect_expr_type(fexpr)
                        if expected != actual:
                            self.give_error(
                                f"Struct '{struct_name}' field '{fname}' expects {expected}, got {actual}"
                            )
                        break

                if not found:
                    self.give_error(f"Struct '{struct_name}' has no field '{fname}'")

            return struct_name

        if t == "VarExpr":
            name = expr.name

            for scope in reversed(self.scopes):
                if name in scope:
                    return scope[name]

            if name in self.struct_defs:
                return name

            if name in self.func_sigs:
                self.give_error(f"Function '{name}' cannot be used as a value")

            self.give_error(f"Unknown variable or type '{name}'")

        if t == "UnaryExpr":
            if expr.op == "not":
                inner = self.detect_expr_type(expr.expr)
                if inner != "Bool":
                    self.give_error("Operator 'not' requires Bool")
                return "Bool"

            if expr.op == "-":
                inner = self.detect_expr_type(expr.expr)
                if inner not in ("Int32", "Float32"):
                    self.give_error("Unary '-' requires numeric type")
                return inner

            if expr.op == "+":
                inner = self.detect_expr_type(expr.expr)
                if inner not in ("Int32", "Float32"):
                    self.give_error("Unary '+' requires numeric type")
                return inner

        if t == "CallExpr":
            func_name = expr.func_name

            if func_name not in self.func_sigs:
                self.give_error(f"Unknown function '{func_name}'")

            params, return_type = self.func_sigs[func_name]

            if len(expr.args) != len(params):
                self.give_error(
                    f"Function '{func_name}' expects {len(params)} arguments, "
                    f"got {len(expr.args)}"
                )

            for (arg_expr, (param_name, param_type)) in zip(expr.args, params):
                arg_type = self.detect_expr_type(arg_expr)
                if arg_type != param_type:
                    self.give_error(
                        f"Function '{func_name}' argument '{param_name}' "
                        f"expects type {param_type}, got {arg_type}"
                    )

            return return_type

        if t == "BinaryExpr":
            left = self.detect_expr_type(expr.left)
            right = self.detect_expr_type(expr.right)

            if expr.op in ("<", ">", "<=", ">=", "==", "!="):
                if left != right:
                    self.give_error(f"Type mismatch in comparison: {left} vs {right}")
                return "Bool"

            if expr.op in ("and", "or"):
                if left != "Bool" or right != "Bool":
                    self.give_error("Boolean operators require Bool operands")
                return "Bool"

            if expr.op in ("+", "-", "*", "/", "**", "%", "//"):
                if left != right:
                    self.give_error(f"Type mismatch in arithmetic: {left} vs {right}")
                if expr.op in ("/", "//", "%"):
                    r = expr.right
                    if type(r).__name__ == "LiteralExpr" and r.value.value == "0":
                        self.give_error("Division by zero is not allowed")
                return left

            self.give_error(f"Unknown operator '{expr.op}'")

        self.give_error("Unknown expression type")

    def parse_return(self):
        if self.return_type is None:
            self.give_error("Return outside function")

        tokens = self.current_line

        if len(tokens) == 1:
            value = LiteralExpr(Token(TokenType.NONE, "None"), "NoneType")
            if self.return_type != "NoneType":
                self.give_error(f"Expected {self.return_type}, got NoneType")
            return ReturnStmt(self.return_type, value)

        expr = self.parse_expr(tokens[1:])

        detected = self.detect_expr_type(expr)

        if detected != self.return_type:
            self.give_error(f"Expected {self.return_type}, got {detected}")

        return ReturnStmt(self.return_type, expr)
    def parse_variable_decl(self):
        tokens = self.current_line

        name = tokens[0].value
        var_type = tokens[2].value

        if var_type == "NoneType":
            self.give_error("Variables cannot have type NoneType")

        if len(tokens) <= 3:
            self.declare_var(name, var_type)
            return VarDecl(name, var_type, None)

        expr_tokens = tokens[4:]

        if (
            len(expr_tokens) == 2
            and expr_tokens[0].type == TokenType.IDENT
            and expr_tokens[1].type == TokenType.CARET
        ):
            expr = RefExpr(VarExpr(expr_tokens[0].value))
        elif tokens[3].type in (
            TokenType.PLUS_ASSIGN,
            TokenType.MINUS_ASSIGN,
            TokenType.MUL_ASSIGN,
            TokenType.DIV_ASSIGN,
            TokenType.MOD_ASSIGN,
            TokenType.FLOORDIV_ASSIGN,
        ):
            op = tokens[3].value[:-1]
            expr = BinaryExpr(VarExpr(name), op, self.parse_expr(expr_tokens))
        else:
            expr = self.parse_expr(expr_tokens)

        detected = self.detect_expr_type(expr)

        if detected != var_type:
            self.give_error(f"Variable '{name}' expects type {var_type}, got {detected}")

        if isinstance(expr, RefExpr) and isinstance(expr.inner, VarExpr):
            self.aliases[name] = expr.inner.name

        self.declare_var(name, var_type)

        return VarDecl(name, var_type, expr)
    def parse_struct_init(self, struct_name, tokens):
        fields = {}

        i = 0
        while i < len(tokens):
            if tokens[i].type != TokenType.IDENT:
                self.give_error(f"Expected field name in struct '{struct_name}' initializer")
            fname = tokens[i].value
            if fname in fields:
                self.give_error(f"Duplicate field '{fname}' in struct '{struct_name}' initializer")
            i += 1

            if i >= len(tokens) or tokens[i].type != TokenType.ASSIGN:
                self.give_error(f"Expected '=' after field '{fname}'")
            i += 1

            expr_tokens = []
            while i < len(tokens) and tokens[i].type != TokenType.COMMA:
                expr_tokens.append(tokens[i])
                i += 1

            expr = self.parse_expr(expr_tokens)

            fields[fname] = expr

            if i < len(tokens) and tokens[i].type == TokenType.COMMA:
                i += 1

        return StructInitExpr(struct_name, fields)

    def parse_augmented_assign(self):
        tokens = self.current_line

        name = tokens[0].value
        op = tokens[1].value[:-1]

        expr_tokens = tokens[2:]
        rhs = self.parse_expr(expr_tokens)

        var_type = self.lookup_var(name)
        rhs_type = self.detect_expr_type(rhs)

        if var_type != rhs_type:
            self.give_error(
                f"Variable '{name}' expects type {var_type}, got {rhs_type}"
            )

        full_expr = BinaryExpr(VarExpr(name), op, rhs)

        return Assign(name, full_expr)

if __name__ == "__main__":
    code = """
struct Z:
    z: Int32
struct Point:
    x: Int32 = 0
    y: Int32 = 0
    z: Z = Z(z=0)
def add(x: Int32, y: Int32) -> Int32
    if x < 2:
        result: Int32 = x + y * 2
    elif x == 2:
        result: Int32 = x * y
    else: 
        result: Int32 = x + y ** 2
    MyPoint: Point = Point(x=0,y=0)
    result += 2 ** 3 - MyPoint.z.z
    return result
value: Int32 = add(10,87)
is_true: Bool = value > 90
"""
    parser = Parser()
    result = parser.parse(code)

    print_ast(result)
    