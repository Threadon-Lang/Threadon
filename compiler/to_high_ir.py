
from .parser import Parser
from .nodes import (
    FunctionDef,
    IfStmt,
    VarDecl,
    Assign,
    ReturnStmt,
    StructInitExpr,
    BinaryExpr,
    CallExpr,
    LiteralExpr,
    VarExpr,
    FieldAccessExpr,
    UnaryExpr,
    RefExpr,
)
from .checker import CombinedChecker

from collections import defaultdict


class SSAValue:
    def __init__(self, name, type_):
        self.name = name
        self.type = type_
        self.users = []
        self.def_instr = None

    def __str__(self):
        return f"{self.name}: {self.type}"


class IRInstr:
    def __init__(self, op, args, result=None):
        self.op = op
        self.args = args
        self.result = result

        if isinstance(self.result, SSAValue):
            self.result.def_instr = self

        for a in self.args:
            if isinstance(a, SSAValue):
                a.users.append(self)

    def __str__(self):
        if self.op == "struct_init":
            tname = self.args[0]
            parts = []
            for k in range(1, len(self.args), 2):
                parts.append(f"{self.args[k]}={self.args[k + 1].name}")
            inner = f"struct_init %{tname}({', '.join(parts)})"
            if isinstance(self.result, SSAValue):
                return f"{self.result.name}: {self.result.type} = {inner}"
            return inner

        args = ", ".join(str(a) for a in self.args)
        if isinstance(self.result, SSAValue):
            return f"{self.result.name}: {self.result.type} = {self.op} {args}"
        return f"{self.op} {args}"


class IRPhi:
    def __init__(self, result, incoming):
        self.result = result
        self.incoming = incoming
        self.result.def_instr = self
        for _, v in incoming:
            v.users.append(self)

    def __str__(self):
        parts = ", ".join(f"{blk}: {val.name}" for blk, val in self.incoming)
        return f"{self.result.name}: {self.result.type} = phi {parts}"


class IRBlock:
    def __init__(self, label):
        self.label = label
        self.instructions = []
        self.terminator = None
        self.predecessors = []
        self.successors = []

    def add_instr(self, instr):
        self.instructions.append(instr)

    def set_terminator(self, instr):
        self.terminator = instr

    def __str__(self):
        out = [f"{self.label}:"]
        for instr in self.instructions:
            out.append(f"  {instr}")
        if self.terminator:
            out.append(f"  {self.terminator}")
        return "\n".join(out)


class IRFunction:
    def __init__(self, name, params, return_type):
        self.name = name
        self.params = params
        self.return_type = return_type
        self.blocks = []
        self.block_map = {}

    def add_block(self, block):
        self.blocks.append(block)
        self.block_map[block.label] = block

    def build_cfg(self):
        for block in self.blocks:
            block.predecessors = []
            block.successors = []

        for block in self.blocks:
            if block.terminator is None:
                continue
            op = block.terminator.op
            args = block.terminator.args
            if op == "br":
                target = args[0]
                block.successors.append(target)
                self.block_map[target].predecessors.append(block.label)
            elif op == "cond_br":
                _, t1, t2 = args
                block.successors.extend([t1, t2])
                self.block_map[t1].predecessors.append(block.label)
                self.block_map[t2].predecessors.append(block.label)

    def compute_dominators(self):
        dom = {b.label: set(self.block_map.keys()) for b in self.blocks}
        entry = self.blocks[0].label
        dom[entry] = {entry}
        changed = True
        while changed:
            changed = False
            for block in self.blocks:
                if block.label == entry:
                    continue
                preds = block.predecessors
                if not preds:
                    continue
                new_dom = set(self.block_map.keys())
                for p in preds:
                    new_dom &= dom[p]
                new_dom.add(block.label)
                if new_dom != dom[block.label]:
                    dom[block.label] = new_dom
                    changed = True
        return dom

    def compute_liveness(self):
        live_in = defaultdict(set)
        live_out = defaultdict(set)

        changed = True
        while changed:
            changed = False

            for block in reversed(self.blocks):
                old_in = live_in[block.label].copy()
                old_out = live_out[block.label].copy()

                out = set()
                for succ in block.successors:
                    out |= live_in[succ]
                live_out[block.label] = out

                uses = set()
                defs = set()

                for instr in block.instructions:
                    if isinstance(instr.result, SSAValue):
                        defs.add(instr.result.name)

                    if isinstance(instr, IRPhi):
                        for _, val in instr.incoming:
                            uses.add(val.name)
                    else:
                        for a in instr.args:
                            if isinstance(a, SSAValue):
                                uses.add(a.name)

                if block.terminator:
                    term = block.terminator
                    for a in term.args:
                        if isinstance(a, SSAValue):
                            uses.add(a.name)

                live_in[block.label] = uses | (out - defs)

                if old_in != live_in[block.label] or old_out != live_out[block.label]:
                    changed = True

        return live_in, live_out

    def __str__(self):
        out = []
        out.append(
            f"func {self.name}(" +
            ", ".join(f"{n}: {t}" for n, t in self.params) +
            f") -> {self.return_type}"
        )
        self.build_cfg()
        dom = self.compute_dominators()
        live_in, live_out = self.compute_liveness()
        for block in self.blocks:
            out.append("")
            out.append(str(block))
            out.append(f"    preds: {block.predecessors}")
            out.append(f"    succs: {block.successors}")
            out.append(f"    dominators: {sorted(dom[block.label])}")
            out.append(f"    live_in: {sorted(live_in[block.label])}")
            out.append(f"    live_out: {sorted(live_out[block.label])}")
        return "\n".join(out)


