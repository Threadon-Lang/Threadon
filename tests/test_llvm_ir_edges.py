"""Edge-case coverage for the LLVM IR backend.

Every test here lowers real SSA IR (or a whole hand-built IR module) through
LLVMIRCompiler and asserts on the emitted textual IR.  The hand-built IR uses
the same IR objects produced by SSABuilder; it lets us reach backend paths
that are difficult to trigger through surface syntax while still exercising
the real emitter.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from compiler.threadon.to_high_ir import (
    IRBlock,
    IRFunction,
    IRInstr,
    IRModule,
    SSAValue,
)
from compiler.threadon.to_llvm_ir import LLVMIRCompiler


def v(name, type_):
    return SSAValue(name, type_)


def ins(op, *args, result=None):
    return IRInstr(op, list(args), result=result)


def make_block(label, instrs, term=None):
    b = IRBlock(label)
    for x in instrs:
        b.add_instr(x)
    b.set_terminator(term or IRInstr("ret_void", []))
    return b


def make_func(name, blocks, return_type="NoneType", params=()):
    f = IRFunction(name, list(params), return_type)
    for b in blocks:
        f.add_block(b)
    return f


def emit(
    instrs,
    *,
    debug=False,
    flag_inf=False,
    types=None,
    module_vars=None,
    class_bases=None,
    native_exports=None,
    extra_funcs=(),
    blocks=None,
    result_type="NoneType",
    compiler=None,
):
    """Compile one `run` function containing `instrs` and return LLVM IR text."""
    m = IRModule()
    for name, fields in (types or {}).items():
        m.add_type(name, fields)
    m.module_vars = list(module_vars or [])
    m.class_bases = dict(class_bases or {})
    b = make_block("entry", instrs)
    m.add_func(make_func("run", [b] if blocks is None else list(blocks), result_type))
    for f in extra_funcs:
        m.add_func(f)
    c = compiler or LLVMIRCompiler(debug_mode=debug, flag_inf=flag_inf)
    return c.compile(m, native_exports=native_exports)


def cast(result, src_type, target_type, src_name="%src", debug=False, flag_inf=False, types=None):
    """Lower a cast of SSA value `src_name` (of `src_type`) into `target_type`."""
    dst = v(result, target_type)
    return emit(
        [ins("cast", v(src_name, src_type), target_type, result=dst)],
        debug=debug,
        flag_inf=flag_inf,
        types=types,
    )


def has_msg(llvm, message):
    """Diagnostic strings are emitted as byte-escaped global constants."""
    encoded = "".join(f"\\{byte:02x}" for byte in message.encode("utf-8"))
    return encoded in llvm


def test_type_mapping_edges_and_float_predicate():
    m = IRModule()
    m.add_type("Point", [("x", "Int32")])
    c = LLVMIRCompiler()
    c.compile(m)
    assert c.to_llvm_type(None) == "void"
    assert c.to_llvm_type("Dict[String,List[Int32]]") == "{ i64, i8**, { i64, i64, i32* }* }"
    assert c.to_llvm_type("Dict[Int32]") == "{ i64, i32*, i32* }"
    assert c.to_llvm_type("Wrapper.Point") == "%struct.Point"
    assert c.to_llvm_type("some.Point*") == "%struct.Point*"
    assert c.is_float_type("Float32") is True
    assert c.is_float_type("Int32") is False


def test_constructor_rejects_excessive_stack_depth():
    with pytest.raises(Exception, match="Current stack depth is to big"):
        LLVMIRCompiler(max_stack_depth=500_001)


def test_global_bool_store_uses_byte_sized_atomic():
    llvm = emit([ins("global_store", "flag", v("%b", "Bool"))])
    assert "= zext i1 %b to i8" in llvm
    assert "store atomic i8" in llvm and "i8* @flag seq_cst, align 1" in llvm


def test_identity_lowering_for_scalar_pointer_aggregate_and_union_sources():
    llvm = emit(
        [
            ins("pos", v("%f", "Float32"), result=v("%f2", "Float32")),
            ins("ref_copy", v("%b", "Bool"), result=v("%b2", "Bool")),
            ins("ref_copy", v("%s", "String"), result=v("%s2", "String")),
            ins("ref_copy", v("%p", "Point*"), result=v("%p2", "Point*")),
            ins("ref_copy", v("%st", "Point"), result=v("%st2", "Point")),
            ins("pos", v("%u", "Union[Int32|Float32]"), result=v("%u2", "Union[Int32|Float32]")),
            ins("pos", v("%l", "List[Int32]"), result=v("%l2", "List[Int32]")),
        ],
        types={"Point": [("x", "Int32"), ("y", "Int32")]},
    )
    assert "%f2 = fadd float %f, 0.0" in llvm
    assert "%b2 = xor i1 %b, false" in llvm
    assert "%s2 = getelementptr i8, i8* %s, i32 0" in llvm
    assert "%p2 = getelementptr %struct.Point, %struct.Point* %p, i32 0" in llvm
    assert "store %struct.Point %st, %struct.Point* %st2_ptr" in llvm
    assert "store %union0 %u, %union0* %u2_ptr" in llvm
    assert "store { i64, i64, i32* } %l, { i64, i64, i32* }* %l2_ptr" in llvm
    assert "%struct.Point = type { i32, i32 }" in llvm
    assert "%union0 = type { i8, float, i32 }" in llvm


def test_union_negation_switches_on_every_member():
    llvm = emit(
        [ins("neg", v("%u", "Union[Int32|Float32]"), result=v("%r", "Union[Int32|Float32]"))],
        types={"Point": [("x", "Int32")]},
    )
    assert "%r_tag = extractvalue %union0 %u, 0" in llvm
    assert "switch i8 %r_tag, label %r_default [" in llvm
    assert "i8 0, label %r_m0" in llvm and "i8 1, label %r_m1" in llvm
    assert "%r_mv0 = extractvalue %union0 %u, 1" in llvm
    assert "%r_v0 = fsub float 0.0, %r_mv0" in llvm
    assert "%r_v1 = sub i32 0, %r_mv1" in llvm
    assert "%r = phi %union0 [ %r_res0, %r_m0 ], [ %r_res1, %r_m1 ]" in llvm


def test_debug_unsigned_negation_checks_zero():
    llvm = emit(
        [ins("neg", v("%x", "UInt32"), result=v("%r", "UInt32"))], debug=True
    )
    assert "%r_iszero = icmp eq i32 %x, 0" in llvm
    assert "br i1 %r_iszero, label %r_negok, label %r_negoof" in llvm
    assert has_msg(llvm, "Error: Unsigned integer underflow in negation\n")
    assert "%r = sub i32 0, %x" in llvm


def test_unknown_unary_instruction_and_terminator_are_reported_in_ir():
    c = LLVMIRCompiler()
    assert c._emit_unary("%r", "bogus", v("%x", "Int32")) == "; unknown unary bogus"
    assert c.emit_terminator(IRInstr("bogus_term", [])) == "; UNHANDLED TERMINATOR: bogus_term"
    llvm = emit([IRInstr("mystery_op", [], result=v("%r", "Int32"))])
    assert "; UNHANDLED INSTRUCTION: mystery_op" in llvm


def test_tailcall_and_unknown_builtin_emission():
    llvm = emit(
        [
            ins(
                "tailcall",
                "leaf",
                v("%a", "Int32"),
                v("%b", "Float32"),
                result=v("%r", "Int64"),
            ),
            ins("call", "list.no_such_builtin", v("%x", "Int32"), result=v("%q", "Int32")),
        ]
    )
    assert "%r = tail call i64 @leaf(i32 %a, float %b)" in llvm
    assert "; unknown builtin no_such_builtin" in llvm


def test_const_values_from_strings_and_non_numeric_objects():
    xml = emit(
        [ins("const", "1.5", result=v("%a", "Int32")),
         ins("const", "7", result=v("%b", "Int32")),
         ins("const", None, result=v("%c", "Int32"))]
    )
    assert "%a = fadd i32 0.0, 0x" in xml
    assert "%b = add i32 0, 7" in xml
    assert "%c = add i32 0, 0" in xml


def test_undef_lowering_for_pointers_unions_and_aggregates():
    llvm = emit(
        [
            ins("undef", result=v("%p", "Point*")),
            ins("undef", result=v("%u", "Union[Int32|Float32]")),
            ins("undef", result=v("%l", "List[Int32]")),
            ins("undef", result=v("%b", "Bool")),
            ins("undef", result=v("%i", "Int32")),
        ],
        types={"Point": [("x", "Int32")]},
    )
    assert "%p = bitcast i8* null to %struct.Point*" in llvm
    assert "%u = select i1 false, %union0 undef, %union0 undef" in llvm
    assert "%l_z0 = insertvalue { i64, i64, i32* } undef, i64 0, 0" in llvm
    assert "%l = insertvalue { i64, i64, i32* } %l_z1, i32* null, 2" in llvm
    assert "%b = xor i1 false, false" in llvm
    assert "%i = add i32 0, 0" in llvm


def test_debug_signed_and_unsigned_binary_arithmetic_checks():
    llvm = emit(
        [
            ins("sub", v("%a", "UInt32"), v("%b", "UInt32"), result=v("%s", "UInt32")),
            ins("add", v("%a", "Int32"), v("%b", "Int32"), result=v("%p", "Int32")),
            ins("mul", v("%a", "Int32"), v("%b", "Int32"), result=v("%m", "Int32")),
        ],
        debug=True,
    )
    assert "%s_tmp = sub i32 %a, %b" in llvm
    assert "%s_ovf = icmp ult i32 %a, %b" in llvm
    assert "%s = sub i32 %a, %b" in llvm
    assert "llvm.sadd.with.overflow.i32" in llvm
    assert "llvm.smul.with.overflow.i32" in llvm
    assert has_msg(llvm, "Error: Integer overflow in subtraction\n")


def test_debug_pow_emits_checked_helper_calls():
    llvm = emit(
        [
            ins("pow", v("%a", "Int32"), v("%b", "Int32"), result=v("%r", "Int32")),
            ins("pow", v("%a", "UInt8"), v("%b", "UInt8"), result=q) if False else
            ins("pow", v("%u", "UInt8"), v("%u", "UInt8"), result=v("%ur", "UInt8")),
        ],
        debug=True,
    )
    assert "%r = call i32 @__threadon_pow_i32_checked(i32 %a, i32 %b)" in llvm
    assert "%ur = call i8 @__threadon_pow_u8_checked(i8 %u, i8 %u)" in llvm
    assert "define i32 @__threadon_pow_i32_checked(i32 %base, i32 %exp)" in llvm
    assert "define i8 @__threadon_pow_u8_checked(i8 %base, i8 %exp)" in llvm
    assert "@llvm.umul.with.overflow.i8" in llvm


def test_pow_helper_for_256_bits_and_non_i32_widths():
    llvm = emit(
        [
            ins("pow", v("%a", "Int256"), v("%b", "Int256"), result=v("%r", "Int256")),
            ins("pow", v("%s", "Int16"), v("%s", "Int16"), result=v("%q", "Int16")),
        ],
        debug=True,
    )
    assert "define i256 @__threadon_pow_i256_checked" in llvm
    assert "define i16 @__threadon_pow_i16_checked" in llvm
    assert "@llvm.smul.with.overflow.i16" in llvm

    # The helper's integer-width parameter also has a dedicated 512-bit path.
    c = LLVMIRCompiler()
    c._emit_pow_helper_checked(256, False)
    helper = "\n".join(c.out)
    assert "%re = sext i256 %r0 to i512" in helper
    assert "%ovf_bit = icmp ne i512 %pe, %pte" in helper
    c2 = LLVMIRCompiler()
    c2._emit_pow_helper_checked(256, True)
    assert "%re = zext i256 %r0 to i512" in "\n".join(c2.out)


def test_non_debug_pow_widths_and_float_intrinsics():
    c = LLVMIRCompiler()
    assert c._emit_binary("%r", "pow", v("%a", "Int64"), v("%b", "Int64")) == (
        "%r = call i64 @__threadon_pow_i64(i64 %a, i64 %b)"
    )
    assert c.used_pow_widths == {"64"}
    llvm = emit(
        [
            ins("pow", v("%f", "Float32"), v("%f", "Float32"), result=v("%fr", "Float32")),
            ins("floordiv", v("%f", "Float32"), v("%f", "Float32"), result=v("%fd", "Float32")),
            ins("floordiv", v("%h", "Float16"), v("%h", "Float16"), result=v("%hd", "Float16")),
        ],
        flag_inf=True,
    )
    assert "@llvm.pow.f32" in llvm
    assert "%fr_nonfinite" in llvm
    assert "%fd = call float @llvm.floor.f32(float %fd_div)" in llvm
    assert "declare half @llvm.floor.f16(half) #0" in llvm
    assert "%hd_femsg" in llvm


def test_float_pow_and_floordiv_finite_checks():
    llvm = emit(
        [
            ins("pow", v("%f", "Float64"), v("%f", "Float64"), result=v("%r", "Float64")),
            ins("floordiv", v("%g", "Float32"), v("%g", "Float32"), result=v("%q", "Float32")),
        ],
        flag_inf=True,
    )
    assert "%r = call double @llvm.pow.f64" in llvm
    assert has_msg(llvm, "Float operation: %f ** %f")
    assert has_msg(llvm, "Float operation: %g // %g")
    assert has_msg(llvm, "Error: Non-finite float value (inf or NaN)\n")


def test_debug_bitwise_shift_range_checks():
    llvm = emit(
        [
            ins("shl", v("%a", "UInt32"), v("%n", "UInt32"), result=v("%l", "UInt32")),
            ins("shr", v("%a", "Int32"), v("%n", "Int32"), result=v("%r", "Int32")),
            ins("bit_and", v("%a", "Int32"), v("%n", "Int32"), result=v("%b", "Int32")),
            ins("bit_or", v("%a", "Int32"), v("%n", "Int32"), result=v("%o", "Int32")),
            ins("bit_xor", v("%a", "Int32"), v("%n", "Int32"), result=v("%x", "Int32")),
        ],
        debug=True,
    )
    assert "%l_shftbig = icmp uge i32 %n, 32" in llvm
    assert "br i1 %l_shftbig, label %l_shftof, label %l_shftok" in llvm
    assert "%l = shl i32 %a, %n" in llvm
    assert has_msg(llvm, "shr on Int32")
    assert "%r = ashr i32 %a, %n" in llvm
    assert "%b = and i32 %a, %n" in llvm
    assert "%o = or i32 %a, %n" in llvm
    assert "%x = xor i32 %a, %n" in llvm


def test_debug_integer_truncation_checks_signed_and_unsigned():
    llvm = emit(
        [
            ins("cast", v("%a", "UInt64"), "UInt8", result=v("%u", "UInt8")),
            ins("cast", v("%b", "Int64"), "Int8", result=v("%s", "Int8")),
        ],
        debug=True,
    )
    assert "%u_toobig = icmp ugt i64 %a, 255" in llvm
    assert has_msg(llvm, "Error: Integer truncation overflow (value > 255)\n")
    assert "%u = trunc i64 %a to i8" in llvm
    assert "%s_toobig = icmp sgt i64 %b, 127" in llvm
    assert "%s_toosmall = icmp slt i64 %b, -128" in llvm
    assert "%s_anybad = or i1 %s_toobig, %s_toosmall" in llvm
    assert "%s = trunc i64 %b to i8" in llvm


def test_string_to_integer_cast_range_and_width_choices():
    llvm = emit(
        [
            ins("cast", v("%s", "String"), "UInt8", result=v("%u", "UInt8")),
            ins("cast", v("%s", "String"), "Int64", result=v("%l", "Int64")),
            ins("cast", v("%s", "String"), "Int256", result=v("%w", "Int256")),
            ins("cast", v("%s", "String"), "String", result=v("%t", "String")),
        ],
        debug=True,
    )
    assert has_msg(llvm, "String → Integer cast")
    assert has_msg(llvm, "Invalid integer conversion")
    assert "%_u_toobig = icmp ugt i64 %u_tmp, 255" in llvm
    assert has_msg(llvm, "Error: Integer overflow in string conversion (value out of range for UInt8)\n")
    assert "%l = add i64 %l_tmp, 0" in llvm
    assert "%w = sext i64 %w_tmp to i256" in llvm
    assert "%t = getelementptr i8, i8* %s, i32 0" in llvm
    assert "declare i64 @strtol" in llvm
    assert "declare i64 @strtoull" in llvm


def test_i256_to_string_cast_and_unsupported_string_source():
    llvm = emit(
        [
            ins("cast", v("%a", "Int256"), "String", result=v("%s", "String")),
            ins("cast", v("%b", "UInt256"), "String", result=v("%t", "String")),
            ins("cast", v("%f", "Float32"), "String", result=v("%fs", "String")),
            ins("cast", v("%flag", "Bool"), "String", result=v("%bs", "String")),
        ]
    )
    assert "%s = call i8* @__threadon_to_string_i256(i256 %a, i8* %s_ptr)" in llvm
    assert "%t = call i8* @__threadon_to_string_u256(i256 %b, i8* %t_ptr)" in llvm
    assert "define i8* @__threadon_to_string_i256" in llvm
    assert "define i8* @__threadon_to_string_u256" in llvm
    assert "%fs_fd = fpext float %f to double" in llvm
    assert "snprintf(i8* %fs_buf, i64 64, i8* @.str." in llvm
    assert "%bs_sel = select i1 %flag, i8* @.str." in llvm
    assert "%bs = getelementptr i8, i8* %bs_sel, i64 0" in llvm
    with pytest.raises(Exception, match="Cannot cast List\\[Int32\\] to String"):
        cast("%bad", "List[Int32]", "String")


def test_cast_with_finite_checks_and_bool_targets():
    llvm = emit(
        [
            ins("cast", v("%i", "Int32"), "Float32", result=v("%f", "Float32")),
            ins("cast", v("%d", "Float64"), "Float32", result=v("%n", "Float32")),
            ins("cast", v("%z", "Float32"), "Bool", result=v("%b", "Bool")),
            ins("cast", v("%one", "Bool"), "Float32", result=v("%bf", "Float32")),
        ],
        flag_inf=True,
    )
    assert "%f = sitofp i32 %i to float" in llvm
    assert has_msg(llvm, "Int Int32 → Float32 conversion")
    assert "%n = fptrunc double %d to float" in llvm
    assert has_msg(llvm, "Float Float64 → Float32 narrowing")
    assert "%b = fcmp une float %z, 0.0" in llvm
    assert "%bf = uitofp i1 %one to float" in llvm
    assert has_msg(llvm, "Error: Non-finite float value (inf or NaN)\n")
    assert cast("%q", "Int32", "Bool").count("icmp ne i32") >= 1
    assert "xor i1" in cast("%q", "Bool", "Bool")


def test_debug_float_to_unsigned_integer_cast():
    llvm = cast("%u", "Float32", "UInt16", debug=True)
    assert "%u_fmax = sitofp i64 65535 to float" in llvm
    assert "%u_toobig = fcmp ogt float %src, %u_fmax" in llvm
    assert "%u_toosmall = fcmp olt float %src, 0.0" in llvm
    assert has_msg(llvm, "Error: Float-to-integer overflow\n")
    assert "%u = fptoui float %src to i16" in llvm
    assert has_msg(llvm, "Float Float32 → UInt16 cast")


def test_unsupported_cast_reports_source_and_target():
    with pytest.raises(Exception, match="Unsupported cast from i32 to %struct.Point"):
        cast("%bad", "Int32", "Point", types={"Point": [("x", "Int32")]})
    with pytest.raises(Exception, match="Cannot cast Point to Bool"):
        cast("%bad", "Point", "Bool", types={"Point": [("x", "Int32")]})


def test_union_binary_with_two_unions_and_widening_result():
    utype = "Union[Int32|Float32]"
    llvm = emit(
        [
            ins("add", v("%a", utype), v("%b", utype), result=v("%r", "Int64")),
        ]
    )
    assert "%r_ltag = extractvalue %union0 %a, 0" in llvm
    assert "%r_rtag = extractvalue %union0 %b, 0" in llvm
    assert "switch i8 %r_rtag, label %r_R0_default [" in llvm
    assert "i8 1, label %r_R0_1" in llvm
    assert "%r_rv0_1 = extractvalue %union0 %b, 2" in llvm
    assert "%r_p0_1_a = fadd float" in llvm
    assert "%r_p0_1_c = fptosi float" in llvm
    assert "%r = phi i64" in llvm


def test_union_binary_result_cast_and_cmp_path():
    utype = "Union[Int32|Float32]"
    llvm = emit(
        [
            ins("cmp_eq", v("%a", utype), v("%b", utype), result=v("%c", "Bool")),
        ]
    )
    assert "cmp_eq" not in llvm.split("define", 1)[1][:200]
    assert "= icmp eq i32" in llvm or "= fcmp oeq float" in llvm
    assert "%c = phi i1" in llvm


def test_native_exports_and_dict_returning_call():
    llvm = emit(
        [
            ins(
                "call",
                "n.take",
                v("%d", "Dict[String,Int32]"),
                v("%i", "Int32"),
                result=v("%r", "Dict[String,Int32]"),
            )
        ],
        native_exports=[
            {
                "module": "n",
                "name": "take",
                "ret": "Dict[String,Int32]",
                "args": ["Dict[String,Int32]", "Int32"],
            }
        ],
    )
    assert "declare void @take({ i64, i8**, i32* }*, i32, { i64, i8**, i32* }*)" in llvm
    assert "%d_dptr = alloca { i64, i8**, i32* }" in llvm
    assert "store { i64, i8**, i32* } %d, { i64, i8**, i32* }* %d_dptr" in llvm
    assert "%r_sret = alloca { i64, i8**, i32* }" in llvm
    assert "call void @take({ i64, i8**, i32* }* %d_dptr, i32 %i, { i64, i8**, i32* }* %r_sret)" in llvm
    assert "%r = load { i64, i8**, i32* }, { i64, i8**, i32* }* %r_sret" in llvm


def test_thread_spawn_with_captures_uses_gc_allocated_closure():
    llvm = emit(
        [
            ins(
                "thread_spawn",
                "1",
                "worker",
                "body",
                v("%a", "Int32"),
                v("%s", "String"),
            )
        ]
    )
    assert "%__thread_closure_1 = type { i32, i8* }" in llvm
    assert "call i8* @__threadon_gc_alloc(i64 16, i64 0)" in llvm
    assert "bitcast i8* %cl11 to %__thread_closure_1*" in llvm
    assert "getelementptr inbounds %__thread_closure_1, %__thread_closure_1* %cll12, i64 0, i32 0" in llvm
    assert "store i32 %a, i32* %cf13" in llvm
    assert "store i8* %s, i8** %cf15" in llvm
    assert "call i32 @pthread_create(i64* %tid17, i8* null, i8* (i8*)* @__thread_tramp_1, i8* %cl11)" in llvm
    assert "define internal i8* @__thread_tramp_1(i8* %_cr)" in llvm
    assert "%_cv0 = load i32, i32* %_cp0" in llvm
    assert "call void @body( i32 %_cv0, i8* %_cv1)" in llvm


def test_module_var_initializers_and_missing_initializers():
    llvm = emit(
        [],
        types={"Point": [("x", "Int32")]},
        module_vars=[
            ("flag", "Bool", True),
            ("flt", "Float32", 2),
            ("p", "Point", 7),
            ("unset_bool", "Bool", None),
            ("unset_int", "Int32", None),
        ],
    )
    assert "@flag = global i8 1, align 1" in llvm
    assert "@flt = global float 2.0, align 4" in llvm
    assert "@p = global %struct.Point zeroinitializer, align 4" in llvm
    assert "@unset_bool = global i8 0, align 1" in llvm
    assert "@unset_int = global i32 zeroinitializer, align 4" in llvm
    c = LLVMIRCompiler()
    assert c._const_literal(True, "Bool") == "true"
    assert c._const_literal(False, "Bool") == "false"


def test_string_module_var_is_unsupported():
    with pytest.raises(NotImplementedError, match="String globals not yet supported"):
        emit([], module_vars=[("s", "String", "x")])


def test_nested_dict_type_parsing_and_dict_kv_helper():
    c = LLVMIRCompiler()
    c.compile(IRModule())
    assert c.to_llvm_type("Dict[List[Int32],String]") == "{ i64, { i64, i64, i32* }*, i8** }"
    assert c._parse_dict_kv_types("Dict[List[Int32],String]") == ("List[Int32]", "String")
    assert c._parse_dict_kv_types("Dict[Int32]") == ("Unknown", "Unknown")


def test_struct_print_formats_small_and_large_integer_fields():
    llvm = emit(
        [
            ins("call", "print", v("%small", "Small")),
            ins("call", "print", v("%big", "Big")),
        ],
        types={
            "Small": [("a", "Int8"), ("b", "UInt16")],
            "Big": [("x", "Int64"), ("y", "UInt64")],
        },
    )
    assert "sext i8" in llvm and "zext i16" in llvm
    assert has_msg(llvm, "%d") and has_msg(llvm, "%u")
    assert has_msg(llvm, "%lld") and has_msg(llvm, "%llu")
    assert "define i8* @__threadon_struct_str_Small" in llvm
    assert "define i8* @__threadon_struct_str_Big" in llvm


def test_struct_print_with_list_field_uses_list_string_helper():
    llvm = emit(
        [ins("call", "print", v("%wl", "WithList"))],
        types={"WithList": [("items", "List[Int32]")]},
    )
    assert "call i8* @__threadon_list_str_Int32(" in llvm
    assert "define i8* @__threadon_list_str_Int32" in llvm
    assert has_msg(llvm, "%s")


def test_struct_print_rejects_unsupported_field_type():
    with pytest.raises(Exception, match="struct print: unsupported field type 'TemplatePayload'"):
        emit(
            [ins("call", "print", v("%bad", "Bad"))],
            types={"Bad": [("t", "TemplatePayload")]},
        )


def test_dict_print_formats_bool_float_and_unknown_types():
    llvm = emit(
        [
            ins("call", "print", v("%a", "Dict[Bool,Float32]")),
            ins("call", "print", v("%b", "Dict[Int32,String]")),
            ins("call", "print", v("%c", "Dict[Point,Int32]")),
        ],
        types={"Point": [("x", "Int32")]},
    )
    assert "define i8* @__threadon_dict_str_Bool_Float32" in llvm
    assert "define i8* @__threadon_dict_str_Int32_String" in llvm
    assert "define i8* @__threadon_dict_str_Point_Int32" in llvm
    assert "%kv_bstr = select i1 %kv," in llvm
    assert has_msg(llvm, "%f") and has_msg(llvm, "%lld")
    assert "float %vv" in llvm and "i64 %kv" in llvm


def test_print_boolean_alias_and_unsupported_type():
    llvm = emit([ins("call", "print", v("%b", "Boolean"))])
    assert "None_b0 = zext i1 %b to i32" in llvm
    with pytest.raises(Exception, match="print: unsupported type i8\\*\\*"):
        emit([ins("call", "print", v("%t", "TemplatePayload"))])


def test_print_struct_with_inherited_str_upcasts_to_base():
    base_block = make_block(
        "entry",
        [ins("const", "hi", result=v("%z", "String"))],
        term=IRInstr("ret", [v("%z", "String")]),
    )
    llvm = emit(
        [ins("call", "print", v("%d", "Derived"))],
        types={
            "Base": [("x", "Int32"), ("y", "Int32")],
            "Derived": [("x", "Int32"), ("y", "Int32"), ("z", "Int32")],
        },
        class_bases={"Derived": "Base"},
        extra_funcs=[make_func("Base.__str__", [base_block], "String")],
    )
    assert "extractvalue %struct.Derived %d, 0" in llvm
    assert "insertvalue %struct.Base undef, i32" in llvm
    assert "insertvalue %struct.Base" in llvm and ", 1" in llvm
    assert "call i8* @Base.__str__(%struct.Base" in llvm


def test_list_remove_pointer_equality_and_unsupported_element():
    llvm = emit(
        [
            ins(
                "call",
                "list.remove",
                v("%l", "List[Point*]"),
                v("%p", "Point*"),
                result=v("%r", "List[Point*]"),
            )
        ],
        types={"Point": [("x", "Int32")]},
    )
    assert "icmp eq %struct.Point*" in llvm
    with pytest.raises(Exception, match="'remove' is not supported for list element type Point"):
        emit(
            [
                ins(
                    "call",
                    "list.remove",
                    v("%l", "List[Point]"),
                    v("%p", "Point"),
                    result=v("%r", "List[Point]"),
                )
            ],
            types={"Point": [("x", "Int32")]},
        )


def test_i256_index_and_non_integer_index_errors():
    llvm = emit(
        [
            ins("string_get", v("%s", "String"), v("%i", "Int256"), result=v("%c", "String")),
        ]
    )
    assert "%c_gi_idx64 = trunc i256 %i to i64" in llvm
    with pytest.raises(Exception, match="list index must be an integer, got Float32"):
        emit(
            [
                ins(
                    "list_get",
                    v("%l", "List[Int32]"),
                    v("%f", "Float32"),
                    result=v("%v", "Int32"),
                )
            ]
        )
    with pytest.raises(Exception, match="list mutator index must be an integer, got Float32"):
        emit(
            [
                ins(
                    "string_get",
                    v("%s", "String"),
                    v("%f", "Float32"),
                    result=v("%c", "String"),
                )
            ]
        )


def test_empty_template_concat_and_unknown_field():
    llvm = emit(
        [
            ins("tmpl_concat", result=v("%t", "TemplatePayload")),
            ins("field", v("%x", "Int32"), "x", result=v("%f", "Int32")),
        ]
    )
    assert "%t_arr = alloca [0 x i8*]" in llvm
    assert "; unknown struct field x" in llvm


def test_list_print_rejects_union_elements():
    with pytest.raises(
        Exception, match="list print: unsupported element type 'Union\\[Int32\\|Float32\\]'"
    ):
        emit([ins("call", "print", v("%l", "List[Union[Int32|Float32]]"))])


def test_size_and_align_helper_edges():
    c = LLVMIRCompiler()
    c.compile(IRModule())
    assert c._size_and_align("i16") == (2, 2)
    assert c._size_and_align("half") == (2, 2)
    with pytest.raises(Exception, match="Cannot determine layout of unknown struct 'Missing'"):
        c._size_and_align("%struct.Missing")
    with pytest.raises(Exception, match="Unknown closure type '%__thread_closure_x'"):
        c._size_and_align("%__thread_closure_x")
    with pytest.raises(Exception, match="Cannot determine size of LLVM type 'i7'"):
        c._size_and_align("i7")


def test_operand_and_add_emit_helpers():
    c = LLVMIRCompiler()
    assert c.operand(True) == "true"
    assert c.operand(False) == "false"
    assert c.operand('"quoted"') == '"quoted"'
    assert c.operand("plain") == "plain"
    assert c.operand(3) == "3"
    assert c.operand(None) == "None"
    lines = []
    c._add_emit(lines, None)
    assert lines == []
    c._add_emit(lines, "x")
    c._add_emit(lines, ["y"])
    assert lines == ["x", "y"]


def test_upcast_struct_with_same_type_returns_value():
    c = LLVMIRCompiler()
    arg = v("%x", "Point")
    assert c._upcast_struct([], arg, "Point", "Point", lambda base: base) is arg


def test_union_binary_result_matching_common_type():
    llvm = emit(
        [
            ins(
                "add",
                v("%a", "Union[Int32|Int32]"),
                v("%b", "Union[Int32|Int32]"),
                result=v("%r", "Int32"),
            )
        ]
    )
    assert "%r_p0_0_a = add i32" in llvm
    assert "%r = phi i32" in llvm


def test_float_floordiv_and_narrowing_without_flag_inf():
    llvm = emit(
        [
            ins("floordiv", v("%a", "Float32"), v("%b", "Float32"), result=v("%fd", "Float32")),
            ins("cast", v("%d", "Float64"), "Float32", result=v("%n", "Float32")),
        ]
    )
    assert "%fd_div = fdiv float %a, %b" in llvm
    assert "%fd = call float @llvm.floor.f32(float %fd_div)" in llvm
    assert "%n = fptrunc double %d to float" in llvm


def test_identity_for_integer_scalar():
    llvm = emit([ins("pos", v("%i", "Int32"), result=v("%j", "Int32"))])
    assert "%j = add i32 %i, 0" in llvm


def test_non_debug_pow_width_emits_wrapping_helper():
    llvm = emit(
        [
            ins(
                "pow",
                v("%a", "Int64"),
                v("%b", "Int64"),
                result=v("%r", "Int64"),
            )
        ]
    )
    assert "%r = call i64 @__threadon_pow_i64(i64 %a, i64 %b)" in llvm
    assert "define i64 @__threadon_pow_i64(i64 %base, i64 %exp)" in llvm
    assert "%next = mul i64 %r, %base" in llvm
