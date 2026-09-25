from .nodes import *
from .lexer import Token, TokenType
from .builtins import (
    ALL_INT_TYPES,
    FLOAT_TYPES,
    NUMERIC_TYPES,
    BUILTIN_SIGS,
    builtin_return_type,
    common_numeric_type,
    group_members,
    is_union_type,
    union_members,
    union_str,
)

class ComptimeError(Exception):
    pass

class ComptimeInterpreter:
    def __init__(self, struct_defs=None, func_sigs=None, class_defs=None):
        self.struct_defs = struct_defs or {}
        self.func_sigs = func_sigs or {}
        self.class_defs = class_defs or {}
        self.variables = {}
        self.return_value = None
        self._in_function = False

    def eval(self, node):
        t = type(node).__name__
        method_name = f"eval_{t}"
        if hasattr(self, method_name):
            return getattr(self, method_name)(node)
        raise ComptimeError(f"Cannot evaluate {t} at compile time")

    def eval_VarDecl(self, node):
        val = self.eval(node.expr) if node.expr is not None else None
        self.variables[node.name] = (node.var_type, val)
        return val

    def eval_Assign(self, node):
        val = self.eval(node.expr)
        if node.name not in self.variables:
            raise ComptimeError(f"Variable '{node.name}' not declared")
        self.variables[node.name] = (self.variables[node.name][0], val)
        return val

    def eval_ReturnStmt(self, node):
        self.return_value = self.eval(node.value) if node.value is not None else None
        raise ReturnSignal(self.return_value)

    def eval_IfStmt(self, node):
        cond = self.eval(node.condition)
        if not isinstance(cond, bool):
            raise ComptimeError(f"If condition must be bool, got {type(cond)}")
        
        if cond:
            for stmt in node.body:
                self.eval(stmt)
        else:
            for cond_expr, body in node.elif_blocks:
                elif_cond = self.eval(cond_expr)
                if elif_cond:
                    for stmt in body:
                        self.eval(stmt)
                    return
            if node.else_body:
                for stmt in node.else_body:
                    self.eval(stmt)

    def eval_WhileStmt(self, node):
        max_iterations = 1000000
        iterations = 0
        while True:
            cond = self.eval(node.condition)
            if not isinstance(cond, bool):
                raise ComptimeError(f"While condition must be bool, got {type(cond)}")
            if not cond:
                break
            if iterations >= max_iterations:
                raise ComptimeError("Comptime loop exceeded maximum iterations")
            for stmt in node.body:
                self.eval(stmt)
            if node.step:
                for stmt in node.step:
                    self.eval(stmt)
            iterations += 1

    def eval_ExprStmt(self, node):
        return self.eval(node.expr)

    def eval_BreakStmt(self, node):
        raise BreakSignal()

    def eval_ContinueStmt(self, node):
        raise ContinueSignal()

    def eval_LiteralExpr(self, node):
        from .lexer import TokenType
        tok = node.value
        if tok.type == TokenType.NUMBER:
            val = tok.value
            if "." in val or "e" in val or "E" in val:
                return float(val)
            return int(val)
        if tok.type == TokenType.TRUE:
            return True
        if tok.type == TokenType.FALSE:
            return False
        if tok.type == TokenType.STRING:
            return tok.value
        if tok.type == TokenType.NONE:
            return None
        return tok.value

    def eval_VarExpr(self, node):
        if node.name not in self.variables:
            raise ComptimeError(f"Variable '{node.name}' not defined")
        return self.variables[node.name][1]

    def eval_BinaryExpr(self, node):
        left = self.eval(node.left)
        right = self.eval(node.right)
        
        if node.op == "+":
            return left + right
        elif node.op == "-":
            return left - right
        elif node.op == "*":
            return left * right
        elif node.op == "/":
            if right == 0:
                raise ComptimeError("Division by zero")
            return left / right
        elif node.op == "//":
            if right == 0:
                raise ComptimeError("Division by zero")
            return left // right
        elif node.op == "%":
            return left % right
        elif node.op == "**":
            return left ** right
        elif node.op == "==":
            return left == right
        elif node.op == "!=":
            return left != right
        elif node.op == "<":
            return left < right
        elif node.op == ">":
            return left > right
        elif node.op == "<=":
            return left <= right
        elif node.op == ">=":
            return left >= right
        elif node.op == "and":
            return left and right
        elif node.op == "or":
            return left or right
        raise ComptimeError(f"Unknown binary operator: {node.op}")

    def eval_UnaryExpr(self, node):
        val = self.eval(node.expr)
        if node.op == "-":
            return -val
        elif node.op == "not":
            return not val
        raise ComptimeError(f"Unknown unary operator: {node.op}")

    def eval_CallExpr(self, node):
        func_name = node.func_name
        args = [self.eval(arg) for arg in node.args]
        
        if func_name == "len":
            if isinstance(args[0], (list, str, dict)):
                return len(args[0])
            raise ComptimeError(f"len() not supported for {type(args[0])}")
        if func_name == "print":
            print(*args)
            return None
        if func_name in ("range", "std.range"):
            if len(args) == 1:
                return ComptimeListIterator(list(range(args[0])))
            elif len(args) == 2:
                return ComptimeListIterator(list(range(args[0], args[1])))
            elif len(args) == 3:
                return ComptimeListIterator(list(range(args[0], args[1], args[2])))
            raise ComptimeError("range() expects 1-3 arguments")
        
        # std library functions (with or without std. prefix)
        if func_name in ("abs", "std.abs"):
            if len(args) != 1:
                raise ComptimeError("abs() expects 1 argument")
            x = args[0]
            if isinstance(x, (int, float)):
                return -x if x < 0 else x
            raise ComptimeError(f"abs() not supported for {type(x)}")
        if func_name in ("max", "std.max"):
            if len(args) != 2:
                raise ComptimeError("max() expects 2 arguments")
            a, b = args
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                return a if a > b else b
            raise ComptimeError(f"max() not supported for {type(a)}, {type(b)}")
        if func_name in ("min", "std.min"):
            if len(args) != 2:
                raise ComptimeError("min() expects 2 arguments")
            a, b = args
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                return a if a < b else b
            raise ComptimeError(f"min() not supported for {type(a)}, {type(b)}")
        if func_name in ("clamp", "std.clamp"):
            if len(args) != 3:
                raise ComptimeError("clamp() expects 3 arguments")
            x, lo, hi = args
            if all(isinstance(v, (int, float)) for v in (x, lo, hi)):
                if x < lo:
                    return lo
                if x > hi:
                    return hi
                return x
            raise ComptimeError(f"clamp() not supported for {type(x)}, {type(lo)}, {type(hi)}")
        if func_name in ("is_even", "std.is_even"):
            if len(args) != 1:
                raise ComptimeError("is_even() expects 1 argument")
            n = args[0]
            if isinstance(n, int):
                return n % 2 == 0
            raise ComptimeError(f"is_even() not supported for {type(n)}")
        if func_name in ("is_odd", "std.is_odd"):
            if len(args) != 1:
                raise ComptimeError("is_odd() expects 1 argument")
            n = args[0]
            if isinstance(n, int):
                return n % 2 != 0
            raise ComptimeError(f"is_odd() not supported for {type(n)}")
        
        raise ComptimeError(f"Function '{func_name}' not available at compile time")

    def eval_ListLiteralExpr(self, node):
        return [self.eval(e) for e in node.elements]

    def eval_IndexExpr(self, node):
        obj = self.eval(node.obj)
        idx = self.eval(node.index)
        if isinstance(obj, (list, str, dict)):
            return obj[idx]
        raise ComptimeError(f"Indexing not supported for {type(obj)}")

    def eval_SliceExpr(self, node):
        obj = self.eval(node.obj)
        start = self.eval(node.start) if node.start else None
        end = self.eval(node.end) if node.end else None
        if isinstance(obj, (list, str)):
            return obj[start:end]
        raise ComptimeError(f"Slicing not supported for {type(obj)}")

    def eval_DictLiteralExpr(self, node):
        result = {}
        for k, v in zip(node.keys, node.values):
            result[self.eval(k)] = self.eval(v)
        return result

    def eval_StructInitExpr(self, node):
        fields = {}
        for fname, fexpr in node.fields.items():
            fields[fname] = self.eval(fexpr)
        return fields

    def eval_FieldAccessExpr(self, node):
        obj = self.eval(node.obj)
        if isinstance(obj, dict):
            return obj.get(node.field)
        raise ComptimeError(f"Field access not supported for {type(obj)}")

    def eval_InterpolatedStringExpr(self, node):
        parts = []
        for kind, part in node.parts:
            if kind == "lit":
                parts.append(part)
            else:
                parts.append(str(self.eval(part)))
        return "".join(parts)

    def eval_CastExpr(self, node):
        val = self.eval(node.expr)
        target = node.target_type
        if target in ("Int8", "Int16", "Int32", "Int64", "Int", "Int256"):
            return int(val)
        if target in ("UInt8", "UInt16", "UInt32", "UInt64", "UInt256"):
            return int(val)
        if target in ("Float16", "Float32", "Float64", "Float"):
            return float(val)
        if target == "Bool":
            return bool(val)
        if target == "String":
            return str(val)
        raise ComptimeError(f"Cannot cast to {target} at compile time")

    def eval_MethodCallExpr(self, node):
        obj = self.eval(node.obj)
        # Debug
        # print(f"MethodCallExpr: obj type={type(obj)}, method={node.method}")
        if isinstance(obj, ComptimeListIterator):
            if node.method == "append":
                obj.append(self.eval(node.args[0]))
                return obj
            elif node.method == "pop":
                return obj.pop()
            elif node.method == "len":
                return len(obj)
            elif node.method == "done":
                return obj.done()
            elif node.method == "value":
                return obj.value()
            elif node.method == "advance":
                return obj.advance()
        if isinstance(obj, list):
            # Check if this is an iterator protocol call (done, value, advance)
            # The parser creates a wrapper for the list with iterator state
            if not hasattr(obj, '_comptime_iter'):
                # Wrap the list with iterator state
                obj = ComptimeListIterator(obj)
            
            if node.method == "append":
                obj.append(self.eval(node.args[0]))
                return obj
            elif node.method == "pop":
                return obj.pop()
            elif node.method == "len":
                return len(obj)
            elif node.method == "done":
                return obj.done()
            elif node.method == "value":
                return obj.value()
            elif node.method == "advance":
                return obj.advance()
        if isinstance(obj, dict):
            if node.method == "len":
                return len(obj)
        raise ComptimeError(f"Method '{node.method}' not available at compile time")


