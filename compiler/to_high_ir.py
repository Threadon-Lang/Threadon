from collections import defaultdict

from .builtins import BUILTIN_SIGS
from .nodes import (
    Assign,
    AttrDecl,
    BinaryExpr,
    CallExpr,
    CastExpr,
    ClassInitExpr,
    Expr,
    ExprStmt,
    FieldAccessExpr,
    FieldAssign,
    FunctionDef,
    IfStmt,
    IndexAssign,
    IndexExpr,
    InterpolatedStringExpr,
    ListLiteralExpr,
    LiteralExpr,
    MethodCallExpr,
    RefExpr,
    ReturnStmt,
    StructInitExpr,
    UnaryExpr,
    VarDecl,
    VarExpr,
    WhileStmt,
)


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
                parts.append(
                    f"{self.args[k]}={self.args[k + 1].name}"
                )

            inner = (
                f"struct_init %{tname}"
                f"({', '.join(parts)})"
            )

            if isinstance(self.result, SSAValue):
                return (
                    f"{self.result.name}: "
                    f"{self.result.type} = {inner}"
                )

            return inner

        if self.op == "list_init":
            inner = f"list_init {self.args[0]} ["
            inner += ", ".join(
                a.name for a in self.args[1:]
            )
            inner += "]"

            if isinstance(self.result, SSAValue):
                return (
                    f"{self.result.name}: "
                    f"{self.result.type} = {inner}"
                )

            return inner

        if self.op == "list_get":
            inner = (
                f"list_get "
                f"{self.args[0].name}"
                f"[{self.args[1].name}]"
            )

            if isinstance(self.result, SSAValue):
                return (
                    f"{self.result.name}: "
                    f"{self.result.type} = {inner}"
                )

            return inner

        if self.op == "list_set":
            inner = (
                f"list_set "
                f"{self.args[0].name}"
                f"[{self.args[1].name}]"
                f" = {self.args[2].name}"
            )

            if isinstance(self.result, SSAValue):
                return (
                    f"{self.result.name}: "
                    f"{self.result.type} = {inner}"
                )

            return inner

        args = ", ".join(str(a) for a in self.args)

        if isinstance(self.result, SSAValue):
            return (
                f"{self.result.name}: "
                f"{self.result.type} = "
                f"{self.op} {args}"
            )

        return f"{self.op} {args}"


class IRPhi(IRInstr):
    def __init__(self, result, incoming):
        self.incoming = incoming

        super().__init__(
            "phi",
            [v for _, v in incoming],
            result=result,
        )

    def __str__(self):
        parts = ", ".join(
            f"{blk}: {val.name}"
            for blk, val in self.incoming
        )

        return (
            f"{self.result.name}: "
            f"{self.result.type} = phi {parts}"
        )


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
        if self.terminator is not None:
            raise Exception(
                f"Block '{self.label}' already has "
                f"a terminator: {self.terminator}"
            )

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
        if block.label in self.block_map:
            raise Exception(
                f"Duplicate block label: {block.label}"
            )

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

                if target not in self.block_map:
                    raise Exception(
                        f"Unknown branch target "
                        f"'{target}' from '{block.label}'"
                    )

                block.successors.append(target)
                self.block_map[target].predecessors.append(
                    block.label
                )

            elif op == "cond_br":
                _, t1, t2 = args

                if t1 not in self.block_map:
                    raise Exception(
                        f"Unknown branch target "
                        f"'{t1}' from '{block.label}'"
                    )

                if t2 not in self.block_map:
                    raise Exception(
                        f"Unknown branch target "
                        f"'{t2}' from '{block.label}'"
                    )

                block.successors.extend([t1, t2])

                self.block_map[t1].predecessors.append(
                    block.label
                )
                self.block_map[t2].predecessors.append(
                    block.label
                )

    def compute_dominators(self):
        dom = {
            b.label: set(self.block_map.keys())
            for b in self.blocks
        }

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
                    for a in block.terminator.args:
                        if isinstance(a, SSAValue):
                            uses.add(a.name)

                live_in[block.label] = (
                    uses | (out - defs)
                )

                if (
                    old_in != live_in[block.label]
                    or old_out != live_out[block.label]
                ):
                    changed = True

        return live_in, live_out

    def __str__(self):
        out = []

        out.append(
            f"func {self.name}("
            + ", ".join(
                f"{n}: {t}"
                for n, t, _ in self.params
            )
            + f") -> {self.return_type}"
        )

        self.build_cfg()

        dom = self.compute_dominators()
        live_in, live_out = self.compute_liveness()

        for block in self.blocks:
            out.append("")
            out.append(str(block))
            out.append(
                f"    preds: {block.predecessors}"
            )
            out.append(
                f"    succs: {block.successors}"
            )
            out.append(
                f"    dominators: "
                f"{sorted(dom[block.label])}"
            )
            out.append(
                f"    live_in: "
                f"{sorted(live_in[block.label])}"
            )
            out.append(
                f"    live_out: "
                f"{sorted(live_out[block.label])}"
            )

        return "\n".join(out)


