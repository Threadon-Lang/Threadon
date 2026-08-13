import struct
import re 
import math
import sys

from .builtins import BUILTIN_SIGS
from .to_high_ir import SSAValue

FLOAT_LLVM_TYPES = ("half", "float", "double")

INT_LLVM_BITS = {"i8": 8, "i16": 16, "i32": 32, "i64": 64, "i256": 256}

THREADON_INT_BITS = {
    "Int8": 8, "Int16": 16, "Int32": 32, "Int64": 64, "Int256": 256,
    "UInt8": 8, "UInt16": 16, "UInt32": 32, "UInt64": 64, "UInt256": 256,
}

class LLVMIRCompiler:


    def __init__(self,debug_mode=False,max_stack_depth=10_000,flag_inf=False):

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
        self.flag_inf = flag_inf
        self.max_stack_depth = max_stack_depth
        self.block_end_label = {}
        self.used_checked_pow_widths = set()
        self.used_list_print = set()

    def compile(self, module):
        self.module = module 
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

        emitted = set()
        while True:
            pending = set(self.used_list_print) - emitted
            if not pending:
                break
            for elem_t in pending:
                self._emit_list_str_helper(elem_t)
                emitted.add(elem_t)


        self.out.append("")
        if "input_helper" in self.used_c_runtime:
            self._emit_input_helper()
        
        self.used_c_runtime.add("fprintf")
        self.used_c_runtime.add("exit")
        self.used_c_runtime.add("fflush")
        self.used_c_runtime.add("fgets")
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
            if "malloc" in self.used_c_runtime:
                self.out.append("declare i8* @malloc(i64)")
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
            return "i8"
        if isinstance(t, str) and t.startswith("List[") and t.endswith("]"):
            elem = self.to_llvm_type(t[5:-1])
            return f"{{ i64, {elem}* }}"
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

        self.block_end_label

        param_names = []
        param_types = []
        if entry:
            for instr in entry.instructions:
                if instr.op == "param":
                    param_names.append(instr.result.name)
                    param_types.append(self.to_llvm_type(instr.result.type))

        params_str = ", ".join(f"{t} {n}" for t, n in zip(param_types, param_names))
        ret_type = "void" if func.return_type == "NoneType" else self.to_llvm_type(func.return_type)

        self.out.append(f"define {ret_type} @{func.name}({params_str}) {{")

        self.current_func_name = func.name
        self.current_func_entry_label = func.blocks[0].label if func.blocks else None

        for block in func.blocks:
            self.emit_block(block)

        self.out.append("}")
        self.out.append("")
        
    def emit_block(self, block):
        self.out.append(f"{block.label}:")
        last_label = block.label

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
                stripped = line.strip()
                if (
                    stripped.endswith(":")
                    and len(stripped) > 1
                    and re.match(r"^[A-Za-z_.][A-Za-z0-9_.]*:$", stripped)
                ):
                    last_label = stripped[:-1]

        self.block_end_label[block.label] = last_label

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
    def _emit_binary(self, res, op, left, right):
        l = self.operand(left)
        r = self.operand(right)
        ltype = self.to_llvm_type(left.type)
        is_float = ltype in FLOAT_LLVM_TYPES
        unsigned = self._is_unsigned(left.type)

        if self.debug_mode and op in ("add", "sub", "mul") and not is_float:
            width = int(ltype[1:])
            max_val = (1 << width) - 1 if unsigned else (1 << (width - 1)) - 1
            min_val = 0 if unsigned else -(1 << (width - 1))
            
            bad_label = f"{res.lstrip('%')}_overflow"
            ok_label = f"{res.lstrip('%')}_ok"
            
            op_name = {"add": "addition", "sub": "subtraction", "mul": "multiplication"}[op]
            msg = f"Error: Integer overflow in {op_name}\n"
            msg_global = self._string_global(msg)
            msg_size = len(msg.encode("utf-8")) + 1
            
            ctx = f"Type: {left.type}, Operation: {left.name} {op} {right.name}"
            ctx_global = self._string_global(ctx)

            if ltype == "i256":
                return self._emit_i256_checked_binop(
                    res, op, l, r, unsigned, msg_global, msg_size, ctx_global
                )

            lines = []
            
            if op == "add":
                if unsigned:
                    tmp = f"{res}_tmp"
                    lines.append(f"{tmp} = add {ltype} {l}, {r}")
                    ovf = f"{res}_ovf"
                    lines.append(f"{ovf} = icmp ult {ltype} {tmp}, {l}")
                    lines.append(f"br i1 {ovf}, label %{bad_label}, label %{ok_label}")
                    lines.append("")
                    lines.append(f"{bad_label}:")
                    lines.append(f"  %{res.lstrip('%')}_emsg = getelementptr inbounds [{msg_size} x i8], [{msg_size} x i8]* {msg_global}, i64 0, i64 0")
                    lines.append(f"  call void @__threadon_debug_error(i8* %{res.lstrip('%')}_emsg, i8* {ctx_global})")
                    lines.append("  unreachable")
                    lines.append("")
                    lines.append(f"{ok_label}:")
                    lines.append(f"{res} = add {ltype} {l}, {r}")
                else:
                    intrin = f"llvm.sadd.with.overflow.{ltype}"
                    self.used_intrinsics.add(intrin)
                    tmp_res = f"{res}_ovf_res"
                    ovf_bit = f"{res}_ovf_bit"
                    lines.append(f"{tmp_res} = call {{{ltype}, i1}} @{intrin}({ltype} {l}, {ltype} {r})")
                    lines.append(f"{res} = extractvalue {{{ltype}, i1}} {tmp_res}, 0")
                    lines.append(f"{ovf_bit} = extractvalue {{{ltype}, i1}} {tmp_res}, 1")
                    lines.append(f"br i1 {ovf_bit}, label %{bad_label}, label %{ok_label}")
                    lines.append("")
                    lines.append(f"{bad_label}:")
                    lines.append(f"  %{res.lstrip('%')}_emsg = getelementptr inbounds [{msg_size} x i8], [{msg_size} x i8]* {msg_global}, i64 0, i64 0")
                    lines.append(f"  call void @__threadon_debug_error(i8* %{res.lstrip('%')}_emsg, i8* {ctx_global})")
                    lines.append("  unreachable")
                    lines.append("")
                    lines.append(f"{ok_label}:")
            
            elif op == "sub":
                if unsigned:
                    tmp = f"{res}_tmp"
                    lines.append(f"{tmp} = sub {ltype} {l}, {r}")
                    ovf = f"{res}_ovf"
                    lines.append(f"{ovf} = icmp ult {ltype} {l}, {r}")
                    lines.append(f"br i1 {ovf}, label %{bad_label}, label %{ok_label}")
                    lines.append("")
                    lines.append(f"{bad_label}:")
                    lines.append(f"  %{res.lstrip('%')}_emsg = getelementptr inbounds [{msg_size} x i8], [{msg_size} x i8]* {msg_global}, i64 0, i64 0")
                    lines.append(f"  call void @__threadon_debug_error(i8* %{res.lstrip('%')}_emsg, i8* {ctx_global})")
                    lines.append("  unreachable")
                    lines.append("")
                    lines.append(f"{ok_label}:")
                    lines.append(f"{res} = sub {ltype} {l}, {r}")
                else:
                    intrin = f"llvm.ssub.with.overflow.{ltype}"
                    self.used_intrinsics.add(intrin)
                    tmp_res = f"{res}_ovf_res"
                    ovf_bit = f"{res}_ovf_bit"
                    lines.append(f"{tmp_res} = call {{{ltype}, i1}} @{intrin}({ltype} {l}, {ltype} {r})")
                    lines.append(f"{res} = extractvalue {{{ltype}, i1}} {tmp_res}, 0")
                    lines.append(f"{ovf_bit} = extractvalue {{{ltype}, i1}} {tmp_res}, 1")
                    lines.append(f"br i1 {ovf_bit}, label %{bad_label}, label %{ok_label}")
                    lines.append("")
                    lines.append(f"{bad_label}:")
                    lines.append(f"  %{res.lstrip('%')}_emsg = getelementptr inbounds [{msg_size} x i8], [{msg_size} x i8]* {msg_global}, i64 0, i64 0")
                    lines.append(f"  call void @__threadon_debug_error(i8* %{res.lstrip('%')}_emsg, i8* {ctx_global})")
                    lines.append("  unreachable")
                    lines.append("")
                    lines.append(f"{ok_label}:")
            
            elif op == "mul":
                if unsigned:
                    tmp = f"{res}_tmp"
                    check = f"{res}_check"
                    ovf = f"{res}_ovf"
                    lines.append(f"{tmp} = mul {ltype} {l}, {r}")
                    is_zero = f"{res}_rzero"
                    lines.append(f"{is_zero} = icmp eq {ltype} {r}, 0")
                    lines.append(f"br i1 {is_zero}, label %{ok_label}, label %check_{res.lstrip('%')}")
                    lines.append("")
                    lines.append(f"check_{res.lstrip('%')}:")
                    lines.append(f"{check} = udiv {ltype} {tmp}, {r}")
                    lines.append(f"{ovf} = icmp ne {ltype} {check}, {l}")
                    lines.append(f"br i1 {ovf}, label %{bad_label}, label %{ok_label}")
                    lines.append("")
                    lines.append(f"{bad_label}:")
                    lines.append(f"  %{res.lstrip('%')}_emsg = getelementptr inbounds [{msg_size} x i8], [{msg_size} x i8]* {msg_global}, i64 0, i64 0")
                    lines.append(f"  call void @__threadon_debug_error(i8* %{res.lstrip('%')}_emsg, i8* {ctx_global})")
                    lines.append("  unreachable")
                    lines.append("")
                    lines.append(f"{ok_label}:")
                    lines.append(f"{res} = mul {ltype} {l}, {r}")
                else:
                    intrin = f"llvm.smul.with.overflow.{ltype}"
                    self.used_intrinsics.add(intrin)
                    tmp_res = f"{res}_ovf_res"
                    ovf_bit = f"{res}_ovf_bit"
                    lines.append(f"{tmp_res} = call {{{ltype}, i1}} @{intrin}({ltype} {l}, {ltype} {r})")
                    lines.append(f"{res} = extractvalue {{{ltype}, i1}} {tmp_res}, 0")
                    lines.append(f"{ovf_bit} = extractvalue {{{ltype}, i1}} {tmp_res}, 1")
                    lines.append(f"br i1 {ovf_bit}, label %{bad_label}, label %{ok_label}")
                    lines.append("")
                    lines.append(f"{bad_label}:")
                    lines.append(f"  %{res.lstrip('%')}_emsg = getelementptr inbounds [{msg_size} x i8], [{msg_size} x i8]* {msg_global}, i64 0, i64 0")
                    lines.append(f"  call void @__threadon_debug_error(i8* %{res.lstrip('%')}_emsg, i8* {ctx_global})")
                    lines.append("  unreachable")
                    lines.append("")
                    lines.append(f"{ok_label}:")
            
            return lines

        if op == "pow":
            if is_float:
                intrin = f"llvm.pow.{self._float_suffix(ltype)}"
                self.used_intrinsics.add(intrin)
                line = f"{res} = call {ltype} @{intrin}({ltype} {l}, {ltype} {r})"
                if self.flag_inf:
                    ctx = self._string_global(f"Float operation: {left.name} ** {right.name}")
                    return [line] + self._emit_finite_check(res, ltype, ctx)
                return line
            else:
                if self.debug_mode and ltype in INT_LLVM_BITS:
                    width = ltype[1:]
                    helper = f"__threadon_pow_{'u' if unsigned else 'i'}{width}_checked"
                    self.used_checked_pow_widths.add((width, unsigned))
                    return f"{res} = call {ltype} @{helper}({ltype} {l}, {ltype} {r})"
                if ltype == "i32":
                    self.used_intrinsics.add("llvm.pow.i32")
                    return f"{res} = call i32 @llvm.pow.i32(i32 {l}, i32 {r})"
                width = ltype[1:]
                self.used_pow_widths.add(width)
                return f"{res} = call {ltype} @__threadon_pow_i{width}({ltype} {l}, {ltype} {r})"
        if op == "floordiv" and is_float:
            intrin = f"llvm.floor.{self._float_suffix(ltype)}"
            self.used_intrinsics.add(intrin)
            tmp = f"{res}_div"
            lines = [
                f"{tmp} = fdiv {ltype} {l}, {r}",
                f"{res} = call {ltype} @{intrin}({ltype} {tmp})"
            ]
            if self.flag_inf:
                ctx = self._string_global(f"Float operation: {left.name} // {right.name}")
                return lines + self._emit_finite_check(res, ltype, ctx)
            return lines

        op_map = {
            "add": "fadd" if is_float else "add",
            "sub": "fsub" if is_float else "sub",
            "mul": "fmul" if is_float else "mul",
            "div": "fdiv" if is_float else ("udiv" if unsigned else "sdiv"),
            "floordiv": "udiv" if unsigned else "sdiv",
            "mod": "frem" if is_float else ("urem" if unsigned else "srem"),
            "and": "and",
            "or": "or",
        }
        llvm_op = op_map.get(op, "add")

        if self.debug_mode and op in ("div", "floordiv", "mod") and not is_float:
            self.used_c_runtime.add("exit")
            is_zero = f"{res}_iszero"
            bad_label = f"{res.lstrip('%')}_divzero"
            ok_label = f"{res.lstrip('%')}_divok"
            msg = "Error: Division by zero\n"
            msg_global = self._string_global(msg)
            msg_size = len(msg.encode("utf-8")) + 1
            ctx = self._string_global(f"Division: {left.name} {op} {right.name}")
            
            lines = [
                f"{is_zero} = icmp eq {ltype} {r}, 0",
                f"br i1 {is_zero}, label %{bad_label}, label %{ok_label}",
                "",
                f"{bad_label}:",
                f"  %{res.lstrip('%')}_emsg = getelementptr inbounds [{msg_size} x i8], [{msg_size} x i8]* {msg_global}, i64 0, i64 0",
                f"  call void @__threadon_debug_error(i8* %{res.lstrip('%')}_emsg, i8* {ctx})",
                "  unreachable",
                "",
                f"{ok_label}:",
            ]
            
            if not unsigned and ltype in INT_LLVM_BITS and ltype != "i256":
                width = INT_LLVM_BITS[ltype]
                min_val = -(1 << (width - 1))
                of_label = f"{res.lstrip('%')}_divof"
                ok2_label = f"{res.lstrip('%')}_divok2"
                
                is_min = f"{res}_ismin"
                is_m1 = f"{res}_ism1"
                of_cond = f"{res}_divofcond"
                
                msg2 = "Error: Signed division overflow (MIN / -1)\n"
                msg2_global = self._string_global(msg2)
                msg2_size = len(msg2.encode("utf-8")) + 1
                ctx2 = self._string_global(f"Signed division: {left.name} {op} {right.name}")
                
                lines.extend([
                    f"{is_min} = icmp eq {ltype} {l}, {min_val}",
                    f"{is_m1} = icmp eq {ltype} {r}, -1",
                    f"{of_cond} = and i1 {is_min}, {is_m1}",
                    f"br i1 {of_cond}, label %{of_label}, label %{ok2_label}",
                    "",
                    f"{of_label}:",
                    f"  %{res.lstrip('%')}_emsg2 = getelementptr inbounds [{msg2_size} x i8], [{msg2_size} x i8]* {msg2_global}, i64 0, i64 0",
                    f"  call void @__threadon_debug_error(i8* %{res.lstrip('%')}_emsg2, i8* {ctx2})",
                    "  unreachable",
                    "",
                    f"{ok2_label}:",
                ])
            
            lines.append(f"{res} = {llvm_op} {ltype} {l}, {r}")
            return lines
        
        if self.flag_inf and is_float:
            ctx = self._string_global(f"Float operation: {left.name} {op} {right.name}")
            return [f"{res} = {llvm_op} {ltype} {l}, {r}"] + self._emit_finite_check(
                res, ltype, ctx
            )
        return f"{res} = {llvm_op} {ltype} {l}, {r}"


    def _emit_i256_checked_binop(self, res, op, l, r, unsigned, msg_global, msg_size, ctx_global):
        ext = "zext" if unsigned else "sext"
        ex = f"{res}_ex"
        ey = f"{res}_ey"
        p = f"{res}_p"
        t = f"{res}_t"
        te = f"{res}_te"
        ovf = f"{res}_ovf"
        llvm_op = {"add": "add", "sub": "sub", "mul": "mul"}[op]
        bad = f"{res.lstrip('%')}_overflow"
        ok = f"{res.lstrip('%')}_ok"
        return [
            f"{ex} = {ext} i256 {l} to i512",
            f"{ey} = {ext} i256 {r} to i512",
            f"{p} = {llvm_op} i512 {ex}, {ey}",
            f"{t} = trunc i512 {p} to i256",
            f"{te} = {ext} i256 {t} to i512",
            f"{ovf} = icmp ne i512 {p}, {te}",
            f"br i1 {ovf}, label %{bad}, label %{ok}",
            "",
            f"{bad}:",
            f"  %{res.lstrip('%')}_emsg = getelementptr inbounds [{msg_size} x i8], [{msg_size} x i8]* {msg_global}, i64 0, i64 0",
            f"  call void @__threadon_debug_error(i8* %{res.lstrip('%')}_emsg, i8* {ctx_global})",
            "  unreachable",
            "",
            f"{ok}:",
            f"{res} = {llvm_op} i256 {l}, {r}",
        ]

    def _emit_cast(self, res, rtype, src, target_type):
        src_type = self.to_llvm_type(src.type)
        src_op = self.operand(src)
        src_unsigned = self._is_unsigned(src.type)
        tgt_unsigned = self._is_unsigned(target_type)

        if src_type == "i8*":
            if rtype in INT_LLVM_BITS:
                self.used_c_runtime.add("strtoull" if tgt_unsigned else "strtol")
                tmp = f"{res}_tmp"
                
                lines = []
                
                if self.debug_mode:
                    self.used_c_runtime.add("exit")
                    msg = "Invalid integer conversion"
                    ctx = self._string_global("String → Integer cast")
                    msg_global = self._string_global(msg)
                    msg_size = len(msg.encode("utf-8")) + 1
                    emsg = f"{res.lstrip('%')}_emsg"
                    endptr = f"{res}_endptr"
                    end_val = f"{res}_endval"
                    is_null = f"{res}_isnull"
                    bad_label = f"{res.lstrip('%')}_badconv"
                    ok_label = f"{res.lstrip('%')}_okconv"
                    
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
                
                if self.debug_mode and tb < 64:
                    range_bad = f"{res.lstrip('%')}_range_bad"
                    range_ok = f"{res.lstrip('%')}_range_ok"
                    range_msg = f"Error: Integer overflow in string conversion (value out of range for {target_type})\n"
                    range_msg_g = self._string_global(range_msg)
                    range_msg_sz = len(range_msg.encode("utf-8")) + 1
                    range_ctx = self._string_global(f"String → {target_type} cast")
                    range_emsg_name = f"{res.lstrip('%')}_range_emsg"
                    range_emsg = f"%{range_emsg_name}"
                    

                    if tgt_unsigned:
                        max_val = (1 << tb) - 1
                        lines.extend([
                            f"  %_{res.lstrip('%')}_toobig = icmp ugt i64 {tmp}, {max_val}",
                            f"  br i1 %_{res.lstrip('%')}_toobig, label %{range_bad}, label %{range_ok}",
                            "",
                            f"{range_bad}:",
                            f"  {range_emsg} = getelementptr inbounds [{range_msg_sz} x i8], [{range_msg_sz} x i8]* {range_msg_g}, i64 0, i64 0",
                            f"  call void @__threadon_debug_error(i8* {range_emsg}, i8* {range_ctx})",
                            "  unreachable",
                            "",
                            f"{range_ok}:",
                        ])
                    else:
                        max_val = (1 << (tb - 1)) - 1
                        min_val = -(1 << (tb - 1))
                        lines.extend([
                            f"  %_{res.lstrip('%')}_toobig = icmp sgt i64 {tmp}, {max_val}",
                            f"  %_{res.lstrip('%')}_toosmall = icmp slt i64 {tmp}, {min_val}",
                            f"  %_{res.lstrip('%')}_rangebad = or i1 %_{res.lstrip('%')}_toobig, %_{res.lstrip('%')}_toosmall",
                            f"  br i1 %_{res.lstrip('%')}_rangebad, label %{range_bad}, label %{range_ok}",
                            "",
                            f"{range_bad}:",
                            f"  {range_emsg} = getelementptr inbounds [{range_msg_sz} x i8], [{range_msg_sz} x i8]* {range_msg_g}, i64 0, i64 0",
                            f"  call void @__threadon_debug_error(i8* {range_emsg}, i8* {range_ctx})",
                            "  unreachable",
                            "",
                            f"{range_ok}:",
                        ])
                
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

                lines = []

                if self.debug_mode:
                    self.used_c_runtime.add("exit")
                    msg = "Invalid float conversion"
                    ctx = self._string_global("String → Float cast")
                    msg_global = self._string_global(msg)
                    msg_size = len(msg.encode("utf-8")) + 1
                    endptr = f"{res}_endptr"
                    end_val = f"{res}_endval"
                    is_null = f"{res}_isnull"
                    bad_label = f"{res.lstrip('%')}_badconv"
                    ok_label = f"{res.lstrip('%')}_okconv"

                    lines.extend([
                        f"{endptr} = alloca i8*",
                        f"{tmp} = call double @strtod(i8* {src_op}, i8** {endptr})",
                        f"{end_val} = load i8*, i8** {endptr}",
                        f"{is_null} = icmp eq i8* {end_val}, {src_op}",
                        f"br i1 {is_null}, label %{bad_label}, label %{ok_label}",
                        "",
                        f"{bad_label}:",
                        f"  %{res.lstrip('%')}_emsg = getelementptr inbounds [{msg_size} x i8], [{msg_size} x i8]* {msg_global}, i64 0, i64 0",
                        f"  call void @__threadon_debug_error(i8* %{res.lstrip('%')}_emsg, i8* {ctx})",
                        "  unreachable",
                        "",
                        f"{ok_label}:",
                    ])
                else:
                    lines.append(f"{tmp} = call double @strtod(i8* {src_op}, i8** null)")

                if rtype == "double":
                    lines.append(f"{res} = fadd double {tmp}, 0.0")
                else:
                    lines.append(f"{res} = fptrunc double {tmp} to {rtype}")
                if self.flag_inf:
                    fin_ctx = self._string_global("String → Float conversion")
                    lines.extend(self._emit_finite_check(res, rtype, fin_ctx))
                return lines

            if rtype == "i1":
                self.used_c_runtime.add("strcasecmp")
                false_g = self._string_global("false")
                zero_g = self._string_global("0")
                b0 = f"{res}_b0"
                is_empty = f"{res}_isempty"
                fcmp = f"{res}_fcmp"
                is_false = f"{res}_isfalse"
                zcmp = f"{res}_zcmp"
                is_zero = f"{res}_iszero"
                any_false = f"{res}_anyfalse"
                any_false2 = f"{res}_anyfalse2"

                return [
                    f"{b0} = load i8, i8* {src_op}",
                    f"{is_empty} = icmp eq i8 {b0}, 0",
                    f"{fcmp} = call i32 @strcasecmp(i8* {src_op}, i8* {false_g})",
                    f"{is_false} = icmp eq i32 {fcmp}, 0",
                    f"{zcmp} = call i32 @strcasecmp(i8* {src_op}, i8* {zero_g})",
                    f"{is_zero} = icmp eq i32 {zcmp}, 0",
                    f"{any_false} = or i1 {is_empty}, {is_false}",
                    f"{any_false2} = or i1 {any_false}, {is_zero}",
                    f"{res} = xor i1 {any_false2}, true",
                ]
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
            
            if self.debug_mode and sb > tb:
                bad_label = f"{res.lstrip('%')}_truncof"
                ok_label = f"{res.lstrip('%')}_truncok"
                
                if tgt_unsigned:
                    max_val = (1 << tb) - 1
                    msg = f"Error: Integer truncation overflow (value > {max_val})\n"
                    msg_global = self._string_global(msg)
                    msg_size = len(msg.encode("utf-8")) + 1
                    ctx = self._string_global(f"Int {src.type} → {target_type} cast")
                    
                    max_const = max_val
                    cmp_inst = f"{res}_toobig"
                    
                    lines = [
                        f"{cmp_inst} = icmp ugt {src_type} {src_op}, {max_const}",
                        f"br i1 {cmp_inst}, label %{bad_label}, label %{ok_label}",
                        "",
                        f"{bad_label}:",
                        f"  %{res.lstrip('%')}_emsg = getelementptr inbounds [{msg_size} x i8], [{msg_size} x i8]* {msg_global}, i64 0, i64 0",
                        f"  call void @__threadon_debug_error(i8* %{res.lstrip('%')}_emsg, i8* {ctx})",
                        "  unreachable",
                        "",
                        f"{ok_label}:",
                        f"{res} = trunc {src_type} {src_op} to {rtype}"
                    ]
                    return lines
                else:
                    max_val = (1 << (tb - 1)) - 1
                    min_val = -(1 << (tb - 1))
                    msg = f"Error: Integer truncation overflow\n"
                    msg_global = self._string_global(msg)
                    msg_size = len(msg.encode("utf-8")) + 1
                    ctx = self._string_global(f"Int {src.type} → {target_type} cast")
                    
                    too_big = f"{res}_toobig"
                    too_small = f"{res}_toosmall"
                    any_bad = f"{res}_anybad"
                    
                    lines = [
                        f"{too_big} = icmp sgt {src_type} {src_op}, {max_val}",
                        f"{too_small} = icmp slt {src_type} {src_op}, {min_val}",
                        f"{any_bad} = or i1 {too_big}, {too_small}",
                        f"br i1 {any_bad}, label %{bad_label}, label %{ok_label}",
                        "",
                        f"{bad_label}:",
                        f"  %{res.lstrip('%')}_emsg = getelementptr inbounds [{msg_size} x i8], [{msg_size} x i8]* {msg_global}, i64 0, i64 0",
                        f"  call void @__threadon_debug_error(i8* %{res.lstrip('%')}_emsg, i8* {ctx})",
                        "  unreachable",
                        "",
                        f"{ok_label}:",
                        f"{res} = trunc {src_type} {src_op} to {rtype}"
                    ]
                    return lines
            
            return f"{res} = trunc {src_type} {src_op} to {rtype}" if sb > tb else f"{res} = {'zext' if src_unsigned else 'sext'} {src_type} {src_op} to {rtype}"

        if src_type in INT_LLVM_BITS and rtype in FLOAT_LLVM_TYPES:
            line = f"{res} = {'uitofp' if src_unsigned else 'sitofp'} {src_type} {src_op} to {rtype}"
            if self.flag_inf:
                ctx = self._string_global(f"Int {src.type} → {target_type} conversion")
                return [line] + self._emit_finite_check(res, rtype, ctx)
            return line

        if src_type in FLOAT_LLVM_TYPES and rtype in INT_LLVM_BITS:
            if self.debug_mode:
                bad_label = f"{res.lstrip('%')}_fiof"
                ok_label = f"{res.lstrip('%')}_fiok"
                tb = INT_LLVM_BITS[rtype]
                
                if tgt_unsigned:
                    max_val = (1 << tb) - 1
                    msg = f"Error: Float-to-integer overflow\n"
                    msg_global = self._string_global(msg)
                    msg_size = len(msg.encode("utf-8")) + 1
                    ctx = self._string_global(f"Float {src.type} → {target_type} cast")
                    
                    fmax = f"{res}_fmax"
                    too_big = f"{res}_toobig"
                    too_small = f"{res}_toosmall"
                    any_bad = f"{res}_anybad"
                    
                    lines = [
                        f"{fmax} = sitofp i64 {max_val} to {src_type}",
                        f"{too_big} = fcmp ogt {src_type} {src_op}, {fmax}",
                        f"{too_small} = fcmp olt {src_type} {src_op}, 0.0",
                        f"{any_bad} = or i1 {too_big}, {too_small}",
                        f"br i1 {any_bad}, label %{bad_label}, label %{ok_label}",
                        "",
                        f"{bad_label}:",
                        f"  %{res.lstrip('%')}_emsg = getelementptr inbounds [{msg_size} x i8], [{msg_size} x i8]* {msg_global}, i64 0, i64 0",
                        f"  call void @__threadon_debug_error(i8* %{res.lstrip('%')}_emsg, i8* {ctx})",
                        "  unreachable",
                        "",
                        f"{ok_label}:",
                        f"{res} = fptoui {src_type} {src_op} to {rtype}"
                    ]
                    return lines
                else:
                    max_val = (1 << (tb - 1)) - 1
                    min_val = -(1 << (tb - 1))
                    msg = f"Error: Float-to-integer overflow\n"
                    msg_global = self._string_global(msg)
                    msg_size = len(msg.encode("utf-8")) + 1
                    ctx = self._string_global(f"Float {src.type} → {target_type} cast")
                    
                    fmax = f"{res}_fmax"
                    fmin = f"{res}_fmin"
                    too_big = f"{res}_toobig"
                    too_small = f"{res}_toosmall"
                    any_bad = f"{res}_anybad"
                    
                    lines = [
                        f"{fmax} = sitofp i64 {max_val} to {src_type}",
                        f"{fmin} = sitofp i64 {min_val} to {src_type}",
                        f"{too_big} = fcmp ogt {src_type} {src_op}, {fmax}",
                        f"{too_small} = fcmp olt {src_type} {src_op}, {fmin}",
                        f"{any_bad} = or i1 {too_big}, {too_small}",
                        f"br i1 {any_bad}, label %{bad_label}, label %{ok_label}",
                        "",
                        f"{bad_label}:",
                        f"  %{res.lstrip('%')}_emsg = getelementptr inbounds [{msg_size} x i8], [{msg_size} x i8]* {msg_global}, i64 0, i64 0",
                        f"  call void @__threadon_debug_error(i8* %{res.lstrip('%')}_emsg, i8* {ctx})",
                        "  unreachable",
                        "",
                        f"{ok_label}:",
                        f"{res} = fptosi {src_type} {src_op} to {rtype}"
                    ]
                    return lines
            
            return f"{res} = {'fptoui' if tgt_unsigned else 'fptosi'} {src_type} {src_op} to {rtype}"

        if src_type in FLOAT_LLVM_TYPES and rtype in FLOAT_LLVM_TYPES:
            order = {"half": 0, "float": 1, "double": 2}
            if order[src_type] == order[rtype]:
                return f"{res} = fadd {rtype} {src_op}, 0.0"
            if order[src_type] < order[rtype]:
                return f"{res} = fpext {src_type} {src_op} to {rtype}"
            line = f"{res} = fptrunc {src_type} {src_op} to {rtype}"
            if self.flag_inf:
                ctx = self._string_global(f"Float {src.type} → {target_type} narrowing")
                return [line] + self._emit_finite_check(res, rtype, ctx)
            return line

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


    def _emit_bitwise(self, res, op, left, right):
        l = self.operand(left)
        r = self.operand(right)
        ltype = self.to_llvm_type(left.type)
        unsigned = self._is_unsigned(left.type)
        
        if self.debug_mode and op in ("shl", "shr"):
            width = INT_LLVM_BITS.get(ltype, 64)
            bad_label = f"{res.lstrip('%')}_shftof"
            ok_label = f"{res.lstrip('%')}_shftok"
            msg = "Error: Shift amount >= bit-width\n"
            msg_global = self._string_global(msg)
            msg_size = len(msg.encode("utf-8")) + 1
            ctx = self._string_global(f"{op} on {left.type}")
            
            too_big = f"{res}_shftbig"
            
            lines = [
                f"{too_big} = icmp uge {ltype} {r}, {width}",
                f"br i1 {too_big}, label %{bad_label}, label %{ok_label}",
                "",
                f"{bad_label}:",
                f"  %{res.lstrip('%')}_emsg = getelementptr inbounds [{msg_size} x i8], [{msg_size} x i8]* {msg_global}, i64 0, i64 0",
                f"  call void @__threadon_debug_error(i8* %{res.lstrip('%')}_emsg, i8* {ctx})",
                "  unreachable",
                "",
                f"{ok_label}:",
            ]
            
            op_map = {
                "shl": "shl",
                "shr": "lshr" if unsigned else "ashr",
                "bit_and": "and",
                "bit_or": "or",
                "bit_xor": "xor",
            }
            llvm_op = op_map[op]
            lines.append(f"{res} = {llvm_op} {ltype} {l}, {r}")
            return lines
        
        op_map = {
            "shl": "shl",
            "shr": "lshr" if unsigned else "ashr",
            "bit_and": "and",
            "bit_or": "or",
            "bit_xor": "xor",
        }
        llvm_op = op_map[op]
        return f"{res} = {llvm_op} {ltype} {l}, {r}"
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
                        f"[ {self.operand(v)}, %{self.block_end_label.get(blk, blk)} ]"
                        for blk, v in instr.incoming
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

        if op == "list_init":
            return self._emit_list_init(res, rtype, instr)

        if op == "list_get":
            return self._emit_list_get(res, instr)

        if op == "list_set":
            return self._emit_list_set(res, instr)

        if op == "select":
            return self._emit_select(res, instr)
        if op == "alloca":
            return self._emit_alloca(res, instr.args[0])

        if op == "load":
            return self._emit_load(res, rtype, instr.args[0])

        if op == "store":
            return self._emit_store(instr.args[0], instr.args[1])


            bind(instr.result.name, current)
      
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

    def _error(self, msg):
        print(f"\033[91m\033[1mError:\033[0m {msg}", file=sys.stderr)
        raise SystemExit(1)

    def _f64_hex(self, fval):
        return format(struct.unpack('<Q', struct.pack('<d', fval))[0], '016X')

    def _emit_const(self, res, rtype, val):
        if rtype == "i8" and str(val) == "None":
            return f"{res} = add i8 0, 0"
        if rtype == "i1":
            vstr = "1" if str(val).lower() in ("true", "1") else "0"
            return f"{res} = add i1 0, {vstr}"
        if rtype == "i8*":
            return self._emit_string_const(res, val)
        if rtype in FLOAT_LLVM_TYPES:
            fval = float(val)
            if math.isinf(fval) or math.isnan(fval):
                if self.flag_inf:
                    self._error(
                        f"non-finite floating-point constant {fval} in {rtype} "
                        f"(--flag-inf enabled)"
                    )
                return f"{res} = fadd {rtype} 0.0, 0x{self._f64_hex(fval)}"
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
        if rtype.startswith("{"):
            return f"{res} = insertvalue {rtype} undef, i64 0, 0"
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
        if src_type.startswith("{"):
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
            if self.debug_mode and src_type in INT_LLVM_BITS:
                return self._emit_checked_neg(res, src, src_type, operand.type)
            return f"{res} = sub {src_type} 0, {src}"
        if op == "not":
            return f"{res} = xor i1 {src}, true"
        return f"; unknown unary {op}"

    def _emit_checked_neg(self, res, src, src_type, type_):
        self.used_c_runtime.add("exit")
        bad = f"{res.lstrip('%')}_negoof"
        ok = f"{res.lstrip('%')}_negok"
        if self._is_unsigned(type_):
            msg = "Error: Unsigned integer underflow in negation\n"
            msg_global = self._string_global(msg)
            msg_size = len(msg.encode("utf-8")) + 1
            ctx = self._string_global(f"Unary negate on {type_}")
            is_zero = f"{res}_iszero"
            return [
                f"{is_zero} = icmp eq {src_type} {src}, 0",
                f"br i1 {is_zero}, label %{ok}, label %{bad}",
                "",
                f"{bad}:",
                f"  %{res.lstrip('%')}_emsg = getelementptr inbounds [{msg_size} x i8], [{msg_size} x i8]* {msg_global}, i64 0, i64 0",
                f"  call void @__threadon_debug_error(i8* %{res.lstrip('%')}_emsg, i8* {ctx})",
                "  unreachable",
                "",
                f"{ok}:",
                f"{res} = sub {src_type} 0, {src}",
            ]
        width = INT_LLVM_BITS[src_type]
        min_val = -(1 << (width - 1))
        msg = "Error: Integer overflow in negation\n"
        msg_global = self._string_global(msg)
        msg_size = len(msg.encode("utf-8")) + 1
        ctx = self._string_global(f"Unary negate on {type_}")
        is_min = f"{res}_ismin"
        return [
            f"{is_min} = icmp eq {src_type} {src}, {min_val}",
            f"br i1 {is_min}, label %{bad}, label %{ok}",
            "",
            f"{bad}:",
            f"  %{res.lstrip('%')}_emsg = getelementptr inbounds [{msg_size} x i8], [{msg_size} x i8]* {msg_global}, i64 0, i64 0",
            f"  call void @__threadon_debug_error(i8* %{res.lstrip('%')}_emsg, i8* {ctx})",
            "  unreachable",
            "",
            f"{ok}:",
            f"{res} = sub {src_type} 0, {src}",
        ]
    def _emit_finite_check(self, res, rtype, ctx):
        self.used_c_runtime.add("exit")
        bad = f"{res.lstrip('%')}_nonfinite"
        ok = f"{res.lstrip('%')}_okfinite"
        msg = "Error: Non-finite float value (inf or NaN)\n"
        msg_global = self._string_global(msg)
        msg_size = len(msg.encode("utf-8")) + 1
        is_nan = f"{res}_isnan"
        is_pinf = f"{res}_ispinf"
        is_ninf = f"{res}_isninf"
        bad1 = f"{res}_nonfin1"
        bad2 = f"{res}_nonfin2"
        return [
            f"{is_nan} = fcmp uno {rtype} {res}, 0.0",
            f"{is_pinf} = fcmp oeq {rtype} {res}, 0x7FF0000000000000",
            f"{is_ninf} = fcmp oeq {rtype} {res}, 0xFFF0000000000000",
            f"{bad1} = or i1 {is_nan}, {is_pinf}",
            f"{bad2} = or i1 {bad1}, {is_ninf}",
            f"br i1 {bad2}, label %{bad}, label %{ok}",
            "",
            f"{bad}:",
            f"  %{res.lstrip('%')}_femsg = getelementptr inbounds [{msg_size} x i8], [{msg_size} x i8]* {msg_global}, i64 0, i64 0",
            f"  call void @__threadon_debug_error(i8* %{res.lstrip('%')}_femsg, i8* {ctx})",
            "  unreachable",
            "",
            f"{ok}:",
        ]

    def _float_suffix(self, ltype):
        return {"half": "f16", "float": "f32", "double": "f64"}[ltype]


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
        if instr.result.type == "NoneType":
            call = f"call void @{fname}({args_str})"
            if res is None:
                return call
            return [call, f"{res} = add i8 0, 0"]
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

            if arg.type == "NoneType":
                none_global = self._string_global("None")
                ptr = f"{res}_none{i}"
                lines.append(f"{ptr} = getelementptr inbounds [5 x i8], [5 x i8]* {none_global}, i64 0, i64 0")
                spec = "%s"
                call_args.append(f"i8* {ptr}")
            elif atype in ("i8", "i16", "i32", "i64"):
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
            elif isinstance(arg.type, str) and arg.type.startswith("List["):
                elem_t = arg.type[5:-1]
                if self.to_llvm_type(elem_t).startswith("%struct"):
                    raise Exception(f"print: unsupported list element type '{elem_t}'")
                tag = re.sub(r"[^A-Za-z0-9]", "_", elem_t)
                self.used_list_print.add(elem_t)
                spec = "%s"
                tmp = f"{res}_list{i}"
                lines.append(
                    f"{tmp} = call i8* @__threadon_list_str_{tag}({atype} {val})"
                )
                call_args.append(f"i8* {tmp}")
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

        for width, unsigned in sorted(self.used_checked_pow_widths):
            self._emit_pow_helper_checked(width, unsigned)
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
    def _emit_pow_helper_checked(self, width, unsigned):
        t = f"i{width}"
        ext = "zext" if unsigned else "sext"
        sign = "u" if unsigned else "i"
        self.out.append(f"define {t} @__threadon_pow_{sign}{width}_checked({t} %base, {t} %exp) {{")
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
        if width == 256:
            self.out.append(f"  %re = {ext} {t} %r0 to i512")
            self.out.append(f"  %be = {ext} {t} %base to i512")
            self.out.append("  %pe = mul i512 %re, %be")
            self.out.append(f"  %ovf_val = trunc i512 %pe to {t}")
            self.out.append(f"  %pte = {ext} {t} %ovf_val to i512")
            self.out.append("  %ovf_bit = icmp ne i512 %pe, %pte")
        else:
            self.out.append(f"  %ovf_res = call {{{t}, i1}} @llvm.{'umul' if unsigned else 'smul'}.with.overflow.{t}({t} %r0, {t} %base)")
            self.out.append(f"  %ovf_val = extractvalue {{{t}, i1}} %ovf_res, 0")
            self.out.append(f"  %ovf_bit = extractvalue {{{t}, i1}} %ovf_res, 1")
        self.out.append("  br i1 %ovf_bit, label %overflow, label %cont")
        self.out.append("overflow:")

        msg = "Error: Integer overflow in power operation\n"
        msg_g = self._string_global(msg)
        msg_sz = len(msg.encode("utf-8")) + 1
        ctx = self._string_global(f"{sign}{width} power overflow")
        self.out.append(f"  %emsg = getelementptr inbounds [{msg_sz} x i8], [{msg_sz} x i8]* {msg_g}, i64 0, i64 0")
        self.out.append(f"  call void @__threadon_debug_error(i8* %emsg, i8* {ctx})")
        self.out.append("  unreachable")
        self.out.append("cont:")
        self.out.append(f"  store {t} %ovf_val, {t}* %res")
        self.out.append(f"  %c1 = load {t}, {t}* %cnt")
        self.out.append(f"  %n = add {t} %c1, 1")
        self.out.append(f"  store {t} %n, {t}* %cnt")
        self.out.append("  br label %loop")
        self.out.append("done:")
        self.out.append(f"  %r = load {t}, {t}* %res")
        self.out.append(f"  ret {t} %r")
        self.out.append("}")
        if width != 256:
            self.used_intrinsics.add(f"llvm.{'umul' if unsigned else 'smul'}.with.overflow.{t}")
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
    def _emit_list_str_helper(self, elem_t):
        elem_llvm = self.to_llvm_type(elem_t)
        list_llvm = f"{{ i64, {elem_llvm}* }}"
        tag = re.sub(r"[^A-Za-z0-9]", "_", elem_t)
        buf_size = 4096

        self.used_c_runtime.update(["snprintf", "strlen"])
        bracket_open = self._string_global("[")
        bracket_close = self._string_global("]")
        separator = self._string_global(", ")

        out = []
        out.append(f"define i8* @__threadon_list_str_{tag}({list_llvm} %list) {{")
        out.append("entry:")
        out.append(f"  %len = extractvalue {list_llvm} %list, 0")
        out.append(f"  %data = extractvalue {list_llvm} %list, 1")
        out.append(f"  %buf = alloca [{buf_size} x i8]")
        out.append(f"  %bufp = getelementptr inbounds [{buf_size} x i8], [{buf_size} x i8]* %buf, i64 0, i64 0")
        out.append(f"  %f1 = getelementptr inbounds [2 x i8], [2 x i8]* {bracket_open}, i64 0, i64 0")
        out.append(f"  %c1 = call i32 (i8*, i64, i8*, ...) @snprintf(i8* %bufp, i64 {buf_size}, i8* %f1)")
        out.append("  %e0 = icmp eq i64 %len, 0")
        out.append("  br i1 %e0, label %close, label %loop")
        out.append("")
        out.append("loop:")
        out.append("  %i = phi i64 [ 0, %entry ], [ %inc, %elem ]")
        out.append("  %off = phi i64 [ 1, %entry ], [ %newoff, %elem ]")
        out.append("  %nz = icmp ne i64 %i, 0")
        out.append("  br i1 %nz, label %sep, label %elem")
        out.append("")
        out.append("sep:")
        out.append("  %psep = getelementptr i8, i8* %bufp, i64 %off")
        out.append(f"  %fsep = getelementptr inbounds [3 x i8], [3 x i8]* {separator}, i64 0, i64 0")
        out.append(f"  %csep = call i32 (i8*, i64, i8*, ...) @snprintf(i8* %psep, i64 {buf_size}, i8* %fsep)")
        out.append("  %offsep = add i64 %off, 2")
        out.append("  br label %elem")
        out.append("")
        out.append("elem:")
        out.append("  %boff = phi i64 [ %off, %loop ], [ %offsep, %sep ]")
        out.append(f"  %dp = getelementptr {elem_llvm}, {elem_llvm}* %data, i64 %i")
        out.append(f"  %v = load {elem_llvm}, {elem_llvm}* %dp")
        out.append(f"  %pe = getelementptr i8, i8* %bufp, i64 %boff")

        tmp = 0

        def fresh(base):
            nonlocal tmp
            tmp += 1
            return f"%{base}{tmp}"

        if elem_t.startswith("List["):
            inner_elem = elem_t[5:-1]
            inner_tag = re.sub(r"[^A-Za-z0-9]", "_", inner_elem)
            inner_llvm = self.to_llvm_type(elem_t)
            self.used_list_print.add(inner_elem)
            es = fresh("es")
            out.append(f"  {es} = call i8* @__threadon_list_str_{inner_tag}({inner_llvm} %v)")
            out.append(f"  %f = getelementptr inbounds [3 x i8], [3 x i8]* {self._string_global('%s')}, i64 0, i64 0")
            out.append(f"  %c = call i32 (i8*, i64, i8*, ...) @snprintf(i8* %pe, i64 {buf_size}, i8* %f, i8* {es})")
        elif elem_t == "NoneType":
            none_g = self._string_global("None")
            np = fresh("np")
            out.append(f"  {np} = getelementptr inbounds [5 x i8], [5 x i8]* {none_g}, i64 0, i64 0")
            out.append(f"  %f = getelementptr inbounds [3 x i8], [3 x i8]* {self._string_global('%s')}, i64 0, i64 0")
            out.append(f"  %c = call i32 (i8*, i64, i8*, ...) @snprintf(i8* %pe, i64 {buf_size}, i8* %f, i8* {np})")
        elif elem_llvm in INT_LLVM_BITS:
            unsigned = self._is_unsigned(elem_t)
            if elem_llvm == "i64":
                fmt = "%llu" if unsigned else "%lld"
                out.append(f"  %f = getelementptr inbounds [5 x i8], [5 x i8]* {self._string_global(fmt)}, i64 0, i64 0")
                out.append(f"  %c = call i32 (i8*, i64, i8*, ...) @snprintf(i8* %pe, i64 {buf_size}, i8* %f, {elem_llvm} %v)")
            elif elem_llvm == "i32":
                fmt = "%u" if unsigned else "%d"
                out.append(f"  %f = getelementptr inbounds [3 x i8], [3 x i8]* {self._string_global(fmt)}, i64 0, i64 0")
                out.append(f"  %c = call i32 (i8*, i64, i8*, ...) @snprintf(i8* %pe, i64 {buf_size}, i8* %f, i32 %v)")
            else:
                ext = "zext" if unsigned else "sext"
                fmt = "%u" if unsigned else "%d"
                ve = fresh("ve")
                out.append(f"  {ve} = {ext} {elem_llvm} %v to i32")
                out.append(f"  %f = getelementptr inbounds [3 x i8], [3 x i8]* {self._string_global(fmt)}, i64 0, i64 0")
                out.append(f"  %c = call i32 (i8*, i64, i8*, ...) @snprintf(i8* %pe, i64 {buf_size}, i8* %f, i32 {ve})")
        elif elem_llvm == "i256":
            unsigned = self._is_unsigned(elem_t)
            self.used_bigint_helpers.add("u256" if unsigned else "i256")
            helper = "__threadon_to_string_u256" if unsigned else "__threadon_to_string_i256"
            eb = fresh("eb")
            ep = fresh("ep")
            es = fresh("es")
            out.append(f"  {eb} = alloca [256 x i8]")
            out.append(f"  {ep} = getelementptr [256 x i8], [256 x i8]* {eb}, i64 0, i64 0")
            out.append(f"  {es} = call i8* @{helper}(i256 %v, i8* {ep})")
            out.append(f"  %f = getelementptr inbounds [3 x i8], [3 x i8]* {self._string_global('%s')}, i64 0, i64 0")
            out.append(f"  %c = call i32 (i8*, i64, i8*, ...) @snprintf(i8* %pe, i64 {buf_size}, i8* %f, i8* {es})")
        elif elem_llvm in ("half", "float"):
            ve = fresh("ve")
            out.append(f"  {ve} = fpext {elem_llvm} %v to double")
            out.append(f"  %f = getelementptr inbounds [3 x i8], [3 x i8]* {self._string_global('%f')}, i64 0, i64 0")
            out.append(f"  %c = call i32 (i8*, i64, i8*, ...) @snprintf(i8* %pe, i64 {buf_size}, i8* %f, double {ve})")
        elif elem_llvm == "double":
            out.append(f"  %f = getelementptr inbounds [3 x i8], [3 x i8]* {self._string_global('%f')}, i64 0, i64 0")
            out.append(f"  %c = call i32 (i8*, i64, i8*, ...) @snprintf(i8* %pe, i64 {buf_size}, i8* %f, double %v)")
        elif elem_llvm == "i1":
            ttrue = self._string_global("true")
            tfalse = self._string_global("false")
            tpt = fresh("tpt")
            tpf = fresh("tpf")
            tsel = fresh("tsel")
            out.append(f"  {tpt} = getelementptr inbounds [5 x i8], [5 x i8]* {ttrue}, i64 0, i64 0")
            out.append(f"  {tpf} = getelementptr inbounds [6 x i8], [6 x i8]* {tfalse}, i64 0, i64 0")
            out.append(f"  {tsel} = select i1 %v, i8* {tpt}, i8* {tpf}")
            out.append(f"  %f = getelementptr inbounds [3 x i8], [3 x i8]* {self._string_global('%s')}, i64 0, i64 0")
            out.append(f"  %c = call i32 (i8*, i64, i8*, ...) @snprintf(i8* %pe, i64 {buf_size}, i8* %f, i8* {tsel})")
        elif elem_llvm == "i8*":
            out.append(f"  %f = getelementptr inbounds [3 x i8], [3 x i8]* {self._string_global('%s')}, i64 0, i64 0")
            out.append(f"  %c = call i32 (i8*, i64, i8*, ...) @snprintf(i8* %pe, i64 {buf_size}, i8* %f, i8* %v)")
        else:
            raise Exception(f"list print: unsupported element type '{elem_t}'")

        out.append("  %inc = add i64 %i, 1")
        out.append("  %newoff = call i64 @strlen(i8* %bufp)")
        out.append("  %done = icmp eq i64 %inc, %len")
        out.append("  br i1 %done, label %close, label %loop")
        out.append("")
        out.append("close:")
        out.append("  %coff = phi i64 [ 1, %entry ], [ %newoff, %elem ]")
        out.append("  %pc = getelementptr i8, i8* %bufp, i64 %coff")
        out.append(f"  %f2 = getelementptr inbounds [2 x i8], [2 x i8]* {bracket_close}, i64 0, i64 0")
        out.append(f"  %c2 = call i32 (i8*, i64, i8*, ...) @snprintf(i8* %pc, i64 {buf_size}, i8* %f2)")
        out.append("  ret i8* %bufp")
        out.append("}")
        out.append("")

        for line in out:
            self.out.append(line)

    def _zero_value(self, t):
        if t == "bool" or t in ("Bool", "Boolean"):
            return "false"
        if t in THREADON_INT_BITS or t == "int":
            return "0"
        if t == "float" or t in ("Float16", "Float32", "Float64"):
            return "0.0"
        if t == "String":
            return "null"
        return None

    def _emit_struct_init(self, res, instr):
        struct_name = instr.args[0]
        llvm_type = f"%struct.{struct_name}"
        lines = []
        current = "undef"

        field_updates = []
        filled = set()
        for k in range(1, len(instr.args), 2):
            fname = instr.args[k]
            fval = instr.args[k + 1]
            ftype = self.to_llvm_type(fval.type)
            foperand = self.operand(fval)
            idx = self.struct_field_indices[struct_name][fname]
            field_updates.append((idx, ftype, foperand))
            filled.add(fname)

        for fname, ftype in self.module.types[struct_name].items():
            if fname in filled:
                continue
            zv = self._zero_value(ftype)
            if zv is not None:
                idx = self.struct_field_indices[struct_name][fname]
                field_updates.append((idx, self.to_llvm_type(ftype), zv))

        if not field_updates:
            return f"{res} = select i1 false, {llvm_type} undef, {llvm_type} undef"

        field_updates.sort(key=lambda x: x[0])

        for i, (idx, ftype, foperand) in enumerate(field_updates):
            if i == len(field_updates) - 1:
                lines.append(f"{res} = insertvalue {llvm_type} {current}, {ftype} {foperand}, {idx}")
            else:
                tmp = f"{res}_s{i}"
                lines.append(f"{tmp} = insertvalue {llvm_type} {current}, {ftype} {foperand}, {idx}")
                current = tmp

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

    def _split_llvm_fields(self, inner):
        fields = []
        depth = 0
        current = []
        for ch in inner:
            if ch in "{<":
                depth += 1
            elif ch in "}>":
                depth -= 1
            if ch == "," and depth == 0:
                fields.append("".join(current).strip())
                current = []
            else:
                current.append(ch)
        if current:
            fields.append("".join(current).strip())
        return fields

    def _size_and_align(self, llvm_type):
        if llvm_type in ("i1", "i8"):
            return (1, 1)
        if llvm_type in ("i16", "half"):
            return (2, 2)
        if llvm_type in ("i32", "float"):
            return (4, 4)
        if llvm_type in ("i64", "double", "i8*"):
            return (8, 8)
        if llvm_type == "i256":
            return (32, 32)
        if llvm_type.endswith("*"):
            return (8, 8)
        if llvm_type.startswith("%struct."):
            name = llvm_type[len("%struct."):]
            fields = self.module.types.get(name)
            if fields is None:
                raise Exception(f"Cannot determine layout of unknown struct '{name}'")
            size = 0
            max_align = 1
            for ftype in fields.values():
                fs, fa = self._size_and_align(self.to_llvm_type(ftype))
                size = (size + fa - 1) // fa * fa
                size += fs
                max_align = max(max_align, fa)
            size = (size + max_align - 1) // max_align * max_align
            return (size, max_align)
        if llvm_type.startswith("{") and llvm_type.endswith("}"):
            inner = llvm_type[1:-1].strip()
            size = 0
            max_align = 1
            for field in self._split_llvm_fields(inner):
                fs, fa = self._size_and_align(field)
                size = (size + fa - 1) // fa * fa
                size += fs
                max_align = max(max_align, fa)
            size = (size + max_align - 1) // max_align * max_align
            return (size, max_align)
        raise Exception(f"Cannot determine size of LLVM type '{llvm_type}'")

    def _llvm_sizeof(self, llvm_type):
        size, _ = self._size_and_align(llvm_type)
        return size

    def _emit_list_init(self, res, rtype, instr):
        elem_type = instr.args[0]
        elems = instr.args[1:]
        elem_llvm = self.to_llvm_type(elem_type)
        n = len(elems)
        elem_size = self._llvm_sizeof(elem_llvm)
        total = n * elem_size
        self.used_c_runtime.add("malloc")
        lines = []
        raw = f"{res}_raw"
        lines.append(f"{raw} = call i8* @malloc(i64 {total})")
        data = f"{res}_data"
        lines.append(f"{data} = bitcast i8* {raw} to {elem_llvm}*")
        for i, e in enumerate(elems):
            val = self.operand(e)
            if i == 0:
                lines.append(f"store {elem_llvm} {val}, {elem_llvm}* {data}")
            else:
                ptr = f"{res}_p{i}"
                lines.append(
                    f"{ptr} = getelementptr {elem_llvm}, {elem_llvm}* {data}, i64 {i}"
                )
                lines.append(f"store {elem_llvm} {val}, {elem_llvm}* {ptr}")
        v0 = f"{res}_v0"
        lines.append(f"{v0} = insertvalue {rtype} undef, i64 {n}, 0")
        lines.append(f"{res} = insertvalue {rtype} {v0}, {elem_llvm}* {data}, 1")
        return lines

    def _emit_list_access_lines(self, res, instr):
        obj = instr.args[0]
        idx = instr.args[1]
        obj_type = obj.type
        elem_type = obj_type[5:-1]
        elem_llvm = self.to_llvm_type(elem_type)
        llvm_type = self.to_llvm_type(obj_type)
        obj_op = self.operand(obj)
        idx_op = self.operand(idx)
        idx_llvm = self.to_llvm_type(idx.type)

        lenv = f"{res}_len"
        data = f"{res}_data"
        lines = [
            f"{lenv} = extractvalue {llvm_type} {obj_op}, 0",
            f"{data} = extractvalue {llvm_type} {obj_op}, 1",
        ]

        if idx_llvm == "i64":
            idx64 = f"{res}_idx64"
            lines.append(f"{idx64} = add i64 {idx_op}, 0")
        elif idx_llvm in INT_LLVM_BITS:
            ext = "zext" if self._is_unsigned(idx.type) else "sext"
            idx64 = f"{res}_idx64"
            lines.append(f"{idx64} = {ext} {idx_llvm} {idx_op} to i64")
        else:
            raise Exception(f"list index must be an integer, got {idx.type}")

        if self.debug_mode:
            self.used_c_runtime.add("exit")
            msg = "Error: List index out of bounds\n"
            msg_global = self._string_global(msg)
            msg_size = len(msg.encode("utf-8")) + 1
            ctx = self._string_global(f"List index on {obj_type}")
            bad = f"{res.lstrip('%')}_oob"
            ok = f"{res.lstrip('%')}_ok"
            oob = f"{res}_oobc"
            if self._is_unsigned(idx.type):
                lines.append(f"{oob} = icmp uge i64 {idx64}, {lenv}")
                lines.append(f"br i1 {oob}, label %{bad}, label %{ok}")
            else:
                neg = f"{res}_neg"
                lines.append(f"{neg} = icmp slt {idx_llvm} {idx_op}, 0")
                lines.append(f"br i1 {neg}, label %{bad}, label %chk_{res.lstrip('%')}")
                lines.append(f"chk_{res.lstrip('%')}:")
                lines.append(f"{oob} = icmp uge i64 {idx64}, {lenv}")
                lines.append(f"br i1 {oob}, label %{bad}, label %{ok}")
            lines.append(f"{bad}:")
            lines.append(
                f"  %{res.lstrip('%')}_emsg = getelementptr inbounds "
                f"[{msg_size} x i8], [{msg_size} x i8]* {msg_global}, i64 0, i64 0"
            )
            lines.append(
                f"  call void @__threadon_debug_error(i8* %{res.lstrip('%')}_emsg, i8* {ctx})"
            )
            lines.append("  unreachable")
            lines.append(f"{ok}:")

        return lines, elem_llvm, lenv, data

    def _emit_list_get(self, res, instr):
        lines, elem_llvm, _, _ = self._emit_list_access_lines(res, instr)
        idx64 = f"{res}_idx64"
        data = f"{res}_data"
        gep = f"{res}_gep"
        lines.append(f"{gep} = getelementptr {elem_llvm}, {elem_llvm}* {data}, i64 {idx64}")
        lines.append(f"{res} = load {elem_llvm}, {elem_llvm}* {gep}")
        return lines

    def _emit_list_set(self, res, instr):
        obj = instr.args[0]
        val = instr.args[2]
        lines, elem_llvm, lenv, data = self._emit_list_access_lines(res, instr)
        idx64 = f"{res}_idx64"
        llvm_type = self.to_llvm_type(obj.type)
        gep = f"{res}_gep"
        lines.append(f"{gep} = getelementptr {elem_llvm}, {elem_llvm}* {data}, i64 {idx64}")
        lines.append(f"store {elem_llvm} {self.operand(val)}, {elem_llvm}* {gep}")
        v0 = f"{res}_v0"
        lines.append(f"{v0} = insertvalue {llvm_type} undef, i64 {lenv}, 0")
        lines.append(f"{res} = insertvalue {llvm_type} {v0}, {elem_llvm}* {data}, 1")
        return lines

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