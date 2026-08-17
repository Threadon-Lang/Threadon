import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from compile_test import COMPLEX_SOURCE

from compiler.threadon.checker import CombinedChecker
from compiler.threadon.optimalise_ir import IROptimizer
from compiler.threadon.parser import Parser
from compiler.threadon.to_high_ir import IRPhi, SSABuilder, SSAValue


def build_module(source):
    ast = Parser().parse(source)
    CombinedChecker().run_all(ast)
    return SSABuilder().build_from_ast(ast)


def optimize(source, **kwargs):
    module = build_module(source)
    IROptimizer(**kwargs).optimize(module)
    return module


def block_ops(func, label):
    block = func.block_map[label]
    return [i.op for i in block.instructions]


def assert_valid_cfg(func):
    func.build_cfg()
    labels = set(func.block_map.keys())
    assert len(func.blocks) == len(labels)

    def check_target(block, target):
        assert target in labels, f"block '{block.label}' branches to unknown block '{target}'"

    for block in func.blocks:
        term = block.terminator
        if term is None:
            continue
        if term.op == "br":
            check_target(block, term.args[0])
        elif term.op == "cond_br":
            check_target(block, term.args[1])
            check_target(block, term.args[2])


def assert_reachable(func):
    func.build_cfg()
    seen = set()
    stack = [func.blocks[0].label]
    while stack:
        label = stack.pop()
        if label in seen:
            continue
        seen.add(label)
        block = func.block_map[label]
        term = block.terminator
        if term is None:
            continue
        if term.op == "br":
            stack.append(term.args[0])
        elif term.op == "cond_br":
            stack.append(term.args[1])
            stack.append(term.args[2])
    assert seen == set(func.block_map.keys()), f"unreachable blocks in {func.name}"


def assert_valid_ssa(module):
    for func in module.funcs:
        defined = set()
        for block in func.blocks:
            for instr in block.instructions:
                if isinstance(instr.result, SSAValue):
                    defined.add(instr.result.name)

        def check_use(value, context):
            assert value.name in defined, f"dangling use of {value.name} in {func.name} ({context})"

        for block in func.blocks:
            for instr in block.instructions:
                if isinstance(instr, IRPhi):
                    for _, value in instr.incoming:
                        check_use(value, "phi in " + block.label)
                for arg in instr.args:
                    if isinstance(arg, SSAValue):
                        check_use(arg, instr.op)
            if block.terminator is not None:
                for arg in block.terminator.args:
                    if isinstance(arg, SSAValue):
                        check_use(arg, block.terminator.op + " terminator")


def assert_valid_phi_edges(func):
    func.build_cfg()
    for block in func.blocks:
        preds = set(block.predecessors)
        for instr in block.instructions:
            if isinstance(instr, IRPhi):
                for blk, _ in instr.incoming:
                    assert blk in preds, (
                        f"phi in '{block.label}' references '{blk}', "
                        f"but predecessors are {sorted(preds)}"
                    )


def test_constant_folding():
    module = optimize(
        """
def f() -> Int32
    a: Int32 = 2 + 3 * 4
    return a
"""
    )
    f = module.funcs[0]
    ops = block_ops(f, "entry")
    assert ops == ["const"]
    consts = [i for i in f.block_map["entry"].instructions if i.op == "const"]
    assert [i.args[0] for i in consts] == [14]
    assert f.block_map["entry"].terminator.op == "ret"
    assert f.block_map["entry"].terminator.args[0] == consts[0].result


def test_constant_condition_folds_branch():
    module = optimize(
        """
def f() -> Int32
    a: Int32 = 10
    b: Int32 = 3
    if a > b:
        r: Int32 = a
    else:
        r: Int32 = b
    return r
"""
    )
    f = module.funcs[0]
    assert len(f.blocks) == 1
    assert [b.label for b in f.blocks] == ["entry"]
    ops = block_ops(f, "entry")
    assert "cmp_gt" not in ops
    ret = f.block_map["entry"].terminator
    assert ret.op == "ret"
    ret_val = ret.args[0]
    assert ret_val.def_instr.op == "const"
    assert int(ret_val.def_instr.args[0]) == 10


def test_unreachable_blocks_removed():
    module = optimize(
        """
def f() -> Int32
    a: Int32 = 1
    if a < 0:
        r: Int32 = a + 1
    else:
        r: Int32 = a + 2
    return r
"""
    )
    f = module.funcs[0]
    assert [b.label for b in f.blocks] == ["entry"]
    assert "ifbody0" not in f.block_map
    assert "elsebody" not in f.block_map


