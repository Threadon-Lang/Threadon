from .builtins import (
    ALL_INT_TYPES,
    BUILTIN_SIGS,
    FLOAT_TYPES,
    NUMERIC_TYPES,
    builtin_return_type,
    common_numeric_type,
    expand_type,
    group_members,
    is_group,
    is_union_type,
    union_members,
    union_str,
)
from .importer import Importer, ImporterError
from .lexer import Token, TokenType, lex_lines
from .nodes import *

int_types = ALL_INT_TYPES

VALID_PRIMITIVE_TYPES = ALL_INT_TYPES + FLOAT_TYPES + ("Bool", "String", "NoneType")

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

    if t == "MethodCallExpr":
        args = ", ".join(print_expr(a) for a in expr.args)
        return f"{print_expr(expr.obj)}.{expr.method}({args})"

    if t == "ClassInitExpr":
        args = ", ".join(print_expr(a) for a in expr.args)
        return f"{expr.class_name}({args})"

    if t == "BinaryExpr":
        left = print_expr(expr.left)
        right = print_expr(expr.right)
        return f"{left} {expr.op} {right}"

    if t == "UnaryExpr":
        return f"{expr.op}{print_expr(expr.expr)}"

    if t == "RefExpr":
        return f"{print_expr(expr.inner)}^"

    if t == "ListLiteralExpr":
        return "[" + ", ".join(print_expr(e) for e in expr.elements) + "]"

    if t == "IndexExpr":
        return f"{print_expr(expr.obj)}[{print_expr(expr.index)}]"

    return "<unknown expr>"
def print_ast(ast, indent=0):
    pad = "    " * indent

    for node in ast:
        t = type(node).__name__

        if t == "FunctionDef":
            print(f"{pad}Function {node.name}(")
            for pname, ptype, pdefault in node.params:
                default_str = f" = {print_expr(pdefault)}" if pdefault is not None else ""
                print(f"{pad}    param {pname}: {ptype}{default_str}")
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

        if t == "IndexAssign":
            print(
                f"{pad}IndexAssign {print_expr(node.target)}"
                f"[{print_expr(node.index)}] = {print_expr(node.value)}"
            )
            continue

        if t == "FieldAssign":
            print(f"{pad}FieldAssign {node.name}.{node.field} = {print_expr(node.expr)}")
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

        if t == "WhileStmt":
            print(f"{pad}While {print_expr(node.condition)}:")
            print(f"{pad}{{")
            print_ast(node.body, indent + 1)
            print(f"{pad}}}")
            continue

        if t == "StructDef":
            print(f"{pad}Struct {node.name}")
            print(f"{pad}{{")
            print_ast(node.fields, indent + 1)
            print(f"{pad}}}")
            continue

        if t == "ClassDef":
            base_str = f"({node.base})" if node.base else ""
            print(f"{pad}Class {node.name}{base_str}")
            print(f"{pad}{{")
            print_ast(node.own_fields, indent + 1)
            print_ast(node.methods, indent + 1)
            print(f"{pad}}}")
            continue

        print(f"{pad}<Unknown node {t}>")


