from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from compiler.parser import Parser
from compiler.checker import CombinedChecker
from compiler.to_high_ir import IRPhi, SSAValue, SSABuilder
from compiler.optimalise_ir import IROptimizer

from compile_test import COMPLEX_SOURCE


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
