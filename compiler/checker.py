from .nodes import RefExpr
class UnreachableChecker:


    def __init__(self):
        self.errors = []

    def error(self, msg):
        print("AST Error:", msg)
        raise SystemExit(1)

    def check(self, ast):
        for node in ast:
            if type(node).__name__ == "FunctionDef":
                self.check_function(node)

    def check_function(self, func):
        blocks = self.build_cfg(func)

        reachable = self.compute_reachable(blocks)

        for b in blocks:
            if b["name"] not in reachable:
                self.error(f"Unreachable block '{b['name']}' in function '{func.name}'")

        for b in blocks:
            if b["name"] not in reachable:
                continue
            for stmt, reachable_flag in b["stmts"]:
                if not reachable_flag:
                    self.error(f"Unreachable statement in function '{func.name}'")

    def build_cfg(self, func):
        blocks = []
        entry = self.new_block("entry")
        blocks.append(entry)

        current = entry

        for stmt in func.body:
            current = self.process_stmt(stmt, current, blocks)

            if current is None:
                idx = func.body.index(stmt)
                for s in func.body[idx+1:]:
                    self.error(f"Unreachable statement in function '{func.name}'")
                break

        return blocks

    def new_block(self, name):
        return {"name": name, "stmts": [], "succ": []}

    def process_stmt(self, stmt, current_block, blocks):
        t = type(stmt).__name__

        if t == "ReturnStmt":
            current_block["stmts"].append((stmt, True))
            return None

        if t == "IfStmt":
            current_block["stmts"].append((stmt, True))

            then_block = self.new_block(f"then_{len(blocks)}")
            blocks.append(then_block)
            current_block["succ"].append(then_block["name"])

            for s in stmt.body:
                tb = self.process_stmt(s, then_block, blocks)
                if tb is None:
                    then_block = None
                    break
                else:
                    then_block = tb

            prev_blocks = []
            if then_block is not None:
                prev_blocks.append(then_block)

            for cond, body in stmt.elif_blocks:
                elif_block = self.new_block(f"elif_{len(blocks)}")
                blocks.append(elif_block)
                current_block["succ"].append(elif_block["name"])

                cb = elif_block
                for s in body:
                    nb = self.process_stmt(s, cb, blocks)
                    if nb is None:
                        cb = None
                        break
                    else:
                        cb = nb

                if cb is not None:
                    prev_blocks.append(cb)

            if stmt.else_body:
                else_block = self.new_block(f"else_{len(blocks)}")
                blocks.append(else_block)
                current_block["succ"].append(else_block["name"])

                cb = else_block
                for s in stmt.else_body:
                    nb = self.process_stmt(s, cb, blocks)
                    if nb is None:
                        cb = None
                        break
                    else:
                        cb = nb

                if cb is not None:
                    prev_blocks.append(cb)

            merge_block = self.new_block(f"merge_{len(blocks)}")
            blocks.append(merge_block)

            for b in prev_blocks:
                b["succ"].append(merge_block["name"])

            if not stmt.else_body:
                current_block["succ"].append(merge_block["name"])

            return merge_block

        current_block["stmts"].append((stmt, True))
        return current_block

    def compute_reachable(self, blocks):
        block_map = {b["name"]: b for b in blocks}
        reachable = set()
        work = ["entry"]

        while work:
            bname = work.pop()
            if bname in reachable:
                continue
            reachable.add(bname)
            for succ in block_map[bname]["succ"]:
                work.append(succ)

        return reachable

class ShadowChecker:
    def __init__(self):
        self.errors = []

    def error(self, msg):
        print("AST Error:", msg)
        raise SystemExit(1)

    def check(self, ast):
        self.visit_block(ast, scope={})

    def visit_block(self, stmts, scope):
        local = scope.copy()

        for stmt in stmts:
            t = type(stmt).__name__

            if t == "VarDecl":
                if stmt.name in local:
                    self.error(f"Variable shadowing detected: '{stmt.name}' redeclared")
                local[stmt.name] = True

            elif t == "IfStmt":
                self.visit_block(stmt.body, local.copy())
                for _, body in stmt.elif_blocks:
                    self.visit_block(body, local.copy())
                if stmt.else_body:
                    self.visit_block(stmt.else_body, local.copy())

            elif t == "FunctionDef":
                func_scope = {pname: True for pname, _ in stmt.params}
                self.visit_block(stmt.body, func_scope)

