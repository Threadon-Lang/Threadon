from .to_high_ir import SSAValue



class LLVMIRCompiler:


    def __init__(self):
        self.module = None
        self.struct_field_indices = {}
        self.used_intrinsics = set()
        self.out = []


    def compile(self, module):
        self.module = module
        self.struct_field_indices = {}
        self.used_intrinsics = set()
        self.out = []

        for name, fields in module.types.items():
            self.struct_field_indices[name] = {}
            for idx, (fname, _) in enumerate(fields.items()):
                self.struct_field_indices[name][fname] = idx

        self.out.append('; ModuleID = "main"')
        self.out.append('source_filename = "main"')
        self.out.append("")

        for name, fields in module.types.items():
            llvm_fields = ", ".join(self.to_llvm_type(ft) for ft in fields.values())
            self.out.append(f"%struct.{name} = type {{ {llvm_fields} }}")
        if module.types:
            self.out.append("")

        for func in module.funcs:
            self.emit_function(func)

        if self.used_intrinsics:
            self.out.append("")
            for intrin in sorted(self.used_intrinsics):
                if intrin == "llvm.pow.f64":
                    self.out.append("declare double @llvm.pow.f64(double, double) #0")
                elif intrin == "llvm.pow.i32":
                    self.out.append("declare i32 @llvm.pow.i32(i32, i32) #0")
                elif intrin == "llvm.floor.f64":
                    self.out.append("declare double @llvm.floor.f64(double) #0")
                elif intrin == "llvm.ceil.f64":
                    self.out.append("declare double @llvm.ceil.f64(double) #0")
            self.out.append("")
            self.out.append('attributes #0 = { nounwind readnone speculatable willreturn }')

        return "\n".join(self.out)


    def to_llvm_type(self, t):
        if t is None:
            return "void"
        if t == "int" or t == "Unknown" or t in ("Int8", "Int16", "Int32", "Int64"):
            return {"Int8": "i8", "Int16": "i16", "Int32": "i32", "Int64": "i64"}.get(t, "i32")
        if t == "float" or t in ("Float16", "Float32", "Float64"):
            return "double"
        if t == "bool" or t in ("Bool", "Boolean"):
            return "i1"
        if t == "String":
            return "i8*"
        if t == "NoneType":
            return "void"
        if t in self.module.types:
            return f"%struct.{t}"
        for name in self.module.types:
            if name in str(t):
                return f"%struct.{name}"
        return "i32"

    def is_float_type(self, t):
        return self.to_llvm_type(t) == "double"


    def emit_function(self, func):
        entry = func.blocks[0] if func.blocks else None

        param_names = []
        param_types = []
        if entry:
            for instr in entry.instructions:
                if instr.op == "param":
                    param_names.append(instr.result.name)
                    param_types.append(self.to_llvm_type(instr.result.type))

        params_str = ", ".join(f"{t} {n}" for t, n in zip(param_types, param_names))
        ret_type = self.to_llvm_type(func.return_type)

        self.out.append(f"define {ret_type} @{func.name}({params_str}) {{")

        for block in func.blocks:
            self.emit_block(block)

        self.out.append("}")
        self.out.append("")

    def emit_block(self, block):
        self.out.append(f"{block.label}:")
        for instr in block.instructions:
            if instr.op == "param":
                continue
            lines = self.emit_instr(instr)
            if lines is None:
                continue
            if isinstance(lines, str):
                lines = [lines]
            for line in lines:
                self.out.append(f"  {line}")
        if block.terminator:
            line = self.emit_terminator(block.terminator)
            self.out.append(f"  {line}")


    def emit_instr(self, instr):
        op = instr.op
        res = instr.result.name if isinstance(instr.result, SSAValue) else None
        rtype = self.to_llvm_type(instr.result.type) if isinstance(instr.result, SSAValue) else None

        if op == "const":
            val = instr.args[0]
            return self._emit_const(res, rtype, val)

        if op == "phi":
            incoming = ", ".join(
                f"[ {self.operand(v)}, %{blk} ]" for blk, v in instr.incoming
            )
            return f"{res} = phi {rtype} {incoming}"

        if op == "undef":
            return self._emit_undef(res, rtype)

        if op == "ref_copy":
            return self._emit_identity(res, instr.args[0])

        if op == "neg":
            return self._emit_unary(res, "neg", instr.args[0])
        if op == "pos":
            return self._emit_identity(res, instr.args[0])
        if op == "not":
            return self._emit_unary(res, "not", instr.args[0])

        if op in ("add", "sub", "mul", "div", "floordiv", "mod", "pow"):
            return self._emit_binary(res, op, instr.args[0], instr.args[1])

        if op in ("shl", "shr", "bit_and", "bit_or", "bit_xor"):
            return self._emit_bitwise(res, op, instr.args[0], instr.args[1])

        if op in ("cmp_lt", "cmp_gt", "cmp_le", "cmp_ge", "cmp_eq", "cmp_ne"):
            return self._emit_cmp(res, op, instr.args[0], instr.args[1])

        if op == "call":
            return self._emit_call(res, instr)

        if op == "tailcall":
            return self._emit_tailcall(res, instr)

        if op == "struct_init":
            return self._emit_struct_init(res, instr)

        if op == "field":
            return self._emit_field(res, instr)

        if op == "select":
            return self._emit_select(res, instr)

        return f"; UNHANDLED INSTRUCTION: {op}"


    def _emit_const(self, res, rtype, val):
        if isinstance(val, bool):
            vstr = "1" if val else "0"
            return f"{res} = add i1 0, {vstr}"
        if isinstance(val, float):
            return f"{res} = fadd double 0.0, {val}"
        if isinstance(val, int):
            return f"{res} = add {rtype} 0, {val}"
        if isinstance(val, str):
            if val.startswith('"'):
                return f"; string literal {val}\n  {res} = add i8* null, null"
            if '.' in val:
                return f"{res} = fadd double 0.0, {val}"
            return f"{res} = add {rtype} 0, {val}"
        return f"{res} = add {rtype} 0, 0"

    def _emit_undef(self, res, rtype):
        if rtype.startswith("%struct"):
            return f"{res} = select i1 false, {rtype} undef, {rtype} undef"
        if rtype == "double":
            return f"{res} = fadd double 0.0, 0.0"
        if rtype == "i1":
            return f"{res} = xor i1 false, false"
        return f"{res} = add {rtype} 0, 0"

    def _emit_identity(self, res, src):
        src_type = self.to_llvm_type(src.type)
        src_op = self.operand(src)
        if src_type == "double":
            return f"{res} = fadd double {src_op}, 0.0"
        if src_type == "i1":
            return f"{res} = xor i1 {src_op}, false"
        if src_type.startswith("%struct"):
            return f"{res} = select i1 false, {src_type} {src_op}, {src_type} {src_op}"
        return f"{res} = add {src_type} {src_op}, 0"

    def _emit_unary(self, res, op, operand):
        src = self.operand(operand)
        src_type = self.to_llvm_type(operand.type)
        if op == "neg":
            if src_type == "double":
                return f"{res} = fsub double 0.0, {src}"
            return f"{res} = sub {src_type} 0, {src}"
        if op == "not":
            return f"{res} = xor i1 {src}, true"
        return f"; unknown unary {op}"

    def _emit_binary(self, res, op, left, right):
        l = self.operand(left)
        r = self.operand(right)
        ltype = self.to_llvm_type(left.type)
        is_float = (ltype == "double")

        if op == "pow":
            if is_float:
                self.used_intrinsics.add("llvm.pow.f64")
                return f"{res} = call double @llvm.pow.f64(double {l}, double {r})"
            else:
                self.used_intrinsics.add("llvm.pow.i32")
                return f"{res} = call i32 @llvm.pow.i32(i32 {l}, i32 {r})"

        if op == "floordiv" and is_float:
            self.used_intrinsics.add("llvm.floor.f64")
            tmp = f"{res}_div"
            return [
                f"{tmp} = fdiv double {l}, {r}",
                f"{res} = call double @llvm.floor.f64(double {tmp})"
            ]

        op_map = {
            "add": "fadd" if is_float else "add",
            "sub": "fsub" if is_float else "sub",
            "mul": "fmul" if is_float else "mul",
            "div": "fdiv" if is_float else "sdiv",
            "floordiv": "sdiv",
            "mod": "frem" if is_float else "srem",
        }
        llvm_op = op_map.get(op, "add")
        return f"{res} = {llvm_op} {ltype} {l}, {r}"

    def _emit_bitwise(self, res, op, left, right):
        l = self.operand(left)
        r = self.operand(right)
        op_map = {
            "shl": "shl",
            "shr": "ashr",
            "bit_and": "and",
            "bit_or": "or",
            "bit_xor": "xor",
        }
        llvm_op = op_map[op]
        return f"{res} = {llvm_op} i32 {l}, {r}"

    def _emit_cmp(self, res, op, left, right):
        l = self.operand(left)
        r = self.operand(right)
        ltype = self.to_llvm_type(left.type)
        is_float = (ltype == "double")

        pred_map = {
            "cmp_lt": "olt" if is_float else "slt",
            "cmp_gt": "ogt" if is_float else "sgt",
            "cmp_le": "ole" if is_float else "sle",
            "cmp_ge": "oge" if is_float else "sge",
            "cmp_eq": "oeq" if is_float else "eq",
            "cmp_ne": "one" if is_float else "ne",
        }
        pred = pred_map[op]
        cmp_op = "fcmp" if is_float else "icmp"
        return f"{res} = {cmp_op} {pred} {ltype} {l}, {r}"

    def _emit_call(self, res, instr):
        fname = instr.args[0]
        args = instr.args[1:]
        arg_strs = []
        for a in args:
            atype = self.to_llvm_type(a.type)
            aval = self.operand(a)
            arg_strs.append(f"{atype} {aval}")
        args_str = ", ".join(arg_strs)
        ret_type = self.to_llvm_type(instr.result.type)
        if ret_type == "void":
            return f"call {ret_type} @{fname}({args_str})"
        return f"{res} = call {ret_type} @{fname}({args_str})"

    def _emit_tailcall(self, res, instr):
        fname = instr.args[0]
        args = instr.args[1:]
        arg_strs = []
        for a in args:
            atype = self.to_llvm_type(a.type)
            aval = self.operand(a)
            arg_strs.append(f"{atype} {aval}")
        args_str = ", ".join(arg_strs)
        ret_type = self.to_llvm_type(instr.result.type)
        return f"{res} = tail call {ret_type} @{fname}({args_str})"

    def _emit_struct_init(self, res, instr):
        struct_name = instr.args[0]
        llvm_type = f"%struct.{struct_name}"
        lines = []
        current = "undef"
        n_fields = (len(instr.args) - 1) // 2
        field_idx = 0
        for k in range(1, len(instr.args), 2):
            fval = instr.args[k + 1]
            ftype = self.to_llvm_type(fval.type)
            foperand = self.operand(fval)
            if field_idx == n_fields - 1:
                lines.append(f"{res} = insertvalue {llvm_type} {current}, {ftype} {foperand}, {field_idx}")
            else:
                tmp = f"{res}_s{field_idx}"
                lines.append(f"{tmp} = insertvalue {llvm_type} {current}, {ftype} {foperand}, {field_idx}")
                current = tmp
            field_idx += 1
        return lines

    def _emit_field(self, res, instr):
        base = self.operand(instr.args[0])
        field_name = instr.args[1]
        base_type = instr.args[0].type
        if base_type in self.struct_field_indices:
            idx = self.struct_field_indices[base_type][field_name]
            llvm_type = self.to_llvm_type(base_type)
            return f"{res} = extractvalue {llvm_type} {base}, {idx}"
        return f"; unknown struct field {field_name}"

    def _emit_select(self, res, instr):
        cond = self.operand(instr.args[0])
        tval = self.operand(instr.args[1])
        fval = self.operand(instr.args[2])
        ttype = self.to_llvm_type(instr.args[1].type)
        return f"{res} = select i1 {cond}, {ttype} {tval}, {ttype} {fval}"


    def emit_terminator(self, term):
        op = term.op
        if op == "br":
            return f"br label %{term.args[0]}"
        if op == "cond_br":
            cond = self.operand(term.args[0])
            return f"br i1 {cond}, label %{term.args[1]}, label %{term.args[2]}"
        if op == "ret":
            val = self.operand(term.args[0])
            vtype = self.to_llvm_type(term.args[0].type)
            return f"ret {vtype} {val}"
        if op == "ret_void":
            return "ret void"
        return f"; UNHANDLED TERMINATOR: {op}"


    def operand(self, val):
        if isinstance(val, SSAValue):
            return val.name
        if isinstance(val, bool):
            return "true" if val else "false"
        if isinstance(val, str):
            if val.startswith('"'):
                return val
            return val
        if isinstance(val, (int, float)):
            return str(val)
        return str(val)