from collections import defaultdict, deque

from .builtins import ALL_INT_TYPES, FLOAT_TYPES
from .to_high_ir import IRBlock, IRInstr, IRPhi, SSAValue


class IROptimizer:


    def __init__(self, inline_threshold=30, unroll_factor=4, debug_mode=False):
        self.module = None
        self.func = None
        self.inline_threshold = inline_threshold
        self.unroll_factor = unroll_factor
        self._temp_counter = 0
        self.debug_mode = debug_mode


    def optimize(self, module):
        self.module = module
        for func in list(module.funcs):
            self._optimize_function(func)
        self._inline_module(module)
        for func in list(module.funcs):
            self._optimize_function(func)
        return module

    def _optimize_function(self, func):
        self.func = func
        self._temp_counter = 0
        iteration = 0
        changed = True
        while changed and iteration < 25:
            changed = False
            func.build_cfg()
            changed |= self._sccp()
            changed |= self._constant_folding()
            if not self.debug_mode:
                changed |= self._strength_reduction()
                changed |= self._reassociation()
            changed |= self._algebraic_simplification()
            changed |= self._peephole()
            changed |= self._constant_propagation()
            changed |= self._copy_propagation()
            changed |= self._gvn()
            changed |= self._cse()
            changed |= self._sroa()
            changed |= self._field_forwarding()
            changed |= self._simplify_phi()
            changed |= self._if_conversion()
            changed |= self._tail_call_opt()
            changed |= self._branch_simplification()
            changed |= self._jump_threading()
            changed |= self._dead_code_elimination()
            changed |= self._remove_empty_blocks()
            changed |= self._merge_blocks()
            changed |= self._remove_unreachable_blocks()
            changed |= self._licm()
            changed |= self._loop_unrolling()
            iteration += 1

    def _new_temp(self, type_):
        name = f"%opt{self._temp_counter}"
        self._temp_counter += 1
        return SSAValue(name, type_)


    def _is_pure(self, op):
        return op in {
            "const", "neg", "pos", "not",
            "cmp_lt", "cmp_gt", "cmp_le", "cmp_ge", "cmp_eq", "cmp_ne",
            "add", "sub", "mul", "div", "floordiv", "pow", "mod",
            "field", "ref_copy", "undef", "select",
        }

    def _is_associative(self, op):
        return op in {"add", "mul", "bit_and", "bit_or", "bit_xor"}

    def _is_commutative(self, op):
        return op in {"add", "mul", "cmp_eq", "cmp_ne", "bit_and", "bit_or", "bit_xor"}

    def _get_const_value(self, val):
        if isinstance(val, SSAValue) and val.def_instr and val.def_instr.op == "const":
            return val.def_instr.args[0]
        return None

    def _to_number(self, val):
        if isinstance(val, bool):
            return val
        if isinstance(val, (int, float)):
            return val
        if isinstance(val, str):
            try:
                if '.' in val and not val.startswith('"'):
                    return float(val)
                return int(val)
            except ValueError:
                pass
        return None

    def _is_zero(self, val):
        v = self._get_const_value(val)
        n = self._to_number(v)
        return n == 0 if n is not None else False

    def _int_bounds(self, rtype):
        if rtype in ALL_INT_TYPES:
            width = {
                "Int8": 8, "Int16": 16, "Int32": 32, "Int64": 64, "Int256": 256,
                "UInt8": 8, "UInt16": 16, "UInt32": 32, "UInt64": 64, "UInt256": 256,
            }[rtype]
            if rtype.startswith("UInt"):
                return 0, (1 << width) - 1
            return -(1 << (width - 1)), (1 << (width - 1)) - 1
        return None, None

    def _fits(self, value, rtype):
        lo, hi = self._int_bounds(rtype)
        if lo is None:
            return True
        return lo <= value <= hi

    def _fold_number(self, op, ln, rn, rtype):
        if rtype in ALL_INT_TYPES:
            if op == "div":
                if rn == 0:
                    return None
                q = abs(ln) // abs(rn)
                res = -q if (ln < 0) != (rn < 0) else q
                if self.debug_mode and not self._fits(res, rtype):
                    return None
                return res
            if op == "floordiv":
                if rn == 0:
                    return None
                res = ln // rn
                if self.debug_mode and not self._fits(res, rtype):
                    return None
                return res
            if op == "mod":
                if rn == 0:
                    return None
                q = abs(ln) // abs(rn)
                q = -q if (ln < 0) != (rn < 0) else q
                return ln - q * rn
            if op == "add":
                res = ln + rn
                if self.debug_mode and not self._fits(res, rtype):
                    return None
                return res
            if op == "sub":
                res = ln - rn
                if self.debug_mode and not self._fits(res, rtype):
                    return None
                return res
            if op == "mul":
                res = ln * rn
                if self.debug_mode and not self._fits(res, rtype):
                    return None
                return res
            if op == "pow":
                if isinstance(ln, bool) or isinstance(rn, bool) or rn < 0:
                    return None
                res = ln ** rn
                if self.debug_mode and not self._fits(res, rtype):
                    return None
                return res
            return None
        if op == "add":
            return ln + rn
        if op == "sub":
            return ln - rn
        if op == "mul":
            return ln * rn
        if op == "div":
            if rn == 0:
                return None
            return ln / rn
        if op == "floordiv":
            if rn == 0:
                return None
            return ln // rn
        if op == "mod":
            if rn == 0:
                return None
            return ln % rn
        if op == "pow":
            try:
                return ln ** rn
            except (ZeroDivisionError, ValueError, OverflowError):
                return None
        return None

    def _is_one(self, val):
        v = self._get_const_value(val)
        n = self._to_number(v)
        return n == 1 if n is not None else False

    def _is_true(self, val):
        v = self._get_const_value(val)
        return v is True

    def _is_false(self, val):
        v = self._get_const_value(val)
        return v is False

    def _replace_value(self, old_val, new_val):
        if old_val is new_val:
            return
        for user in list(old_val.users):
            if isinstance(user, IRPhi):
                user.incoming = [
                    (blk, new_val if v is old_val else v) for blk, v in user.incoming
                ]
                user.args = [new_val if a is old_val else a for a in user.args]
            elif isinstance(user, IRInstr):
                user.args = [new_val if a is old_val else a for a in user.args]
            if isinstance(new_val, SSAValue):
                new_val.users.append(user)
        old_val.users.clear()

    def _remove_instr(self, block, idx):
        instr = block.instructions.pop(idx)
        if isinstance(instr.result, SSAValue):
            for a in instr.args:
                if isinstance(a, SSAValue) and instr in a.users:
                    a.users.remove(instr)
            instr.result.def_instr = None
        return instr

    def _make_const_instr(self, value, type_, block, insert_idx):
        v = self._new_temp(type_)
        instr = IRInstr("const", [value], result=v)
        block.instructions.insert(insert_idx, instr)
        return v

    def _replace_terminator_target(self, block, old_label, new_label):
        if not block.terminator:
            return
        t = block.terminator
        if t.op == "br":
            if t.args[0] == old_label:
                t.args[0] = new_label
        elif t.op == "cond_br":
            if t.args[1] == old_label:
                t.args[1] = new_label
            if t.args[2] == old_label:
                t.args[2] = new_label

    def _count_instructions(self, func):
        return sum(len(b.instructions) for b in func.blocks)


    def _sccp(self):
        if not self.func.blocks:
            return False
        changed = False
        entry = self.func.blocks[0].label

        val_map = {}
        def get_lat(name):
            return val_map.get(name, None)
        def meet_lat(name, v):
            old = val_map.get(name)
            if old is None:
                if v is not None:
                    val_map[name] = v
                    return True
                return False
            if isinstance(old, set):
                return False
            if old != v:
                val_map[name] = set()
                return True
            return False

        edge_exec = set()
        edge_work = deque()
        edge_work.append((None, entry))
        ssa_work = deque()

        def add_edge(fr, to):
            if (fr, to) not in edge_exec:
                edge_exec.add((fr, to))
                edge_work.append((fr, to))

        def add_ssa(v):
            if isinstance(v, SSAValue):
                ssa_work.append(v)

        def eval_instr(instr):
            if isinstance(instr, IRPhi):
                block_label = None
                for b in self.func.blocks:
                    if instr in b.instructions:
                        block_label = b.label
                        break
                active = []
                for blk, v in instr.incoming:
                    if (blk, block_label) in edge_exec:
                        active.append(v)
                if not active:
                    return None
                first = get_lat(active[0].name)
                if isinstance(first, set):
                    return set()
                for a in active[1:]:
                    lat = get_lat(a.name)
                    if isinstance(lat, set) or lat != first:
                        return set()
                return first

            op = instr.op
            if op == "const":
                return instr.args[0]
            if op == "undef":
                return set()
            if op in ("neg", "pos", "not"):
                v = get_lat(instr.args[0].name) if isinstance(instr.args[0], SSAValue) else instr.args[0]
                if isinstance(v, set):
                    return set()
                if v is None:
                    return None
                try:
                    n = self._to_number(v)
                    if n is None:
                        return set()
                    if op == "neg":
                        res = -n
                        if self.debug_mode and not self._fits(res, instr.result.type):
                            return set()
                        return res
                    if op == "pos": return n
                    if op == "not": return not n
                except (TypeError, ValueError):
                    return set()
            if op in ("add", "sub", "mul", "div", "floordiv", "mod", "pow",
                      "cmp_lt", "cmp_gt", "cmp_le", "cmp_ge", "cmp_eq", "cmp_ne"):
                l = get_lat(instr.args[0].name) if isinstance(instr.args[0], SSAValue) else instr.args[0]
                r = get_lat(instr.args[1].name) if isinstance(instr.args[1], SSAValue) else instr.args[1]
                if isinstance(l, set) or isinstance(r, set):
                    return set()
                if l is None or r is None:
                    return None
                try:
                    ln = self._to_number(l)
                    rn = self._to_number(r)
                    if ln is None or rn is None:
                        return set()
                    rtype = instr.result.type
                    if op in ("add", "sub", "mul", "div", "floordiv", "mod", "pow"):
                        res = self._fold_number(op, ln, rn, rtype)
                        if res is None:
                            return set()
                        return res
                    if op == "cmp_lt": return ln < rn
                    if op == "cmp_gt": return ln > rn
                    if op == "cmp_le": return ln <= rn
                    if op == "cmp_ge": return ln >= rn
                    if op == "cmp_eq": return ln == rn
                    if op == "cmp_ne": return ln != rn
                except (TypeError, ValueError):
                    return set()
            if op == "select":
                c = get_lat(instr.args[0].name) if isinstance(instr.args[0], SSAValue) else instr.args[0]
                if isinstance(c, set):
                    return set()
                if c is None:
                    return None
                if c is True:
                    return get_lat(instr.args[1].name) if isinstance(instr.args[1], SSAValue) else instr.args[1]
                if c is False:
                    return get_lat(instr.args[2].name) if isinstance(instr.args[2], SSAValue) else instr.args[2]
            return set()

        while edge_work or ssa_work:
            while edge_work:
                _fr, to = edge_work.popleft()
                block = self.func.block_map[to]
                for instr in block.instructions:
                    if isinstance(instr, (IRInstr, IRPhi)) and isinstance(instr.result, SSAValue):
                        res = eval_instr(instr)
                        if meet_lat(instr.result.name, res):
                            add_ssa(instr.result)
                if block.terminator:
                    if block.terminator.op == "br":
                        add_edge(to, block.terminator.args[0])
                    elif block.terminator.op == "cond_br":
                        cond = block.terminator.args[0]
                        c = get_lat(cond.name) if isinstance(cond, SSAValue) else cond
                        if isinstance(c, set) or c is None:
                            add_edge(to, block.terminator.args[1])
                            add_edge(to, block.terminator.args[2])
                        elif c:
                            add_edge(to, block.terminator.args[1])
                        else:
                            add_edge(to, block.terminator.args[2])

            while ssa_work:
                val = ssa_work.popleft()
                for user in val.users:
                    if isinstance(user, (IRInstr, IRPhi)) and isinstance(user.result, SSAValue):
                        res = eval_instr(user)
                        if meet_lat(user.result.name, res):
                            add_ssa(user.result)

        for block in self.func.blocks:
            for instr in list(block.instructions):
                if isinstance(instr.result, SSAValue):
                    lat = get_lat(instr.result.name)
                    if lat is not None and not isinstance(lat, set):
                        if instr.op != "const":
                            old_args = instr.args
                            instr.op = "const"
                            instr.args = [lat]
                            for a in old_args:
                                if isinstance(a, SSAValue) and instr in a.users:
                                    a.users.remove(instr)
                            if isinstance(instr, IRPhi):
                                instr.incoming = []
                            changed = True

        return changed


    def _constant_folding(self):
        changed = False
        for block in self.func.blocks:
            i = 0
            while i < len(block.instructions):
                instr = block.instructions[i]
                if instr.op in ("add", "sub", "mul", "div", "floordiv", "mod", "pow",
                                "cmp_lt", "cmp_gt", "cmp_le", "cmp_ge", "cmp_eq", "cmp_ne"):
                    l = self._get_const_value(instr.args[0])
                    r = self._get_const_value(instr.args[1])
                    if l is not None and r is not None:
                            ln = self._to_number(l)
                            rn = self._to_number(r)
                            if ln is not None and rn is not None:
                                rtype = instr.result.type
                                if instr.op in ("add", "sub", "mul", "div", "floordiv", "mod", "pow"):
                                    res = self._fold_number(instr.op, ln, rn, rtype)
                                    if res is None:
                                        i += 1
                                        continue
                                elif instr.op == "cmp_lt": res = ln < rn
                                elif instr.op == "cmp_gt": res = ln > rn
                                elif instr.op == "cmp_le": res = ln <= rn
                                elif instr.op == "cmp_ge": res = ln >= rn
                                elif instr.op == "cmp_eq": res = ln == rn
                                elif instr.op == "cmp_ne": res = ln != rn
                                else:
                                    i += 1
                                    continue
                                old_args = instr.args
                                instr.op = "const"
                                instr.args = [res]
                                for a in old_args:
                                    if isinstance(a, SSAValue) and instr in a.users:
                                        a.users.remove(instr)
                                changed = True

                elif instr.op in ("neg", "pos", "not"):
                    v = self._get_const_value(instr.args[0])
                    if v is not None:
                        n = self._to_number(v)
                        if n is not None:
                            if instr.op == "neg":
                                res = -n
                                if self.debug_mode and not self._fits(res, instr.result.type):
                                    i += 1
                                    continue
                            elif instr.op == "pos": res = n
                            elif instr.op == "not": res = not n
                            old_args = instr.args
                            instr.op = "const"
                            instr.args = [res]
                            for a in old_args:
                                if isinstance(a, SSAValue) and instr in a.users:
                                    a.users.remove(instr)
                            changed = True

                i += 1
        return changed


    def _strength_reduction(self):
        changed = False
        for block in self.func.blocks:
            i = 0
            while i < len(block.instructions):
                instr = block.instructions[i]
                if instr.op == "mul":
                    left, right = instr.args
                    if self._is_const_power_of_two(right):
                        p = self._const_log2(right)
                        instr.op = "shl"
                        instr.args = [left, p]
                        changed = True
                    elif self._is_const_power_of_two(left):
                        p = self._const_log2(left)
                        instr.op = "shl"
                        instr.args = [right, p]
                        changed = True
                elif instr.op == "pow":
                    left, right = instr.args
                    r = self._get_const_value(right)
                    if r == 2:
                        instr.op = "mul"
                        instr.args = [left, left]
                        changed = True
                    elif r == 3:
                        tmp = self._new_temp(left.type)
                        mul1 = IRInstr("mul", [left, left], result=tmp)
                        block.instructions.insert(i, mul1)
                        instr.op = "mul"
                        instr.args = [left, tmp]
                        changed = True
                        i += 1
                elif instr.op == "div":
                    left, right = instr.args
                    r = self._get_const_value(right)
                    if r is not None:
                        n = self._to_number(r)
                        if n is not None and n != 0:
                            if isinstance(n, float) or (isinstance(n, int) and 'float' in str(left.type).lower()):
                                half = self._make_const_instr(1.0 / n, left.type, block, i)
                                instr.op = "mul"
                                instr.args = [left, half]
                                changed = True
                i += 1
        return changed

    def _is_const_power_of_two(self, val):
        v = self._get_const_value(val)
        n = self._to_number(v)
        if n is None or not isinstance(n, int) or n <= 0:
            return False
        return (n & (n - 1)) == 0

    def _const_log2(self, val):
        v = self._get_const_value(val)
        n = self._to_number(v)
        return n.bit_length() - 1


    def _algebraic_simplification(self):
        changed = False
        for block in self.func.blocks:
            i = 0
            while i < len(block.instructions):
                instr = block.instructions[i]
                op = instr.op

                if op == "add":
                    left, right = instr.args
                    if self._is_zero(right):
                        self._replace_value(instr.result, left)
                        self._remove_instr(block, i)
                        changed = True
                        continue
                    if self._is_zero(left):
                        self._replace_value(instr.result, right)
                        self._remove_instr(block, i)
                        changed = True
                        continue

                elif op == "sub":
                    left, right = instr.args
                    if self._is_zero(right):
                        self._replace_value(instr.result, left)
                        self._remove_instr(block, i)
                        changed = True
                        continue
                    if left is right:
                        old_args = instr.args
                        instr.op = "const"
                        instr.args = [0]
                        for a in old_args:
                            if isinstance(a, SSAValue) and instr in a.users:
                                a.users.remove(instr)
                        changed = True
                        continue

                elif op == "mul":
                    left, right = instr.args
                    if self._is_one(right):
                        self._replace_value(instr.result, left)
                        self._remove_instr(block, i)
                        changed = True
                        continue
                    if self._is_one(left):
                        self._replace_value(instr.result, right)
                        self._remove_instr(block, i)
                        changed = True
                        continue
                    if self._is_zero(left) or self._is_zero(right):
                        old_args = instr.args
                        instr.op = "const"
                        instr.args = [0]
                        for a in old_args:
                            if isinstance(a, SSAValue) and instr in a.users:
                                a.users.remove(instr)
                        changed = True
                        continue

                elif op == "div" or op == "floordiv":
                    left, right = instr.args
                    if self._is_one(right):
                        self._replace_value(instr.result, left)
                        self._remove_instr(block, i)
                        changed = True
                        continue

                elif op == "mod":
                    left, right = instr.args
                    if self._is_zero(left):
                        old_args = instr.args
                        instr.op = "const"
                        instr.args = [0]
                        for a in old_args:
                            if isinstance(a, SSAValue) and instr in a.users:
                                a.users.remove(instr)
                        changed = True
                        continue

                elif op in ("cmp_eq", "cmp_ne"):
                    left, right = instr.args
                    if left is right:
                        result = (op == "cmp_eq")
                        old_args = instr.args
                        instr.op = "const"
                        instr.args = [result]
                        for a in old_args:
                            if isinstance(a, SSAValue) and instr in a.users:
                                a.users.remove(instr)
                        changed = True
                        continue

                elif op == "cmp_lt" or op == "cmp_gt":
                    left, right = instr.args
                    if left is right:
                        old_args = instr.args
                        instr.op = "const"
                        instr.args = [False]
                        for a in old_args:
                            if isinstance(a, SSAValue) and instr in a.users:
                                a.users.remove(instr)
                        changed = True
                        continue

                elif op == "cmp_le" or op == "cmp_ge":
                    left, right = instr.args
                    if left is right:
                        old_args = instr.args
                        instr.op = "const"
                        instr.args = [True]
                        for a in old_args:
                            if isinstance(a, SSAValue) and instr in a.users:
                                a.users.remove(instr)
                        changed = True
                        continue

                elif op == "neg":
                    operand = instr.args[0]
                    if isinstance(operand, SSAValue) and operand.def_instr and operand.def_instr.op == "neg":
                        self._replace_value(instr.result, operand.def_instr.args[0])
                        self._remove_instr(block, i)
                        changed = True
                        continue

                elif op == "not":
                    operand = instr.args[0]
                    if isinstance(operand, SSAValue) and operand.def_instr and operand.def_instr.op == "not":
                        self._replace_value(instr.result, operand.def_instr.args[0])
                        self._remove_instr(block, i)
                        changed = True
                        continue

                elif op == "ref_copy":
                    src = instr.args[0]
                    if isinstance(src, SSAValue) and src.def_instr and src.def_instr.op == "ref_copy":
                        self._replace_value(instr.result, src.def_instr.args[0])
                        self._remove_instr(block, i)
                        changed = True
                        continue

                i += 1
        return changed


    def _peephole(self):
        changed = False
        for block in self.func.blocks:
            i = 0
            while i < len(block.instructions):
                instr = block.instructions[i]

                if instr.op == "cmp_eq" and len(instr.args) == 2:
                    left, right = instr.args
                    if self._is_true(right):
                        self._replace_value(instr.result, left)
                        self._remove_instr(block, i)
                        changed = True
                        continue
                    if self._is_true(left):
                        self._replace_value(instr.result, right)
                        self._remove_instr(block, i)
                        changed = True
                        continue

                if instr.op == "cmp_ne" and len(instr.args) == 2:
                    left, right = instr.args
                    if self._is_false(right):
                        self._replace_value(instr.result, left)
                        self._remove_instr(block, i)
                        changed = True
                        continue
                    if self._is_false(left):
                        self._replace_value(instr.result, right)
                        self._remove_instr(block, i)
                        changed = True
                        continue

                if instr.op == "cmp_eq" and len(instr.args) == 2:
                    left, right = instr.args
                    if self._is_false(right):
                        instr.op = "not"
                        old_args = instr.args
                        instr.args = [left]
                        for a in old_args:
                            if isinstance(a, SSAValue) and instr in a.users:
                                a.users.remove(instr)
                        if isinstance(left, SSAValue):
                            left.users.append(instr)
                        changed = True
                        continue

                if instr.op == "add" and len(instr.args) == 2:
                    left, right = instr.args
                    if isinstance(left, SSAValue) and left.def_instr and left.def_instr.op == "sub" and left.def_instr.args[1] is right:
                        self._replace_value(instr.result, left.def_instr.args[0])
                        self._remove_instr(block, i)
                        changed = True
                        continue
                    if isinstance(right, SSAValue) and right.def_instr and right.def_instr.op == "sub" and right.def_instr.args[1] is left:
                        self._replace_value(instr.result, right.def_instr.args[0])
                        self._remove_instr(block, i)
                        changed = True
                        continue

                if instr.op == "sub" and len(instr.args) == 2:
                    left, right = instr.args
                    if isinstance(left, SSAValue) and left.def_instr and left.def_instr.op == "add":
                        if left.def_instr.args[1] is right:
                            self._replace_value(instr.result, left.def_instr.args[0])
                            self._remove_instr(block, i)
                            changed = True
                            continue
                        if left.def_instr.args[0] is right:
                            self._replace_value(instr.result, left.def_instr.args[1])
                            self._remove_instr(block, i)
                            changed = True
                            continue

                i += 1
        return changed


    def _reassociation(self):
        changed = False
        for block in self.func.blocks:
            i = 0
            while i < len(block.instructions):
                instr = block.instructions[i]
                if not self._is_associative(instr.op):
                    i += 1
                    continue
                left, right = instr.args
                if isinstance(left, SSAValue) and left.def_instr and left.def_instr.op == instr.op:
                    ll, lr = left.def_instr.args
                    if self._get_const_value(lr) is not None and self._get_const_value(right) is not None:
                        c1 = self._to_number(self._get_const_value(lr))
                        c2 = self._to_number(self._get_const_value(right))
                        if c1 is not None and c2 is not None:
                            new_c = self._make_const_instr(
                                c1 + c2 if instr.op == "add" else c1 * c2,
                                lr.type, block, i)
                            instr.args = [ll, new_c]
                            if left in left.users:
                                left.users.remove(instr)
                            if isinstance(ll, SSAValue):
                                ll.users.append(instr)
                            changed = True
                            continue
                i += 1
        return changed


    def _constant_propagation(self):
        changed = False
        for block in self.func.blocks:
            i = 0
            fresh = set()
            while i < len(block.instructions):
                instr = block.instructions[i]
                if instr.op == "const":
                    i += 1
                    continue
                new_args = list(instr.args)
                replaced = False
                for j, a in enumerate(instr.args):
                    if isinstance(a, SSAValue) and a.def_instr and a.def_instr.op == "const" and a not in fresh:
                        const_val = a.def_instr.args[0]
                        new_c = self._make_const_instr(const_val, a.type, block, i)
                        new_args[j] = new_c
                        fresh.add(new_c)
                        replaced = True
                if replaced:
                    for a in instr.args:
                        if isinstance(a, SSAValue) and instr in a.users:
                            a.users.remove(instr)
                    instr.args = new_args
                    for a in instr.args:
                        if isinstance(a, SSAValue):
                            a.users.append(instr)
                    changed = True
                    i += 1
                    continue
                i += 1
        return changed


    def _copy_propagation(self):
        changed = False
        for block in self.func.blocks:
            for instr in list(block.instructions):
                if instr.op == "ref_copy" and isinstance(instr.result, SSAValue):
                    src = instr.args[0]
                    if isinstance(src, SSAValue):
                        self._replace_value(instr.result, src)
                        changed = True
        if changed:
            self._dead_code_elimination()
        return changed


    def _cse(self):
        changed = False
        for block in self.func.blocks:
            seen = {}
            to_remove = []
            for idx, instr in enumerate(block.instructions):
                if not self._is_pure(instr.op):
                    continue
                if isinstance(instr, IRPhi) or instr.op == "call":
                    continue
                args = tuple(
                    a.name if isinstance(a, SSAValue) else a for a in instr.args
                )
                if isinstance(instr.result, SSAValue):
                    key = (instr.op, instr.result.type, args)
                else:
                    key = (instr.op, None, args)
                if key in seen:
                    self._replace_value(instr.result, seen[key])
                    to_remove.append(idx)
                    changed = True
                else:
                    seen[key] = instr.result
            for idx in reversed(to_remove):
                self._remove_instr(block, idx)
        return changed


    def _gvn(self):
        changed = False
        self.func.build_cfg()
        dom = self.func.compute_dominators()
        children = defaultdict(list)
        entry = self.func.blocks[0].label
        for label, dom_set in dom.items():
            if label == entry:
                continue
            idom = None
            for d in dom_set:
                if d == label:
                    continue
                if idom is None or len(dom[d]) > len(dom[idom]):
                    idom = d
            if idom:
                children[idom].append(label)

        vn_table = {}
        def hash_instr(instr):
            if isinstance(instr, IRPhi):
                inc = tuple(sorted((blk, v.name if isinstance(v, SSAValue) else v)
                                   for blk, v in instr.incoming))
                return ("phi", inc)
            args = []
            for a in instr.args:
                if isinstance(a, SSAValue):
                    args.append(a.name)
                else:
                    args.append(a)
            if self._is_commutative(instr.op):
                args = tuple(sorted(args))
            else:
                args = tuple(args)
            if isinstance(instr.result, SSAValue):
                return (instr.op, instr.result.type, args)
            return (instr.op, None, args)

        def process_block(label):
            nonlocal changed
            block = self.func.block_map[label]
            to_remove = []
            for idx, instr in enumerate(block.instructions):
                if not self._is_pure(instr.op) or isinstance(instr, IRPhi):
                    continue
                if instr.op == "call":
                    continue
                h = hash_instr(instr)
                if h in vn_table:
                    other = vn_table[h]
                    if other is not instr.result and other.name in dom[label]:
                        self._replace_value(instr.result, other)
                        to_remove.append(idx)
                        changed = True
                        continue
                vn_table[h] = instr.result

            for idx in reversed(to_remove):
                self._remove_instr(block, idx)

            for child in children[label]:
                process_block(child)

        process_block(entry)
        return changed


    def _sroa(self):
        changed = False
        for block in self.func.blocks:
            i = 0
            while i < len(block.instructions):
                instr = block.instructions[i]
                if instr.op != "struct_init":
                    i += 1
                    continue
                result = instr.result
                if not all(isinstance(u, IRInstr) and u.op == "field" for u in result.users):
                    i += 1
                    continue
                field_values = {}
                for k in range(1, len(instr.args), 2):
                    fname = instr.args[k]
                    fval = instr.args[k + 1]
                    field_values[fname] = fval

                for user in list(result.users):
                    if isinstance(user, IRInstr) and user.op == "field":
                        field_name = user.args[1]
                        if field_name in field_values:
                            self._replace_value(user.result, field_values[field_name])
                            for b in self.func.blocks:
                                if user in b.instructions:
                                    b.instructions.remove(user)
                                    break
                            changed = True

                if not result.users:
                    self._remove_instr(block, i)
                    changed = True
                    continue
                i += 1
        return changed


    def _field_forwarding(self):
        changed = False
        for block in self.func.blocks:
            i = 0
            while i < len(block.instructions):
                instr = block.instructions[i]
                if instr.op != "field":
                    i += 1
                    continue
                base = instr.args[0]
                field = instr.args[1]
                found = None
                for j in range(i - 1, -1, -1):
                    prev = block.instructions[j]
                    if prev.op == "struct_init" and prev.result is base:
                        for k in range(1, len(prev.args), 2):
                            if prev.args[k] == field:
                                found = prev.args[k + 1]
                                break
                        break
                    if isinstance(prev.result, SSAValue) and prev.result is base:
                        break
                if found is not None:
                    self._replace_value(instr.result, found)
                    self._remove_instr(block, i)
                    changed = True
                    continue
                i += 1
        return changed


    def _simplify_phi(self):
        changed = False
        for block in self.func.blocks:
            i = 0
            while i < len(block.instructions):
                instr = block.instructions[i]
                if not isinstance(instr, IRPhi):
                    i += 1
                    continue
                unique = []
                for _, v in instr.incoming:
                    if v is not instr.result and v not in unique:
                        unique.append(v)
                if len(unique) == 1:
                    self._replace_value(instr.result, unique[0])
                    block.instructions.pop(i)
                    for _, v in instr.incoming:
                        if instr in v.users:
                            v.users.remove(instr)
                    changed = True
                    continue
                if len(instr.incoming) > 0:
                    first = instr.incoming[0][1]
                    if all(v is first for _, v in instr.incoming):
                        self._replace_value(instr.result, first)
                        block.instructions.pop(i)
                        for _, v in instr.incoming:
                            if instr in v.users:
                                v.users.remove(instr)
                        changed = True
                        continue
                seen_blocks = {}
                for blk, v in instr.incoming:
                    seen_blocks[blk] = (blk, v)
                new_incoming = list(seen_blocks.values())
                if len(new_incoming) < len(instr.incoming):
                    instr.incoming = new_incoming
                    changed = True
                i += 1
        return changed


    def _if_conversion(self):
        changed = False
        for block in self.func.blocks:
            if not block.terminator or block.terminator.op != "cond_br":
                continue
            cond, t_label, f_label = block.terminator.args
            t_block = self.func.block_map.get(t_label)
            f_block = self.func.block_map.get(f_label)
            if not t_block or not f_block:
                continue
            if not (t_block.terminator and t_block.terminator.op == "br" and
                    f_block.terminator and f_block.terminator.op == "br" and
                    t_block.terminator.args[0] == f_block.terminator.args[0]):
                continue
            merge = self.func.block_map.get(t_block.terminator.args[0])
            if not merge or len(merge.predecessors) != 2:
                continue
            if len(t_block.instructions) != 1 or len(f_block.instructions) != 1:
                continue
            t_instr = t_block.instructions[0]
            f_instr = f_block.instructions[0]
            for phi in merge.instructions:
                if not isinstance(phi, IRPhi):
                    continue
                t_val = None
                f_val = None
                for blk, v in phi.incoming:
                    if blk == t_label:
                        t_val = v
                    if blk == f_label:
                        f_val = v
                if t_val is None or f_val is None:
                    continue
                if t_instr.result is t_val and f_instr.result is f_val:
                    sel = IRInstr("select", [cond, t_val, f_val], result=phi.result)
                    idx = merge.instructions.index(phi)
                    merge.instructions[idx] = sel
                    for _, v in phi.incoming:
                        if phi in v.users:
                            v.users.remove(phi)
                    if isinstance(cond, SSAValue):
                        cond.users.append(sel)
                    t_val.users.append(sel)
                    f_val.users.append(sel)
                    sel.result.def_instr = sel
                    block.terminator = IRInstr("br", [merge.label])
                    if t_label in merge.predecessors:
                        merge.predecessors.remove(t_label)
                    if f_label in merge.predecessors:
                        merge.predecessors.remove(f_label)
                    if block.label not in merge.predecessors:
                        merge.predecessors.append(block.label)
                    t_block.instructions.clear()
                    t_block.terminator = None
                    f_block.instructions.clear()
                    f_block.terminator = None
                    changed = True
                    break
        return changed


    def _tail_call_opt(self):
        changed = False
        for block in self.func.blocks:
            if not block.terminator or block.terminator.op != "ret":
                continue
            ret_val = block.terminator.args[0]
            if not isinstance(ret_val, SSAValue):
                continue
            for i in range(len(block.instructions) - 1, -1, -1):
                instr = block.instructions[i]
                if instr is ret_val.def_instr and instr.op == "call":
                    if instr.args[0] == self.func.name:
                        instr.op = "tailcall"
                        block.terminator = IRInstr("ret", [instr.result])
                        changed = True
                    break
        return changed


    def _branch_simplification(self):
        changed = False
        for block in self.func.blocks:
            if not block.terminator:
                continue
            t = block.terminator
            if t.op == "cond_br":
                cond = t.args[0]
                if self._is_true(cond):
                    block.terminator = IRInstr("br", [t.args[1]])
                    changed = True
                elif self._is_false(cond):
                    block.terminator = IRInstr("br", [t.args[2]])
                    changed = True
            elif t.op == "br":
                tgt = self.func.block_map.get(t.args[0])
                if tgt and tgt.terminator and tgt.terminator.op == "br" and len(tgt.instructions) == 0:
                    t.args[0] = tgt.terminator.args[0]
                    changed = True
        return changed


    def _jump_threading(self):
        changed = False
        for block in self.func.blocks:
            if not block.terminator or block.terminator.op != "cond_br":
                continue
            cond, t1, t2 = block.terminator.args
            if isinstance(cond, SSAValue) and cond.def_instr:
                defi = cond.def_instr
                if defi.op in ("cmp_eq", "cmp_ne"):
                    l, r = defi.args
                    lv = self._get_const_value(l)
                    rv = self._get_const_value(r)
                    if lv is not None and rv is not None:
                        eq = (lv == rv)
                        is_eq = (defi.op == "cmp_eq")
                        result = eq if is_eq else not eq
                        if result:
                            block.terminator = IRInstr("br", [t1])
                        else:
                            block.terminator = IRInstr("br", [t2])
                        changed = True
        return changed


    def _dead_code_elimination(self):
        changed = False
        for block in self.func.blocks:
            i = len(block.instructions) - 1
            while i >= 0:
                instr = block.instructions[i]
                if isinstance(instr, IRPhi):
                    if isinstance(instr.result, SSAValue) and not instr.result.users:
                        block.instructions.pop(i)
                        for _, v in instr.incoming:
                            if instr in v.users:
                                v.users.remove(instr)
                        changed = True
                elif isinstance(instr.result, SSAValue) and not instr.result.users and self._is_pure(instr.op):
                        self._remove_instr(block, i)
                        changed = True
                i -= 1
        return changed


    def _remove_empty_blocks(self):
        changed = False
        self.func.build_cfg()
        to_remove = []
        for block in self.func.blocks:
            if block.label == "entry":
                continue
            if len(block.instructions) != 0:
                continue
            if not block.terminator or block.terminator.op != "br":
                continue
            target_label = block.terminator.args[0]
            if target_label == block.label:
                continue
            target = self.func.block_map.get(target_label)
            if not target:
                continue
            duplicate = False
            for pred_label in list(block.predecessors):
                pred = self.func.block_map[pred_label]
                t = pred.terminator
                if not t:
                    continue
                if t.op == "br":
                    if t.args[0] == target_label:
                        duplicate = True
                        break
                elif t.op == "cond_br" and target_label in (t.args[1], t.args[2]):
                    duplicate = True
                    break
            if duplicate:
                continue
            for pred_label in list(block.predecessors):
                pred = self.func.block_map[pred_label]
                self._replace_terminator_target(pred, block.label, target_label)
                for t_instr in target.instructions:
                    if isinstance(t_instr, IRPhi):
                        t_instr.incoming = [
                            (pred_label if blk == block.label else blk, val)
                            for blk, val in t_instr.incoming
                        ]
                if block.label in target.predecessors:
                    target.predecessors.remove(block.label)
                if pred_label not in target.predecessors:
                    target.predecessors.append(pred_label)
                if target_label not in pred.successors:
                    pred.successors.append(target_label)
                if block.label in pred.successors:
                    pred.successors.remove(block.label)
            to_remove.append(block)
            changed = True
        for block in to_remove:
            self.func.blocks.remove(block)
            del self.func.block_map[block.label]
        return changed


    def _merge_blocks(self):
        changed = False
        self.func.build_cfg()
        i = 0
        while i < len(self.func.blocks):
            block = self.func.blocks[i]
            if not block.terminator or block.terminator.op != "br":
                i += 1
                continue
            target_label = block.terminator.args[0]
            target = self.func.block_map.get(target_label)
            if not target:
                i += 1
                continue
            if len(target.predecessors) == 1 and target.predecessors[0] == block.label:
                block.instructions.extend(target.instructions)
                block.terminator = target.terminator
                for b in self.func.blocks:
                    self._replace_terminator_target(b, target_label, block.label)
                    for instr in b.instructions:
                        if isinstance(instr, IRPhi):
                            instr.incoming = [
                                (block.label if blk == target_label else blk, val)
                                for blk, val in instr.incoming
                            ]
                self.func.blocks.remove(target)
                del self.func.block_map[target_label]
                changed = True
                continue
            i += 1
        return changed


    def _remove_unreachable_blocks(self):
        if not self.func.blocks:
            return False
        reachable = set()
        queue = [self.func.blocks[0].label]
        while queue:
            label = queue.pop(0)
            if label in reachable:
                continue
            reachable.add(label)
            block = self.func.block_map[label]
            if block.terminator:
                if block.terminator.op == "br":
                    queue.append(block.terminator.args[0])
                elif block.terminator.op == "cond_br":
                    queue.append(block.terminator.args[1])
                    queue.append(block.terminator.args[2])
        to_remove = [b for b in self.func.blocks if b.label not in reachable]
        if not to_remove:
            return False
        for block in to_remove:
            self.func.blocks.remove(block)
            del self.func.block_map[block.label]
            for b in self.func.blocks:
                if block.label in b.predecessors:
                    b.predecessors.remove(block.label)
                if block.label in b.successors:
                    b.successors.remove(block.label)
                for instr in b.instructions:
                    if isinstance(instr, IRPhi):
                        instr.incoming = [
                            (blk, val) for blk, val in instr.incoming if blk != block.label
                        ]
                if b.terminator and b.terminator.op == "cond_br":
                    _cond, t1, t2 = b.terminator.args
                    if t1 == block.label:
                        b.terminator = IRInstr("br", [t2])
                    elif t2 == block.label:
                        b.terminator = IRInstr("br", [t1])
        return True


    def _licm(self):
        changed = False
        self.func.build_cfg()
        dom = self.func.compute_dominators()
        back_edges = []
        for block in self.func.blocks:
            if not block.terminator:
                continue
            if block.terminator.op == "br":
                tgt = block.terminator.args[0]
                if tgt in dom[block.label]:
                    back_edges.append((block.label, tgt))
            elif block.terminator.op == "cond_br":
                for tgt in (block.terminator.args[1], block.terminator.args[2]):
                    if tgt in dom[block.label]:
                        back_edges.append((block.label, tgt))

        for header, tail in back_edges:
            loop_blocks = {header}
            queue = [tail]
            while queue:
                b = queue.pop(0)
                if b not in loop_blocks:
                    loop_blocks.add(b)
                    for pred in self.func.block_map[b].predecessors:
                        if pred not in loop_blocks:
                            queue.append(pred)

            for label in loop_blocks:
                block = self.func.block_map[label]
                i = 0
                while i < len(block.instructions):
                    instr = block.instructions[i]
                    if not self._is_pure(instr.op) or isinstance(instr, IRPhi):
                        i += 1
                        continue
                    if instr.op in ("call", "struct_init"):
                        i += 1
                        continue
                    invariant = True
                    for a in instr.args:
                        if isinstance(a, SSAValue) and a.def_instr:
                            def_block = None
                            for b in self.func.blocks:
                                if a.def_instr in b.instructions:
                                    def_block = b.label
                                    break
                            if def_block in loop_blocks:
                                invariant = False
                                break
                    if invariant:
                        preheader = self._get_or_create_preheader(header, dom)
                        if preheader:
                            moved = block.instructions.pop(i)
                            preheader.instructions.append(moved)
                            changed = True
                            continue
                    i += 1
        return changed

    def _get_or_create_preheader(self, header_label, dom):
        header = self.func.block_map[header_label]
        preds = [p for p in header.predecessors]
        non_back = []
        for p in preds:
            if p not in dom[header_label] or p == header_label:
                non_back.append(p)
        if len(non_back) == 1:
            return self.func.block_map[non_back[0]]
        pre = IRBlock(f"pre_{header_label}")
        pre.set_terminator(IRInstr("br", [header_label]))
        self.func.add_block(pre)
        for p in non_back:
            pred = self.func.block_map[p]
            self._replace_terminator_target(pred, header_label, pre.label)
            if header_label in pred.successors:
                pred.successors.remove(header_label)
            if pre.label not in pred.successors:
                pred.successors.append(pre.label)
            if p not in pre.predecessors:
                pre.predecessors.append(p)
            if p in header.predecessors:
                header.predecessors.remove(p)
        header.predecessors.append(pre.label)
        pre.successors.append(header_label)
        for instr in header.instructions:
            if isinstance(instr, IRPhi):
                instr.incoming = [
                    (pre.label if blk in non_back else blk, val)
                    for blk, val in instr.incoming
                ]
        return pre


    def _loop_unrolling(self):
        changed = False
        self.func.build_cfg()
        dom = self.func.compute_dominators()
        back_edges = []
        for block in self.func.blocks:
            if not block.terminator:
                continue
            if block.terminator.op == "br":
                tgt = block.terminator.args[0]
                if tgt in dom[block.label]:
                    back_edges.append((block.label, tgt))
            elif block.terminator.op == "cond_br":
                for tgt in (block.terminator.args[1], block.terminator.args[2]):
                    if tgt in dom[block.label]:
                        back_edges.append((block.label, tgt))

        for header_label, tail_label in back_edges:
            header = self.func.block_map[header_label]
            for instr in header.instructions:
                if not isinstance(instr, IRPhi):
                    continue
                if len(instr.incoming) != 2:
                    continue
                init_val = None
                next_val = None
                for blk, v in instr.incoming:
                    if blk == tail_label:
                        next_val = v
                    else:
                        init_val = v
                if init_val is None or next_val is None:
                    continue
                if not (isinstance(next_val, SSAValue) and next_val.def_instr and
                        next_val.def_instr.op == "add" and instr.result in next_val.def_instr.args):
                    continue
                step = None
                for a in next_val.def_instr.args:
                    if a is not instr.result:
                        step = self._get_const_value(a)
                if step is None:
                    continue
                step_n = self._to_number(step)
                if step_n is None or step_n == 0:
                    continue
                if not header.terminator or header.terminator.op != "cond_br":
                    continue
                cond = header.terminator.args[0]
                if not (isinstance(cond, SSAValue) and cond.def_instr):
                    continue
                cmp_instr = cond.def_instr
                if cmp_instr.op not in ("cmp_lt", "cmp_le", "cmp_gt", "cmp_ge"):
                    continue
                bound = None
                for a in cmp_instr.args:
                    if a is not instr.result:
                        bound = self._get_const_value(a)
                if bound is None:
                    continue
                bound_n = self._to_number(bound)
                init_n = self._to_number(self._get_const_value(init_val))
                if bound_n is None or init_n is None:
                    continue
                trip = None
                if cmp_instr.op == "cmp_lt" and step_n > 0:
                    trip = (bound_n - init_n + step_n - 1) // step_n
                elif cmp_instr.op == "cmp_le" and step_n > 0:
                    trip = (bound_n - init_n + step_n) // step_n
                if trip is None or trip <= 0 or trip > self.unroll_factor * 2:
                    continue
                factor = min(trip, self.unroll_factor)
                if factor < 2:
                    continue
                if trip > factor:
                    continue
        return changed


    def _inline_module(self, module):
        changed = True
        self._inline_counter = 0
        while changed:
            changed = False
            func_map = {f.name: f for f in module.funcs}
            for func in list(module.funcs):
                self.func = func
                func.build_cfg()
                for block in list(func.blocks):
                    i = 0
                    while i < len(block.instructions):
                        instr = block.instructions[i]
                        if instr.op != "call":
                            i += 1
                            continue
                        callee_name = instr.args[0]
                        callee = func_map.get(callee_name)
                        if not callee or callee is func:
                            i += 1
                            continue
                        if self._count_instructions(callee) > self.inline_threshold:
                            i += 1
                            continue
                        self._inline_call(func, block, i, instr, callee)
                        changed = True
                        i = 0

    def _inline_call(self, caller, block, idx, call_instr, callee):
        suffix = f"_inl{self._inline_counter}"
        self._inline_counter += 1
        value_map = {}
        label_map = {}

        def map_val(old):
            if not isinstance(old, SSAValue):
                return old
            if old not in value_map:
                new_v = SSAValue(old.name + suffix, old.type)
                value_map[old] = new_v
            return value_map[old]

        def map_label(old):
            if old not in label_map:
                label_map[old] = old + suffix
            return label_map[old]

        new_blocks = []
        for cb in callee.blocks:
            nb = IRBlock(map_label(cb.label))
            nb.predecessors = [map_label(p) for p in cb.predecessors]
            nb.successors = [map_label(s) for s in cb.successors]
            new_blocks.append((cb, nb))
            caller.add_block(nb)

        new_block_map = {b.label: b for _, b in new_blocks}

        for old_block, new_block in new_blocks:
            for old_instr in old_block.instructions:
                if isinstance(old_instr, IRPhi):
                    new_incoming = [(map_label(blk), map_val(v)) for blk, v in old_instr.incoming]
                    new_result = map_val(old_instr.result)
                    new_phi = IRPhi(new_result, new_incoming)
                    new_block.add_instr(new_phi)
                else:
                    new_args = [map_val(a) for a in old_instr.args]
                    new_result = map_val(old_instr.result) if isinstance(old_instr.result, SSAValue) else None
                    new_instr = IRInstr(old_instr.op, new_args, result=new_result)
                    new_block.add_instr(new_instr)
                    if isinstance(new_result, SSAValue):
                        new_result.def_instr = new_instr
                    for a in new_args:
                        if isinstance(a, SSAValue):
                            a.users.append(new_instr)

            if old_block.terminator:
                old_term = old_block.terminator
                if old_term.op == "br":
                    new_term = IRInstr("br", [map_label(old_term.args[0])])
                elif old_term.op == "cond_br":
                    new_term = IRInstr(
                        "cond_br",
                        [
                            map_val(old_term.args[0]),
                            map_label(old_term.args[1]),
                            map_label(old_term.args[2]),
                        ],
                    )
                elif old_term.op == "ret_void":
                    new_term = IRInstr("ret_void", [])
                else:
                    new_term = IRInstr(
                        old_term.op, [map_val(a) for a in old_term.args]
                    )
                new_block.set_terminator(new_term)

        call_args = call_instr.args[1:]
        for (pname, ptype, _), arg in zip(callee.params, call_args):
            entry_new = new_block_map[map_label(callee.blocks[0].label)]
            for instr in entry_new.instructions:
                if instr.op == "param" and instr.args[0] == pname:
                    self._replace_value(instr.result, arg)
                    break

        ret_infos = []
        for old_block, new_block in new_blocks:
            t = new_block.terminator
            if t and t.op == "ret":
                ret_infos.append((new_block, t.args[0] if len(t.args) > 0 else None))

        block.instructions.pop(idx)
        for a in call_instr.args:
            if isinstance(a, SSAValue) and call_instr in a.users:
                a.users.remove(call_instr)

        inlined_entry_label = map_label(callee.blocks[0].label)
        after_label = f"after{suffix}"
        after_block = IRBlock(after_label)
        caller.add_block(after_block)
        after_block.instructions = block.instructions[idx:]
        after_block.terminator = block.terminator
        block.instructions = block.instructions[:idx]
        block.terminator = IRInstr("br", [inlined_entry_label])

        block.successors = [inlined_entry_label]
        entry_new = new_block_map[inlined_entry_label]
        entry_new.predecessors = [block.label]

        if ret_infos:
            incoming = []
            for rb, rv in ret_infos:
                rb.terminator = IRInstr("br", [after_label])
                rb.successors = [after_label]
                after_block.predecessors.append(rb.label)
                if rv is not None:
                    incoming.append((rb.label, rv))
            call_result = call_instr.result
            if isinstance(call_result, SSAValue) and incoming:
                phi = IRPhi(call_result, incoming)
                after_block.instructions.insert(0, phi)

        for instr in after_block.instructions:
            if isinstance(instr, IRPhi):
                instr.incoming = [
                    (after_label if blk == block.label else blk, val)
                    for blk, val in instr.incoming
                ]

        for old_block, new_block in new_blocks:
            new_block.instructions = [i for i in new_block.instructions if not (i.op == "param" and i.result.users == [])]