class DuplicateChecker:
    def __init__(self):
        self.global_functions = {}
        self.global_vars = {}

    def error(self, msg):
        print("AST Error:", msg)
        raise SystemExit(1)

    def check(self, ast):
        for node in ast:
            self.visit(node, scope=self.global_vars)

    def visit(self, node, scope):
        t = type(node).__name__

        if t == "FunctionDef":
            return self.visit_function(node)

        if t == "VarDecl":
            return self.visit_vardecl(node, scope)

        if t == "Assign":
            return self.visit_assign(node, scope)

        if t == "IfStmt":
            return self.visit_if(node, scope)

        if t == "ReturnStmt":
            return None

        return None

    def visit_function(self, func):
        if func.name in self.global_functions:
            self.error(f"Duplicate function '{func.name}'")

        self.global_functions[func.name] = func

        func_scope = {}

        for pname, ptype in func.params:
            func_scope[pname] = True

        for stmt in func.body:
            self.visit(stmt, func_scope)

    def visit_vardecl(self, var, scope):
        if var.name in scope:
            self.error(f"Duplicate variable '{var.name}' in same scope")
        scope[var.name] = True

    def visit_assign(self, node, scope):
        if node.name not in scope:
            self.error(f"Variable '{node.name}' assigned before declaration")

    def visit_if(self, node, parent_scope):
        if_scope = parent_scope.copy()
        elif_scopes = []
        else_scope = parent_scope.copy() if node.else_body else None

        for stmt in node.body:
            self.visit(stmt, if_scope)

        for cond, body in node.elif_blocks:
            s = parent_scope.copy()
            for stmt in body:
                self.visit(stmt, s)
            elif_scopes.append(s)

        if node.else_body:
            for stmt in node.else_body:
                self.visit(stmt, else_scope)

        all_scopes = [if_scope] + elif_scopes + ([else_scope] if else_scope else [])

        merged_vars = set().union(*all_scopes)

        common_vars = set.intersection(*map(set, all_scopes))

        partial_vars = merged_vars - common_vars

        for v in partial_vars:
            self.error(
                f"Variable '{v}' declared only in some branches of if/elif/else"
            )

        for v in common_vars:
            parent_scope[v] = True
class UnusedVariableChecker:
    def __init__(self):
        self.warnings = []

    def warn(self, msg):
        print("AST Warning:", msg)

    def check(self, ast):
        global_decl = set()
        global_used = set()

        for node in ast:
            t = type(node).__name__

            if t == "FunctionDef":
                self.check_function(node)
            elif t == "VarDecl":
                global_decl.add(node.name)
                if node.expr:
                    self.visit_expr(node.expr, global_used)
            elif t == "Assign":
                self.visit_expr(node.expr, global_used)
                global_decl.add(node.name)
                global_used.add(node.name)

        for var in global_decl:
            if var not in global_used:
                self.warn(f"Variable '{var}' declared but never used")

    def check_function(self, func):
        declared = set(pname for pname, _ in func.params)
        used = set()

        for stmt in func.body:
            self.visit_stmt(stmt, declared, used)

        for p in func.params:
            pname = p[0]
            if pname not in used:
                self.warn(f"Parameter '{pname}' in function '{func.name}' is never used")

        local_decl = declared - set(pname for pname, _ in func.params)
        for var in local_decl:
            if var not in used:
                self.warn(f"Variable '{var}' in function '{func.name}' declared but never used")

    def visit_stmt(self, stmt, declared, used):
        t = type(stmt).__name__

        if t == "VarDecl":
            declared.add(stmt.name)
            if stmt.expr:
                self.visit_expr(stmt.expr, used)

        elif t == "Assign":
            self.visit_expr(stmt.expr, used)
            declared.add(stmt.name)
            used.add(stmt.name)

        elif t == "ExprStmt":
            self.visit_expr(stmt.expr, used)

        elif t == "ReturnStmt":
            if stmt.value:
                self.visit_expr(stmt.value, used)

        elif t == "IfStmt":
            self.visit_expr(stmt.condition, used)
            for s in stmt.body:
                self.visit_stmt(s, declared, used)
            for cond, body in stmt.elif_blocks:
                self.visit_expr(cond, used)
                for s in body:
                    self.visit_stmt(s, declared, used)
            if stmt.else_body:
                for s in stmt.else_body:
                    self.visit_stmt(s, declared, used)

    def visit_expr(self, expr, used):
        t = type(expr).__name__

        if t == "VarExpr":
            used.add(expr.name)
        elif t == "BinaryExpr":
            self.visit_expr(expr.left, used)
            self.visit_expr(expr.right, used)
        elif t == "UnaryExpr":
            self.visit_expr(expr.expr, used)
        elif t == "CallExpr":
            for a in expr.args:
                self.visit_expr(a, used)
        elif t == "StructInitExpr":
            for _, e in expr.fields.items():
                self.visit_expr(e, used)
        elif t == "FieldAccessExpr":
            self.visit_expr(expr.obj, used)
        elif t == "RefExpr":
            self.visit_expr(expr.inner, used)

