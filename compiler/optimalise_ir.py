class IROptimizer:


    def optimize(self, module: IRModule):
        for func in module.funcs:
            self._optimize_function(func)
        return module

    def _optimize_function(self, func: IRFunction):
        changed = True
        while changed:
            changed = False
            func.build_cfg()

            changed |= self._constant_folding(func)
            changed |= self._algebraic_simplification(func)
            changed |= self._constant_propagation(func)
            changed |= self._copy_propagation(func)
            changed |= self._cse(func)
            changed |= self._simplify_phi(func)
            changed |= self._dead_code_elimination(func)
            changed |= self._remove_empty_blocks(func)
            changed |= self._merge_blocks(func)
            changed |= self._remove_unreachable_blocks(func)


    def _is_pure(self, op: str) -> bool:

        return op in {
            "const", "neg", "pos", "not",
            "cmp_lt", "cmp_gt", "cmp_le", "cmp_ge", "cmp_eq", "cmp_ne",
            "add", "sub", "mul", "div", "floordiv", "pow", "mod",
            "field", "ref_copy", "undef",
        }

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
                if '.' in val:
                    return float(val)
                return int(val)
            except ValueError:
                pass
        return None

    def _is_zero(self, val) -> bool:
        v = self._get_const_value(val)
        n = self._to_number(v)
        return n == 0 if n is not None else False

    def _is_one(self, val) -> bool:
        v = self._get_const_value(val)
        n = self._to_number(v)
        return n == 1 if n is not None else False

    def _replace_value(self, old_val: SSAValue, new_val: SSAValue):

        if old_val is new_val:
            return
        for user in list(old_val.users):
            if isinstance(user, IRInstr):
                user.args = [new_val if a is old_val else a for a in user.args]
            elif isinstance(user, IRPhi):
                user.incoming = [
                    (blk, new_val if v is old_val else v) for blk, v in user.incoming
                ]
            if isinstance(new_val, SSAValue):
                new_val.users.append(user)
        old_val.users.clear()

    def _remove_instr(self, block: IRBlock, idx: int):

        instr = block.instructions.pop(idx)
        if isinstance(instr.result, SSAValue):
            for a in instr.args:
                if isinstance(a, SSAValue) and instr in a.users:
                    a.users.remove(instr)
            instr.result.def_instr = None
        return instr

    def _make_const_instr(self, value, type_, block: IRBlock, insert_idx: int):

        v = SSAValue(f"%t_opt_{id(value) & 0xFFFF}", type_)
        instr = IRInstr("const", [value], result=v)
        block.instructions.insert(insert_idx, instr)
        return v


    def _eval_binary(self, op, left, right):
        l = self._to_number(left)
        r = self._to_number(right)
        if l is None or r is None:
            raise ValueError("Niet-numeriek")
        if op == "add":      return l + r
        if op == "sub":      return l - r
        if op == "mul":      return l * r
        if op == "div":      return l / r
        if op == "floordiv": return l // r
        if op == "mod":      return l % r
        if op == "pow":      return l ** r
        if op == "cmp_lt":   return l < r
        if op == "cmp_gt":   return l > r
        if op == "cmp_le":   return l <= r
        if op == "cmp_ge":   return l >= r
        if op == "cmp_eq":   return l == r
        if op == "cmp_ne":   return l != r
        raise ValueError(f"Onbekende op {op}")

    def _eval_unary(self, op, val):
        v = self._to_number(val)
        if v is None:
            raise ValueError("Niet-numeriek")
        if op == "neg": return -v
        if op == "pos": return v
        if op == "not": return not v
        raise ValueError(f"Onbekende op {op}")

    def _constant_folding(self, func: IRFunction) -> bool:
        changed = False
        for block in func.blocks:
            i = 0
            while i < len(block.instructions):
                instr = block.instructions[i]

                if instr.op in ("add", "sub", "mul", "div", "floordiv", "mod", "pow",
                                "cmp_lt", "cmp_gt", "cmp_le", "cmp_ge", "cmp_eq", "cmp_ne"):
                    l = self._get_const_value(instr.args[0])
                    r = self._get_const_value(instr.args[1])
                    if l is not None and r is not None:
                        try:
                            result = self._eval_binary(instr.op, l, r)
                            old_args = instr.args
                            instr.op = "const"
                            instr.args = [result]
                            for a in old_args:
                                if isinstance(a, SSAValue) and instr in a.users:
                                    a.users.remove(instr)
                            changed = True
                        except Exception:
                            pass

                elif instr.op in ("neg", "pos", "not"):
                    v = self._get_const_value(instr.args[0])
                    if v is not None:
                        try:
                            result = self._eval_unary(instr.op, v)
                            old_args = instr.args
                            instr.op = "const"
                            instr.args = [result]
                            for a in old_args:
                                if isinstance(a, SSAValue) and instr in a.users:
                                    a.users.remove(instr)
                            changed = True
                        except Exception:
                            pass

                i += 1
        return changed


    def _algebraic_simplification(self, func: IRFunction) -> bool:
        changed = False
        for block in func.blocks:
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
                        instr.op = "const"
                        old_args = instr.args
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
                        instr.op = "const"
                        old_args = instr.args
                        instr.args = [0]
                        for a in old_args:
                            if isinstance(a, SSAValue) and instr in a.users:
                                a.users.remove(instr)
                        changed = True
                        continue

                elif op == "div":
                    left, right = instr.args
                    if self._is_one(right):
                        self._replace_value(instr.result, left)
                        self._remove_instr(block, i)
                        changed = True
                        continue

                elif op in ("cmp_eq", "cmp_ne"):
                    left, right = instr.args
                    if left is right:
                        result = (op == "cmp_eq")
                        instr.op = "const"
                        old_args = instr.args
                        instr.args = [result]
                        for a in old_args:
                            if isinstance(a, SSAValue) and instr in a.users:
                                a.users.remove(instr)
                        changed = True
                        continue

                i += 1
        return changed


    def _constant_propagation(self, func: IRFunction) -> bool:

        changed = False
        for block in func.blocks:
            i = 0
            while i < len(block.instructions):
                instr = block.instructions[i]
                if instr.op == "const":
                    i += 1
                    continue

                new_args = list(instr.args)
                replaced = False
                for j, a in enumerate(instr.args):
                    if isinstance(a, SSAValue) and a.def_instr and a.def_instr.op == "const":
                        const_val = a.def_instr.args[0]
                        new_c = self._make_const_instr(const_val, a.type, block, i)
                        new_args[j] = new_c
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
                    continue

                i += 1
        return changed


    def _copy_propagation(self, func: IRFunction) -> bool:
        changed = False
        for block in func.blocks:
            for instr in list(block.instructions):
                if instr.op == "ref_copy" and isinstance(instr.result, SSAValue):
                    src = instr.args[0]
                    if isinstance(src, SSAValue):
                        self._replace_value(instr.result, src)
                        changed = True
        if changed:
            self._dead_code_elimination(func)
        return changed


    def _cse(self, func: IRFunction) -> bool:
        changed = False
        for block in func.blocks:
            seen = {}
            to_remove = []
            for idx, instr in enumerate(block.instructions):
                if not self._is_pure(instr.op):
                    continue
                if isinstance(instr, IRPhi) or instr.op == "call":
                    continue

                key = (instr.op, tuple(
                    a.name if isinstance(a, SSAValue) else a for a in instr.args
                ))
                if key in seen:
                    self._replace_value(instr.result, seen[key])
                    to_remove.append(idx)
                    changed = True
                else:
                    seen[key] = instr.result

            for idx in reversed(to_remove):
                self._remove_instr(block, idx)
        return changed


    def _simplify_phi(self, func: IRFunction) -> bool:
        changed = False
        for block in func.blocks:
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

                i += 1
        return changed


    def _dead_code_elimination(self, func: IRFunction) -> bool:
        changed = False
        for block in func.blocks:
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

                elif isinstance(instr.result, SSAValue) and not instr.result.users:
                    if self._is_pure(instr.op):
                        self._remove_instr(block, i)
                        changed = True

                i -= 1
        return changed


    def _remove_empty_blocks(self, func: IRFunction) -> bool:
        changed = False
        to_remove = []
        for block in func.blocks:
            if block.label == "entry":
                continue
            if len(block.instructions) != 0:
                continue
            if not block.terminator or block.terminator.op != "br":
                continue

            target_label = block.terminator.args[0]
            if target_label == block.label:
                continue

            target = func.block_map.get(target_label)
            if not target:
                continue

            for pred_label in list(block.predecessors):
                pred = func.block_map[pred_label]
                if pred.terminator.op == "br":
                    pred.terminator.args = [target_label]
                elif pred.terminator.op == "cond_br":
                    args = pred.terminator.args
                    pred.terminator.args = [
                        args[0],
                        target_label if args[1] == block.label else args[1],
                        target_label if args[2] == block.label else args[2],
                    ]

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
            func.blocks.remove(block)
            del func.block_map[block.label]
        return changed


    def _merge_blocks(self, func: IRFunction) -> bool:
        changed = False
        i = 0
        while i < len(func.blocks):
            block = func.blocks[i]
            if not block.terminator or block.terminator.op != "br":
                i += 1
                continue

            target_label = block.terminator.args[0]
            target = func.block_map.get(target_label)
            if not target:
                i += 1
                continue

            if len(target.predecessors) == 1 and target.predecessors[0] == block.label:
                block.instructions.extend(target.instructions)
                block.terminator = target.terminator

                for b in func.blocks:
                    if b.terminator:
                        if b.terminator.op == "br" and b.terminator.args[0] == target_label:
                            b.terminator.args[0] = block.label
                        elif b.terminator.op == "cond_br":
                            if b.terminator.args[1] == target_label:
                                b.terminator.args[1] = block.label
                            if b.terminator.args[2] == target_label:
                                b.terminator.args[2] = block.label

                for b in func.blocks:
                    for instr in b.instructions:
                        if isinstance(instr, IRPhi):
                            instr.incoming = [
                                (block.label if blk == target_label else blk, val)
                                for blk, val in instr.incoming
                            ]

                func.blocks.remove(target)
                del func.block_map[target_label]
                changed = True
                continue

            i += 1
        return changed


    def _remove_unreachable_blocks(self, func: IRFunction) -> bool:
        if not func.blocks:
            return False

        reachable = set()
        queue = [func.blocks[0].label]

        while queue:
            label = queue.pop(0)
            if label in reachable:
                continue
            reachable.add(label)
            block = func.block_map[label]
            if block.terminator:
                if block.terminator.op == "br":
                    queue.append(block.terminator.args[0])
                elif block.terminator.op == "cond_br":
                    queue.append(block.terminator.args[1])
                    queue.append(block.terminator.args[2])

        to_remove = [b for b in func.blocks if b.label not in reachable]
        if not to_remove:
            return False

        for block in to_remove:
            func.blocks.remove(block)
            del func.block_map[block.label]

            for b in func.blocks:
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
                    cond, t1, t2 = b.terminator.args
                    if t1 == block.label:
                        b.terminator = IRInstr("br", [t2])
                    elif t2 == block.label:
                        b.terminator = IRInstr("br", [t1])

        return True