def test_dead_code_elimination():
    module = optimize(
        """
def f() -> Int32
    x: Int32 = 1 + 2
    return 0
"""
    )
    f = module.funcs[0]
    ops = block_ops(f, "entry")
    assert ops == ["const"]
    ret_val = f.block_map["entry"].terminator.args[0]
    assert ret_val.def_instr.op == "const"
    assert int(ret_val.def_instr.args[0]) == 0


def test_copy_propagation():
    module = optimize(
        """
def f(b: Int32) -> Int32
    a: Int32 = b
    return a
"""
    )
    f = module.funcs[0]
    ops = block_ops(f, "entry")
    assert ops == ["param"]


def test_inlining_small_function():
    module = optimize(
        """
def add(a: Int32, b: Int32) -> Int32
    return a + b
def run() -> Int32
    x: Int32 = add(3, 4)
    return x
""",
        inline_threshold=10,
    )
    run = module.funcs[1]
    calls = [i for b in run.blocks for i in b.instructions if i.op == "call"]
    assert calls == []
    consts = [i for b in run.blocks for i in b.instructions if i.op == "const"]
    assert any(int(i.args[0]) == 7 for i in consts)


def test_no_inlining_over_threshold():
    module = optimize(
        """
def big(x: Int32) -> Int32
    a: Int32 = x + 1
    b: Int32 = a + 1
    c: Int32 = b + 1
    d: Int32 = c + 1
    e: Int32 = d + 1
    return e
def run() -> Int32
    z: Int32 = big(1)
    return z
""",
        inline_threshold=2,
    )
    run = module.funcs[1]
    calls = [i for b in run.blocks for i in b.instructions if i.op == "call"]
    assert len(calls) == 1


def test_phi_uses_original_block_labels():
    module = optimize(
        """
def max2(a: Int32, b: Int32) -> Int32
    if a > b:
        r: Int32 = a
    else:
        r: Int32 = b
    return r
"""
    )
    f = module.funcs[0]
    phis = [i for b in f.blocks for i in b.instructions if isinstance(i, IRPhi)]
    assert len(phis) == 1
    incoming_labels = [blk for blk, _ in phis[0].incoming]
    assert incoming_labels == ["entry", "elsebody"]


def test_while_loop_phi_edges_preserved():
    module = optimize(
        """
def run() -> Int32
    i: Int32 = 0
    while i < 3:
        i += 1
    return i
"""
    )
    f = module.funcs[0]
    assert_valid_cfg(f)
    assert_reachable(f)
    assert_valid_phi_edges(f)
    assert_valid_ssa(module)
    phis = [i for b in f.blocks for i in b.instructions if isinstance(i, IRPhi)]
    assert len(phis) == 1
    assert len(phis[0].incoming) == 2


def test_inline_into_loop_phi_edges_preserved():
    module = optimize(
        """
def helper(x: Int32) -> Int32
    return x * 2

def run() -> Int32
    i: Int32 = 0
    s: Int32 = 0
    while i < 4:
        s += helper(i)
        i += 1
    return s
""",
        inline_threshold=100,
    )
    f = next(x for x in module.funcs if x.name == "run")
    assert_valid_cfg(f)
    assert_reachable(f)
    assert_valid_phi_edges(f)
    assert_valid_ssa(module)


def test_optimized_module_structural_invariants():
    module = optimize(COMPLEX_SOURCE, inline_threshold=30)
    for func in module.funcs:
        assert_valid_cfg(func)
        assert_reachable(func)
    assert_valid_ssa(module)


def test_unoptimized_module_structural_invariants():
    module = build_module(COMPLEX_SOURCE)
    for func in module.funcs:
        assert_valid_cfg(func)
        assert_reachable(func)
    assert_valid_ssa(module)


def test_algebraic_simplification():
    module = optimize(
        """
def f(x: Int32) -> Int32
    a: Int32 = x * 1
    b: Int32 = x + 0
    c: Int32 = x * 0
    d: Int32 = x - 0
    return a + b + c + d
"""
    )
    f = module.funcs[0]
    ops = block_ops(f, "entry")
    assert "mul" not in ops
    assert "shl" in ops


def test_if_conversion_produces_select():
    module = optimize(
        """
def f(x: Int32) -> Int32
    if x > 0:
        r: Int32 = 5
    else:
        r: Int32 = 6
    return r
"""
    )
    f = module.funcs[0]
    selects = [i for b in f.blocks for i in b.instructions if i.op == "select"]
    assert len(selects) == 1
    cond = selects[0].args[0]
    assert cond.def_instr.op == "cmp_gt"
    assert len(f.blocks) == 1