class Parser:
    def __init__(self, importer=None, module_name=""):
        self.importer = importer or Importer()
        self.module_name = module_name
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
        self.qfunc = {}
        self.qstruct = {}
        self.qclass = {}
        self.class_defs = {}
        self.class_ast = {}
        self.class_method_map = {}
        self.func_import_aliases = {}
        self.struct_import_aliases = {}
        self.class_import_aliases = {}
        self.module_aliases = {}
        self.lazy_imports = {}
        self.current_class = None
        self._infer_return = False
        self._inferred_ret = None
        self._pending_inferred = {}
        self._in_init = False
        self._in_function = False
        self._in_struct = False
        self._in_class = False


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
            if tok.type in (TokenType.INDENT, TokenType.DEDENT) and tok.value != None:
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
        declared = self.var_declared_stack.pop()
        modified = self.modified_stack.pop()
        if self.scopes:
            self.scopes[-1].update(branch)
            self.var_declared_stack[-1].update(declared)
            self.modified_stack[-1].update(modified)

    def push_scope(self):
        self.scopes.append({})
        self.var_declared_stack.append({})
        self.modified_stack.append(set())

    def pop_scope(self):
        self.scopes.pop()
        self.var_declared_stack.pop()
        self.modified_stack.pop()

    def declare_var(self, name, type_):
        if name in self.scopes[-1]:
            self.give_error(f"Variable '{name}' already declared in this scope")
        self.scopes[-1][name] = type_
        self.var_declared_stack[-1][name] = type_

    def _narrow_var(self, name, expr_type, declared=None):
        if declared is None:
            declared = self.var_declared_stack[-1].get(name, expr_type)
        if (
            is_union_type(declared)
            and not is_union_type(expr_type)
            and expr_type in union_members(declared)
        ):
            self.scopes[-1][name] = expr_type
        else:
            self.scopes[-1][name] = declared

    def lookup_var(self, name):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        self.give_error(f"Unknown variable '{name}'")

    def _lookup_declared(self, name):
        for stack in reversed(self.var_declared_stack):
            if name in stack:
                return stack[name]
        return None

    def parse_line(self):
        if not self.current_line:
            return None

        first = self.current_line[0].type

        if first in (
            TokenType.IMPORT,
            TokenType.FROM,
            TokenType.LAZYIMPORT,
            TokenType.LAZYFROM,
        ):
            return self.parse_import()

        if first == TokenType.DEF:
            return self.parse_function()

        if first == TokenType.RETURN:
            return self.parse_return()
        if first == TokenType.IDENT and len(self.current_line) > 1 and self.current_line[1].type == TokenType.COLON:
            return self.parse_variable_decl()
        if first == TokenType.IF:
            return self.parse_if()
        if first == TokenType.WHILE:
            return self.parse_while()
        if first == TokenType.STRUCT:
            return self.parse_struct()
        if first == TokenType.CLASS:
            return self.parse_class()

        if first == TokenType.ELSE:
            return self.parse_else_error()

        if first == TokenType.ELIF:
            return self.parse_elif_error()
        if first == TokenType.IDENT and len(self.current_line) > 1 and self.current_line[1].type in (
                TokenType.PLUS_ASSIGN,
                TokenType.MINUS_ASSIGN,
                TokenType.MUL_ASSIGN,
                TokenType.DIV_ASSIGN,
                TokenType.MOD_ASSIGN,
                TokenType.FLOORDIV_ASSIGN):
                return self.parse_augmented_assign()

        if (
            first == TokenType.IDENT
            and self.current_line[0].value == "self"
            and len(self.current_line) > 3
            and self.current_line[1].type == TokenType.DOT
            and self.current_line[2].type == TokenType.IDENT
            and self.current_line[3].type == TokenType.COLON
        ):
            return self.parse_self_field_decl()

        if (
            first == TokenType.IDENT
            and len(self.current_line) > 4
            and self.current_line[1].type == TokenType.DOT
            and self.current_line[2].type == TokenType.IDENT
            and self.current_line[3].type == TokenType.ASSIGN
        ):
            return self.parse_field_assign()

        if (
            first == TokenType.IDENT
            and len(self.current_line) > 1
            and self.current_line[1].type == TokenType.ASSIGN
        ):
            return self.parse_assign()

        if first == TokenType.IDENT and len(self.current_line) > 2 and self.current_line[1].type == TokenType.LBRACKET:
            return self.parse_index_assign()

        if (
            first == TokenType.IDENT
            and len(self.current_line) > 4
            and self.current_line[1].type == TokenType.DOT
            and self.current_line[2].type == TokenType.IDENT
            and self.current_line[3].type == TokenType.LBRACKET
        ):
            return self.parse_field_index_assign()

        if first == TokenType.IDENT and len(self.current_line) > 1:
            second = self.current_line[1].type
            is_call = second == TokenType.LPAREN
            is_qualified_call = (
                second == TokenType.DOT
                and len(self.current_line) > 3
                and self.current_line[2].type == TokenType.IDENT
                and self.current_line[3].type == TokenType.LPAREN
            )
            if is_call or is_qualified_call:
                expr = self.parse_expr(self.current_line)
                self.detect_expr_type(expr)
                return ExprStmt(expr)

        self.give_error("What for random things where you doing there")
        return None

    def qualify(self, name):
        return f"{self.module_name}.{name}" if self.module_name else name

    def _load_module(self, module_path):
        try:
            return self.importer.load(module_path)
        except ImporterError as e:
            self.give_error(str(e))

    def _copy_class_recursive(self, qmember, mod):
        if qmember in self.class_defs:
            return
        self.class_defs[qmember] = mod.class_defs[qmember]
        self.class_ast[qmember] = mod.class_ast[qmember]
        self.class_method_map[qmember] = mod.class_method_map[qmember]
        for method_name, func_name in mod.class_method_map[qmember].items():
            self.func_sigs[func_name] = mod.func_sigs[func_name]
        base = mod.class_ast[qmember].base
        if base is not None:
            self._copy_class_recursive(base, mod)

    def bind_import(self, mod, module_path, name, bound):
        qmember = f"{module_path}.{name}" if module_path else name

        if name in mod.func_exports:
            self.func_import_aliases[bound] = qmember
            self.func_sigs[qmember] = mod.func_sigs[qmember]
        elif name in mod.struct_exports:
            self.struct_import_aliases[bound] = qmember
            self.struct_defs[qmember] = mod.struct_defs[qmember]
        elif name in mod.class_exports:
            self.class_import_aliases[bound] = qmember
            self._copy_class_recursive(qmember, mod)
        elif name in mod.var_exports:
            self.give_error(
                f"Cannot import variable '{name}' from module '{module_path}'"
                f" (only functions and structs can be imported)"
            )
        else:
            self.give_error(f"Module '{module_path}' has no member '{name}'")

    def handle_import_module(self, module_path, bound, lazy):
        self.module_aliases[bound] = module_path
        if not lazy:
            self._load_module(module_path)

    def handle_from_import(self, module_path, names, lazy):
        if lazy:
            for name, alias in names:
                bound = alias or name
                self.lazy_imports[bound] = (module_path, name)
            return

        mod = self._load_module(module_path)
        for name, alias in names:
            bound = alias or name
            self.bind_import(mod, module_path, name, bound)

    def _split_call_args(self, ts, start):
        args = []
        depth = 0
        current = []
        j = start
        while j < len(ts):
            tok = ts[j]
            if tok.type in (TokenType.LPAREN, TokenType.LBRACKET, TokenType.LBRACE):
                depth += 1
                current.append(tok)
            elif tok.type == TokenType.RPAREN:
                if depth == 0:
                    break
                depth -= 1
                current.append(tok)
            elif tok.type in (TokenType.RBRACKET, TokenType.RBRACE):
                depth -= 1
                current.append(tok)
            elif tok.type == TokenType.COMMA and depth == 0:
                args.append(self.parse_expr(current))
                current = []
            else:
                current.append(tok)
            j += 1
        if current:
            args.append(self.parse_expr(current))
        return args

    def parse_import(self):
        tokens = self.current_line
        first = tokens[0].type
        lazy = first in (TokenType.LAZYIMPORT, TokenType.LAZYFROM)
        is_from = first in (TokenType.FROM, TokenType.LAZYFROM)

        if len(tokens) < 2:
            self.give_error("Invalid import statement")

        i = 1
        parts = []
        if tokens[i].type != TokenType.IDENT:
            self.give_error("Expected module name in import")
        parts.append(tokens[i].value)
        i += 1

        while i < len(tokens) and tokens[i].type == TokenType.DOT:
            i += 1
            if i >= len(tokens) or tokens[i].type != TokenType.IDENT:
                self.give_error("Expected module name after '.'")
            parts.append(tokens[i].value)
            i += 1

        module_path = ".".join(parts)

        if is_from:
            if i >= len(tokens) or tokens[i].type != TokenType.IMPORT:
                self.give_error("Expected 'import' after module name")

            i += 1
            names = []
            while i < len(tokens):
                if tokens[i].type == TokenType.MUL:
                    self.give_error("Wildcard imports (*) are not allowed")
                if tokens[i].type != TokenType.IDENT:
                    self.give_error("Expected name to import")
                name = tokens[i].value
                i += 1

                alias = None
                if i < len(tokens) and tokens[i].type == TokenType.AS:
                    i += 1
                    if i >= len(tokens) or tokens[i].type != TokenType.IDENT:
                        self.give_error("Expected alias name after 'as'")
                    alias = tokens[i].value
                    i += 1

                names.append((name, alias))

                if i < len(tokens):
                    if tokens[i].type != TokenType.COMMA:
                        self.give_error("Unexpected token in import statement")
                    i += 1
                    if i >= len(tokens):
                        self.give_error("Trailing comma in import is not allowed")

            if not names:
                self.give_error("Expected at least one name to import")

            self.handle_from_import(module_path, names, lazy)
            return ImportStmt(module_path, names, lazy, True)

        bound = parts[0]
        if i < len(tokens):
            if tokens[i].type != TokenType.AS:
                self.give_error("Unexpected token after module name")
            i += 1
            if i >= len(tokens) or tokens[i].type != TokenType.IDENT:
                self.give_error("Expected alias name after 'as'")
            bound = tokens[i].value
            i += 1

        if i < len(tokens):
            self.give_error("Unexpected token at end of import statement")

        self.handle_import_module(module_path, bound, lazy)
        return ImportStmt(module_path, [(None, bound)], lazy, False)

    def resolve_func_name(self, name):
        if name in self.qfunc:
            return self.qfunc[name]
        if name in self.func_import_aliases:
            return self.func_import_aliases[name]
        if name in self.lazy_imports:
            module_path, member = self.lazy_imports[name]
            mod = self._load_module(module_path)
            qmember = f"{module_path}.{member}" if module_path else member

            if member in mod.func_exports:
                self.func_import_aliases[name] = qmember
                self.func_sigs[qmember] = mod.func_sigs[qmember]
                del self.lazy_imports[name]
                return qmember
            if member in mod.struct_exports:
                self.give_error(f"'{name}' is a type, not a function")
            self.give_error(f"Module '{module_path}' has no member '{member}'")
        return name

    def resolve_type(self, name, strict=True):
        if name in self.qclass:
            return self.qclass[name]
        if name in self.class_import_aliases:
            return self.class_import_aliases[name]
        if name in self.qstruct:
            return self.qstruct[name]
        if name in self.struct_import_aliases:
            return self.struct_import_aliases[name]
        if name in self.lazy_imports:
            module_path, member = self.lazy_imports[name]
            mod = self._load_module(module_path)
            qmember = f"{module_path}.{member}" if module_path else member

            if member in mod.struct_exports:
                self.struct_import_aliases[name] = qmember
                self.struct_defs[qmember] = mod.struct_defs[qmember]
                del self.lazy_imports[name]
                return qmember
            if member in mod.class_exports:
                self.class_import_aliases[name] = qmember
                self._copy_class_recursive(qmember, mod)
                del self.lazy_imports[name]
                return qmember
            if member in mod.func_exports:
                if strict:
                    self.give_error(f"'{name}' is a function, not a type")
                return name
            self.give_error(f"Module '{module_path}' has no member '{member}'")

        if "." in name:
            segments = name.split(".")
            if segments[0] in self.module_aliases:
                qname, kind = self.resolve_qualified(segments)
                if kind in ("struct", "class"):
                    return qname
                if strict:
                    self.give_error(f"'{name}' is a function, not a type")
                return name
        return name

    def parse_type_token(self, tok, ctx):
        if tok is None:
            self.give_error(f"Expected a type in {ctx}")
        if tok.type == TokenType.TYPE:
            return tok.value
        if tok.type == TokenType.IDENT:
            resolved = self.resolve_type(tok.value)
            if resolved in self.struct_defs or resolved in self.class_defs:
                return resolved
            self.give_error(f"Unknown type '{tok.value}' in {ctx}")
        self.give_error(f"Expected a type in {ctx}")

    def _parse_type_atom(self, tokens, ctx, start=0):
        """Parse a single (non-union) type starting at ``tokens[start]``.

        Returns ``(type_str, next_index)``. Supports primitives, dotted
        struct names, ``List[T]`` and ``Dict[K,V]``.
        """
        if start >= len(tokens):
            self.give_error(f"Expected a type in {ctx}")

        tok = tokens[start]

        if tok.type == TokenType.IDENT and tok.value == "List":
            if start + 1 >= len(tokens) or tokens[start + 1].type != TokenType.LBRACKET:
                self.give_error("Expected '[' after 'List' in type")

            depth = 0
            end = None
            for k in range(start + 1, len(tokens)):
                if tokens[k].type == TokenType.LBRACKET:
                    depth += 1
                elif tokens[k].type == TokenType.RBRACKET:
                    depth -= 1
                    if depth == 0:
                        end = k
                        break
            if end is None:
                self.give_error("Unmatched '[' in type")

            elem_type, _ = self.parse_type_from_tokens(
                tokens[start + 2:end], ctx, 0, allow_union=False
            )
            if elem_type is not None and (
                is_group(elem_type) or is_union_type(elem_type)
            ):
                self.give_error(
                    f"List element type cannot be a type group or union in {ctx}"
                )
            return f"List[{elem_type}]", end + 1

        if tok.type == TokenType.IDENT and tok.value == "Dict":
            if start + 1 >= len(tokens) or tokens[start + 1].type != TokenType.LBRACKET:
                self.give_error("Expected '[' after 'Dict' in type")

            depth = 0
            end = None
            for k in range(start + 1, len(tokens)):
                if tokens[k].type == TokenType.LBRACKET:
                    depth += 1
                elif tokens[k].type == TokenType.RBRACKET:
                    depth -= 1
                    if depth == 0:
                        end = k
                        break
            if end is None:
                self.give_error("Unmatched '[' in type")

            inner_tokens = tokens[start + 2:end]
            comma_idx = None
            depth = 0
            for ci, ct in enumerate(inner_tokens):
                if ct.type == TokenType.LBRACKET:
                    depth += 1
                elif ct.type == TokenType.RBRACKET:
                    depth -= 1
                elif ct.type == TokenType.COMMA and depth == 0:
                    comma_idx = ci
                    break
            if comma_idx is None:
                self.give_error("Dict type requires two type parameters: Dict[K, V]")

            key_type, _ = self.parse_type_from_tokens(
                inner_tokens[:comma_idx], ctx, 0, allow_union=False
            )
            val_type, _ = self.parse_type_from_tokens(
                inner_tokens[comma_idx + 1:], ctx, 0, allow_union=False
            )
            return f"Dict[{key_type},{val_type}]", end + 1

        if tok.type == TokenType.TYPE:
            return tok.value, start + 1

        if tok.type == TokenType.IDENT:
            parts = [tok.value]
            i = start + 1
            while (
                i + 1 < len(tokens)
                and tokens[i].type == TokenType.DOT
                and tokens[i + 1].type == TokenType.IDENT
            ):
                parts.append(tokens[i + 1].value)
                i += 2
            resolved = self.resolve_type(".".join(parts))
            if resolved in self.struct_defs or resolved in self.class_defs:
                return resolved, i
            self.give_error(f"Unknown type '{'.'.join(parts)}' in {ctx}")

        self.give_error(f"Expected a type in {ctx}")

    def _normalize_union(self, members, ctx):
        if not members:
            self.give_error(f"Expected a type in {ctx}")
        seen = set()
        result = []
        for m in members:
            if m in seen:
                continue
            if not self._is_valid_type(m):
                self.give_error(f"Unknown type '{m}' in {ctx}")
            seen.add(m)
            result.append(m)
        result.sort()
        return result

    def parse_type_from_tokens(self, tokens, ctx, start=0, allow_union=True):
        """Parse a type starting at ``tokens[start]``.

        Returns ``(type_str, next_index)``. Supports primitives, dotted
        struct names, ``List[T]`` and type groups/unions like ``Int | Float``.
        """
        if start >= len(tokens):
            self.give_error(f"Expected a type in {ctx}")

        members = []

        while True:
            atom, next_idx = self._parse_type_atom(tokens, ctx, start)

            if is_group(atom):
                members.extend(group_members(atom))
            elif is_union_type(atom):
                members.extend(union_members(atom))
            else:
                members.append(atom)

            if (
                next_idx < len(tokens)
                and tokens[next_idx].type == TokenType.PIPE
            ):
                if not allow_union:
                    self.give_error("Union types are not allowed here")
                start = next_idx + 1
                if start >= len(tokens):
                    self.give_error(f"Expected a type after '|' in {ctx}")
                continue

            break

        members = self._normalize_union(members, ctx)

        if len(members) == 1:
            return members[0], next_idx

        return union_str(members), next_idx

    def import_member(self, module_path, member):
        mod = self._load_module(module_path)
        qmember = f"{module_path}.{member}" if module_path else member

        if member in mod.func_exports:
            self.func_sigs[qmember] = mod.func_sigs[qmember]
            return qmember, "func"
        if member in mod.struct_exports:
            self.struct_defs[qmember] = mod.struct_defs[qmember]
            return qmember, "struct"
        if member in mod.class_exports:
            self._copy_class_recursive(qmember, mod)
            return qmember, "class"
        if member in mod.var_exports:
            self.give_error(
                f"Module '{module_path}' has no function or type '{member}'"
            )
        self.give_error(f"Module '{module_path}' has no member '{member}'")
        return None, None

    def resolve_qualified(self, parts):
        bound = parts[0]
        if bound not in self.module_aliases:
            self.give_error(f"Module '{bound}' is not imported")

        base = self.module_aliases[bound]
        base_segments = base.split(".")
        member = parts[-1]

        full_segments = base_segments[:]
        for segment in parts[1:-1]:
            if full_segments and full_segments[-1] == segment:
                continue
            full_segments.append(segment)

        usage_path = ".".join(full_segments)
        return self.import_member(usage_path, member)

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
        self.qfunc = {}
        self.qstruct = {}
        self.qclass = {}
        self.class_defs = {}
        self.class_ast = {}
        self.class_method_map = {}
        self.func_import_aliases = {}
        self.struct_import_aliases = {}
        self.class_import_aliases = {}
        self.module_aliases = {}
        self.lazy_imports = {}
        self.current_class = None
        self._infer_return = False
        self._inferred_ret = None
        self._pending_inferred = {}
        self._in_init = False
        self._in_struct = False
        self._in_class = False
        self._in_function = False

        self.scopes = []
        self.var_declared_stack = []
        self.modified_stack = []
        self.push_scope()

        try:
            self.lexed_lines = lex_lines(code)
        except SyntaxError as e:
            self.give_error(f"Lexical error: {e}")

        if not self.module_name:
            self._auto_import_stdlib()

        while self.line_number <= len(self.lexed_lines):
            self.read_line()
            node = self.parse_line()
            if node is not None:
                self.ast.append(node)

        return self.ast

    def _auto_import_stdlib(self):

        if not self.importer or self.importer.find_source("std") is None:
            return
        mod = self._load_module("std")
        for name in sorted(mod.func_exports):
            qname = f"std.{name}"
            self.func_import_aliases[name] = qname
            self.func_sigs[qname] = mod.func_sigs[qname]
        for name in sorted(mod.struct_exports):
            qname = f"std.{name}"
            self.struct_import_aliases[name] = qname
            self.struct_defs[qname] = mod.struct_defs[qname]
        for name in sorted(mod.class_exports):
            qname = f"std.{name}"
            self._copy_class_recursive(qname, mod)
    def parse_struct(self):
        if self.return_type is not None:
            self.give_error("Struct must be declared at the top level")

        tokens = self.current_line

        if len(tokens) < 2:
            self.give_error("Struct must have a name")

        name = tokens[1].value
        qname = self.qualify(name)
        self.qstruct[name] = qname
        parent_indent = self.current_indent

        self._in_struct = True
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
                fields.append(self.parse_variable_decl(allow_union=False))
            else:
                self.give_error("Struct body may only contain variable declarations")

        self._in_struct = False
        self.pop_scope()
        self.struct_defs[qname] = fields

        return StructDef(qname, fields)

    def parse_class(self):
        if self.return_type is not None:
            self.give_error("Class must be declared at the top level")

        tokens = self.current_line

        if len(tokens) < 2:
            self.give_error("Class must have a name")

        name = tokens[1].value
        qname = self.qualify(name)
        self.qclass[name] = qname

        base = None
        i = 2
        if i < len(tokens) and tokens[i].type == TokenType.LPAREN:
            if (
                i + 2 >= len(tokens)
                or tokens[i + 1].type != TokenType.IDENT
                or tokens[i + 2].type != TokenType.RPAREN
            ):
                self.give_error("Expected a single base class name in parentheses")
            base_q = self.resolve_type(tokens[i + 1].value)
            if base_q not in self.class_defs:
                self.give_error(f"Unknown base class '{tokens[i + 1].value}'")
            base = base_q
            i += 3

        if i < len(tokens) and tokens[i].type == TokenType.COLON:
            i += 1
        if i < len(tokens):
            self.give_error("Unexpected token in class declaration")

        parent_indent = self.current_indent

        own_fields = self._scan_class_fields(qname, base, parent_indent)

        inherited = []
        if base is not None:
            inherited = self._fields_of(base)

        for inherited_field in inherited:
            if inherited_field.name in own_fields:
                self.give_error(
                    f"Class '{name}' redefines inherited field '{inherited_field.name}'"
                )

        flattened = inherited + list(own_fields.values())
        self.class_defs[qname] = flattened
        self.class_ast[qname] = ClassDef(
            qname, base, flattened, [], list(own_fields.values())
        )

        methods = []
        self.push_scope()
        self.current_class = qname

        while True:
            peeked = self.peek_line()
            if peeked is None:
                break

            indent, dedent, cleaned = peeked

            if not cleaned:
                level = self.next_nonempty_level()
                if level is not None and level <= parent_indent:
                    break
                self.read_line()
                continue

            if not self.line_is_within_body(indent, dedent, parent_indent):
                break

            self.read_line()

            if cleaned[0].type == TokenType.DEF:
                methods.append(self.parse_method())
            else:
                self.parse_line()

        self.pop_scope()
        self.current_class = None

        node = ClassDef(qname, base, flattened, methods, list(own_fields.values()))
        self.class_ast[qname] = node

        return node

    def _scan_class_fields(self, qname, base, parent_indent):
        own_fields = {}
        i = self.line_number
        level = parent_indent
        while i <= len(self.lexed_lines):
            raw = self.lexed_lines[i - 1]
            if not raw:
                i += 1
                continue
            indent, dedent, cleaned = strip_indent_tokens(raw)
            level += indent - dedent
            if not cleaned:
                i += 1
                continue
            if level <= parent_indent:
                break
            if (
                len(cleaned) >= 4
                and cleaned[0].type == TokenType.IDENT
                and cleaned[0].value == "self"
                and cleaned[1].type == TokenType.DOT
                and cleaned[2].type == TokenType.IDENT
                and cleaned[3].type == TokenType.COLON
            ):
                fname = cleaned[2].value
                ftype, _ = self.parse_type_from_tokens(
                    cleaned, "class field declaration", 4, allow_union=False
                )
                if (
                    fname in own_fields
                    and own_fields[fname].var_type != ftype
                ):
                    self.give_error(
                        f"Field '{fname}' declared with conflicting types "
                        f"in class '{qname}'"
                    )
                own_fields[fname] = VarDecl(fname, ftype, None)
            elif (
                level == parent_indent + 1
                and cleaned[0].type == TokenType.IDENT
                and len(cleaned) > 1
                and cleaned[1].type == TokenType.COLON
            ):
                fname = cleaned[0].value
                ftype, next_idx = self.parse_type_from_tokens(
                    cleaned, "class field declaration", 2, allow_union=False
                )
                if (
                    next_idx < len(cleaned)
                    and cleaned[next_idx].type == TokenType.ASSIGN
                ):
                    self.give_error(
                        f"Class field '{fname}' cannot have an initializer "
                        f"at class body level"
                    )
                if fname in own_fields:
                    self.give_error(f"Duplicate field '{fname}' in class '{qname}'")
                own_fields[fname] = VarDecl(fname, ftype, None)
            i += 1
        return own_fields

    def parse_method(self):
        tokens = self.current_line

        if len(tokens) < 4:
            self.give_error("Invalid method definition")

        parent_indent = self.current_indent
        method_name = tokens[1].value
        func_name = f"{self.current_class}.{method_name}"
        is_init = method_name == "__init__"

        params = []
        i = 3
        seen_self = False

        while i < len(tokens) and tokens[i].type != TokenType.RPAREN:
            if tokens[i].type != TokenType.IDENT:
                self.give_error("Expected parameter name")
            param_name = tokens[i].value
            i += 1

            if not seen_self and param_name == "self":
                seen_self = True
                if i < len(tokens) and tokens[i].type == TokenType.COLON:
                    i += 1
                    param_type, i = self.parse_type_from_tokens(
                        tokens, "method signature", i
                    )
                elif i < len(tokens) and tokens[i].type == TokenType.IDENT:
                    param_type, i = self.parse_type_from_tokens(
                        tokens, "method signature", i
                    )
                else:
                    self.give_error("Expected ':' after 'self'")
            else:
                if i >= len(tokens) or tokens[i].type != TokenType.COLON:
                    self.give_error("Expected ':' after parameter name")
                i += 1
                param_type, i = self.parse_type_from_tokens(
                    tokens, "method signature", i
                )

            default = None
            if i < len(tokens) and tokens[i].type == TokenType.ASSIGN:
                i += 1
                default_tokens = []
                depth = 0
                while i < len(tokens):
                    tok = tokens[i]
                    if depth == 0 and tok.type in (
                        TokenType.COMMA,
                        TokenType.RPAREN,
                    ):
                        break
                    if tok.type in (TokenType.LBRACKET, TokenType.LPAREN):
                        depth += 1
                    elif tok.type in (TokenType.RBRACKET, TokenType.RPAREN):
                        depth -= 1
                    default_tokens.append(tok)
                    i += 1
                if not default_tokens:
                    self.give_error("Expected default value after '='")
                default = self.parse_expr(default_tokens)

            params.append((param_name, param_type, default))

            if i < len(tokens) and tokens[i].type == TokenType.COMMA:
                i += 1
                if i < len(tokens) and tokens[i].type == TokenType.RPAREN:
                    self.give_error("Trailing comma in parameter list is not allowed")

        if i >= len(tokens) or tokens[i].type != TokenType.RPAREN:
            self.give_error("Expected ')' after parameters")
        i += 1

        if is_init and i < len(tokens) and tokens[i].type == TokenType.ARROW:
            self.give_error("'__init__' cannot have a return type")

        return_type = None
        if i < len(tokens):
            if tokens[i].type == TokenType.ARROW:
                i += 1
                return_type, _ = self.parse_type_from_tokens(
                    tokens, "return type", i
                )
            elif tokens[i].type != TokenType.COLON:
                self.give_error("Expected '->' after ')'")

        params = [
            (pname, self.resolve_type(ptype), pdefault)
            for pname, ptype, pdefault in params
        ]
        if return_type is not None:
            return_type = self.resolve_type(return_type)

        if not seen_self:
            self.give_error("Method must have a 'self' parameter")

        self_type = params[0][1]
        if self_type != self.current_class:
            self.give_error(
                f"'self' parameter of method '{method_name}' must be of type "
                f"'{self.current_class}'"
            )

        self._validate_params_defaults(params, func_name)

        if is_init:
            return_type = self.current_class
        elif return_type is None:
            self._pending_inferred[func_name] = params

        if return_type is not None:
            self.func_sigs[func_name] = (params, return_type)

        self.class_method_map.setdefault(self.current_class, {})[method_name] = func_name

        self.push_scope()
        for pname, ptype, _ in params:
            self.declare_var(pname, ptype)

        self._in_init = is_init
        if is_init:
            self.return_type = self.current_class
            self._infer_return = False
            self._inferred_ret = None
        else:
            self.return_type = return_type
            self._infer_return = return_type is None
            self._inferred_ret = None

        func_body = self.parse_block(parent_indent)

        self.pop_scope()
        self.return_type = None
        self._in_init = False

        if is_init:
            func_body.append(ReturnStmt(self.current_class, VarExpr("self")))
            return_type = self.current_class
        elif self._infer_return:
            if self._inferred_ret is None:
                ret = "NoneType"
            else:
                ret = self._inferred_ret
            self._infer_return = False
            self._inferred_ret = None
            del self._pending_inferred[func_name]
            self.func_sigs[func_name] = (params, ret)
            return_type = ret
        else:
            if return_type != "NoneType" and not self.all_paths_return(func_body):
                self.give_error("Function must return a value on all code paths")

        if method_name == "__str__":
            if len(params) != 1:
                self.give_error("Method '__str__' must take only the 'self' parameter")
            if return_type != "String":
                self.give_error(
                    f"Method '__str__' must return a String, got {return_type}"
                )

        return FunctionDef(func_name, params, return_type, func_body)

    def _validate_params_defaults(self, params, func_name):
        seen_default = False
        for pname, _, pdefault in params:
            if pdefault is not None:
                seen_default = True
            elif seen_default:
                self.give_error(
                    f"Parameter '{pname}' without a default value cannot "
                    f"follow a parameter with a default value"
                )

        for pname, ptype, pdefault in params:
            if pdefault is None:
                continue
            if not self._is_const_expr(pdefault):
                self.give_error(
                    f"Default value for parameter '{pname}' must be a "
                    f"constant expression"
                )
            default_type = self.detect_expr_type(pdefault)
            if default_type != ptype:
                if (
                    self._is_const_int_expr(pdefault) and ptype in self._INT_TYPES
                ) or (
                    self._is_const_float_expr(pdefault) and ptype in self._FLOAT_TYPES
                ):
                    self._set_expr_type(pdefault, ptype)
                    self._check_literal_range(pdefault, ptype)
                else:
                    self.give_error(
                        f"Default value for parameter '{pname}' must have "
                        f"type {ptype}, got {default_type}"
                    )

    def parse_self_field_decl(self):
        tokens = self.current_line

        field = tokens[2].value
        i = 4
        ftype, i = self.parse_type_from_tokens(
            tokens, "self field declaration", i, allow_union=False
        )

        expr = None
        if i < len(tokens):
            if tokens[i].type != TokenType.ASSIGN:
                self.give_error("Expected '=' in self field declaration")
            expr = self.parse_expr(tokens[i + 1:])

        if self.current_class is None:
            self.give_error("'self' can only be used inside a class method")

        declared = None
        for decl in self.class_defs[self.current_class]:
            if decl.name == field:
                declared = decl
                break
        if declared is None:
            self.give_error(f"Class '{self.current_class}' has no field '{field}'")

        if expr is not None:
            detected = self.detect_expr_type(expr)
            if not self._is_valid_type(ftype):
                self.give_error(f"Unknown type '{ftype}'")
            if detected != ftype:
                if not self._try_adapt_literal(expr, detected, ftype):
                    self.give_error(
                        f"Field '{field}' expects type {ftype}, got {detected}"
                    )

        return AttrDecl("self", field, ftype, expr)

    def _fields_of(self, type_name):
        if type_name in self.class_defs:
            return self.class_defs[type_name]
        if type_name in self.struct_defs:
            return self.struct_defs[type_name]
        return []

    def _aggregate_types(self):
        return set(self.struct_defs) | set(self.class_defs)

    def _base_of(self, cls):
        node = self.class_ast.get(cls)
        if node is None:
            return None
        return node.base

    def _resolve_method_owner(self, obj_type, method_name):
        cls = obj_type
        seen = set()
        while cls is not None and cls not in seen:
            seen.add(cls)
            if method_name in self.class_method_map.get(cls, {}):
                return cls
            cls = self._base_of(cls)
        return None

    def _resolve_init(self, obj_type):
        cls = obj_type
        seen = set()
        while cls is not None and cls not in seen:
            seen.add(cls)
            if "__init__" in self.class_method_map.get(cls, {}):
                return cls
            cls = self._base_of(cls)
        return None

    def parse_class_init(self, class_name, tokens):
        args = []
        if tokens:
            args = self._split_call_args(tokens, 0)
        return ClassInitExpr(class_name, args)

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
        branch_modified = [self.modified_stack.pop()]

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
            branch_modified.append(self.modified_stack.pop())
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
                branch_modified.append(self.modified_stack.pop())
                has_else = True

        if has_else:
            common = set(branch_scopes[0])
            for s in branch_scopes[1:]:
                common &= set(s)
            for name in common:
                self.scopes[-1][name] = branch_scopes[0][name]

        for bm in branch_modified:
            for name in bm:
                if name in self.scopes[-1]:
                    self.scopes[-1][name] = self.var_declared_stack[-1].get(
                        name, self.scopes[-1][name]
                    )

        return IfStmt(condition, body, elif_blocks, else_body)

    def parse_else_error(self):
        self.give_error("'else' without matching 'if'")
    def parse_elif_error(self):
        self.give_error("'elif' without matching 'if'")

    def parse_while(self):
        tokens = self.current_line

        if len(tokens) < 2:
            self.give_error("Invalid 'while' statement")

        parent_indent = self.current_indent
        cond_tokens = tokens[1:]

        if cond_tokens[-1].type != TokenType.COLON:
            self.give_error("Expected ':' after 'while' condition")

        cond_tokens = cond_tokens[:-1]

        condition = self.parse_expr(cond_tokens)

        cond_type = self.detect_expr_type(condition)
        if cond_type != "Bool":
            self.give_error(f"While condition must be Bool, got {cond_type}")

        body = self.parse_block(parent_indent)
        body_modified = self.modified_stack[-1]
        self.pop_scope()

        for name in body_modified:
            if name in self.scopes[-1]:
                self.scopes[-1][name] = self.var_declared_stack[-1].get(
                    name, self.scopes[-1][name]
                )

        return WhileStmt(condition, body)

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

            param_type, consumed = self.parse_type_from_tokens(
                tokens, "function signature", i
            )
            i = consumed

            default = None
            if i < len(tokens) and tokens[i].type == TokenType.ASSIGN:
                i += 1
                default_tokens = []
                depth = 0
                while i < len(tokens):
                    tok = tokens[i]
                    if depth == 0 and tok.type in (
                        TokenType.COMMA,
                        TokenType.RPAREN,
                    ):
                        break
                    if tok.type in (TokenType.LBRACKET, TokenType.LPAREN):
                        depth += 1
                    elif tok.type in (TokenType.RBRACKET, TokenType.RPAREN):
                        depth -= 1
                    default_tokens.append(tok)
                    i += 1
                if not default_tokens:
                    self.give_error("Expected default value after '='")
                default = self.parse_expr(default_tokens)

            params.append((param_name, param_type, default))

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

        return_type, _ = self.parse_type_from_tokens(
            tokens, "return type", i
        )

        func_name_q = self.qualify(func_name)
        params = [
            (pname, self.resolve_type(ptype), pdefault)
            for pname, ptype, pdefault in params
        ]
        return_type = self.resolve_type(return_type)

        seen_default = False
        for pname, _, pdefault in params:
            if pdefault is not None:
                seen_default = True
            elif seen_default:
                self.give_error(
                    f"Parameter '{pname}' without a default value cannot "
                    f"follow a parameter with a default value"
                )

        for pname, ptype, pdefault in params:
            if pdefault is None:
                continue
            if not self._is_const_expr(pdefault):
                self.give_error(
                    f"Default value for parameter '{pname}' must be a "
                    f"constant expression"
                )
            default_type = self.detect_expr_type(pdefault)
            if default_type != ptype:
                if (
                    self._is_const_int_expr(pdefault) and ptype in self._INT_TYPES
                ) or (
                    self._is_const_float_expr(pdefault) and ptype in self._FLOAT_TYPES
                ):
                    self._set_expr_type(pdefault, ptype)
                    self._check_literal_range(pdefault,ptype)
                else:
                    self.give_error(
                        f"Default value for parameter '{pname}' must have "
                        f"type {ptype}, got {default_type}"
                    )

        self.qfunc[func_name] = func_name_q
        self.func_sigs[func_name_q] = (params, return_type)

        self._in_function = True
        self.push_scope()
        for pname, ptype, _ in params:
            self.declare_var(pname, ptype)

        self.return_type = return_type
        func_body = self.parse_block(parent_indent)
        self.pop_scope()
        self._in_function = False
        self.return_type = None

        if return_type != "NoneType" and not self.all_paths_return(func_body):
            self.give_error("Function must return a value on all code paths")

        return FunctionDef(func_name_q, params, return_type, func_body)

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


    def parse_interpolated_string(self, tok):
        kind = "f" if tok.type == TokenType.FSTRING else "t"
        raw = tok.value
        parts = []
        lit = []
        escapes = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "{": "{", "}": "}"}
        i = 0
        n = len(raw)

        while i < n:
            c = raw[i]

            if c == "\\":
                if i + 1 < n:
                    lit.append(escapes.get(raw[i + 1], raw[i + 1]))
                    i += 2
                else:
                    lit.append(c)
                    i += 1
                continue

            if c == "{":
                depth = 1
                j = i + 1
                expr_chars = []

                while j < n and depth > 0:
                    cc = raw[j]

                    if cc == "\\":
                        expr_chars.append(cc)
                        if j + 1 < n:
                            expr_chars.append(raw[j + 1])
                            j += 2
                        else:
                            j += 1
                        continue

                    if cc == "{":
                        depth += 1
                    elif cc == "}":
                        depth -= 1

                        if depth == 0:
                            break

                    expr_chars.append(cc)
                    j += 1

                if depth != 0:
                    self.give_error("Unterminated '{' in interpolated string")

                if lit:
                    parts.append(("lit", "".join(lit)))
                    lit = []

                expr_text = "".join(expr_chars).strip()

                if not expr_text:
                    self.give_error("Empty interpolation in interpolated string")

                tokens = [ln for ln in lex_lines(expr_text) if ln]

                if not tokens:
                    self.give_error("Invalid interpolation in interpolated string")

                parts.append(("expr", self.parse_expr(tokens[0])))
                i = j + 1
                continue

            lit.append(c)
            i += 1

        if lit:
            parts.append(("lit", "".join(lit)))

        return InterpolatedStringExpr(kind, parts)


    def parse_expr(self, tokens):
        def find_op(ts, op_types, last=True, skip_prefix_unary=False):
            idx = None
            depth = 0
            start = 0
            if skip_prefix_unary and ts and ts[0].type in (TokenType.MINUS, TokenType.PLUS):
                start = 1
            for k, tok in enumerate(ts):
                if k < start:
                    continue
                if tok.type in (TokenType.LPAREN, TokenType.LBRACKET):
                    depth += 1
                elif tok.type in (TokenType.RPAREN, TokenType.RBRACKET):
                    depth -= 1
                elif depth == 0 and tok.type in op_types:
                    if last or idx is None:
                        idx = k
            return idx

        def parse_field_access(ts):
            if len(ts) < 3:
                return None

            if ts[0].value in self.module_aliases:
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
        def parse_qualified_call(ts):
            if len(ts) < 5:
                return None
            if ts[0].type != TokenType.IDENT or ts[1].type != TokenType.DOT:
                return None

            parts = [ts[0].value]
            i = 1
            while i + 1 < len(ts) and ts[i].type == TokenType.DOT and ts[i + 1].type == TokenType.IDENT:
                parts.append(ts[i + 1].value)
                i += 2

            if i >= len(ts) or ts[i].type != TokenType.LPAREN:
                return None

            qname, kind = self.resolve_qualified(parts)

            if kind == "struct":
                return self.parse_struct_init(qname, ts[i + 1:-1])

            if kind == "class":
                if ts[-1].type != TokenType.RPAREN:
                    self.give_error("Unmatched '(' in call")
                return self.parse_class_init(qname, ts[i + 1:-1])

            if ts[-1].type != TokenType.RPAREN:
                self.give_error("Unmatched '(' in call")

            args = self._split_call_args(ts, i + 1)
            return CallExpr(qname, args)

        def factor(ts):
            fa = parse_field_access(ts)
            if fa is not None:
                return fa

            qualified = parse_qualified_call(ts)
            if qualified is not None:
                return qualified

            if not ts:
                self.give_error("Empty expression")
            if len(ts) >= 3 and ts[0].type == TokenType.IDENT and ts[1].type == TokenType.LPAREN:
                type_name = self.resolve_type(ts[0].value, strict=False)

                if type_name in self.struct_defs:
                    return self.parse_struct_init(type_name, ts[2:-1])

                if type_name in self.class_defs:
                    return self.parse_class_init(type_name, ts[2:-1])
            if len(ts) >= 3 and ts[0].type == TokenType.TYPE and ts[1].type == TokenType.LPAREN:
                target_type = ts[0].value
                if ts[-1].type != TokenType.RPAREN:
                    self.give_error("Unmatched '(' in cast")
                inner_tokens = ts[2:-1]
                inner_expr = self.parse_expr(inner_tokens)
                return CastExpr(target_type, inner_expr)
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
                func_name = self.resolve_func_name(ts[0].value)
                args = self._split_call_args(ts, 2)
                return CallExpr(func_name, args)

            if len(ts) == 1:
                tok = ts[0]
                if tok.type == TokenType.STRING:
                    return LiteralExpr(tok, "String")
                if tok.type in (TokenType.FSTRING, TokenType.TSTRING):
                    return self.parse_interpolated_string(tok)
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

        def parse_list_literal(ts):
            if not ts or ts[0].type != TokenType.LBRACKET:
                return None

            depth = 0
            end = None
            for k, tok in enumerate(ts):
                if tok.type == TokenType.LBRACKET:
                    depth += 1
                elif tok.type == TokenType.RBRACKET:
                    depth -= 1
                    if depth == 0:
                        end = k
                        break
            if end is None:
                self.give_error("Unmatched '[' in list literal")
            if end != len(ts) - 1:
                self.give_error("Unexpected tokens after list literal")

            inner = ts[1:end]
            if not inner:
                return ListLiteralExpr([])

            elements = []
            current = []
            depth = 0
            for tok in inner:
                if tok.type in (TokenType.LBRACKET, TokenType.LPAREN):
                    depth += 1
                elif tok.type in (TokenType.RBRACKET, TokenType.RPAREN):
                    depth -= 1
                if tok.type == TokenType.COMMA and depth == 0:
                    if not current:
                        self.give_error("Empty element in list literal")
                    elements.append(self.parse_expr(current))
                    current = []
                else:
                    current.append(tok)

            if current:
                elements.append(self.parse_expr(current))
            return ListLiteralExpr(elements)

        def parse_dict_literal(ts):
            if not ts or ts[0].type != TokenType.LBRACE:
                return None

            depth = 0
            end = None
            for k, tok in enumerate(ts):
                if tok.type == TokenType.LBRACE:
                    depth += 1
                elif tok.type == TokenType.RBRACE:
                    depth -= 1
                    if depth == 0:
                        end = k
                        break
            if end is None:
                self.give_error("Unmatched '{' in dict literal")
            if end != len(ts) - 1:
                self.give_error("Unexpected tokens after dict literal")

            inner = ts[1:end]
            if not inner:
                return DictLiteralExpr([], [])

            pair_tokens_list = []
            current_pair = []
            depth = 0
            for tok in inner:
                if tok.type in (TokenType.LBRACE, TokenType.LPAREN, TokenType.LBRACKET):
                    depth += 1
                elif tok.type in (TokenType.RBRACE, TokenType.RPAREN, TokenType.RBRACKET):
                    depth -= 1
                if tok.type == TokenType.COMMA and depth == 0:
                    pair_tokens_list.append(current_pair)
                    current_pair = []
                else:
                    current_pair.append(tok)
            if current_pair:
                pair_tokens_list.append(current_pair)

            keys = []
            values = []
            for pair in pair_tokens_list:
                colon_idx = None
                depth = 0
                for ci, ct in enumerate(pair):
                    if ct.type in (TokenType.LBRACE, TokenType.LPAREN, TokenType.LBRACKET):
                        depth += 1
                    elif ct.type in (TokenType.RBRACE, TokenType.RPAREN, TokenType.RBRACKET):
                        depth -= 1
                    elif ct.type == TokenType.COLON and depth == 0:
                        colon_idx = ci
                        break
                if colon_idx is None:
                    self.give_error("Dict literal entries must be 'key: value' pairs")
                key_tokens = pair[:colon_idx]
                val_tokens = pair[colon_idx + 1:]
                if not key_tokens or not val_tokens:
                    self.give_error("Dict literal entry cannot have empty key or value")
                keys.append(self.parse_expr(key_tokens))
                values.append(self.parse_expr(val_tokens))

            return DictLiteralExpr(keys, values)

        def index_postfix(ts):
            lit = parse_list_literal(ts)
            if lit is not None:
                return lit

            lit = parse_dict_literal(ts)
            if lit is not None:
                return lit

            if ts and ts[0].type == TokenType.IDENT and ts[0].value in self.module_aliases:
                return factor(ts)

            split = None
            split_is_index = False
            depth = 0
            for k, tok in enumerate(ts):
                if tok.type == TokenType.LPAREN:
                    depth += 1
                elif tok.type == TokenType.RPAREN:
                    depth -= 1
                elif tok.type == TokenType.LBRACKET and depth == 0:
                    split = k
                    split_is_index = True
                    break
                elif tok.type == TokenType.DOT and depth == 0:
                    if k > 0 and k + 1 < len(ts) and ts[k + 1].type == TokenType.IDENT:
                        split = k
                        split_is_index = False
                        break

            if split is None:
                return factor(ts)

            base = factor(ts[:split])
            rest = ts[split:]

            while True:
                if not rest:
                    break
                if (
                    rest[0].type == TokenType.DOT
                    and len(rest) >= 3
                    and rest[1].type == TokenType.IDENT
                    and rest[2].type == TokenType.LPAREN
                ):
                    depth = 0
                    end = None
                    for k in range(2, len(rest)):
                        tok = rest[k]
                        if tok.type == TokenType.LPAREN:
                            depth += 1
                        elif tok.type == TokenType.RPAREN:
                            depth -= 1
                            if depth == 0:
                                end = k
                                break
                    if end is None:
                        self.give_error("Unmatched '(' in method call")
                    args = self._split_call_args(rest[3:end], 0)
                    base = MethodCallExpr(base, rest[1].value, args)
                    rest = rest[end + 1:]
                    continue

                if (
                    rest[0].type == TokenType.DOT
                    and len(rest) >= 2
                    and rest[1].type == TokenType.IDENT
                ):
                    base = FieldAccessExpr(base, rest[1].value)
                    rest = rest[2:]
                    continue

                if rest[0].type == TokenType.LBRACKET:
                    depth = 1
                    end = None
                    for k in range(1, len(rest)):
                        tok = rest[k]
                        if tok.type == TokenType.LBRACKET:
                            depth += 1
                        elif tok.type == TokenType.RBRACKET:
                            depth -= 1
                            if depth == 0:
                                end = k
                                break
                    if end is None:
                        self.give_error("Unmatched '[' in index expression")
                    index_tokens = rest[1:end]
                    if not index_tokens:
                        self.give_error("Empty index expression")
                    index = self.parse_expr(index_tokens)
                    base = IndexExpr(base, index)
                    rest = rest[end + 1:]
                    continue

                if not rest:
                    break
                self.give_error("Unexpected tokens after index expression")
            return base

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
            return index_postfix(ts)

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
        if t == "InterpolatedStringExpr":
            return "String"
        if t == "RefExpr":
            inner_type = self.detect_expr_type(expr.inner)
            return inner_type
        if t == "ListLiteralExpr":
            if getattr(expr, "type", None) is not None:
                return expr.type
            if not expr.elements:
                return "List[Unknown]"
            first = self.detect_expr_type(expr.elements[0])
            for i in range(1, len(expr.elements)):
                elem_type = self.detect_expr_type(expr.elements[i])
                if elem_type != first:
                    if not self._try_adapt_literal(
                        expr.elements[i], elem_type, first
                    ):
                        self.give_error(
                            "All elements of a list must have the same type"
                        )
            expr.type = f"List[{first}]"
            return expr.type
        if t == "DictLiteralExpr":
            if getattr(expr, "type", None) is not None:
                return expr.type
            if not expr.keys:
                return "Dict[Unknown,Unknown]"
            key_type = self.detect_expr_type(expr.keys[0])
            val_type = self.detect_expr_type(expr.values[0])
            for i in range(1, len(expr.keys)):
                kt = self.detect_expr_type(expr.keys[i])
                if kt != key_type:
                    if not self._try_adapt_literal(
                        expr.keys[i], kt, key_type
                    ):
                        self.give_error(
                            "All keys of a dict must have the same type"
                        )
                vt = self.detect_expr_type(expr.values[i])
                if vt != val_type:
                    if not self._try_adapt_literal(
                        expr.values[i], vt, val_type
                    ):
                        self.give_error(
                            "All values of a dict must have the same type"
                        )
            expr.type = f"Dict[{key_type},{val_type}]"
            return expr.type
        if t == "IndexExpr":
            obj_type = self.detect_expr_type(expr.obj)
            index_type = self.detect_expr_type(expr.index)
            if isinstance(obj_type, str) and obj_type.startswith("List["):
                if index_type not in ALL_INT_TYPES:
                    self.give_error(f"List index must be an integer, got {index_type}")
                return obj_type[5:-1]
            if isinstance(obj_type, str) and obj_type.startswith("Dict["):
                bracket_content = obj_type[5:-1]
                comma_idx = None
                depth = 0
                for ci, ch in enumerate(bracket_content):
                    if ch == '[':
                        depth += 1
                    elif ch == ']':
                        depth -= 1
                    elif ch == ',' and depth == 0:
                        comma_idx = ci
                        break
                if comma_idx is not None:
                    key_expected = bracket_content[:comma_idx].strip()
                    val_type = bracket_content[comma_idx + 1:].strip()
                else:
                    val_type = bracket_content.strip()
                if index_type != key_expected:
                    self.give_error(
                        f"Dict index must be {key_expected}, got {index_type}"
                    )
                return val_type
            self.give_error(f"'{obj_type}' is not indexable")
        if t == "FieldAccessExpr":
            obj_type = self.detect_expr_type(expr.obj)

            fields = self._fields_of(obj_type)

            if not fields and obj_type not in self.struct_defs and obj_type not in self.class_defs:
                self.give_error(
                    f"'{obj_type}' is not a struct or class, "
                    f"cannot access field '{expr.field}'"
                )

            for field_decl in fields:
                if field_decl.name == expr.field:
                    return field_decl.var_type

            self.give_error(f"'{obj_type}' has no field '{expr.field}'")
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
                            if not self._try_adapt_literal(fexpr, actual, expected):
                                self.give_error(
                                    f"Struct '{struct_name}' field '{fname}' expects {expected}, got {actual}"
                                )
                        break

                if not found:
                    self.give_error(f"Struct '{struct_name}' has no field '{fname}'")

            return struct_name

        if t == "VarExpr":
            name = expr.name

            if name in self.module_aliases:
                self.give_error(f"Module '{name}' cannot be used as a value")

            for scope in reversed(self.scopes):
                if name in scope:
                    return scope[name]

            if name in self.struct_defs:
                return name

            if name in self.class_defs:
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

            if expr.op in ("-", "+"):
                inner = self.detect_expr_type(expr.expr)
                if is_union_type(inner):
                    for m in union_members(inner):
                        if m not in NUMERIC_TYPES:
                            self.give_error(
                                f"Unary '{expr.op}' requires numeric type, "
                                f"got {inner}"
                            )
                    return inner
                if inner not in NUMERIC_TYPES:
                    self.give_error("Unary '-' requires numeric type")
                return inner

        if t == "CallExpr":
            func_name = expr.func_name

            if func_name in BUILTIN_SIGS:
                arg_types = [self.detect_expr_type(a) for a in expr.args]
                try:
                    return builtin_return_type(
                        func_name,
                        arg_types,
                        aggregate_types=self._aggregate_types(),
                    )
                except ValueError as e:
                    self.give_error(str(e))

            if func_name not in self.func_sigs:
                self.give_error(f"Unknown function '{func_name}'")

            params, return_type = self.func_sigs[func_name]

            required = sum(1 for p in params if p[2] is None)
            if len(expr.args) < required or len(expr.args) > len(params):
                if required == len(params):
                    self.give_error(
                        f"Function '{func_name}' expects {len(params)} arguments, "
                        f"got {len(expr.args)}"
                    )
                else:
                    self.give_error(
                        f"Function '{func_name}' expects between {required} and "
                        f"{len(params)} arguments, got {len(expr.args)}"
                    )

            for (arg_expr, (param_name, param_type, _)) in zip(expr.args, params):
                arg_type = self.detect_expr_type(arg_expr)
                if not self._is_valid_type(param_type):
                    self.give_error(f"Unknown type '{var_type}'")
                if arg_type != param_type:
                    if not self._check_assign(arg_expr, arg_type, param_type,
                                              f"Argument '{param_name}'"):
                        if not self._try_adapt_literal(arg_expr, arg_type, param_type):
                            self.give_error(
                                f"Function '{func_name}' argument '{param_name}' "
                                f"expects type {param_type}, got {arg_type}"
                            )

            return return_type

        if t == "BinaryExpr":
            left = self.detect_expr_type(expr.left)
            right = self.detect_expr_type(expr.right)

            if is_union_type(left) or is_union_type(right):
                lms = union_members(left) if is_union_type(left) else [left]
                rms = union_members(right) if is_union_type(right) else [right]

                if expr.op in ("and", "or"):
                    self.give_error(
                        "Boolean operators require Bool operands, "
                        f"not {left} vs {right}"
                    )

                if expr.op in ("<", ">", "<=", ">=", "==", "!="):
                    for lm in lms:
                        for rm in rms:
                            if common_numeric_type(lm, rm) is None:
                                self.give_error(
                                    f"Type mismatch in comparison: "
                                    f"{left} vs {right}"
                                )
                    return "Bool"

                if expr.op == "+" and "String" in lms and "String" in rms:
                    other = (lms | rms) - {"String"}
                    if not other:
                        return "String"

                if expr.op in ("+", "-", "*", "/", "**", "%", "//"):
                    result_members = set()
                    for lm in lms:
                        for rm in rms:
                            if expr.op == "+" and lm == "String" and rm == "String":
                                result_members.add("String")
                                continue
                            common = common_numeric_type(lm, rm)
                            if common is None:
                                self.give_error(
                                    f"Type mismatch in arithmetic: "
                                    f"{left} vs {right}"
                                )
                            result_members.add(common)
                    if len(result_members) == 1:
                        return result_members.pop()
                    return union_str(result_members)

                self.give_error(f"Unknown operator '{expr.op}'")

            if left != right:
                if self._try_adapt_literal(expr.left, left, right):
                    left = right
                elif self._try_adapt_literal(expr.right, right, left):
                    right = left

            if expr.op in ("<", ">", "<=", ">=", "==", "!="):
                if left != right:
                    self.give_error(f"Type mismatch in comparison: {left} vs {right}")
                return "Bool"

            if expr.op in ("and", "or"):
                if left != "Bool" or right != "Bool":
                    self.give_error("Boolean operators require Bool operands")
                return "Bool"

            if expr.op == "+" and left == "String" and right == "String":
                return "String"

            if expr.op in ("+", "-", "*", "/", "**", "%", "//"):
                if left != right:
                    self.give_error(f"Type mismatch in arithmetic: {left} vs {right}")
                if expr.op in ("/", "//", "%"):
                    const_val = self._const_eval(expr.right)
                    is_zero = False
                    if const_val is not None:
                        val, _ = const_val
                        is_zero = (val == 0)
                    elif type(expr.right).__name__ == "LiteralExpr" and expr.right.value.value == "0":
                        is_zero = True

                    if is_zero:
                        self.give_error("Division by zero is not allowed")
                return left

            self.give_error(f"Unknown operator '{expr.op}'")
        if t == "CastExpr":
            inner_type = self.detect_expr_type(expr.expr)
            numeric_or_str = NUMERIC_TYPES + ("String", "Bool")
            if is_union_type(inner_type):
                self.give_error(f"Cannot cast type '{inner_type}' to '{expr.target_type}'")
            if inner_type not in numeric_or_str:
                self.give_error(f"Cannot cast type '{inner_type}' to '{expr.target_type}'")
            if expr.target_type not in NUMERIC_TYPES + ("Bool", "String"):
                self.give_error(f"Unknown cast target type '{expr.target_type}'")
            self._try_adapt_literal(expr.expr, inner_type, expr.target_type)
            return expr.target_type
        if t == "MethodCallExpr":
            obj_type = self.detect_expr_type(expr.obj)
            expr.obj_type = obj_type

            if obj_type not in self.class_defs:
                self.give_error(
                    f"'{obj_type}' is not a class, "
                    f"cannot call method '{expr.method}'"
                )

            owner = self._resolve_method_owner(obj_type, expr.method)
            if owner is None:
                self.give_error(f"Class '{obj_type}' has no method '{expr.method}'")
            expr.owner = owner

            func_name = self.class_method_map[owner][expr.method]
            expr.func_name = func_name

            if func_name not in self.func_sigs:
                if func_name in self._pending_inferred:
                    self.give_error(
                        f"Method '{expr.method}' must declare a return type "
                        f"before it is called"
                    )
                self.give_error(f"Unknown method '{expr.method}'")

            params, ret_type = self.func_sigs[func_name]

            required = sum(1 for p in params[1:] if p[2] is None)
            if len(expr.args) < required or len(expr.args) > len(params) - 1:
                if required == len(params) - 1:
                    self.give_error(
                        f"Method '{expr.method}' expects {required} arguments, "
                        f"got {len(expr.args)}"
                    )
                else:
                    self.give_error(
                        f"Method '{expr.method}' expects between {required} and "
                        f"{len(params) - 1} arguments, got {len(expr.args)}"
                    )

            for (arg_expr, (param_name, param_type, _)) in zip(expr.args, params[1:]):
                arg_type = self.detect_expr_type(arg_expr)
                if not self._is_valid_type(param_type):
                    self.give_error(f"Unknown type '{param_type}'")
                if arg_type != param_type:
                    if not self._check_assign(arg_expr, arg_type, param_type,
                                              f"Argument '{param_name}'"):
                        if not self._try_adapt_literal(arg_expr, arg_type, param_type):
                            self.give_error(
                                f"Method '{expr.method}' argument '{param_name}' "
                                f"expects type {param_type}, got {arg_type}"
                            )

            expr.ret_type = ret_type
            return ret_type
        if t == "ClassInitExpr":
            class_name = expr.class_name

            if class_name not in self.class_defs:
                self.give_error(f"Unknown class '{class_name}'")

            owner = self._resolve_init(class_name)
            if owner is not None:
                func_name = self.class_method_map[owner]["__init__"]
                expr.init_name = func_name
                params, _ = self.func_sigs[func_name]
                required = sum(1 for p in params[1:] if p[2] is None)
                if len(expr.args) < required or len(expr.args) > len(params) - 1:
                    if required == len(params) - 1:
                        self.give_error(
                            f"Class '{class_name}' '__init__' expects "
                            f"{required} arguments, got {len(expr.args)}"
                        )
                    else:
                        self.give_error(
                            f"Class '{class_name}' '__init__' expects between "
                            f"{required} and {len(params) - 1} arguments, "
                            f"got {len(expr.args)}"
                        )
                for (arg_expr, (param_name, param_type, _)) in zip(expr.args, params[1:]):
                    arg_type = self.detect_expr_type(arg_expr)
                    if not self._is_valid_type(param_type):
                        self.give_error(f"Unknown type '{param_type}'")
                    if arg_type != param_type:
                        if not self._check_assign(arg_expr, arg_type, param_type,
                                                  f"Argument '{param_name}'"):
                            if not self._try_adapt_literal(arg_expr, arg_type, param_type):
                                self.give_error(
                                    f"Class '{class_name}' '__init__' argument "
                                    f"'{param_name}' expects type {param_type}, "
                                    f"got {arg_type}"
                                )
            elif expr.args:
                self.give_error(
                    f"Class '{class_name}' has no '__init__' taking arguments"
                )

            return class_name
        self.give_error("Unknown expression type")
    def _const_eval(self, expr):

        t = type(expr).__name__
        
        if t == "LiteralExpr":
            val = expr.value.value
            if expr.type in ALL_INT_TYPES:
                return (int(val), expr.type)
            if expr.type in FLOAT_TYPES:
                return (float(val), expr.type)
            return None
        
        if t == "UnaryExpr":
            inner = self._const_eval(expr.expr)
            if inner is None:
                return None
            val, typ = inner
            if expr.op == "-":
                return (-val, typ)
            if expr.op == "+":
                return (val, typ)
            return None
        
        if t == "BinaryExpr":
            left = self._const_eval(expr.left)
            right = self._const_eval(expr.right)
            if left is None or right is None:
                return None
            lval, ltyp = left
            rval, rtyp = right
            
            if ltyp != rtyp:
                return None
                
            op = expr.op
            try:
                if op == "+":
                    return (lval + rval, ltyp)
                elif op == "-":
                    return (lval - rval, ltyp)
                elif op == "*":
                    return (lval * rval, ltyp)
                elif op == "/":
                    if rval == 0:
                        self.give_error("Division by zero in constant expression")
                    return (lval / rval, ltyp)
                elif op == "//":
                    if rval == 0:
                        self.give_error("Division by zero in constant expression")
                    return (lval // rval, ltyp)
                elif op == "%":
                    if rval == 0:
                        self.give_error("Division by zero in constant expression")
                    return (lval % rval, ltyp)
                elif op == "**":
                    return (lval ** rval, ltyp)
            except ZeroDivisionError:
                self.give_error("Division by zero in constant expression")
        
        return None
    def parse_return(self):
        if self._in_init:
            self.give_error("'__init__' cannot have explicit return statements")

        if self.return_type is None:
            if self._infer_return:
                tokens = self.current_line

                if len(tokens) == 1:
                    value = LiteralExpr(Token(TokenType.NONE, "None"), "NoneType")
                    if (
                        self._inferred_ret is not None
                        and self._inferred_ret != "NoneType"
                    ):
                        self.give_error(
                            f"Inconsistent return types in method: "
                            f"expected {self._inferred_ret}, got NoneType"
                        )
                    self._inferred_ret = "NoneType"
                    return ReturnStmt("NoneType", value)

                expr = self.parse_expr(tokens[1:])
                detected = self.detect_expr_type(expr)
                if self._inferred_ret is None:
                    self._inferred_ret = detected
                elif self._inferred_ret != detected:
                    self.give_error(
                        f"Inconsistent return types in method: "
                        f"expected {self._inferred_ret}, got {detected}"
                    )
                return ReturnStmt(detected, expr)
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
            if not self._check_assign(expr, detected, self.return_type,
                                      "Return statement"):
                if not self._try_adapt_literal(expr, detected, self.return_type):
                    self.give_error(f"Expected {self.return_type}, got {detected}")

        return ReturnStmt(self.return_type, expr)
    def parse_variable_decl(self, allow_union=True):
        if not self._in_function and not self._in_struct:
            self.give_error("Variable declaration at top level is not allowed; declare variables inside a function instead")
        
        tokens = self.current_line

        name = tokens[0].value

        i = 2
        var_type, i = self.parse_type_from_tokens(
            tokens, "variable declaration", i, allow_union=allow_union
        )

        if i >= len(tokens):
            self.declare_var(name, var_type)
            return VarDecl(name, var_type, None)
        expr_tokens = tokens[i + 1:]

        if (
            len(expr_tokens) == 2
            and expr_tokens[0].type == TokenType.IDENT
            and expr_tokens[1].type == TokenType.CARET
        ):
            expr = RefExpr(VarExpr(expr_tokens[0].value))
        elif tokens[i].type in (
            TokenType.PLUS_ASSIGN,
            TokenType.MINUS_ASSIGN,
            TokenType.MUL_ASSIGN,
            TokenType.DIV_ASSIGN,
            TokenType.MOD_ASSIGN,
            TokenType.FLOORDIV_ASSIGN,
        ):
            op = tokens[i].value[:-1]
            expr = BinaryExpr(VarExpr(name), op, self.parse_expr(expr_tokens))
        else:
            expr = self.parse_expr(expr_tokens)

        detected = self.detect_expr_type(expr)

        if not self._is_valid_type(var_type):
            self.give_error(f"Unknown type '{var_type}'")
        if detected != var_type:
            if self._check_assign(expr, detected, var_type,
                                  f"Variable '{name}'"):
                pass
            else:
                is_literal = (
                    self._is_const_int_expr(expr) and var_type in self._INT_TYPES
                ) or (
                    self._is_const_float_expr(expr) and var_type in self._FLOAT_TYPES
                )

                if is_literal:
                    self._set_expr_type(expr, var_type)
                    self._check_literal_range(expr,var_type)
                elif self._try_adapt_literal(expr, detected, var_type):
                    pass
                else:
                    self.give_error(f"Variable '{name}' expects type {var_type}, got {detected}")
        if isinstance(expr, RefExpr) and isinstance(expr.inner, VarExpr):
            self.aliases[name] = expr.inner.name

        self.declare_var(name, var_type)
        self._narrow_var(name, detected, var_type)
        self.modified_stack[-1].add(name)

        return VarDecl(name, var_type, expr)

    _INT_TYPES = ALL_INT_TYPES
    _FLOAT_TYPES = FLOAT_TYPES

    def _check_assign(self, expr, value_type, target_type, what):
        """Strict compile-time check when assigning ``value_type`` to a
        ``target_type``. Returns True when the value is accepted; raises a
        compile error otherwise. Only union-typed targets are handled here;
        concrete targets fall through to the literal-adaptation logic."""
        if is_union_type(target_type):
            members = union_members(target_type)
            if is_union_type(value_type):
                if value_type == target_type:
                    return True
                if set(union_members(value_type)).issubset(members):
                    return True
                self.give_error(
                    f"{what} expects type {target_type}, got {value_type}"
                )
            if value_type in members:
                return True
            self.give_error(
                f"{what} expects type {target_type}, got {value_type}"
            )
        if is_union_type(value_type):
            self.give_error(
                f"{what} expects type {target_type}, got {value_type}"
            )
        return False

    def _is_const_expr(self, e):
        t = type(e).__name__
        if t == "LiteralExpr":
            return True
        if t == "BinaryExpr" and e.op in ("+", "-", "*", "/", "//", "%", "**"):
            return self._is_const_expr(e.left) and self._is_const_expr(e.right)
        if t == "UnaryExpr" and e.op in ("+", "-"):
            return self._is_const_expr(e.expr)
        return False
    def _is_valid_type(self, t):
        if is_group(t):
            return True
        if is_union_type(t):
            return all(self._is_valid_type(m) for m in union_members(t))
        if t in VALID_PRIMITIVE_TYPES:
            return True
        if t in self.struct_defs:
            return True
        if t in self.struct_import_aliases.values():
            return True
        if t in self.class_defs:
            return True
        if t in self.class_import_aliases.values():
            return True
        if isinstance(t, str) and t.startswith("List[") and t.endswith("]"):
            return self._is_valid_type(t[5:-1])
        if isinstance(t, str) and t.startswith("Dict[") and t.endswith("]"):
            inner = t[5:-1]
            comma_idx = None
            depth = 0
            for ci, ch in enumerate(inner):
                if ch == '[':
                    depth += 1
                elif ch == ']':
                    depth -= 1
                elif ch == ',' and depth == 0:
                    comma_idx = ci
                    break
            if comma_idx is not None:
                k = inner[:comma_idx].strip()
                v = inner[comma_idx + 1:].strip()
            else:
                k = inner.strip()
                v = "Unknown"
            return self._is_valid_type(k) and self._is_valid_type(v)
        if isinstance(t, str) and t.endswith("*") and self._is_valid_type(t[:-1]):
            return True
        return False
    def _is_const_int_expr(self, e):
        t = type(e).__name__
        if t == "LiteralExpr" and e.type in self._INT_TYPES:
            return True
        if t == "BinaryExpr" and e.op in ("+", "-", "*", "/", "//", "%", "**"):
            return self._is_const_int_expr(e.left) and self._is_const_int_expr(e.right)
        if t == "UnaryExpr" and e.op in ("+", "-"):
            return self._is_const_int_expr(e.expr)
        return False

    def _is_const_float_expr(self, e):
        t = type(e).__name__
        if t == "LiteralExpr" and e.type in self._FLOAT_TYPES:
            return True
        if t == "BinaryExpr" and e.op in ("+", "-", "*", "/", "//", "%", "**"):
            return self._is_const_float_expr(e.left) and self._is_const_float_expr(e.right)
        if t == "UnaryExpr" and e.op in ("+", "-"):
            return self._is_const_float_expr(e.expr)
        return False
    def _int_fits(self, val, type_name):
        if type_name.startswith("UInt"):
            width = int(type_name[4:])
            return 0 <= val < (1 << width)
        else:
            width = int(type_name[3:])
            return -(1 << (width - 1)) <= val < (1 << (width - 1))

    def _check_literal_range(self, expr, target_type):
        if target_type not in self._INT_TYPES:
            return
        if not self._is_const_int_expr(expr):
            return
        const_val = self._const_eval(expr)
        if const_val is None:
            return
        val, _ = const_val
        if not self._int_fits(val, target_type):
            self.give_error(f"Integer literal {val} out of range for type '{target_type}'")
    def _set_expr_type(self, e, new_type):
        t = type(e).__name__
        if t == "LiteralExpr":
            if e.type in self._INT_TYPES and new_type in self._INT_TYPES:
                val = int(e.value.value)
                if not self._int_fits(val, new_type):
                    self.give_error(f"Integer literal {val} out of range for type '{new_type}'")
                e.type = new_type
            elif e.type in self._FLOAT_TYPES and new_type in self._FLOAT_TYPES:
                e.type = new_type
        elif t == "BinaryExpr":
            self._set_expr_type(e.left, new_type)
            self._set_expr_type(e.right, new_type)
        elif t == "UnaryExpr":
            self._set_expr_type(e.expr, new_type)
    def _dict_parse_inner(self, dict_type):
        """Parse 'Dict[K,V]' into (K, V) or return None."""
        if not dict_type.startswith("Dict[") or not dict_type.endswith("]"):
            return None
        inner = dict_type[5:-1]
        comma_idx = None
        depth = 0
        for ci, ch in enumerate(inner):
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
            elif ch == ',' and depth == 0:
                comma_idx = ci
                break
        if comma_idx is None:
            return None
        return inner[:comma_idx].strip(), inner[comma_idx + 1:].strip()

    def _try_adapt_literal(self, node, node_type, want_type):
        return self._try_adapt_literal_inner(node, node_type, want_type, promote_num=False)

    def _try_adapt_literal_inner(self, node, node_type, want_type, promote_num=False):
        if node_type == want_type:
            return True
        if (
            isinstance(node_type, str)
            and node_type.startswith("List[")
            and isinstance(want_type, str)
            and want_type.startswith("List[")
        ):
            if type(node).__name__ != "ListLiteralExpr":
                return False
            dst_elem = want_type[5:-1]
            for elem in node.elements:
                elem_type = self.detect_expr_type(elem)
                if elem_type == dst_elem:
                    continue
                if not self._try_adapt_literal_inner(elem, elem_type, dst_elem, promote_num=True):
                    return False
            node.type = want_type
            return True
        if (
            isinstance(node_type, str)
            and node_type.startswith("Dict[")
            and isinstance(want_type, str)
            and want_type.startswith("Dict[")
        ):
            if type(node).__name__ != "DictLiteralExpr":
                return False
            wk = self._dict_parse_inner(want_type)
            dk = self._dict_parse_inner(node_type)
            if wk is None or dk is None:
                return False
            wk_key, wk_val = wk
            dk_key, dk_val = dk
            for i in range(len(node.keys)):
                kt = self.detect_expr_type(node.keys[i])
                if kt != wk_key:
                    if not self._try_adapt_literal_inner(node.keys[i], kt, wk_key, promote_num=True):
                        return False
                vt = self.detect_expr_type(node.values[i])
                if vt != wk_val:
                    if is_group(wk_val) and is_union_type(
                        expand_type(wk_val)
                    ):
                        if vt not in union_members(expand_type(wk_val)):
                            return False
                    elif not self._try_adapt_literal_inner(node.values[i], vt, wk_val, promote_num=True):
                        return False
            node.type = want_type
            return True
        if node_type in self._INT_TYPES and want_type in self._INT_TYPES:
            if self._is_const_int_expr(node):
                self._check_literal_range(node, want_type)
                self._set_expr_type(node, want_type)
                return True
        elif promote_num and node_type in self._INT_TYPES and want_type in self._FLOAT_TYPES:
            if self._is_const_int_expr(node):
                self._set_expr_type(node, want_type)
                return True
        elif node_type in self._FLOAT_TYPES and want_type in self._FLOAT_TYPES:
            if self._is_const_float_expr(node):
                self._set_expr_type(node, want_type)
                return True
        return False
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
            depth = 0
            while i < len(tokens):
                tok = tokens[i]
                if tok.type in (TokenType.LBRACKET, TokenType.LPAREN):
                    depth += 1
                elif tok.type in (TokenType.RBRACKET, TokenType.RPAREN):
                    depth -= 1
                if tok.type == TokenType.COMMA and depth == 0:
                    break
                expr_tokens.append(tok)
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

        current_type = self.lookup_var(name)
        var_type = self._lookup_declared(name) or current_type
        rhs_type = self.detect_expr_type(rhs)

        if not self._is_valid_type(var_type):
            self.give_error(f"Unknown type '{var_type}'")
        if var_type != rhs_type:
            if not self._check_assign(rhs, rhs_type, var_type,
                                      f"Variable '{name}'"):
                self.give_error(
                    f"Variable '{name}' expects type {var_type}, got {rhs_type}"
                )

        full_expr = BinaryExpr(VarExpr(name), op, rhs)

        result_type = self.detect_expr_type(full_expr)

        self._narrow_var(name, result_type, var_type)
        self.modified_stack[-1].add(name)

        return Assign(name, full_expr)

    def parse_field_assign(self):
        tokens = self.current_line

        name = tokens[0].value
        field = tokens[2].value

        base_type = self.lookup_var(name)

        if base_type not in self.struct_defs and base_type not in self.class_defs:
            self.give_error(
                f"'{name}' is not a struct or class, "
                f"cannot assign to field '{field}'"
            )

        fields = self._fields_of(base_type)

        ftype = None
        for decl in fields:
            if decl.name == field:
                ftype = decl.var_type
                break
        if ftype is None:
            self.give_error(f"'{base_type}' has no field '{field}'")

        rhs = self.parse_expr(tokens[4:])
        rhs_type = self.detect_expr_type(rhs)
        if not self._is_valid_type(rhs_type):
            self.give_error(f"Unknown type '{rhs_type}'")
        if ftype != rhs_type:
            self.give_error(
                f"Field '{name}.{field}' expects type {ftype}, got {rhs_type}"
            )

        return FieldAssign(name, field, rhs)

    def parse_assign(self):
        tokens = self.current_line

        name = tokens[0].value
        current_type = self.lookup_var(name)
        var_type = self._lookup_declared(name) or current_type

        rhs = self.parse_expr(tokens[2:])
        rhs_type = self.detect_expr_type(rhs)
        if not self._is_valid_type(var_type):
            self.give_error(f"Unknown type '{var_type}'")
        if var_type != rhs_type:
            if not self._check_assign(rhs, rhs_type, var_type,
                                      f"Variable '{name}'"):
                if (
                    self._is_const_int_expr(rhs) and var_type in self._INT_TYPES
                ) or (
                    self._is_const_float_expr(rhs) and var_type in self._FLOAT_TYPES
                ):
                    self._set_expr_type(rhs, var_type)
                    self._check_literal_range(rhs,var_type)
                elif self._try_adapt_literal(rhs, rhs_type, var_type):
                    pass
                else:
                    self.give_error(
                        f"Variable '{name}' expects type {var_type}, got {rhs_type}"
                    )

        self._narrow_var(name, rhs_type, var_type)
        self.modified_stack[-1].add(name)

        return Assign(name, rhs)

    def parse_index_assign(self):
        tokens = self.current_line

        depth = 0
        assign_idx = None
        last_rb = None
        for k in range(1, len(tokens)):
            tok = tokens[k]
            if tok.type in (TokenType.LBRACKET, TokenType.LPAREN):
                depth += 1
            elif tok.type in (TokenType.RBRACKET, TokenType.RPAREN):
                depth -= 1
                if depth == 0 and tok.type == TokenType.RBRACKET:
                    last_rb = k
            elif tok.type == TokenType.ASSIGN and depth == 0:
                assign_idx = k
                break
        if assign_idx is None or last_rb is None or last_rb + 1 != assign_idx:
            self.give_error("Expected '=' after index expression")

        target = self.parse_expr(tokens[:assign_idx])
        if type(target).__name__ != "IndexExpr":
            self.give_error("Invalid index assignment target")

        value = self.parse_expr(tokens[assign_idx + 1:])

        target_type = self.detect_expr_type(target)
        value_type = self.detect_expr_type(value)
        if not self._is_valid_type(target_type):
            self.give_error(f"Unknown type '{target_type}'")
        if value_type != target_type:
            if not self._try_adapt_literal(value, value_type, target_type):
                self.give_error(
                    f"List element expects type {target_type}, got {value_type}"
                )

        return IndexAssign(target, target.index, value)

    def parse_field_index_assign(self):
        tokens = self.current_line

        depth = 0
        assign_idx = None
        last_rb = None
        for k in range(1, len(tokens)):
            tok = tokens[k]
            if tok.type in (TokenType.LBRACKET, TokenType.LPAREN):
                depth += 1
            elif tok.type in (TokenType.RBRACKET, TokenType.RPAREN):
                depth -= 1
                if depth == 0 and tok.type == TokenType.RBRACKET:
                    last_rb = k
            elif tok.type == TokenType.ASSIGN and depth == 0:
                assign_idx = k
                break
        if assign_idx is None or last_rb is None or last_rb + 1 != assign_idx:
            self.give_error("Expected '=' after index expression")

        target = self.parse_expr(tokens[:assign_idx])
        if type(target).__name__ != "IndexExpr":
            self.give_error("Invalid index assignment target")

        value = self.parse_expr(tokens[assign_idx + 1:])

        target_type = self.detect_expr_type(target)
        value_type = self.detect_expr_type(value)
        if not self._is_valid_type(target_type):
            self.give_error(f"Unknown type '{target_type}'")
        if value_type != target_type:
            if not self._try_adapt_literal(value, value_type, target_type):
                self.give_error(
                    f"List element expects type {target_type}, got {value_type}"
                )

        return IndexAssign(target, target.index, value)

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
    