import struct

from .builtins import BUILTIN_SIGS
from .to_high_ir import SSAValue

FLOAT_LLVM_TYPES = ("half", "float", "double")

INT_LLVM_BITS = {"i8": 8, "i16": 16, "i32": 32, "i64": 64, "i256": 256}

THREADON_INT_BITS = {
    "Int8": 8, "Int16": 16, "Int32": 32, "Int64": 64, "Int256": 256,
    "UInt8": 8, "UInt16": 16, "UInt32": 32, "UInt64": 64, "UInt256": 256,
}

class LLVMIRCompiler:


    def __init__(self,debug_mode=False,max_stack_depth=10_000):

        if max_stack_depth > 500_000:
            raise Exception("Current stack depth is to big")

        self.module = None
        self.struct_field_indices = {}
        self.used_intrinsics = set()
        self.used_c_runtime = set()
        self.used_bigint_helpers = set()
        self.used_pow_widths = set()
        self.string_globals = {}
        self.out = []
        self.debug_mode = debug_mode
        self.max_stack_depth = max_stack_depth

    def compile(self, module):
        self.module = module
        self.struct_field_indices = {}
        self.used_intrinsics = set()
        self.used_c_runtime = set()
        self.used_bigint_helpers = set()
        self.used_pow_widths = set()
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

        self._emit_bigint_helpers()


        self.out.append("")
        self._emit_input_helper()

        self.used_c_runtime.add("fprintf")
        self.used_c_runtime.add("exit")
        self.used_c_runtime.add("fflush")
        self.used_c_runtime.add("fgets")
        self.used_c_runtime.add("printf")
        self.used_c_runtime.add("strcspn")


        err_fmt = (
            "\x1b[1;31m[RUNTIME ERROR]\x1b[0m\n"
            "\x1b[33m│\x1b[0m \x1b[1m%s\x1b[0m\n"
            "\x1b[33m├─>\x1b[0m \x1b[90mLocation:\x1b[0m \x1b[36m%s\x1b[0m\n"
            "\x1b[33m└─>\x1b[0m \x1b[90mProcess terminated with exit code 1\x1b[0m\n"
        )
        fmt_g = self._string_global(err_fmt)
        fmt_sz = len(err_fmt.encode("utf-8")) + 1

        self.out.append("")
        self.out.append("define void @__threadon_debug_error(i8* %msg, i8* %ctx) {")
        self.out.append("  %se = load i8*, i8** @stderr")
        self.out.append(f"  %fmt = getelementptr inbounds [{fmt_sz} x i8], [{fmt_sz} x i8]* {fmt_g}, i64 0, i64 0")
        self.out.append("  call i32 (i8*, i8*, ...) @fprintf(i8* %se, i8* %fmt, i8* %msg, i8* %ctx)")
        self.out.append("  call void @exit(i32 1)")
        self.out.append("  unreachable")
        self.out.append("}")

        self._emit_stack_overflow_protection()

        if self.used_intrinsics:
            self.out.append("")
            for intrin in sorted(self.used_intrinsics):
                if intrin.startswith("llvm.pow.f"):
                    suffix = intrin.rsplit(".", 1)[1]
                    t = {"f16": "half", "f32": "float", "f64": "double"}[suffix]
                    self.out.append(f"declare {t} @{intrin}({t}, {t}) #0")
                elif intrin == "llvm.pow.i32":
                    self.out.append("declare i32 @llvm.pow.i32(i32, i32) #0")
                elif intrin.startswith(("llvm.floor.f", "llvm.ceil.f")):
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
            if "strtoull" in self.used_c_runtime:
                self.out.append("declare i64 @strtoull(i8*, i8**, i32)")
            if "strtod" in self.used_c_runtime:
                self.out.append("declare double @strtod(i8*, i8**)")
            if "strcasecmp" in self.used_c_runtime:
                self.out.append("declare i32 @strcasecmp(i8*, i8*)")
            if "exit" in self.used_c_runtime:
                self.out.append("declare void @exit(i32)")
            if "fprintf" in self.used_c_runtime:
                self.out.append("@stderr = external global i8*")
            if "snprintf" in self.used_c_runtime:
                self.out.append("declare i32 @snprintf(i8*, i64, i8*, ...)")
            if "strlen" in self.used_c_runtime:
                self.out.append("declare i64 @strlen(i8*)")
            self.out.append("")

        return "\n".join(self.out)

    def to_llvm_type(self, t):
        if t is None:
            return "void"
        if isinstance(t, str) and t.endswith("*"):
            base = self.to_llvm_type(t[:-1])
            return f"{base}*"
        if t == "int" or t == "Unknown" or t in THREADON_INT_BITS:
            return f"i{THREADON_INT_BITS.get(t, 32)}"
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

    def _is_unsigned(self, t):
        return isinstance(t, str) and t.startswith("UInt")

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

        self.current_func_name = func.name
        self.current_func_entry_label = func.blocks[0].label if func.blocks else None

        for block in func.blocks:
            self.emit_block(block)

        self.out.append("}")
        self.out.append("")
        
    def emit_block(self, block):
        self.out.append(f"{block.label}:")

        if (block.label == getattr(self, 'current_func_entry_label', None) and
                getattr(self, 'current_func_name', None) not in
                ("__threadon_check_depth", "__threadon_decrement_depth")):
            self.out.append("  call void @__threadon_check_depth()")

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
            if (block.terminator.op in ("ret", "ret_void") and
                    getattr(self, 'current_func_name', None) not in
                    ("__threadon_check_depth", "__threadon_decrement_depth")):
                self.out.append("  call void @__threadon_decrement_depth()")

            line = self.emit_terminator(block.terminator)
            self.out.append(f"  {line}")
    def _emit_stack_overflow_protection(self):


        self.out.append("")
        self.out.append("@__threadon_call_depth = global i32 0")

        msg = "Error: stack overflow detected"
        msg_gname = self._string_global(msg)
        msg_size = len(msg.encode("utf-8")) + 1

        ctx = f"Runtime stack depth exceeded (max {self.max_stack_depth})"
        ctx_gname = self._string_global(ctx)
        ctx_size = len(ctx.encode("utf-8")) + 1

        self.out.append("")
        self.out.append("define void @__threadon_check_depth() {")
        self.out.append("entry:")
        self.out.append("  %depth = load i32, i32* @__threadon_call_depth")
        self.out.append("  %new   = add i32 %depth, 1")
        self.out.append("  store i32 %new, i32* @__threadon_call_depth")
        self.out.append(f"  %cmp   = icmp sgt i32 %new, {self.max_stack_depth}")
        self.out.append("  br i1 %cmp, label %overflow, label %ok")
        self.out.append("overflow:")
        self.out.append(f"  %msg = getelementptr inbounds [{msg_size} x i8], [{msg_size} x i8]* {msg_gname}, i64 0, i64 0")
        self.out.append(f"  %ctx = getelementptr inbounds [{ctx_size} x i8], [{ctx_size} x i8]* {ctx_gname}, i64 0, i64 0")
        self.out.append("  call void @__threadon_debug_error(i8* %msg, i8* %ctx)")
        self.out.append("  unreachable")
        self.out.append("ok:")
        self.out.append("  ret void")
        self.out.append("}")

        self.out.append("")
        self.out.append("define void @__threadon_decrement_depth() {")
        self.out.append("entry:")
        self.out.append("  %depth = load i32, i32* @__threadon_call_depth")
        self.out.append("  %new   = sub i32 %depth, 1")
        self.out.append("  store i32 %new, i32* @__threadon_call_depth")
        self.out.append("  ret void")
        self.out.append("}")
    def _emit_cast(self, res, rtype, src, target_type):
        src_type = self.to_llvm_type(src.type)
        src_op = self.operand(src)
        src_unsigned = self._is_unsigned(src.type)
        tgt_unsigned = self._is_unsigned(target_type)

        if src_type == "i8*":
            if rtype in INT_LLVM_BITS:
                self.used_c_runtime.add("strtoull" if tgt_unsigned else "strtol")
                tmp = f"{res}_tmp"
                endptr = f"{res}_endptr"
                end_val = f"{res}_endval"
                is_null = f"{res}_isnull"
                bad_label = f"{res.lstrip('%')}_badconv"
                ok_label = f"{res.lstrip('%')}_okconv"
                
                lines = []
                
                if self.debug_mode:
                    self.used_c_runtime.add("exit")
                    msg = "Invalid integer conversion"
                    ctx = self._string_global("String → Integer cast")
                    msg_global = self._string_global(msg)
                    msg_size = len(msg.encode("utf-8")) + 1
                    emsg = f"{res.lstrip('%')}_emsg"
                    
                    lines.extend([
                        f"{endptr} = alloca i8*",
                        f"{tmp} = call i64 @{'strtoull' if tgt_unsigned else 'strtol'}(i8* {src_op}, i8** {endptr}, i32 10)",
                        f"{end_val} = load i8*, i8** {endptr}",
                        f"{is_null} = icmp eq i8* {end_val}, {src_op}",
                        f"br i1 {is_null}, label %{bad_label}, label %{ok_label}",
                        "",
                        f"{bad_label}:",
                        f"  %{emsg} = getelementptr inbounds [{msg_size} x i8], [{msg_size} x i8]* {msg_global}, i64 0, i64 0",
                        f"  call void @__threadon_debug_error(i8* %{emsg}, i8* {ctx})",
                        "  unreachable",
                        "",
                        f"{ok_label}:",
                    ])
                else:
                    lines.append(f"{tmp} = call i64 @{'strtoull' if tgt_unsigned else 'strtol'}(i8* {src_op}, i8** null, i32 10)")
                
                tb = INT_LLVM_BITS[rtype]
                if tb == 64:
                    lines.append(f"{res} = add i64 {tmp}, 0")
                elif tb < 64:
                    lines.append(f"{res} = trunc i64 {tmp} to {rtype}")
                else:
                    lines.append(f"{res} = {'zext' if tgt_unsigned else 'sext'} i64 {tmp} to {rtype}")
                return lines

            if rtype in FLOAT_LLVM_TYPES:
                self.used_c_runtime.add("strtod")
                tmp = f"{res}_tmp"
                endptr = f"{res}_endptr"
                end_val = f"{res}_endval"
                is_null = f"{res}_isnull"
                bad_label = f"{res.lstrip('%')}_badconv"
                ok_label = f"{res.lstrip('%')}_okconv"
                
                lines = []
                
                if self.debug_mode:
                    self.used_c_runtime.add("exit")
                    msg = "Invalid float conversion"
                    ctx = self._string_global("String → Float cast")
                    msg_global = self._string_global(msg)
                    msg_size = len(msg.encode("utf-8")) + 1
                    emsg = f"{res.lstrip('%')}_emsg"
                    
                    lines.extend([
                        f"{endptr} = alloca i8*",
                        f"{tmp} = call double @strtod(i8* {src_op}, i8** {endptr})",
                        f"{end_val} = load i8*, i8** {endptr}",
                        f"{is_null} = icmp eq i8* {end_val}, {src_op}",
                        f"br i1 {is_null}, label %{bad_label}, label %{ok_label}",
                        "",
                        f"{bad_label}:",
                        f"  %{emsg} = getelementptr inbounds [{msg_size} x i8], [{msg_size} x i8]* {msg_global}, i64 0, i64 0",
                        f"  call void @__threadon_debug_error(i8* %{emsg}, i8* {ctx})",
                        "  unreachable",
                        "",
                        f"{ok_label}:",
                    ])
                else:
                    lines.append(f"{tmp} = call double @strtod(i8* {src_op}, i8** null)")
                
                if rtype != "double":
                    lines.append(f"{res} = fptrunc double {tmp} to {rtype}")
                else:
                    lines.append(f"{res} = fadd double {tmp}, 0.0")
                return lines

            if rtype == "i1":
                self.used_c_runtime.add("strcasecmp")
                self.used_c_runtime.add("strlen")
                zero_global = self._string_global("0")
                false_global = self._string_global("false")
                z = f"{res}_z"
                f = f"{res}_f"
                ln = f"{res}_len"
                is_z = f"{res}_iszero"
                is_f = f"{res}_isfalse"
                is_empty = f"{res}_isempty"
                falsey1 = f"{res}_falsey1"
                falsey2 = f"{res}_falsey2"
                return [
                    f"{z} = call i32 @strcasecmp(i8* {src_op}, i8* {zero_global})",
                    f"{f} = call i32 @strcasecmp(i8* {src_op}, i8* {false_global})",
                    f"{ln} = call i64 @strlen(i8* {src_op})",
                    f"{is_z} = icmp eq i32 {z}, 0",
                    f"{is_f} = icmp eq i32 {f}, 0",
                    f"{is_empty} = icmp eq i64 {ln}, 0",
                    f"{falsey1} = or i1 {is_z}, {is_f}",
                    f"{falsey2} = or i1 {falsey1}, {is_empty}",
                    f"{res} = xor i1 {falsey2}, true"
                ]
            
            raise Exception(f"Cannot cast String to {target_type}")

        if rtype == "i8*":
            if src_type in INT_LLVM_BITS:
                self.used_c_runtime.add("snprintf")
                buf = f"{res}_buf"
                if src_type == "i256":
                    self.used_bigint_helpers.add("u256" if src_unsigned else "i256")
                    helper = "__threadon_to_string_u256" if src_unsigned else "__threadon_to_string_i256"
                    buf = f"{res}_buf"
                    ptr = f"{res}_ptr"
                    return [
                        f"{buf} = alloca [256 x i8]",
                        f"{ptr} = getelementptr [256 x i8], [256 x i8]* {buf}, i64 0, i64 0",
                        f"{res} = call i8* @{helper}(i256 {src_op}, i8* {ptr})"
                    ]
                if src_type == "i64":
                    fmt = self._string_global("%llu" if src_unsigned else "%lld")
                else:
                    fmt = self._string_global("%u" if src_unsigned else "%d")
                return [
                    f"{buf} = alloca [32 x i8]",
                    f"call i32 (i8*, i64, i8*, ...) @snprintf(i8* {buf}, i64 32, i8* {fmt}, {src_type} {src_op})",
                    f"{res} = getelementptr [32 x i8], [32 x i8]* {buf}, i64 0, i64 0"
                ]
            if src_type in FLOAT_LLVM_TYPES:
                self.used_c_runtime.add("snprintf")
                buf = f"{res}_buf"
                fmt = self._string_global("%f")
                if src_type == "double":
                    val = src_op
                else:
                    val = f"{res}_fd"
                    return [
                        f"{buf} = alloca [64 x i8]",
                        f"{val} = fpext {src_type} {src_op} to double",
                        f"call i32 (i8*, i64, i8*, ...) @snprintf(i8* {buf}, i64 64, i8* {fmt}, double {val})",
                        f"{res} = getelementptr [64 x i8], [64 x i8]* {buf}, i64 0, i64 0"
                    ]
                return [
                    f"{buf} = alloca [64 x i8]",
                    f"call i32 (i8*, i64, i8*, ...) @snprintf(i8* {buf}, i64 64, i8* {fmt}, double {val})",
                    f"{res} = getelementptr [64 x i8], [64 x i8]* {buf}, i64 0, i64 0"
                ]
            if src_type == "i1":
                self.used_c_runtime.add("snprintf")
                t_global = self._string_global("true")
                f_global = self._string_global("false")
                sel = f"{res}_sel"
                return [
                    f"{sel} = select i1 {src_op}, i8* {t_global}, i8* {f_global}",
                    f"{res} = getelementptr i8, i8* {sel}, i64 0"
                ]
            raise Exception(f"Cannot cast {src.type} to String")

        if src_type in INT_LLVM_BITS and rtype in INT_LLVM_BITS:
            sb, tb = INT_LLVM_BITS[src_type], INT_LLVM_BITS[rtype]
            if sb == tb:
                return f"{res} = add {rtype} {src_op}, 0"
            if sb > tb:
                return f"{res} = trunc {src_type} {src_op} to {rtype}"
            return f"{res} = {'zext' if src_unsigned else 'sext'} {src_type} {src_op} to {rtype}"

        if src_type in INT_LLVM_BITS and rtype in FLOAT_LLVM_TYPES:
            return f"{res} = {'uitofp' if src_unsigned else 'sitofp'} {src_type} {src_op} to {rtype}"

        if src_type in FLOAT_LLVM_TYPES and rtype in INT_LLVM_BITS:
            return f"{res} = {'fptoui' if tgt_unsigned else 'fptosi'} {src_type} {src_op} to {rtype}"

        if src_type in FLOAT_LLVM_TYPES and rtype in FLOAT_LLVM_TYPES:
            order = {"half": 0, "float": 1, "double": 2}
            if order[src_type] == order[rtype]:
                return f"{res} = fadd {rtype} {src_op}, 0.0"
            if order[src_type] < order[rtype]:
                return f"{res} = fpext {src_type} {src_op} to {rtype}"
            return f"{res} = fptrunc {src_type} {src_op} to {rtype}"

        if rtype == "i1":
            if src_type in INT_LLVM_BITS:
                return f"{res} = icmp ne {src_type} {src_op}, 0"
            if src_type in FLOAT_LLVM_TYPES:
                return f"{res} = fcmp une {src_type} {src_op}, 0.0"
            if src_type == "i1":
                return f"{res} = xor i1 {src_op}, false"
            raise Exception(f"Cannot cast {src.type} to Bool")

        if src_type == "i1" and rtype in INT_LLVM_BITS:
            return f"{res} = zext i1 {src_op} to {rtype}"

        if src_type == "i1" and rtype in FLOAT_LLVM_TYPES:
            return f"{res} = uitofp i1 {src_op} to {rtype}"

        raise Exception(f"Unsupported cast from {src_type} to {rtype}")
    def emit_instr(self, instr):
        op = instr.op
        res = instr.result.name if isinstance(instr.result, SSAValue) else None
        rtype = self.to_llvm_type(instr.result.type) if isinstance(instr.result, SSAValue) else None

        if op == "const":
            val = instr.args[0]
            return self._emit_const(res, rtype, val)
        if op == "cast":
            return self._emit_cast(res, rtype, instr.args[0], instr.args[1])
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

        if op in ("add", "sub", "mul", "div", "floordiv", "mod", "pow", "and", "or"):
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
        if isinstance(val, int) or (isinstance(val, str) and '.' not in val):
            v = int(val)
            width = int(rtype[1:])
            v %= (1 << width)
            if v >= (1 << (width - 1)):
                v -= (1 << width)
            return f"{res} = add {rtype} 0, {v}"
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


    def _emit_bitwise(self, res, op, left, right):
        l = self.operand(left)
        r = self.operand(right)
        ltype = self.to_llvm_type(left.type)
        unsigned = self._is_unsigned(left.type)
        op_map = {
            "shl": "shl",
            "shr": "lshr" if unsigned else "ashr",
            "bit_and": "and",
            "bit_or": "or",
            "bit_xor": "xor",
        }
        llvm_op = op_map[op]
        return f"{res} = {llvm_op} {ltype} {l}, {r}"
    def _emit_cmp(self, res, op, left, right):
        l = self.operand(left)
        r = self.operand(right)
        ltype = self.to_llvm_type(left.type)
        is_float = ltype in FLOAT_LLVM_TYPES
        unsigned = self._is_unsigned(left.type)

        pred_map = {
            "cmp_lt": "olt" if is_float else ("ult" if unsigned else "slt"),
            "cmp_gt": "ogt" if is_float else ("ugt" if unsigned else "sgt"),
            "cmp_le": "ole" if is_float else ("ule" if unsigned else "sle"),
            "cmp_ge": "oge" if is_float else ("uge" if unsigned else "sge"),
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

        return f"; unknown builtin {fname}"

    def _emit_print(self, res, args):
        self.used_c_runtime.add("printf")
        specs = []
        call_args = []
        lines = []
        for i, arg in enumerate(args):
            atype = self.to_llvm_type(arg.type)
            val = self.operand(arg)
            unsigned = self._is_unsigned(arg.type)

            if atype in ("i8", "i16", "i32", "i64"):
                if atype == "i64":
                    spec = "%llu" if unsigned else "%lld"
                    call_args.append(f"i64 {val}")
                else:
                    spec = "%u" if unsigned else "%d"
                    if atype != "i32":
                        ext = f"{res}_ext{i}"
                        lines.append(f"{ext} = {'zext' if unsigned else 'sext'} {atype} {val} to i32")
                        val = ext
                    call_args.append(f"i32 {val}")
            elif atype == "i256":
                self.used_bigint_helpers.add("u256" if unsigned else "i256")
                helper = "__threadon_to_string_u256" if unsigned else "__threadon_to_string_i256"
                buf = f"{res}_b{i}"
                ptr = f"{res}_p{i}"
                tmp = f"{res}_s{i}"
                lines.append(f"{buf} = alloca [256 x i8]")
                lines.append(f"{ptr} = getelementptr [256 x i8], [256 x i8]* {buf}, i64 0, i64 0")
                lines.append(f"{tmp} = call i8* @{helper}(i256 {val}, i8* {ptr})")
                spec = "%s"
                call_args.append(f"i8* {tmp}")
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
        psize = len(b"%s") + 1
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

    def _emit_bigint_helpers(self):
        kinds = set(self.used_bigint_helpers)
        if "i256" in kinds:
            kinds.add("u256")
        for kind in sorted(kinds):
            if kind == "u256":
                self._emit_to_string_u256()
            elif kind == "i256":
                self._emit_to_string_i256()
            self.out.append("")

        for width in sorted(self.used_pow_widths):
            self._emit_pow_helper(width)
            self.out.append("")

    def _emit_to_string_u256(self):
        self.out.append("define i8* @__threadon_to_string_u256(i256 %v, i8* %buf) {")
        self.out.append("entry:")
        self.out.append("  %end = getelementptr i8, i8* %buf, i64 255")
        self.out.append("  store i8 0, i8* %end")
        self.out.append("  %idx0 = getelementptr i8, i8* %end, i64 -1")
        self.out.append("  %iszero = icmp eq i256 %v, 0")
        self.out.append("  br i1 %iszero, label %zero, label %loop")
        self.out.append("zero:")
        self.out.append("  store i8 48, i8* %idx0")
        self.out.append("  ret i8* %idx0")
        self.out.append("loop:")
        self.out.append("  %vphi = phi i256 [ %v, %entry ], [ %q, %cont ]")
        self.out.append("  %iphi = phi i8* [ %idx0, %entry ], [ %p, %cont ]")
        self.out.append("  %r = urem i256 %vphi, 10")
        self.out.append("  %rt = trunc i256 %r to i8")
        self.out.append("  %d = add i8 48, %rt")
        self.out.append("  store i8 %d, i8* %iphi")
        self.out.append("  %q = udiv i256 %vphi, 10")
        self.out.append("  %qd = icmp eq i256 %q, 0")
        self.out.append("  br i1 %qd, label %done, label %cont")
        self.out.append("cont:")
        self.out.append("  %p = getelementptr i8, i8* %iphi, i64 -1")
        self.out.append("  br label %loop")
        self.out.append("done:")
        self.out.append("  ret i8* %iphi")
        self.out.append("}")

    def _emit_to_string_i256(self):
        self.out.append("define i8* @__threadon_to_string_i256(i256 %v, i8* %buf) {")
        self.out.append("entry:")
        self.out.append("  %neg = icmp slt i256 %v, 0")
        self.out.append("  %negv = sub i256 0, %v")
        self.out.append("  %abs = select i1 %neg, i256 %negv, i256 %v")
        self.out.append("  %s = call i8* @__threadon_to_string_u256(i256 %abs, i8* %buf)")
        self.out.append("  br i1 %neg, label %dash, label %body")
        self.out.append("dash:")
        self.out.append("  %dp = getelementptr i8, i8* %s, i64 -1")
        self.out.append("  store i8 45, i8* %dp")
        self.out.append("  ret i8* %dp")
        self.out.append("body:")
        self.out.append("  ret i8* %s")
        self.out.append("}")

    def _emit_pow_helper(self, width):
        t = f"i{width}"
        self.out.append(f"define {t} @__threadon_pow_i{width}({t} %base, {t} %exp) {{")
        self.out.append("entry:")
        self.out.append(f"  %res = alloca {t}")
        self.out.append(f"  store {t} 1, {t}* %res")
        self.out.append(f"  %cnt = alloca {t}")
        self.out.append(f"  store {t} 0, {t}* %cnt")
        self.out.append("  br label %loop")
        self.out.append("loop:")
        self.out.append(f"  %c = load {t}, {t}* %cnt")
        self.out.append(f"  %cmp = icmp ult {t} %c, %exp")
        self.out.append("  br i1 %cmp, label %body, label %done")
        self.out.append("body:")
        self.out.append(f"  %r0 = load {t}, {t}* %res")
        self.out.append(f"  %m = mul {t} %r0, %base")
        self.out.append(f"  store {t} %m, {t}* %res")
        self.out.append(f"  %c1 = load {t}, {t}* %cnt")
        self.out.append(f"  %n = add {t} %c1, 1")
        self.out.append(f"  store {t} %n, {t}* %cnt")
        self.out.append("  br label %loop")
        self.out.append("done:")
        self.out.append(f"  %r = load {t}, {t}* %res")
        self.out.append(f"  ret {t} %r")
        self.out.append("}")



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