def test_gvn_deduplicates_common_subexpressions():
    module = optimize(
        """
def f(x: Int32) -> Int32
    a: Int32 = x + 1
    b: Int32 = x + 1
    return a + b
"""
    )
    f = module.funcs[0]
    adds = [i for b in f.blocks for i in b.instructions if i.op == "add"]
    assert len(adds) == 2
    assert any(a.args[0] is a.args[1] for a in adds)


def test_strength_reduction_mul_to_shl():
    module = optimize(
        """
def f(x: Int32) -> Int32
    a: Int32 = x * 4
    return a
"""
    )
    f = module.funcs[0]
    ops = block_ops(f, "entry")
    assert "mul" not in ops
    assert "shl" in ops
    shl = next(i for i in f.block_map["entry"].instructions if i.op == "shl")
    assert int(shl.args[1]) == 2


def test_algebraic_mul_zero():
    module = optimize(
        """
def f(x: Int32) -> Int32
    a: Int32 = x * 0
    return a
"""
    )
    f = module.funcs[0]
    ops = block_ops(f, "entry")
    assert "mul" not in ops
    ret_val = f.block_map["entry"].terminator.args[0]
    assert ret_val.def_instr.op == "const"
    assert int(ret_val.def_instr.args[0]) == 0


def test_algebraic_div_one():
    module = optimize(
        """
def f(x: Int32) -> Int32
    a: Int32 = x / 1
    return a
"""
    )
    f = module.funcs[0]
    ops = block_ops(f, "entry")
    assert "div" not in ops
    assert f.block_map["entry"].terminator.args[0].name == "%t0"


def test_algebraic_mod_zero_left():
    module = optimize(
        """
def f(x: Int32) -> Int32
    a: Int32 = 0 % x
    return a
"""
    )
    f = module.funcs[0]
    ops = block_ops(f, "entry")
    assert "mod" not in ops
    ret_val = f.block_map["entry"].terminator.args[0]
    assert ret_val.def_instr.op == "const"
    assert int(ret_val.def_instr.args[0]) == 0


def test_algebraic_self_subtraction():
    module = optimize(
        """
def f(x: Int32) -> Int32
    a: Int32 = x - x
    return a
"""
    )
    f = module.funcs[0]
    ops = block_ops(f, "entry")
    assert "sub" not in ops
    ret_val = f.block_map["entry"].terminator.args[0]
    assert ret_val.def_instr.op == "const"
    assert int(ret_val.def_instr.args[0]) == 0


def test_algebraic_add_zero():
    module = optimize(
        """
def f(x: Int32) -> Int32
    a: Int32 = x + 0
    b: Int32 = 0 + x
    return a + b
"""
    )
    f = module.funcs[0]
    ops = block_ops(f, "entry")
    assert ops.count("add") == 1


def test_self_comparison_folding():
    module = optimize(
        """
def f(x: Int32) -> Bool
    a: Bool = x == x
    b: Bool = x != x
    c: Bool = x < x
    d: Bool = x <= x
    e: Bool = x >= x
    return a
"""
    )
    f = module.funcs[0]
    ops = block_ops(f, "entry")
    assert not any(op.startswith("cmp") for op in ops)
    ret_val = f.block_map["entry"].terminator.args[0]
    assert ret_val.def_instr.op == "const"
    assert ret_val.def_instr.args[0] is True


def test_double_negation_eliminated():
    module = optimize(
        """
def f(x: Int32) -> Int32
    a: Int32 = -(-x)
    return a
"""
    )
    f = module.funcs[0]
    ops = block_ops(f, "entry")
    assert "neg" not in ops


def test_double_not_eliminated():
    module = optimize(
        """
def f(b: Bool) -> Bool
    a: Bool = not (not b)
    return a
"""
    )
    f = module.funcs[0]
    ops = block_ops(f, "entry")
    assert "not" not in ops


def test_ref_copy_chain_collapsed():
    module = optimize(
        """
def f(x: Int32) -> Int32
    a: Int32 = x^
    b: Int32 = a^
    return b
"""
    )
    f = module.funcs[0]
    ops = block_ops(f, "entry")
    assert "ref_copy" not in ops

    term_val = f.block_map["entry"].terminator.args[0]
    assert term_val.def_instr is not None
    assert term_val.def_instr.op in ("load", "add", "const", "param")

