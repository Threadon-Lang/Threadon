from .to_high_ir import SSAValue
from .builtins import BUILTIN_SIGS
import struct 

FLOAT_LLVM_TYPES = ("half", "float", "double")

class LLVMIRCompiler:


    def __init__(self):
        self.module = None
        self.struct_field_indices = {}
        self.used_intrinsics = set()
        self.used_c_runtime = set()
        self.string_globals = {}
        self.out = []


    def compile(self, module):
        self.module = module
        self.struct_field_indices = {}
        self.used_intrinsics = set()
        self.used_c_runtime = set()
        self.string_globals = {}
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

        if "input_helper" in self.used_c_runtime:
            self.out.append("")
            self._emit_input_helper()
        if "to_int_str" in self.used_c_runtime:
            self.out.append("")
            self._emit_str_to_int_helper()
        if "to_float_str" in self.used_c_runtime:
            self.out.append("")
            self._emit_str_to_float_helper()
        if "to_bool_str" in self.used_c_runtime:
            self.out.append("")
            self._emit_str_to_bool_helper()

        if self.used_intrinsics:
            self.out.append("")
            for intrin in sorted(self.used_intrinsics):
                if intrin.startswith("llvm.pow.f"):
                    suffix = intrin.rsplit(".", 1)[1]
                    t = {"f16": "half", "f32": "float", "f64": "double"}[suffix]
                    self.out.append(f"declare {t} @{intrin}({t}, {t}) #0")
                elif intrin == "llvm.pow.i32":
                    self.out.append("declare i32 @llvm.pow.i32(i32, i32) #0")
                elif intrin.startswith("llvm.floor.f"):
                    suffix = intrin.rsplit(".", 1)[1]
                    t = {"f16": "half", "f32": "float", "f64": "double"}[suffix]
                    self.out.append(f"declare {t} @{intrin}({t}) #0")
                elif intrin.startswith("llvm.ceil.f"):
                    suffix = intrin.rsplit(".", 1)[1]
                    t = {"f16": "half", "f32": "float", "f64": "double"}[suffix]
                    self.out.append(f"declare {t} @{intrin}({t}) #0")
            self.out.append("")
            self.out.append('attributes #0 = { nounwind readnone speculatable willreturn }')
        if self.string_globals:
            self.out.append("")
            for content, gname in self.string_globals.items():
                raw = content.encode("utf-8", "replace")
                escaped = "".join(f"\\{b:02x}" for b in raw) + "\\00"
                size = len(raw) + 1
                self.out.append(f'{gname} = private unnamed_addr constant [{size} x i8] c"{escaped}"')

        if self.used_c_runtime:
            self.out.append("")
            if "printf" in self.used_c_runtime:
                self.out.append("declare i32 @printf(i8*, ...)")
            if "fprintf" in self.used_c_runtime:
                self.out.append("declare i32 @fprintf(i8*, i8*, ...)")
            if "scanf" in self.used_c_runtime:
                self.out.append("declare i32 @scanf(i8*, ...)")
            if "fflush" in self.used_c_runtime:
                self.out.append("declare i32 @fflush(i8*)")
                self.out.append("@stdout = external global i8*")
            if "fgets" in self.used_c_runtime:
                self.out.append("declare i8* @fgets(i8*, i32, i8*)")
                self.out.append("@stdin = external global i8*")
            if "strcspn" in self.used_c_runtime:
                self.out.append("declare i64 @strcspn(i8*, i8*)")
            if "strtol" in self.used_c_runtime:
                self.out.append("declare i64 @strtol(i8*, i8**, i32)")
            if "strtod" in self.used_c_runtime:
                self.out.append("declare double @strtod(i8*, i8**)")
            if "strcasecmp" in self.used_c_runtime:
                self.out.append("declare i32 @strcasecmp(i8*, i8*)")
            if "exit" in self.used_c_runtime:
                self.out.append("declare void @exit(i32)")
            if "fprintf" in self.used_c_runtime:
                self.out.append("@stderr = external global i8*")
            self.out.append("")

        return "\n".join(self.out)


    def to_llvm_type(self, t):
        if t is None:
            return "void"
        if isinstance(t, str) and t.endswith("*"):
            base = self.to_llvm_type(t[:-1])
            return f"{base}*"
        if t == "int" or t == "Unknown" or t in ("Int8", "Int16", "Int32", "Int64"):
            return {"Int8": "i8", "Int16": "i16", "Int32": "i32", "Int64": "i64"}.get(t, "i32")
        if t == "float" or t in ("Float16", "Float32", "Float64"):
            return {"Float16": "half", "Float32": "float", "Float64": "double"}.get(t, "float")
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
        return self.to_llvm_type(t) in FLOAT_LLVM_TYPES

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

        if op == "store_field":
            return self._emit_store_field(res, instr)

        if op == "select":
            return self._emit_select(res, instr)
        if op == "alloca":
            return self._emit_alloca(res, instr.args[0])

        if op == "load":
            return self._emit_load(res, rtype, instr.args[0])

        if op == "store":
            return self._emit_store(instr.args[0], instr.args[1])
        return f"; UNHANDLED INSTRUCTION: {op}"

    def _emit_alloca(self, res, var_type):
        llvm_type = self.to_llvm_type(var_type)
        return f"{res} = alloca {llvm_type}"

    def _emit_load(self, res, rtype, ptr_val):
        ptr_op = self.operand(ptr_val)
        return f"{res} = load {rtype}, {rtype}* {ptr_op}"

    def _emit_store(self, val, ptr_val):
        val_type = self.to_llvm_type(val.type)
        val_op = self.operand(val)
        ptr_op = self.operand(ptr_val)
        return f"store {val_type} {val_op}, {val_type}* {ptr_op}"

    def _f64_hex(self, fval):
        return format(struct.unpack('<Q', struct.pack('<d', fval))[0], '016X')

    def _emit_const(self, res, rtype, val):
        if rtype == "i1":
            vstr = "1" if str(val).lower() in ("true", "1") else "0"
            return f"{res} = add i1 0, {vstr}"
        if rtype == "i8*":
            return self._emit_string_const(res, val)
        if rtype in FLOAT_LLVM_TYPES:
            fval = float(val)
            if rtype == "float":
                fval = struct.unpack('<f', struct.pack('<f', fval))[0]
                return f"{res} = fadd float 0.0, 0x{self._f64_hex(fval)}"
            if rtype == "half":
                fval = struct.unpack('<f', struct.pack('<f', fval))[0]
                return f"{res} = fadd half 0.0, 0x{self._f64_hex(fval)}"
            return f"{res} = fadd {rtype} 0.0, {fval}"
        if isinstance(val, int):
            return f"{res} = add {rtype} 0, {val}"
        if isinstance(val, str):
            if '.' in val:
                return f"{res} = fadd {rtype} 0.0, {val}"
            return f"{res} = add {rtype} 0, {val}"
        return f"{res} = add {rtype} 0, 0"
    def _emit_string_const(self, res, val):
        gname = self._string_global(val)
        size = len(val.encode("utf-8", "replace")) + 1
        return (
            f"{res} = getelementptr inbounds "
            f"[{size} x i8], [{size} x i8]* {gname}, i64 0, i64 0"
        )

    def _string_global(self, content):
        if content not in self.string_globals:
            self.string_globals[content] = f"@.str.{len(self.string_globals)}"
        return self.string_globals[content]

    def _emit_undef(self, res, rtype):
        if rtype.startswith("%struct"):
            return f"{res} = select i1 false, {rtype} undef, {rtype} undef"
        if rtype in FLOAT_LLVM_TYPES:
            return f"{res} = fadd {rtype} 0.0, 0.0"
        if rtype == "i1":
            return f"{res} = xor i1 false, false"
        return f"{res} = add {rtype} 0, 0"

    def _emit_identity(self, res, src):
        src_type = self.to_llvm_type(src.type)
        src_op = self.operand(src)
        if src_type in FLOAT_LLVM_TYPES:
            return f"{res} = fadd {src_type} {src_op}, 0.0"
        if src_type == "i1":
            return f"{res} = xor i1 {src_op}, false"
        if src_type == "i8*" or (src_type.startswith("%struct") and src_type.endswith("*")):
            return f"{res} = getelementptr {src_type[:-1]}, {src_type} {src_op}, i32 0"
        if src_type.startswith("%struct"):
            ptr = f"{res}_ptr"
            return [
                f"{ptr} = alloca {src_type}",
                f"store {src_type} {src_op}, {src_type}* {ptr}",
                f"{res} = load {src_type}, {src_type}* {ptr}",
            ]
        return f"{res} = add {src_type} {src_op}, 0"
    def _emit_unary(self, res, op, operand):
        src = self.operand(operand)
        src_type = self.to_llvm_type(operand.type)
        if op == "neg":
            if src_type in FLOAT_LLVM_TYPES:
                return f"{res} = fsub {src_type} 0.0, {src}"
            return f"{res} = sub {src_type} 0, {src}"
        if op == "not":
            return f"{res} = xor i1 {src}, true"
        return f"; unknown unary {op}"
    def _float_suffix(self, ltype):
        return {"half": "f16", "float": "f32", "double": "f64"}[ltype]

    def _emit_binary(self, res, op, left, right):
        l = self.operand(left)
        r = self.operand(right)
        ltype = self.to_llvm_type(left.type)
        is_float = ltype in FLOAT_LLVM_TYPES

        if op == "pow":
            if is_float:
                intrin = f"llvm.pow.{self._float_suffix(ltype)}"
                self.used_intrinsics.add(intrin)
                return f"{res} = call {ltype} @{intrin}({ltype} {l}, {ltype} {r})"
            else:
                self.used_intrinsics.add("llvm.pow.i32")
                return f"{res} = call i32 @llvm.pow.i32(i32 {l}, i32 {r})"

        if op == "floordiv" and is_float:
            intrin = f"llvm.floor.{self._float_suffix(ltype)}"
            self.used_intrinsics.add(intrin)
            tmp = f"{res}_div"
            return [
                f"{tmp} = fdiv {ltype} {l}, {r}",
                f"{res} = call {ltype} @{intrin}({ltype} {tmp})"
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
        is_float = ltype in FLOAT_LLVM_TYPES

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
        if fname in BUILTIN_SIGS:
            return self._emit_builtin(res, fname, instr.args[1:])
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

    def _emit_builtin(self, res, fname, args):
        if fname == "print":
            return self._emit_print(res, args)
        if fname == "input":
            return self._emit_input(res, args[0])
        if fname == "to_int":
            return self._emit_to_int(res, args[0])
        if fname == "to_float":
            return self._emit_to_float(res, args[0])
        if fname == "to_bool":
            return self._emit_to_bool(res, args[0])
        return f"; unknown builtin {fname}"

    def _emit_print(self, res, args):
        self.used_c_runtime.add("printf")
        specs = []
        call_args = []
        lines = []
        for i, arg in enumerate(args):
            atype = self.to_llvm_type(arg.type)
            val = self.operand(arg)

            if atype in ("i8", "i16", "i32"):
                spec = "%d"
                if atype != "i32":
                    ext = f"{res}_ext{i}"
                    lines.append(f"{ext} = sext {atype} {val} to i32")
                    val = ext
                call_args.append(f"i32 {val}")
            elif atype == "i64":
                spec = "%lld"
                call_args.append(f"i64 {val}")
            elif atype == "double":
                spec = "%f"
                call_args.append(f"double {val}")
            elif atype == "i1":
                spec = "%d"
                btmp = f"{res}_b{i}"
                lines.append(f"{btmp} = zext i1 {val} to i32")
                call_args.append(f"i32 {btmp}")
            elif atype == "i8*":
                spec = "%s"
                call_args.append(f"i8* {val}")
            elif atype in ("half", "float"):
                spec = "%f"
                ext = f"{res}_fext{i}"
                lines.append(f"{ext} = fpext {atype} {val} to double")
                call_args.append(f"double {ext}")
            elif atype == "double":
                spec = "%f"
                call_args.append(f"double {val}")
            else:
                raise Exception(f"print: unsupported type {atype}")

            specs.append(spec)

        fmt = " ".join(specs) + "\n"
        fmt_global = self._string_global(fmt)
        size = len(fmt.encode("utf-8")) + 1
        ptr = f"{res}_fmt"
        lines.append(
            f"{ptr} = getelementptr inbounds "
            f"[{size} x i8], [{size} x i8]* {fmt_global}, i64 0, i64 0"
        )
        arg_str = ", " + ", ".join(call_args) if call_args else ""
        lines.append(f"call i32 (i8*, ...) @printf(i8* {ptr}{arg_str})")
        return lines
    def _emit_input(self, res, arg):
        self.used_c_runtime.update(["printf", "fflush", "fgets", "strcspn"])
        self.used_c_runtime.add("input_helper")
        return f"{res} = call i8* @__threadon_input(i8* {self.operand(arg)})"

    def _emit_input_helper(self):
        buf_size = 1024
        pfmt = self._string_global("%s")
        psize = len("%s".encode("utf-8")) + 1
        nl = "\n"
        nl_global = self._string_global(nl)
        nl_size = len(nl.encode("utf-8")) + 1
        self.out.append("define i8* @__threadon_input(i8* %prompt) {")
        self.out.append("entry:")
        self.out.append(
            f"  %pfmt = getelementptr inbounds "
            f"[{psize} x i8], [{psize} x i8]* {pfmt}, i64 0, i64 0"
        )
        self.out.append("  call i32 (i8*, ...) @printf(i8* %pfmt, i8* %prompt)")
        self.out.append("  %so = load i8*, i8** @stdout")
        self.out.append("  %fl = call i32 @fflush(i8* %so)")
        self.out.append("  %buf = getelementptr inbounds "
                        f"[{buf_size} x i8], [{buf_size} x i8]* "
                        "@__threadon_input_buf, i64 0, i64 0")
        self.out.append("  %si = load i8*, i8** @stdin")
        self.out.append(f"  %n = call i8* @fgets(i8* %buf, i32 {buf_size}, i8* %si)")
        self.out.append("  %ok = icmp ne i8* %n, null")
        self.out.append("  br i1 %ok, label %read_ok, label %read_eof")
        self.out.append("read_eof:")
        self.out.append("  store i8 0, i8* %buf")
        self.out.append("  br label %read_ok")
        self.out.append("read_ok:")
        self.out.append(
            f"  %nl = getelementptr inbounds "
            f"[{nl_size} x i8], [{nl_size} x i8]* {nl_global}, i64 0, i64 0"
        )
        self.out.append("  %off = call i64 @strcspn(i8* %buf, i8* %nl)")
        self.out.append("  %end = getelementptr i8, i8* %buf, i64 %off")
        self.out.append("  store i8 0, i8* %end")
        self.out.append("  ret i8* %buf")
        self.out.append("}")
        self.out.append("")
        self.out.append(f"@__threadon_input_buf = private global [{buf_size} x i8] zeroinitializer")
        self.out.append("")

    def _emit_conv_error(self, eglobal, esize):
        self.out.append("  %se = load i8*, i8** @stderr")
        self.out.append(
            f"  %efmt = getelementptr inbounds "
            f"[{esize} x i8], [{esize} x i8]* {eglobal}, i64 0, i64 0"
        )
        self.out.append("  call i32 (i8*, ...) @fprintf(i8* %se, i8* %efmt)")
        self.out.append("  call void @exit(i32 1)")
        self.out.append("  unreachable")

    def _emit_str_to_int_helper(self):
        emsg = "error: could not convert string to an integer\n"
        eglobal = self._string_global(emsg)
        esize = len(emsg.encode("utf-8")) + 1
        self.out.append("define i32 @__threadon_str_to_int(i8* %s) {")
        self.out.append("entry:")
        self.out.append("  %end = alloca i8*")
        self.out.append("  %v = call i64 @strtol(i8* %s, i8** %end, i32 10)")
        self.out.append("  %ep = load i8*, i8** %end")
        self.out.append("  %c = load i8, i8* %ep")
        self.out.append("  %ok = icmp eq i8 %c, 0")
        self.out.append("  br i1 %ok, label %conv_ok, label %conv_err")
        self.out.append("conv_err:")
        self._emit_conv_error(eglobal, esize)
        self.out.append("conv_ok:")
        self.out.append("  %r = trunc i64 %v to i32")
        self.out.append("  ret i32 %r")
        self.out.append("}")
        self.out.append("")

    def _emit_str_to_float_helper(self):
        emsg = "error: could not convert string to a float\n"
        eglobal = self._string_global(emsg)
        esize = len(emsg.encode("utf-8")) + 1
        self.out.append("define double @__threadon_str_to_float(i8* %s) {")
        self.out.append("entry:")
        self.out.append("  %end = alloca i8*")
        self.out.append("  %v = call double @strtod(i8* %s, i8** %end)")
        self.out.append("  %ep = load i8*, i8** %end")
        self.out.append("  %c = load i8, i8* %ep")
        self.out.append("  %ok = icmp eq i8 %c, 0")
        self.out.append("  br i1 %ok, label %conv_ok, label %conv_err")
        self.out.append("conv_err:")
        self._emit_conv_error(eglobal, esize)
        self.out.append("conv_ok:")
        self.out.append("  ret double %v")
        self.out.append("}")
        self.out.append("")

    def _emit_str_to_bool_helper(self):
        true_s = self._string_global("true")
        true_size = len("true".encode("utf-8")) + 1
        one_s = self._string_global("1")
        one_size = len("1".encode("utf-8")) + 1
        false_s = self._string_global("false")
        false_size = len("false".encode("utf-8")) + 1
        zero_s = self._string_global("0")
        zero_size = len("0".encode("utf-8")) + 1
        emsg = "error: could not convert string to a boolean\n"
        eglobal = self._string_global(emsg)
        esize = len(emsg.encode("utf-8")) + 1
        self.out.append("define i1 @__threadon_str_to_bool(i8* %s) {")
        self.out.append("entry:")
        self.out.append(
            f"  %t = getelementptr inbounds "
            f"[{true_size} x i8], [{true_size} x i8]* {true_s}, i64 0, i64 0"
        )
        self.out.append("  %ct = call i32 @strcasecmp(i8* %s, i8* %t)")
        self.out.append("  %ist = icmp eq i32 %ct, 0")
        self.out.append("  br i1 %ist, label %conv_true, label %check_false")
        self.out.append("check_false:")
        self.out.append(
            f"  %f = getelementptr inbounds "
            f"[{false_size} x i8], [{false_size} x i8]* {false_s}, i64 0, i64 0"
        )
        self.out.append("  %cf = call i32 @strcasecmp(i8* %s, i8* %f)")
        self.out.append("  %isf = icmp eq i32 %cf, 0")
        self.out.append("  br i1 %isf, label %conv_false, label %check_one")
        self.out.append("check_one:")
        self.out.append(
            f"  %o = getelementptr inbounds "
            f"[{one_size} x i8], [{one_size} x i8]* {one_s}, i64 0, i64 0"
        )
        self.out.append("  %co = call i32 @strcasecmp(i8* %s, i8* %o)")
        self.out.append("  %iso = icmp eq i32 %co, 0")
        self.out.append("  br i1 %iso, label %conv_true, label %check_zero")
        self.out.append("check_zero:")
        self.out.append(
            f"  %z = getelementptr inbounds "
            f"[{zero_size} x i8], [{zero_size} x i8]* {zero_s}, i64 0, i64 0"
        )
        self.out.append("  %cz = call i32 @strcasecmp(i8* %s, i8* %z)")
        self.out.append("  %isz = icmp eq i32 %cz, 0")
        self.out.append("  br i1 %isz, label %conv_false, label %conv_err")
        self.out.append("conv_true:")
        self.out.append("  ret i1 true")
        self.out.append("conv_false:")
        self.out.append("  ret i1 false")
        self.out.append("conv_err:")
        self._emit_conv_error(eglobal, esize)
        self.out.append("}")
        self.out.append("")

    def _emit_to_int(self, res, arg):
        atype = self.to_llvm_type(arg.type)
        val = self.operand(arg)
        if atype in FLOAT_LLVM_TYPES:
            return f"{res} = fptosi {atype} {val} to i32"
        if atype == "i1":
            return f"{res} = zext i1 {val} to i32"
        if atype == "i8*":
            self.used_c_runtime.update(["printf", "strtol", "fprintf", "exit"])
            self.used_c_runtime.add("to_int_str")
            return f"{res} = call i32 @__threadon_str_to_int(i8* {val})"
        return f"{res} = add i32 0, 0"

    def _emit_to_float(self, res, arg):
        atype = self.to_llvm_type(arg.type)
        val = self.operand(arg)
        if atype == "i8*":
            self.used_c_runtime.update(["printf", "strtod", "fprintf", "exit"])
            self.used_c_runtime.add("to_float_str")
            tmp = f"{res}_d"
            return [
                f"{tmp} = call double @__threadon_str_to_float(i8* {val})",
                f"{res} = fptrunc double {tmp} to float",
            ]
        return f"{res} = sitofp i32 {val} to float"

    def _emit_to_bool(self, res, arg):
        atype = self.to_llvm_type(arg.type)
        val = self.operand(arg)
        if atype == "i8*":
            self.used_c_runtime.update(["printf", "strcasecmp", "fprintf", "exit"])
            self.used_c_runtime.add("to_bool_str")
            return f"{res} = call i1 @__threadon_str_to_bool(i8* {val})"
        if atype in FLOAT_LLVM_TYPES:
            return f"{res} = fcmp une {atype} {val}, 0.0"
        return f"{res} = icmp ne i32 {val}, 0"

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

    def _emit_store_field(self, res, instr):
        base = self.operand(instr.args[0])
        field_name = instr.args[1]
        fval = instr.args[2]
        base_type = instr.args[0].type
        idx = self.struct_field_indices[base_type][field_name]
        llvm_type = self.to_llvm_type(base_type)
        ftype = self.to_llvm_type(fval.type)
        foperand = self.operand(fval)
        return f"{res} = insertvalue {llvm_type} {base}, {ftype} {foperand}, {idx}"

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