class IRModule:
    def __init__(self):
        self.types = {}
        self.funcs = []

    def add_type(self, name, fields):
        self.types[name] = {fname: ftype for fname, ftype in fields}

    def add_func(self, func):
        self.funcs.append(func)

    def __str__(self):
        out = ["module:"]
        for name, fields in self.types.items():
            fs = ", ".join(f"{n}: {t}" for n, t in fields.items())
            out.append(f"  type %{name} = {{ {fs} }}")
        out.append("")
        for f in self.funcs:
            out.append(str(f))
            out.append("")
        return "\n".join(out).rstrip()


class SSABuilder:
    def __init__(self):
        self.module = IRModule()
        self.current_func = None
        self.current_block = None
        self.env_stack = []
        self.temp_counter = 0
        self.func_returns = {}

    def new_temp(self, type_):
        name = f"%t{self.temp_counter}"
        self.temp_counter += 1
        return SSAValue(name, type_)

    def push_env(self):
        self.env_stack.append({})

    def pop_env(self):
        self.env_stack.pop()

    def set_var(self, name, value: SSAValue):
        self.env_stack[-1][name] = value

    def get_var(self, name):
        for env in reversed(self.env_stack):
            if name in env:
                return env[name]
        raise Exception(f"Unknown variable {name}")

    def build_from_ast(self, ast):
        for node in ast:
            if type(node).__name__ == "StructDef":
                fields = [(f.name, f.var_type) for f in node.fields]
                self.module.add_type(node.name, fields)

        for node in ast:
            if isinstance(node, FunctionDef):
                self.func_returns[node.name] = node.return_type

        for node in ast:
            if isinstance(node, FunctionDef):
                self.emit_function(node)
        return self.module

    def emit_function(self, func_ast: FunctionDef):
        f = IRFunction(func_ast.name, func_ast.params, func_ast.return_type)
        self.module.add_func(f)
        self.current_func = f
        self.temp_counter = 0

        entry = IRBlock("entry")
        f.add_block(entry)
        self.current_block = entry
        self.push_env()

        for pname, ptype in func_ast.params:
            val = self.new_temp(ptype)
            self.set_var(pname, val)
            entry.add_instr(IRInstr("param", [pname], result=val))

        for stmt in func_ast.body:
            self.emit_stmt(stmt)

        self.pop_env()
        self.current_func = None
        self.current_block = None

    def emit_stmt(self, node):
        if isinstance(node, VarDecl):
            self.emit_var_decl(node)
        elif isinstance(node, Assign):
            self.emit_assign(node)
        elif isinstance(node, ReturnStmt):
            self.emit_return(node)
        elif isinstance(node, IfStmt):
            self.emit_if(node)
        else:
            pass

    def emit_var_decl(self, node: VarDecl):
        if node.expr is None:
            val = self.new_temp(node.var_type)
            self.set_var(node.name, val)
            self.current_block.add_instr(IRInstr("undef", [], result=val))
        elif isinstance(node.expr, RefExpr):
            src = self.emit_expr(node.expr.inner)
            dest = self.new_temp(node.var_type)
            self.current_block.add_instr(IRInstr("ref_copy", [src], result=dest))
            self.set_var(node.name, dest)
        else:
            rhs = self.emit_expr(node.expr)
            self.set_var(node.name, rhs)

    def emit_assign(self, node: Assign):
        rhs = self.emit_expr(node.expr)
        self.set_var(node.name, rhs)

    def emit_return(self, node: ReturnStmt):
        if node.value is None:
            self.current_block.set_terminator(IRInstr("ret_void", []))
        elif isinstance(node.value, LiteralExpr) and node.value.type == "NoneType":
            self.current_block.set_terminator(IRInstr("ret_void", []))
        else:
            val = self.emit_expr(node.value)
            self.current_block.set_terminator(IRInstr("ret", [val]))

    def emit_if(self, node: IfStmt):
        parent_env = self.env_stack[-1].copy()
        merge = IRBlock("merge")
        self.current_func.add_block(merge)

        branches = [(node.condition, node.body)] + list(node.elif_blocks)
        n = len(branches)
        has_else = node.else_body is not None

        cond_blocks = []
        body_blocks = []
        for i in range(n):
            cb = IRBlock(f"ifcond{i}")
            bb = IRBlock(f"ifbody{i}")
            cond_blocks.append(cb)
            body_blocks.append(bb)
            self.current_func.add_block(cb)
            self.current_func.add_block(bb)

        if has_else:
            else_block = IRBlock("elsebody")
            self.current_func.add_block(else_block)
        else:
            fallthrough = IRBlock("fallthrough")
            self.current_func.add_block(fallthrough)

        self.current_block.set_terminator(IRInstr("br", [cond_blocks[0].label]))

        merge_preds = []

        for i in range(n):
            cond, body = branches[i]
            cb = cond_blocks[i]
            bb = body_blocks[i]

            if i + 1 < n:
                false_tgt = cond_blocks[i + 1].label
            elif has_else:
                false_tgt = else_block.label
            else:
                false_tgt = fallthrough.label

            self.current_block = cb
            cond_val = self.emit_expr(cond)
            cb.set_terminator(IRInstr("cond_br", [cond_val, bb.label, false_tgt]))

            self.current_block = bb
            self.push_env()
            for stmt in body:
                self.emit_stmt(stmt)
            env = self.env_stack[-1].copy()
            self.pop_env()
            if bb.terminator is None:
                bb.set_terminator(IRInstr("br", [merge.label]))
                merge_preds.append((bb.label, env))

        if has_else:
            self.current_block = else_block
            self.push_env()
            for stmt in node.else_body:
                self.emit_stmt(stmt)
            env = self.env_stack[-1].copy()
            self.pop_env()
            if else_block.terminator is None:
                else_block.set_terminator(IRInstr("br", [merge.label]))
                merge_preds.append((else_block.label, env))
        else:
            fallthrough.set_terminator(IRInstr("br", [merge.label]))
            merge_preds.append((fallthrough.label, parent_env))

        self.current_block = merge
        self.push_env()

        all_vars = set(parent_env)
        for _, env in merge_preds:
            all_vars |= set(env)

        for var in all_vars:
            vals = []
            for _, env in merge_preds:
                if var in env:
                    vals.append(env[var])
                elif var in parent_env:
                    vals.append(parent_env[var])
                else:
                    undef = self.new_temp("Unknown")
                    merge.add_instr(IRInstr("undef", [], result=undef))
                    vals.append(undef)

            if all(v.name == vals[0].name for v in vals):
                self.set_var(var, vals[0])
            else:
                res = self.new_temp(vals[0].type)
                incoming = [(merge_preds[k][0], vals[k]) for k in range(len(vals))]
                merge.add_instr(IRPhi(res, incoming))
                self.set_var(var, res)

    def emit_expr(self, expr):
        if isinstance(expr, LiteralExpr):
            t = expr.type
            val = expr.value.value
            if t == "String":
                val = f'"{val}"'
            v = self.new_temp(t)
            self.current_block.add_instr(IRInstr("const", [val], result=v))
            return v

        if isinstance(expr, VarExpr):
            return self.get_var(expr.name)

        if isinstance(expr, RefExpr):
            src = self.emit_expr(expr.inner)
            v = self.new_temp(src.type)
            self.current_block.add_instr(IRInstr("ref_copy", [src], result=v))
            return v

        if isinstance(expr, UnaryExpr):
            operand = self.emit_expr(expr.expr)
            op_map = {"-": "neg", "+": "pos", "not": "not"}
            op = op_map.get(expr.op, expr.op)
            v = self.new_temp(operand.type)
            self.current_block.add_instr(IRInstr(op, [operand], result=v))
            return v

        if isinstance(expr, BinaryExpr):
            left = self.emit_expr(expr.left)
            right = self.emit_expr(expr.right)
            op_map = {
                "<": "cmp_lt",
                ">": "cmp_gt",
                "<=": "cmp_le",
                ">=": "cmp_ge",
                "==": "cmp_eq",
                "!=": "cmp_ne",
                "+": "add",
                "-": "sub",
                "*": "mul",
                "/": "div",
                "//": "floordiv",
                "**": "pow",
                "%": "mod",
            }
            op = op_map.get(expr.op, expr.op)
            v = self.new_temp(left.type)
            self.current_block.add_instr(IRInstr(op, [left, right], result=v))
            return v

        if isinstance(expr, CallExpr):
            args = [self.emit_expr(a) for a in expr.args]
            v = self.new_temp(self.func_returns.get(expr.func_name, "Unknown"))
            self.current_block.add_instr(IRInstr("call", [expr.func_name] + args, result=v))
            return v

        if isinstance(expr, StructInitExpr):
            args = [expr.struct_name]
            for fname, fexpr in expr.fields.items():
                args.append(fname)
                args.append(self.emit_expr(fexpr))
            v = self.new_temp(expr.struct_name)
            self.current_block.add_instr(IRInstr("struct_init", args, result=v))
            return v

        if isinstance(expr, FieldAccessExpr):
            base = self.emit_expr(expr.obj)
            ftype = self.module.types.get(base.type, {}).get(expr.field, "Unknown")
            v = self.new_temp(ftype)
            self.current_block.add_instr(IRInstr("field", [base, expr.field], result=v))
            return v

        raise Exception(f"Unknown expr type: {type(expr).__name__}")