def test_tail_call_optimization():
    module = optimize(
        """
def fact(n: Int32) -> Int32
    return fact(n - 1)
"""
    )
    f = module.funcs[0]
    ops = [i.op for b in f.blocks for i in b.instructions]
    assert "call" not in ops
    assert "tailcall" in ops


def test_inline_chain_collapses_to_entry():
    module = optimize(
        """
def f(x: Int32) -> Int32
    return x
def g(x: Int32) -> Int32
    return f(x)
def run() -> Int32
    return g(1)
""",
        inline_threshold=10,
    )
    run = module.funcs[2]
    assert [b.label for b in run.blocks] == ["entry"]
    calls = [i for b in run.blocks for i in b.instructions if i.op == "call"]
    assert calls == []
    assert_valid_cfg(run)
    assert_reachable(run)


def test_peephole_add_sub_cancel():
    module = optimize(
        """
def f(x: Int32, y: Int32) -> Int32
    c: Int32 = x - y
    d: Int32 = c + y
    return d
"""
    )
    f = module.funcs[0]
    ops = block_ops(f, "entry")
    assert "add" not in ops
    assert "sub" not in ops
    assert f.block_map["entry"].terminator.args[0].name == "%t0"


def test_peephole_sub_add_cancel():
    module = optimize(
        """
def f(x: Int32, y: Int32) -> Int32
    c: Int32 = x + y
    d: Int32 = c - y
    return d
"""
    )
    f = module.funcs[0]
    ops = block_ops(f, "entry")
    assert "add" not in ops
    assert "sub" not in ops
    assert f.block_map["entry"].terminator.args[0].name == "%t0"


def test_unused_phi_removed():
    module = optimize(
        """
def f(x: Int32) -> Int32
    if x > 0:
        y: Int32 = 1
    else:
        y: Int32 = 2
    return x
"""
    )
    f = module.funcs[0]
    phis = [i for b in f.blocks for i in b.instructions if isinstance(i, IRPhi)]
    assert phis == []


def test_float_constant_folding():
    module = optimize(
        """
def f() -> Float32
    a: Float32 = 1.5 + 2.5
    return a
"""
    )
    f = module.funcs[0]
    ops = block_ops(f, "entry")
    assert ops == ["const"]
    consts = [i for i in f.block_map["entry"].instructions if i.op == "const"]
    assert [i.args[0] for i in consts] == [4.0]


def test_float_division_to_multiplication():
    module = optimize(
        """
def f(x: Float32) -> Float32
    a: Float32 = x / 2.0
    return a
"""
    )
    f = module.funcs[0]
    ops = block_ops(f, "entry")
    assert "div" not in ops
    assert "mul" in ops


def test_if_conversion_guarded_for_multiple_instructions():
    module = optimize(
        """
def f(x: Int32) -> Int32
    if x > 0:
        a: Int32 = x + 1
        r: Int32 = a
    else:
        a: Int32 = x + 2
        r: Int32 = a
    return r
"""
    )
    f = module.funcs[0]
    selects = [i for b in f.blocks for i in b.instructions if i.op == "select"]
    assert selects == []
    assert_valid_cfg(f)
    assert_reachable(f)


def test_reassociation_folds_constants():
    module = optimize(
        """
def f(x: Int32) -> Int32
    a: Int32 = (x + 3) + 5
    return a
"""
    )
    f = module.funcs[0]
    consts = [i for i in f.block_map["entry"].instructions if i.op == "const"]
    assert any(int(i.args[0]) == 8 for i in consts)


def test_inline_function_with_branches():
    module = optimize(
        """
def max2(a: Int32, b: Int32) -> Int32
    if a > b:
        r: Int32 = a
    else:
        r: Int32 = b
    return r
def run() -> Int32
    return max2(7, 3)
""",
        inline_threshold=10,
    )
    run = module.funcs[1]
    calls = [i for b in run.blocks for i in b.instructions if i.op == "call"]
    assert calls == []
    assert_valid_cfg(run)
    assert_reachable(run)
    assert_valid_ssa(module)


def test_deep_inline_structural_invariants():
    module = optimize(COMPLEX_SOURCE, inline_threshold=10000)
    for func in module.funcs:
        assert_valid_cfg(func)
        assert_reachable(func)
    assert_valid_ssa(module)


def test_default_optimized_module_structural_invariants():
    module = optimize(COMPLEX_SOURCE)
    for func in module.funcs:
        assert_valid_cfg(func)
        assert_reachable(func)
    assert_valid_ssa(module)