class IRModule:
    def __init__(self):
        self.types = {}
        self.funcs = []
        self.class_bases = {}

    def add_type(self, name, fields):
        self.types[name] = {
            fname: ftype
            for fname, ftype in fields
        }

    def add_func(self, func):
        self.funcs.append(func)

    def __str__(self):
        out = ["module:"]

        for name, fields in self.types.items():
            fs = ", ".join(
                f"{n}: {t}"
                for n, t in fields.items()
            )

            out.append(
                f"  type %{name} = {{ {fs} }}"
            )

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
        self.func_params = {}

        self.aliases = {}

        self.ptr_vars = {}
        self.ref_vars = set()

        self._if_seq = 0

        self._render_funcs = {}
        self._render_seq = 0


    def new_temp(self, type_):
        name = f"%t{self.temp_counter}"
        self.temp_counter += 1
        return SSAValue(name, type_)

    def push_env(self):
        self.env_stack.append({})

    def pop_env(self):
        if not self.env_stack:
            raise Exception("Environment stack underflow")

        self.env_stack.pop()

    def _resolve_alias(self, name):
        seen = set()

        while (
            name in self.aliases
            and name not in seen
        ):
            seen.add(name)
            name = self.aliases[name]

        return name

    def get_var(self, name):
        name = self._resolve_alias(name)

        if name in self.ptr_vars:
            ptr = self.ptr_vars[name]

            elem_type = ptr.type[:-1]

            loaded = self.new_temp(elem_type)

            self.current_block.add_instr(
                IRInstr(
                    "load",
                    [ptr],
                    result=loaded,
                )
            )

            return loaded

        for env in reversed(self.env_stack):
            if name in env:
                return env[name]

        raise Exception(
            f"Unknown variable {name}"
        )

    def set_var(self, name, value):
        name = self._resolve_alias(name)

        if name in self.ptr_vars:
            ptr = self.ptr_vars[name]

            self.current_block.add_instr(
                IRInstr(
                    "store",
                    [value, ptr],
                    result=None,
                )
            )

            return

        if not self.env_stack:
            raise Exception(
                "No environment available"
            )

        self.env_stack[-1][name] = value


    def _emit_stmt_list(self, stmts):

        for stmt in stmts:
            if self.current_block.terminator is not None:
                break

            self.emit_stmt(stmt)


    def build_from_ast(self, ast, native_sigs=None):
        for node in ast:
            if type(node).__name__ == "StructDef":
                fields = [
                    (f.name, f.var_type)
                    for f in node.fields
                ]

                self.module.add_type(
                    node.name,
                    fields,
                )

            elif type(node).__name__ == "ClassDef":
                fields = [
                    (f.name, f.var_type)
                    for f in node.fields
                ]

                self.module.add_type(
                    node.name,
                    fields,
                )
                self.module.class_bases[node.name] = node.base

        for node in ast:
            if isinstance(node, FunctionDef):
                self._register_func(node)

            elif type(node).__name__ == "ClassDef":
                for method in node.methods:
                    self._register_func(method)

        for qname, (params, return_type) in (native_sigs or {}).items():
            self.func_returns[qname] = return_type
            self.func_params[qname] = params

        for node in ast:
            if isinstance(node, FunctionDef):
                self.emit_function(node)

            elif type(node).__name__ == "ClassDef":
                for method in node.methods:
                    self.emit_function(method)

        return self.module

    def _register_func(self, func_ast):
        self.func_returns[func_ast.name] = func_ast.return_type
        self.func_params[func_ast.name] = func_ast.params


    def collect_ref_vars(self, func_ast: FunctionDef):
        ref_vars = set()

        def walk_expr(expr):
            if expr is None:
                return

            t = type(expr).__name__

            if t == "RefExpr":
                inner = expr.inner

                if type(inner).__name__ == "VarExpr":
                    ref_vars.add(inner.name)

                walk_expr(inner)

            elif t == "BinaryExpr":
                walk_expr(expr.left)
                walk_expr(expr.right)

            elif t == "UnaryExpr":
                walk_expr(expr.expr)

            elif t == "CallExpr":
                for a in expr.args:
                    walk_expr(a)

            elif t == "FieldAccessExpr":
                walk_expr(expr.obj)

            elif t == "MethodCallExpr":
                walk_expr(expr.obj)
                for a in expr.args:
                    walk_expr(a)

            elif t == "ClassInitExpr":
                for a in expr.args:
                    walk_expr(a)

            elif t == "StructInitExpr":
                for v in expr.fields.values():
                    walk_expr(v)

            elif t == "ListLiteralExpr":
                for e in expr.elements:
                    walk_expr(e)

            elif t == "IndexExpr":
                walk_expr(expr.obj)
                walk_expr(expr.index)

        def walk_stmt(stmt):
            t = type(stmt).__name__

            if (
                t == "VarDecl"
                or t == "Assign"
                or t == "FieldAssign"
                or t == "AttrDecl"
            ):
                walk_expr(stmt.expr)

            elif t == "IndexAssign":
                walk_expr(stmt.target)
                walk_expr(stmt.index)
                walk_expr(stmt.value)

            elif t == "ReturnStmt":
                walk_expr(stmt.value)

            elif t == "ExprStmt":
                walk_expr(stmt.expr)

            elif t == "IfStmt":
                walk_expr(stmt.condition)

                for s in stmt.body:
                    walk_stmt(s)

                for cond, body in stmt.elif_blocks:
                    walk_expr(cond)

                    for s in body:
                        walk_stmt(s)

                if stmt.else_body is not None:
                    for s in stmt.else_body:
                        walk_stmt(s)

            elif t == "WhileStmt":
                walk_expr(stmt.condition)

                for s in stmt.body:
                    walk_stmt(s)

        for stmt in func_ast.body:
            walk_stmt(stmt)

        return ref_vars

    def _promote_to_alloca(
        self,
        name,
        var_type,
        init_val,
    ):
        name = self._resolve_alias(name)

        if name in self.ptr_vars:
            return self.ptr_vars[name]

        ptr = self.new_temp(
            f"{var_type}*"
        )

        self.current_block.add_instr(
            IRInstr(
                "alloca",
                [var_type],
                result=ptr,
            )
        )

        self.current_block.add_instr(
            IRInstr(
                "store",
                [init_val, ptr],
                result=None,
            )
        )

        self.ptr_vars[name] = ptr

        return ptr


    def emit_function(self, func_ast: FunctionDef):
        f = IRFunction(
            func_ast.name,
            func_ast.params,
            func_ast.return_type,
        )

        self.module.add_func(f)

        self.current_func = f
        self.temp_counter = 0
        self._if_seq = 0

        self.aliases = {}

        self.ref_vars = self.collect_ref_vars(
            func_ast
        )

        self.ptr_vars = {}

        entry = IRBlock("entry")
        f.add_block(entry)

        self.current_block = entry

        self.push_env()

        for pname, ptype, _ in func_ast.params:
            val = self.new_temp(ptype)

            self.set_var(
                pname,
                val,
            )

            entry.add_instr(
                IRInstr(
                    "param",
                    [pname],
                    result=val,
                )
            )

            if pname in self.ref_vars:
                self._promote_to_alloca(
                    pname,
                    ptype,
                    val,
                )

        self._emit_stmt_list(
            func_ast.body
        )

        self.pop_env()

        self.current_func = None
        self.current_block = None


    def emit_stmt(self, node):
        if self.current_block.terminator is not None:
            return

        if isinstance(node, VarDecl):
            self.emit_var_decl(node)

        elif isinstance(node, Assign):
            self.emit_assign(node)

        elif isinstance(node, IndexAssign):
            self.emit_index_assign(node)

        elif isinstance(node, FieldAssign):
            self.emit_field_assign(node)

        elif isinstance(node, AttrDecl):
            self.emit_attr_decl(node)

        elif isinstance(node, ReturnStmt):
            self.emit_return(node)

        elif isinstance(node, IfStmt):
            self.emit_if(node)

        elif isinstance(node, WhileStmt):
            self.emit_while(node)

        elif isinstance(node, ExprStmt):
            self.emit_expr(node.expr)

    def emit_var_decl(self, node):
        if node.expr is None:
            val = self.new_temp(
                node.var_type
            )

            self.set_var(
                node.name,
                val,
            )

            self.current_block.add_instr(
                IRInstr(
                    "undef",
                    [],
                    result=val,
                )
            )

            if node.name in self.ref_vars:
                self._promote_to_alloca(
                    node.name,
                    node.var_type,
                    self.get_var(node.name),
                )

            return

        if isinstance(node.expr, RefExpr):
            inner = node.expr.inner

            if type(inner).__name__ == "VarExpr":
                src_name = self._resolve_alias(
                    inner.name
                )

                if src_name not in self.ptr_vars:
                    cur_val = self.get_var(
                        src_name
                    )

                    self._promote_to_alloca(
                        src_name,
                        cur_val.type,
                        cur_val,
                    )

                self.ptr_vars[node.name] = (
                    self.ptr_vars[src_name]
                )

            else:
                src = self.emit_expr(
                    node.expr.inner
                )

                dest = self.new_temp(
                    src.type
                )

                self.current_block.add_instr(
                    IRInstr(
                        "ref_copy",
                        [src],
                        result=dest,
                    )
                )

                self.set_var(
                    node.name,
                    dest,
                )

            return

        rhs = self.emit_expr(node.expr)

        if node.name in self.ref_vars:
            self._promote_to_alloca(
                node.name,
                node.var_type,
                rhs,
            )
        else:
            self.set_var(
                node.name,
                rhs,
            )

    def emit_assign(self, node):
        rhs = self.emit_expr(node.expr)
        self.set_var(
            node.name,
            rhs,
        )

    def emit_index_assign(self, node):
        value = self.emit_expr(
            node.value
        )

        return self.assign_into(
            node.target,
            value,
        )

    def assign_into(self, target, value):
        if isinstance(target, IndexExpr):
            base = self.emit_expr(
                target.obj
            )

            idx = self.emit_expr(
                target.index
            )

            new = self.new_temp(
                base.type
            )

            self.current_block.add_instr(
                IRInstr(
                    "list_set",
                    [base, idx, value],
                    result=new,
                )
            )

            return self.assign_into(
                target.obj,
                new,
            )

        if isinstance(target, FieldAccessExpr):
            base = self.get_var(
                target.obj.name
            )

            fres = self.new_temp(
                base.type
            )

            self.current_block.add_instr(
                IRInstr(
                    "store_field",
                    [
                        base,
                        target.field,
                        value,
                    ],
                    result=fres,
                )
            )

            self.set_var(
                target.obj.name,
                fres,
            )

            return value

        if isinstance(target, VarExpr):
            self.set_var(
                target.name,
                value,
            )

            return value

        return value

    def emit_field_assign(self, node):
        rhs = self.emit_expr(
            node.expr
        )

        base = self.get_var(
            node.name
        )

        res = self.new_temp(
            base.type
        )

        self.current_block.add_instr(
            IRInstr(
                "store_field",
                [
                    base,
                    node.field,
                    rhs,
                ],
                result=res,
            )
        )

        self.set_var(
            node.name,
            res,
        )

    def emit_attr_decl(self, node):
        if node.expr is None:
            return

        rhs = self.emit_expr(
            node.expr
        )

        base = self.get_var(
            node.name
        )

        res = self.new_temp(
            base.type
        )

        self.current_block.add_instr(
            IRInstr(
                "store_field",
                [
                    base,
                    node.field,
                    rhs,
                ],
                result=res,
            )
        )

        self.set_var(
            node.name,
            res,
        )

    def emit_return(self, node):
        if node.value is None:
            self.current_block.set_terminator(
                IRInstr(
                    "ret_void",
                    [],
                )
            )

            return

        val = self.emit_expr(
            node.value
        )

        if val.type == "NoneType":
            self.current_block.set_terminator(
                IRInstr(
                    "ret_void",
                    [],
                )
            )
        else:
            self.current_block.set_terminator(
                IRInstr(
                    "ret",
                    [val],
                )
            )


    def emit_if(self, node):
        parent_env = self.env_stack[-1].copy()

        seq = self._if_seq
        self._if_seq += 1

        suffix = f"{seq}_" if seq else ""

        merge = IRBlock(
            f"merge{suffix}"
        )

        self.current_func.add_block(
            merge
        )

        branches = (
            [(node.condition, node.body)]
            + list(node.elif_blocks)
        )

        n = len(branches)
        has_else = (
            node.else_body is not None
        )

        cond_blocks = []
        body_blocks = []

        for i in range(n):
            cb = IRBlock(
                f"ifcond{suffix}{i}"
            )

            bb = IRBlock(
                f"ifbody{suffix}{i}"
            )

            cond_blocks.append(cb)
            body_blocks.append(bb)

            self.current_func.add_block(cb)
            self.current_func.add_block(bb)

        if has_else:
            else_block = IRBlock(
                f"elsebody{suffix}"
            )

            self.current_func.add_block(
                else_block
            )
        else:
            fallthrough = IRBlock(
                f"fallthrough{suffix}"
            )

            self.current_func.add_block(
                fallthrough
            )

        if self.current_block.terminator is None:
            self.current_block.set_terminator(
                IRInstr(
                    "br",
                    [cond_blocks[0].label],
                )
            )

        merge_preds = []

        for i in range(n):
            cond, body = branches[i]

            cb = cond_blocks[i]
            bb = body_blocks[i]

            if i + 1 < n:
                false_tgt = (
                    cond_blocks[i + 1].label
                )
            elif has_else:
                false_tgt = else_block.label
            else:
                false_tgt = fallthrough.label

            self.current_block = cb

            cond_val = self.emit_expr(
                cond
            )

            if cb.terminator is None:
                cb.set_terminator(
                    IRInstr(
                        "cond_br",
                        [
                            cond_val,
                            bb.label,
                            false_tgt,
                        ],
                    )
                )

            self.current_block = bb

            self.push_env()

            self._emit_stmt_list(body)

            env = self.env_stack[-1].copy()

            self.pop_env()

            if bb.terminator is None:
                bb.set_terminator(
                    IRInstr(
                        "br",
                        [merge.label],
                    )
                )

                merge_preds.append(
                    (bb.label, env)
                )

        if has_else:
            self.current_block = else_block

            self.push_env()

            self._emit_stmt_list(
                node.else_body
            )

            env = self.env_stack[-1].copy()

            self.pop_env()

            if else_block.terminator is None:
                else_block.set_terminator(
                    IRInstr(
                        "br",
                        [merge.label],
                    )
                )

                merge_preds.append(
                    (else_block.label, env)
                )

        else:
            fallthrough.set_terminator(
                IRInstr(
                    "br",
                    [merge.label],
                )
            )

            merge_preds.append(
                (
                    fallthrough.label,
                    parent_env,
                )
            )


        self.current_block = merge

        merge_env = {}

        all_vars = set(parent_env)

        for _, env in merge_preds:
            all_vars |= set(env)

        for var in all_vars:
            vals = []

            for _, env in merge_preds:
                if var in env:
                    vals.append(
                        env[var]
                    )

                elif var in parent_env:
                    vals.append(
                        parent_env[var]
                    )

                else:
                    undef = self.new_temp(
                        "Unknown"
                    )

                    merge.add_instr(
                        IRInstr(
                            "undef",
                            [],
                            result=undef,
                        )
                    )

                    vals.append(undef)

            if not vals:
                continue

            if all(
                v.name == vals[0].name
                for v in vals
            ):
                merge_env[var] = vals[0]

            else:
                res = self.new_temp(
                    vals[0].type
                )

                incoming = [
                    (
                        merge_preds[k][0],
                        vals[k],
                    )
                    for k in range(len(vals))
                ]

                phi = IRPhi(
                    res,
                    incoming,
                )

                merge.add_instr(phi)

                merge_env[var] = res

        self.env_stack[-1] = merge_env


    def emit_while(self, node):


        parent_env = self.env_stack[-1].copy()

        seq = self._if_seq
        self._if_seq += 1

        suffix = f"{seq}_" if seq else ""

        entry_block = self.current_block

        cond_block = IRBlock(
            f"whilecond{suffix}"
        )

        body_block = IRBlock(
            f"whilebody{suffix}"
        )

        latch_block = IRBlock(
            f"whilelatch{suffix}"
        )

        merge_block = IRBlock(
            f"whilemerge{suffix}"
        )

        for block in (
            cond_block,
            body_block,
            latch_block,
            merge_block,
        ):
            self.current_func.add_block(
                block
            )


        if entry_block.terminator is None:
            entry_block.set_terminator(
                IRInstr(
                    "br",
                    [cond_block.label],
                )
            )


        assigned = set()

        for stmt in node.body:
            self._collect_assigned(
                stmt,
                assigned,
            )

        loop_vars = {
            var
            for var in assigned
            if var in parent_env
            and var not in self.ptr_vars
        }


        phis = {}

        for var in sorted(loop_vars):
            initial = parent_env[var]

            result = self.new_temp(
                initial.type
            )

            phi = IRPhi(
                result,
                [
                    (
                        entry_block.label,
                        initial,
                    )
                ],
            )

            phis[var] = phi

            cond_block.add_instr(phi)


        cond_env = dict(parent_env)

        for var, phi in phis.items():
            cond_env[var] = phi.result

        self.env_stack[-1] = cond_env

        self.current_block = cond_block

        cond_val = self.emit_expr(
            node.condition
        )

        if cond_block.terminator is None:
            cond_block.set_terminator(
                IRInstr(
                    "cond_br",
                    [
                        cond_val,
                        body_block.label,
                        merge_block.label,
                    ],
                )
            )


        self.current_block = body_block

        self.push_env()

        for var, phi in phis.items():
            self.env_stack[-1][var] = (
                phi.result
            )

        self._emit_stmt_list(
            node.body
        )

        body_env = self.env_stack[-1].copy()
        body_end = self.current_block

        self.pop_env()


        if body_end.terminator is None:
            body_end.set_terminator(
                IRInstr(
                    "br",
                    [latch_block.label],
                )
            )

            back_edge_exists = True

        else:
            back_edge_exists = False


        if back_edge_exists:
            self.current_block = latch_block

            latch_block.set_terminator(
                IRInstr(
                    "br",
                    [cond_block.label],
                )
            )

            back_label = latch_block.label

            for var, phi in phis.items():
                back_val = self._safe_env_lookup(
                    body_env,
                    var,
                    body_end,
                )

                phi.incoming.append(
                    (
                        back_label,
                        back_val,
                    )
                )

                phi.args = [
                    value
                    for _, value in phi.incoming
                ]

                if isinstance(
                    back_val,
                    SSAValue,
                ):
                    if phi not in back_val.users:
                        back_val.users.append(
                            phi
                        )


        self.current_block = merge_block

        merge_env = dict(parent_env)

        for var, phi in phis.items():
            merge_env[var] = phi.result

        self.env_stack[-1] = merge_env


    def _collect_assigned(self, stmt, out):


        if isinstance(stmt, (list, tuple)):
            for s in stmt:
                self._collect_assigned(
                    s,
                    out,
                )
            return

        t = type(stmt).__name__

        if t == "Assign":
            out.add(stmt.name)

        elif t == "FieldAssign":
            out.add(stmt.name)

        elif t == "AttrDecl":
            out.add(stmt.name)

        elif t == "IndexAssign":
            self._collect_target_names(
                stmt.target,
                out,
            )

        elif t == "VarDecl":
            out.add(stmt.name)

        elif t == "IfStmt":
            self._collect_assigned(
                stmt.body,
                out,
            )

            for _, body in stmt.elif_blocks:
                self._collect_assigned(
                    body,
                    out,
                )

            if stmt.else_body is not None:
                self._collect_assigned(
                    stmt.else_body,
                    out,
                )

        elif t == "WhileStmt":
            for s in stmt.body:
                self._collect_assigned(
                    s,
                    out,
                )

    def _collect_target_names(self, target, out):
        if isinstance(target, VarExpr):
            out.add(target.name)

        elif isinstance(target, IndexExpr):
            self._collect_target_names(
                target.obj,
                out,
            )

        elif isinstance(target, FieldAccessExpr):
            self._collect_target_names(
                target.obj,
                out,
            )


    def _safe_env_lookup(
        self,
        env,
        var,
        block,
    ):
        if var in env:
            return env[var]

        raise Exception(
            f"SSA error: loop variable '{var}' "
            f"has no value on back-edge from "
            f"block '{block.label}'"
        )


    def _is_expr_node(self, x):
        return x is not None and (
            isinstance(x, Expr)
            or type(x).__name__ == "CastExpr"
        )

    def _var_names(self, expr):
        names = []

        if isinstance(expr, VarExpr):
            return [expr.name]

        if isinstance(expr, LiteralExpr):
            return []

        for attr in ("left", "right", "expr", "inner", "obj", "index"):
            sub = getattr(expr, attr, None)

            if self._is_expr_node(sub):
                names += self._var_names(sub)

        for attr in ("args", "elements"):
            items = getattr(expr, attr, None)

            if isinstance(items, list):
                for item in items:
                    if self._is_expr_node(item):
                        names += self._var_names(item)

        fields = getattr(expr, "fields", None)

        if isinstance(fields, dict):
            for fval in fields.values():
                if self._is_expr_node(fval):
                    names += self._var_names(fval)
        elif isinstance(fields, list):
            for item in fields:
                if isinstance(item, tuple) and len(item) == 2:
                    if self._is_expr_node(item[1]):
                        names += self._var_names(item[1])
                elif self._is_expr_node(item):
                    names += self._var_names(item)

        parts = getattr(expr, "parts", None)

        if isinstance(parts, list):
            for kind, val in parts:
                if kind == "expr" and self._is_expr_node(val):
                    names += self._var_names(val)

        return names

    def _emit_const_string(self, text):
        v = self.new_temp("String")

        self.current_block.add_instr(
            IRInstr(
                "const",
                [text],
                result=v,
            )
        )

        return v

    def _interp_part_to_string(self, part):
        kind, val = part

        if kind == "lit":
            return self._emit_const_string(val)

        v = self.emit_expr(val)

        if v.type != "String":
            cast = self.new_temp("String")

            self.current_block.add_instr(
                IRInstr(
                    "cast",
                    [v, "String"],
                    result=cast,
                )
            )

            return cast

        return v

    def emit_interpolated_string(self, node):
        if node.kind == "f":
            parts = [
                self._interp_part_to_string(p)
                for p in node.parts
            ]

            res = self.new_temp("String")

            self.current_block.add_instr(
                IRInstr(
                    "tmpl_concat",
                    parts,
                    result=res,
                )
            )

            return res

        return self._emit_t_string(node)

    def _emit_t_string(self, node):
        captures = []

        for kind, val in node.parts:
            if kind == "lit":
                continue

            for name in self._var_names(val):
                name = self._resolve_alias(name)

                if name not in captures:
                    captures.append(name)

        ptrs = []

        for name in captures:
            val = self.get_var(name)
            ptr = self._promote_to_alloca(
                name,
                val.type,
                val,
            )
            ptrs.append(ptr)

        shape = (
            tuple(
                (
                    kind,
                    val if kind == "lit" else type(val).__name__,
                )
                for kind, val in node.parts
            ),
            tuple(p.type for p in ptrs),
        )

        if shape in self._render_funcs:
            render_name = self._render_funcs[shape]
        else:
            render_name = f"__threadon_render_{self._render_seq}"
            self._render_seq += 1
            self._render_funcs[shape] = render_name
            self._build_render_function(
                render_name,
                node,
                captures,
                ptrs,
            )

        tmpl = self.new_temp("String")

        self.current_block.add_instr(
            IRInstr(
                "template_new",
                [render_name] + ptrs,
                result=tmpl,
            )
        )

        return tmpl

    def _build_render_function(
        self,
        render_name,
        node,
        captures,
        ptrs,
    ):
        render = IRFunction(render_name, [], "String")
        self.module.add_func(render)

        entry = IRBlock("entry")
        render.add_block(entry)

        saved_func = self.current_func
        saved_block = self.current_block
        saved_env = self.env_stack
        saved_ptrs = self.ptr_vars
        saved_aliases = self.aliases
        saved_tc = self.temp_counter
        saved_seq = self._if_seq

        self.current_func = render
        self.current_block = entry
        self.env_stack = []
        self.ptr_vars = {}
        self.aliases = {}
        self.temp_counter = 0
        self._if_seq = 0

        self.push_env()

        payload = self.new_temp("TemplatePayload")

        entry.add_instr(
            IRInstr(
                "param",
                ["payload"],
                result=payload,
            )
        )

        render.payload_param_name = payload.name

        for i, name in enumerate(captures):
            vtype = ptrs[i].type[:-1]

            pv = self.new_temp(vtype)

            entry.add_instr(
                IRInstr(
                    "tmpl_payload_val",
                    [i, vtype],
                    result=pv,
                )
            )

            self.env_stack[-1][name] = pv

        parts = [
            self._interp_part_to_string(p)
            for p in node.parts
        ]

        res = self.new_temp("String")

        entry.add_instr(
            IRInstr(
                "tmpl_concat",
                parts,
                result=res,
            )
        )

        entry.set_terminator(
            IRInstr("ret", [res])
        )

        self.current_func = saved_func
        self.current_block = saved_block
        self.env_stack = saved_env
        self.ptr_vars = saved_ptrs
        self.aliases = saved_aliases
        self.temp_counter = saved_tc
        self._if_seq = saved_seq

    def _fill_default_args(self, func_name, args, self_slots):
        params = self.func_params.get(func_name)

        if params is not None:
            if self_slots:
                params = params[1:]

            for _, _, default in params[len(args):]:
                if default is None:
                    raise Exception(
                        f"Missing argument for call to '{func_name}'"
                    )

                args.append(self.emit_expr(default))

        return args

    def _emit_method_call(self, expr):
        obj_val = self.emit_expr(expr.obj)
        owner = expr.owner or expr.obj_type
        obj_type = expr.obj_type

        if owner != obj_type:
            owner_fields = self.module.types.get(owner, {})

            parts = [owner]

            for fname in owner_fields:
                fv = self.new_temp(owner_fields[fname])

                self.current_block.add_instr(
                    IRInstr(
                        "field",
                        [obj_val, fname],
                        result=fv,
                    )
                )

                parts.append(fname)
                parts.append(fv)

            self_val = self.new_temp(owner)

            self.current_block.add_instr(
                IRInstr(
                    "struct_init",
                    parts,
                    result=self_val,
                )
            )
        else:
            self_val = obj_val

        args = [
            self.emit_expr(a)
            for a in expr.args
        ]

        args = self._fill_default_args(
            expr.func_name,
            args,
            self_slots=True,
        )

        ret_type = self.func_returns.get(
            expr.func_name,
            expr.ret_type or "Unknown",
        )

        v = self.new_temp(ret_type)

        self.current_block.add_instr(
            IRInstr(
                "call",
                [expr.func_name] + [self_val] + args,
                result=v,
            )
        )

        return v

    def _emit_class_init(self, expr):
        init_name = expr.init_name

        args = [
            self.emit_expr(a)
            for a in expr.args
        ]

        if init_name is None:
            v = self.new_temp(expr.class_name)

            self.current_block.add_instr(
                IRInstr(
                    "undef",
                    [],
                    result=v,
                )
            )

            return v

        self_val = self.new_temp(expr.class_name)

        self.current_block.add_instr(
            IRInstr(
                "undef",
                [],
                result=self_val,
            )
        )

        args = self._fill_default_args(
            init_name,
            args,
            self_slots=True,
        )

        ret_type = self.func_returns.get(
            init_name,
            expr.class_name,
        )

        v = self.new_temp(ret_type)

        self.current_block.add_instr(
            IRInstr(
                "call",
                [init_name] + [self_val] + args,
                result=v,
            )
        )

        return v

    def emit_expr(self, expr):
        if isinstance(expr, LiteralExpr):
            t = expr.type
            val = expr.value.value

            v = self.new_temp(t)

            self.current_block.add_instr(
                IRInstr(
                    "const",
                    [val],
                    result=v,
                )
            )

            return v

        if isinstance(expr, CastExpr):
            src = self.emit_expr(
                expr.expr
            )

            v = self.new_temp(
                expr.target_type
            )

            self.current_block.add_instr(
                IRInstr(
                    "cast",
                    [
                        src,
                        expr.target_type,
                    ],
                    result=v,
                )
            )

            return v

        if isinstance(expr, InterpolatedStringExpr):
            return self.emit_interpolated_string(expr)

        if isinstance(expr, VarExpr):
            return self.get_var(
                expr.name
            )

        if isinstance(expr, RefExpr):
            src = self.emit_expr(
                expr.inner
            )

            v = self.new_temp(
                src.type
            )

            self.current_block.add_instr(
                IRInstr(
                    "ref_copy",
                    [src],
                    result=v,
                )
            )

            return v

        if isinstance(expr, UnaryExpr):
            operand = self.emit_expr(
                expr.expr
            )

            op_map = {
                "-": "neg",
                "+": "pos",
                "not": "not",
            }

            op = op_map.get(
                expr.op,
                expr.op,
            )

            v = self.new_temp(
                operand.type
            )

            self.current_block.add_instr(
                IRInstr(
                    op,
                    [operand],
                    result=v,
                )
            )

            return v

        if isinstance(expr, BinaryExpr):
            left = self.emit_expr(
                expr.left
            )

            right = self.emit_expr(
                expr.right
            )

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

            op = op_map.get(
                expr.op,
                expr.op,
            )

            vtype = (
                "Bool"
                if op.startswith("cmp_")
                else left.type
            )

            v = self.new_temp(vtype)

            self.current_block.add_instr(
                IRInstr(
                    op,
                    [left, right],
                    result=v,
                )
            )

            return v

        if isinstance(expr, CallExpr):
            args = [
                self.emit_expr(a)
                for a in expr.args
            ]

            params = self.func_params.get(
                expr.func_name
            )

            if params is not None:
                for _, _, default in params[
                    len(expr.args):
                ]:
                    if default is None:
                        raise Exception(
                            f"Missing argument for "
                            f"call to "
                            f"'{expr.func_name}'"
                        )

                    args.append(
                        self.emit_expr(default)
                    )

            ret_type = self.func_returns.get(
                expr.func_name
            )

            if ret_type is None:
                ret_type = BUILTIN_SIGS.get(
                    expr.func_name,
                    ("", "Unknown"),
                )[1]

            v = self.new_temp(
                ret_type
            )

            self.current_block.add_instr(
                IRInstr(
                    "call",
                    [expr.func_name] + args,
                    result=v,
                )
            )

            return v

        if isinstance(expr, StructInitExpr):
            args = [expr.struct_name]

            for fname, fexpr in (
                expr.fields.items()
            ):
                args.append(fname)
                args.append(
                    self.emit_expr(fexpr)
                )

            v = self.new_temp(
                expr.struct_name
            )

            self.current_block.add_instr(
                IRInstr(
                    "struct_init",
                    args,
                    result=v,
                )
            )

            return v

        if isinstance(expr, MethodCallExpr):
            return self._emit_method_call(expr)

        if isinstance(expr, ClassInitExpr):
            return self._emit_class_init(expr)

        if isinstance(expr, ListLiteralExpr):
            elems = [
                self.emit_expr(e)
                for e in expr.elements
            ]

            if (
                expr.type is not None
                and expr.type.startswith("List[")
            ):
                elem_type = expr.type[5:-1]

            elif elems:
                elem_type = elems[0].type

            else:
                elem_type = "Unknown"

            v = self.new_temp(
                f"List[{elem_type}]"
            )

            self.current_block.add_instr(
                IRInstr(
                    "list_init",
                    [elem_type] + elems,
                    result=v,
                )
            )

            return v

        if isinstance(expr, IndexExpr):
            obj = self.emit_expr(
                expr.obj
            )

            idx = self.emit_expr(
                expr.index
            )

            obj_type = obj.type

            if (
                isinstance(obj_type, str)
                and obj_type.startswith("List[")
            ):
                elem_type = obj_type[5:-1]
            else:
                elem_type = "Unknown"

            v = self.new_temp(
                elem_type
            )

            self.current_block.add_instr(
                IRInstr(
                    "list_get",
                    [obj, idx],
                    result=v,
                )
            )

            return v

        if isinstance(expr, FieldAccessExpr):
            base = self.emit_expr(
                expr.obj
            )

            ftype = self.module.types.get(
                base.type,
                {},
            ).get(
                expr.field,
                "Unknown",
            )

            v = self.new_temp(
                ftype
            )

            self.current_block.add_instr(
                IRInstr(
                    "field",
                    [
                        base,
                        expr.field,
                    ],
                    result=v,
                )
            )

            return v

        raise Exception(
            f"Unknown expr type: "
            f"{type(expr).__name__}"
        )