class ComptimeListIterator:
    """Wrapper for lists to support iterator protocol (done, value, advance)"""
    def __init__(self, lst):
        self._lst = lst
        self._idx = 0
        self._value = lst[0] if lst else None
        self._done = len(lst) == 0
        self._comptime_iter = True
    
    def done(self):
        return self._done
    
    def value(self):
        return self._value
    
    def advance(self):
        if self._idx + 1 < len(self._lst):
            self._idx += 1
            self._value = self._lst[self._idx]
            self._done = False
            return self
        else:
            self._done = True
            return self
    
    # Delegate other list operations
    def append(self, val):
        self._lst.append(val)
        return self
    
    def pop(self):
        return self._lst.pop()
    
    def __len__(self):
        return len(self._lst)
    
    def __getitem__(self, idx):
        return self._lst[idx]
    
    def __setitem__(self, idx, val):
        self._lst[idx] = val
    
    def get(self, key, default=None):
        # For compatibility
        if key == "_done":
            return self._done
        if key == "_value":
            return self._value
        if key == "_idx":
            return self._idx
        return default

    def eval_RefExpr(self, node):
        return self.eval(node.inner)

class ReturnSignal(Exception):
    def __init__(self, value):
        self.value = value

class BreakSignal(Exception):
    pass

class ContinueSignal(Exception):
    pass


def eval_comptime(node, struct_defs, func_sigs, class_defs):
    interpreter = ComptimeInterpreter(struct_defs, func_sigs, class_defs)
    try:
        for stmt in node.body:
            interpreter.eval(stmt)
        if node.return_value is not None:
            value = interpreter.eval(node.return_value)
        else:
            value = interpreter.return_value
        
        # Cast to declared type
        return _cast_to_type(value, node.var_type)
    except ReturnSignal as e:
        value = e.value
        return _cast_to_type(value, node.var_type)


def _cast_to_type(value, target_type):
    if value is None:
        return None
    if target_type in ("Int8", "Int16", "Int32", "Int64", "Int", "Int256"):
        return int(value)
    if target_type in ("UInt8", "UInt16", "UInt32", "UInt64", "UInt256"):
        return int(value)
    if target_type in ("Float16", "Float32", "Float64", "Float"):
        return float(value)
    if target_type == "Bool":
        return bool(value)
    if target_type == "String":
        return str(value)
    return value