def test_sroa_replaces_struct_field_with_constant():
    module = optimize(
        """
struct P:
    x: Int32
    y: Int32
def f() -> Int32
    p: P = P(x=7, y=8)
    return p.x + p.y
"""
    )
    f = module.funcs[0]
    entry = f.block_map["entry"]
    field_ops = [i for i in entry.instructions if i.op == "field"]
    assert field_ops == []
    consts = [i for i in entry.instructions if i.op == "const"]
    assert any(int(i.args[0]) == 15 for i in consts)


def test_sccp_collapses_elif_chain():
    module = optimize(
        """
def f(x: Int32) -> Int32
    if 1 > 0:
        r: Int32 = 10
    elif 2 > 0:
        r: Int32 = 20
    else:
        r: Int32 = 30
    return r
"""
    )
    f = module.funcs[0]
    assert [b.label for b in f.blocks] == ["entry"]
    ret_val = f.block_map["entry"].terminator.args[0]
    assert ret_val.def_instr.op == "const"
    assert int(ret_val.def_instr.args[0]) == 10


def test_inline_multiple_calls_to_same_function():
    module = optimize(
        """
def add(a: Int32, b: Int32) -> Int32
    return a + b
def run() -> Int32
    x: Int32 = add(1, 2)
    y: Int32 = add(3, 4)
    return x + y
""",
        inline_threshold=10,
    )
    run = module.funcs[1]
    calls = [i for b in run.blocks for i in b.instructions if i.op == "call"]
    assert calls == []
    assert [b.label for b in run.blocks] == ["entry"]
    ret_val = run.blocks[0].terminator.args[0]
    assert ret_val.def_instr.op == "const"
    assert int(ret_val.def_instr.args[0]) == 10


def test_inlining_threshold_boundary():
    source = """
def callee(x: Int32) -> Int32
    a: Int32 = x + 1
    b: Int32 = a + 1
    return b
def run() -> Int32
    z: Int32 = callee(1)
    return z
"""
    inlined = optimize(source, inline_threshold=5)
    run = inlined.funcs[1]
    calls = [i for b in run.blocks for i in b.instructions if i.op == "call"]
    assert calls == []

    not_inlined = optimize(source, inline_threshold=4)
    run = not_inlined.funcs[1]
    calls = [i for b in run.blocks for i in b.instructions if i.op == "call"]
    assert len(calls) == 1


def test_no_cse_for_reordered_operands():
    module = optimize(
        """
def f(a: Int32, b: Int32) -> Int32
    c: Int32 = a + b
    d: Int32 = b + a
    return c + d
"""
    )
    f = module.funcs[0]
    adds = [i for b in f.blocks for i in b.instructions if i.op == "add"]
    assert len(adds) == 3


def test_comparison_constant_folding():
    module = optimize(
        """
def f() -> Bool
    return 1 < 2
"""
    )
    f = module.funcs[0]
    ops = block_ops(f, "entry")
    assert ops == ["const"]
    ret_val = f.block_map["entry"].terminator.args[0]
    assert ret_val.def_instr.op == "const"
    assert ret_val.def_instr.args[0] is True


def test_float_comparison_constant_folding():
    module = optimize(
        """
def f() -> Bool
    return 1.5 > 1.0
"""
    )
    f = module.funcs[0]
    ops = block_ops(f, "entry")
    assert ops == ["const"]
    ret_val = f.block_map["entry"].terminator.args[0]
    assert ret_val.def_instr.op == "const"
    assert ret_val.def_instr.args[0] is True


def test_augmented_assignment_constant_folding():
    module = optimize(
        """
def run() -> Int32
    x: Int32 = 5
    x += 3
    return x
"""
    )
    f = module.funcs[0]
    ops = block_ops(f, "entry")
    assert ops == ["const"]
    ret_val = f.block_map["entry"].terminator.args[0]
    assert ret_val.def_instr.op == "const"
    assert int(ret_val.def_instr.args[0]) == 8


@pytest.mark.parametrize(
    "expr,expected",
    [
        ("2 + 3", 5),
        ("10 - 4", 6),
        ("3 * 5", 15),
        ("20 // 4", 5),
        ("2 ** 5", 32),
        ("17 % 5", 2),
        ("(2 + 3) * 4", 20),
    ],
)
def test_constant_folding_arithmetic(expr, expected):
    module = optimize(
        f"""
def f() -> Int32
    return {expr}
"""
    )
    f = module.funcs[0]
    ret_val = f.block_map["entry"].terminator.args[0]
    assert ret_val.def_instr.op == "const"
    assert int(ret_val.def_instr.args[0]) == expected
