"""Final backend edge cases for the LLVM IR emitter.

The tests lower real SSA IR modules through LLVMIRCompiler and assert on the
emitted textual IR, in the same style as tests/test_llvm_ir_edges.py.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from compile_test import run_llvm
from compiler.threadon.compiler import compile_source
from compiler.threadon.importer import Importer
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


def compile_module(instrs, *, debug=False, native_exports=None):
    """Compile one `run` function containing `instrs` into LLVM IR text."""
    module = IRModule()
    block = IRBlock("entry")
    for instr in instrs:
        block.add_instr(instr)
    block.set_terminator(IRInstr("ret_void", []))
    func = IRFunction("run", [], "NoneType")
    func.add_block(block)
    module.add_func(func)
    return LLVMIRCompiler(debug_mode=debug).compile(
        module, native_exports=native_exports
    )


def test_resultless_void_call_emits_bare_call():
    llvm = compile_module(
        [ins("call", "host_sink", v("%x", "Int32"))],
        native_exports=[
            {"module": "host", "name": "host_sink", "ret": "NoneType", "args": ["Int32"]}
        ],
    )
    assert "declare void @host_sink(i32)" in llvm
    assert "\n  call void @host_sink(i32 %x)\n" in llvm
    assert "= call void @host_sink" not in llvm


def test_debug_pow_on_wide_integer_still_uses_checked_helper():
    llvm = compile_module(
        [ins("pow", v("%a", "Int64"), v("%b", "Int64"), result=v("%r", "Int64"))],
        debug=True,
    )
    assert "%r = call i64 @__threadon_pow_i64_checked(i64 %a, i64 %b)" in llvm
    assert "define i64 @__threadon_pow_i64_checked(i64 %base, i64 %exp) {" in llvm
    assert "@__threadon_pow_i64(" not in llvm


def test_float_to_string_cast_uses_snprintf():
    llvm64 = compile_module(
        [ins("cast", v("%d", "Float64"), "String", result=v("%s", "String"))]
    )
    assert (
        "call i32 (i8*, i64, i8*, ...) @snprintf"
        "(i8* %s_buf, i64 64, i8* @.str.0, double %d)" in llvm64
    )

    llvm32 = compile_module(
        [ins("cast", v("%f", "Float32"), "String", result=v("%s", "String"))]
    )
    assert "%s_fd = fpext float %f to double" in llvm32
    assert (
        "call i32 (i8*, i64, i8*, ...) @snprintf"
        "(i8* %s_buf, i64 64, i8* @.str.0, double %s_fd)" in llvm32
    )


def test_non_debug_wide_integer_power_uses_wrapping_helper():
    source = """
def power(a: Int64, b: Int64) -> Int64
    return a ** b

def main() -> Int32
    x: Int64 = Int64(input(""))
    y: Int64 = power(x, 3)
    print(y)
    return 0
"""
    llvm = compile_source(source, importer=Importer(), inline_threshold=0)
    assert "define i64 @__threadon_pow_i64(i64 %base, i64 %exp)" in llvm
    result = run_llvm(llvm, input="2\n")
    assert result.returncode == 0, result.stderr
    assert result.stdout == "8\n"


def test_union_print_dispatches_all_members_and_merges():
    llvm = compile_module(
        [
            ins(
                "call",
                "print",
                v("%u", "Union[Int32|Bool]"),
                result=v("%p", "NoneType"),
            )
        ]
    )
    assert "%union0 = type { i8, i1, i32 }" in llvm
    assert re.search(r"switch i8 %p_tag0, label %\w+ \[", llvm)
    assert "i8 0, label %" in llvm and "i8 1, label %" in llvm
    assert "extractvalue %union0 %u, 1" in llvm
    assert "extractvalue %union0 %u, 2" in llvm
    assert "call i32 (i8*, ...) @printf(i8* %" in llvm
    assert "br label %p_merge" in llvm
    assert "  p_merge:\n" in llvm