class DeadStoreChecker:
    def __init__(self):
        self.warnings = []

    def warn(self, msg):
        print("AST Warning:", msg)

    def check(self, ast):
        for node in ast:
            if type(node).__name__ == "FunctionDef":
                self.check_function(node)

    def check_function(self, func):
        writes = {}
        reads = set()

        self.walk_block(func.body, writes, reads)

        for var, write_list in writes.items():
            if var not in reads:
                for stmt, line in write_list:
                    self.warn(f"Dead store: variable '{var}' assigned but never used")

    def walk_block(self, stmts, writes, reads):
        for stmt in stmts:
            t = type(stmt).__name__

            if t == "VarDecl":
                if stmt.expr:
                    self.walk_expr(stmt.expr, reads)
                writes.setdefault(stmt.name, []).append((stmt, None))

            elif t == "Assign":
                self.walk_expr(stmt.expr, reads)
                reads.add(stmt.name)

                writes.setdefault(stmt.name, []).append((stmt, None))

            elif t == "ReturnStmt":
                if stmt.value:
                    self.walk_expr(stmt.value, reads)

            elif t == "IfStmt":
                self.walk_expr(stmt.condition, reads)
                self.walk_block(stmt.body, writes, reads)
                for cond, body in stmt.elif_blocks:
                    self.walk_expr(cond, reads)
                    self.walk_block(body, writes, reads)
                if stmt.else_body:
                    self.walk_block(stmt.else_body, writes, reads)

    def walk_expr(self, expr, reads):
        t = type(expr).__name__

        if t == "VarExpr":
            reads.add(expr.name)

        elif t == "BinaryExpr":
            self.walk_expr(expr.left, reads)
            self.walk_expr(expr.right, reads)

        elif t == "UnaryExpr":
            self.walk_expr(expr.expr, reads)

        elif t == "CallExpr":
            for a in expr.args:
                self.walk_expr(a, reads)

        elif t == "StructInitExpr":
            for _, e in expr.fields.items():
                self.walk_expr(e, reads)

        elif t == "FieldAccessExpr":
            self.walk_expr(expr.obj, reads)

        elif t == "RefExpr":
            self.walk_expr(expr.inner, reads)

class MissingReturnChecker:
    def __init__(self):
        pass

    def error(self, msg):
        print("AST Error:", msg)
        raise SystemExit(1)

    def check(self, ast):
        for node in ast:
            if type(node).__name__ == "FunctionDef":
                self.check_function(node)

    def check_function(self, func):
        if not self.block_returns(func.body):
            self.error(f"Function '{func.name}' does not return on all paths")

    def block_returns(self, stmts):


        for stmt in stmts:
            t = type(stmt).__name__

            if t == "ReturnStmt":
                return True

            if t == "IfStmt":
                then_ret = self.block_returns(stmt.body)

                elif_rets = []
                for cond, body in stmt.elif_blocks:
                    elif_rets.append(self.block_returns(body))

                if stmt.else_body:
                    else_ret = self.block_returns(stmt.else_body)
                else:
                    else_ret = False

                if then_ret and all(elif_rets) and else_ret:
                    return True

        return False
class AliasChecker:
    def __init__(self):
        self.aliases = {}

    def error(self, msg):
        print("AST Error:", msg)
        raise SystemExit(1)

    def check(self, ast):
        for node in ast:
            if type(node).__name__ == "FunctionDef":
                self.check_function(node)

    def check_function(self, func):
        self.aliases = {}
        declared = set(pname for pname, _ in func.params)

        for stmt in func.body:
            self.visit_stmt(stmt, declared)

        self.check_cycles()

    def visit_stmt(self, stmt, declared):
        t = type(stmt).__name__

        if t == "VarDecl":
            declared.add(stmt.name)
            if isinstance(stmt.expr, RefExpr):
                self.check_ref_decl(stmt, declared)

        elif t == "ExprStmt":
            pass

        elif t == "IfStmt":
            for s in stmt.body:
                self.visit_stmt(s, declared)
            for cond, body in stmt.elif_blocks:
                for s in body:
                    self.visit_stmt(s, declared)
            if stmt.else_body:
                for s in stmt.else_body:
                    self.visit_stmt(s, declared)

    def check_ref_decl(self, var_decl, declared):
        name = var_decl.name
        inner = var_decl.expr.inner

        if type(inner).__name__ != "VarExpr":
            self.error(f"Reference declaration '{name}' must refer to a variable")

        target = inner.name

        if target not in declared:
            self.error(f"Reference declaration '{name}' refers to unknown variable '{target}'")

        if name in self.aliases:
            self.error(f"Variable '{name}' already has an alias")

        if name == target:
            self.error(f"Variable '{name}' cannot be a reference to itself")

        self.aliases[name] = target

    def check_cycles(self):
        visited = set()
        stack = set()

        def dfs(v):
            if v in stack:
                self.error(f"Alias cycle detected involving '{v}'")
            if v in visited:
                return
            visited.add(v)
            stack.add(v)
            if v in self.aliases:
                dfs(self.aliases[v])
            stack.remove(v)

        for v in list(self.aliases.keys()):
            dfs(v)
class CombinedChecker:
    def __init__(self):
        self.unreachable_checker = UnreachableChecker()
        self.shadow_checker = ShadowChecker()
        self.duplicate_checker = DuplicateChecker()
        self.unused_checker = UnusedVariableChecker()
        self.dead_store_checker = DeadStoreChecker()
        self.missing_return_checker = MissingReturnChecker()
        self.alias_checker = AliasChecker()

    def run_all(self, ast):
        self.duplicate_checker.check(ast)
        self.shadow_checker.check(ast)
        self.unreachable_checker.check(ast)
        self.missing_return_checker.check(ast)
        self.alias_checker.check(ast)
        self.unused_checker.check(ast)
        self.dead_store_checker.check(ast)
