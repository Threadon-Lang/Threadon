"""Behavioral regression tests for the final IR optimizer cleanup.

These tests build small IR fragments (and a couple of source-level modules)
that assert the concrete transformation performed by each pass, including the
SSA user bookkeeping that the optimizer relies on for dead code elimination.
"""

import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from compiler.threadon.checker import CombinedChecker
from compiler.threadon.optimalise_ir import IROptimizer
from compiler.threadon.parser import Parser
from compiler.threadon.to_high_ir import (
    IRBlock,
    IRFunction,
    IRInstr,
    IRModule,
    IRPhi,
    SSAValue,
    SSABuilder,
)


_counter = itertools.count()


def new_value(type_="Int32"):
    return SSAValue(f"%final{next(_counter)}", type_)


def const(value_, type_="Int32"):
    return IRInstr("const", [value_], result=new_value(type_))


def instr(op, args, type_="Int32"):
    return IRInstr(op, list(args), result=new_value(type_))


def mkblock(label, instructions=(), terminator=None):
    block = IRBlock(label)
    for instruction in instructions:
        block.add_instr(instruction)
    if terminator is not None:
        block.set_terminator(terminator)
    return block


def mkfunc(*blocks, name="f", params=(), return_type="Int32"):
    func = IRFunction(name, list(params), return_type)
    for block in blocks:
        func.add_block(block)
    return func


def mkopt(func=None, **kwargs):
    opt = IROptimizer(**kwargs)
    if func is not None:
        opt.func = func
    return opt


def optimize(source, **kwargs):
    ast = Parser().parse(source)
    CombinedChecker().run_all(ast)
    module = SSABuilder().build_from_ast(ast)
    return IROptimizer(**kwargs).optimize(module)


def assert_valid_cfg_and_ssa(module):
    for func in module.funcs:
        func.build_cfg()
        labels = set(func.block_map)
        seen = set()
        stack = [func.blocks[0].label]
        while stack:
            label = stack.pop()
            if label in seen:
                continue
            seen.add(label)
            terminator = func.block_map[label].terminator
            if terminator is None:
                continue
            if terminator.op == "br":
                assert terminator.args[0] in labels
                stack.append(terminator.args[0])
            elif terminator.op == "cond_br":
                assert terminator.args[1] in labels
                assert terminator.args[2] in labels
                stack.extend(terminator.args[1:])
        assert seen == labels

        defined = {
            i.result.name
            for b in func.blocks
            for i in b.instructions
            if isinstance(i.result, SSAValue)
        }
        for block in func.blocks:
            for instruction in block.instructions:
                for arg in instruction.args:
                    if isinstance(arg, SSAValue):
                        assert arg.name in defined
                if isinstance(instruction, IRPhi):
                    for label, _ in instruction.incoming:
                        assert label in block.predecessors
            if block.terminator:
                for arg in block.terminator.args:
                    if isinstance(arg, SSAValue):
                        assert arg.name in defined


# ---------------------------------------------------------------------------
# _sccp / _constant_folding with normalized numeric constants
# ---------------------------------------------------------------------------


def test_sccp_folds_unary_binary_and_comparison_constants():
    a = const(3)
    b = const(2)
    neg = instr("neg", [a.result])
    add = instr("add", [a.result, b.result])
    ne = instr("cmp_ne", [a.result, b.result], "Bool")
    block = mkblock(
        "entry", [a, b, neg, add, ne], IRInstr("ret", [ne.result])
    )
    func = mkfunc(block)

    assert mkopt(func)._sccp() is True
    assert neg.op == "const" and neg.args == [-3]
    assert add.op == "const" and add.args == [5]
    assert ne.op == "const" and ne.args == [True]
    assert block.terminator.args == [ne.result]


def test_constant_folding_folds_every_comparison_operator():
    a = const(1)
    b = const(2)
    ops = [
        instr(op, [a.result, b.result], "Bool")
        for op in (
            "cmp_lt", "cmp_gt", "cmp_le", "cmp_ge", "cmp_eq", "cmp_ne",
        )
    ]
    block = mkblock("entry", [a, b, *ops], IRInstr("ret", [ops[-1].result]))
    func = mkfunc(block, return_type="Bool")

    assert mkopt(func)._constant_folding() is True
    assert [i.args[0] for i in ops] == [True, False, True, False, False, True]
    assert b.result.users == []


# ---------------------------------------------------------------------------
# _reassociation SSA bookkeeping
# ---------------------------------------------------------------------------


def test_reassociation_updates_ssa_users():
    x = new_value()
    c3 = const(3)
    c5 = const(5)
    inner = instr("add", [x, c3.result])
    outer = instr("add", [inner.result, c5.result])
    block = mkblock(
        "entry", [c3, c5, inner, outer], IRInstr("ret", [outer.result])
    )
    func = mkfunc(block)

    assert mkopt(func)._reassociation() is True
    assert outer.args[0] is x
    new_c = outer.args[1]
    assert isinstance(new_c, SSAValue)
    assert new_c.def_instr.op == "const"
    assert new_c.def_instr.args == [8]
    assert outer in x.users
    assert outer in new_c.users
    assert outer not in inner.result.users
    assert outer not in c5.result.users
    assert inner.result.users == []
    assert block.instructions.index(new_c.def_instr) < block.instructions.index(outer)


def test_reassociation_updates_ssa_users_for_multiplication():
    x = new_value()
    c3 = const(3)
    c4 = const(4)
    inner = instr("mul", [x, c3.result])
    outer = instr("mul", [inner.result, c4.result])
    block = mkblock(
        "entry", [c3, c4, inner, outer], IRInstr("ret", [outer.result])
    )
    func = mkfunc(block)

    assert mkopt(func)._reassociation() is True
    new_c = outer.args[1]
    assert new_c.def_instr.args == [12]
    assert outer in x.users
    assert outer in new_c.users
    assert outer not in inner.result.users
    assert outer not in c4.result.users


# ---------------------------------------------------------------------------
# _gvn dominance and _sroa user bookkeeping
# ---------------------------------------------------------------------------


def test_gvn_reuses_value_defined_in_strictly_dominating_block():
    x = new_value()
    y = new_value()
    first = IRInstr("add", [x, y], result=new_value())
    entry = mkblock("entry", [first], IRInstr("br", ["body"]))
    duplicate = instr("add", [x, y])
    body = mkblock("body", [duplicate], IRInstr("ret", [duplicate.result]))
    func = mkfunc(entry, body)

    assert mkopt(func)._gvn() is True
    assert body.instructions == []
    assert body.terminator.args == [first.result]
    assert first.result.users == [body.terminator]


def test_gvn_keeps_duplicates_in_non_dominating_sibling_blocks():
    c = const(1)
    x = new_value()
    left_add = IRInstr("add", [x, c.result], result=new_value())
    right_add = IRInstr("add", [x, c.result], result=new_value())
    entry = mkblock("entry", [c], IRInstr("cond_br", [True, "L", "R"]))
    left = mkblock("L", [left_add], IRInstr("ret", [left_add.result]))
    right = mkblock("R", [right_add], IRInstr("ret", [right_add.result]))
    func = mkfunc(entry, left, right)

    assert mkopt(func)._gvn() is False
    assert left.instructions == [left_add]
    assert right.instructions == [right_add]
    assert left.terminator.args == [left_add.result]
    assert right.terminator.args == [right_add.result]


def test_sroa_forwards_field_and_removes_struct_and_field_users():
    x = const(7)
    st = IRInstr("struct_init", ["P", "a", x.result], result=new_value("P"))
    field = IRInstr("field", [st.result, "a"], result=new_value())
    block = mkblock(
        "entry", [x, st, field], IRInstr("ret", [field.result])
    )
    func = mkfunc(block)

    assert mkopt(func)._sroa() is True
    assert block.instructions == [x]
    assert block.terminator.args == [x.result]
    assert st.result.users == []
    assert st.result.def_instr is None
    assert field.result.users == []
    assert field.result.def_instr is None
    assert field not in st.result.users
    assert field not in x.result.users
    assert x.result.users == [block.terminator]


# ---------------------------------------------------------------------------
# CFG cleanup passes with validated terminators
# ---------------------------------------------------------------------------


def test_remove_empty_blocks_and_merge_blocks_on_valid_cfg():
    x = new_value()
    entry = mkblock("entry", [], IRInstr("br", ["jump"]))
    jump = mkblock("jump", [], IRInstr("br", ["merge"]))
    merge = mkblock("merge", [], IRInstr("ret", [x]))
    func = mkfunc(entry, jump, merge)
    opt = mkopt(func)

    assert opt._remove_empty_blocks() is True
    assert [b.label for b in func.blocks] == ["entry", "merge"]
    assert entry.terminator.args == ["merge"]
    assert opt._merge_blocks() is True
    assert [b.label for b in func.blocks] == ["entry"]
    assert entry.terminator.op == "ret"
    assert entry.terminator.args == [x]


def test_licm_leaves_impure_call_in_loop_body():
    x = new_value()
    call = instr("call", ["helper", x])
    entry = mkblock("entry", [], IRInstr("br", ["header"]))
    header = mkblock("header", [], IRInstr("cond_br", [True, "body", "exit"]))
    body = mkblock("body", [call], IRInstr("br", ["header"]))
    exit_ = mkblock("exit", [], IRInstr("ret", [x]))
    func = mkfunc(entry, header, body, exit_)

    assert mkopt(func)._licm() is False
    assert body.instructions == [call]
    assert "pre_header" not in func.block_map


def test_public_optimizer_keeps_cfg_and_phis_valid_with_inlining_and_loops():
    module = optimize(
        """
def choose(a: Int32, b: Int32) -> Int32
    if a > b:
        r: Int32 = a + 1
    else:
        r: Int32 = b + 2
    return r

def run() -> Int32
    i: Int32 = 0
    total: Int32 = 0
    while i < 3:
        total += choose(i, 1)
        i += 1
    return total
""",
        inline_threshold=30,
    )
    assert_valid_cfg_and_ssa(module)

    run = next(func for func in module.funcs if func.name == "run")
    assert [b.label for b in run.blocks]
    assert all(b.terminator is not None for b in run.blocks)


# ---------------------------------------------------------------------------
# Numeric helpers and SCCP lattice corners
# ---------------------------------------------------------------------------


def test_numeric_helpers_handle_non_numeric_and_float_values():
    opt = mkopt()
    assert opt._to_number("not-a-number") is None
    assert opt._int_bounds("Float32") == (None, None)
    assert opt._fits(1.5, "Float32") is True

    a = const(7.5, "Float32")
    b = const(2.0, "Float32")
    ops = [
        instr(op, [a.result, b.result], "Float32")
        for op in ("add", "sub", "mul", "div", "floordiv", "mod")
    ]
    block = mkblock("entry", [a, b, *ops], IRInstr("ret", [ops[-1].result]))
    func = mkfunc(block, return_type="Float32")

    assert mkopt(func)._constant_folding() is True
    assert [i.args[0] for i in ops] == [9.5, 5.5, 15.0, 3.75, 3.0, 1.5]


def test_constant_folding_integer_division_truncates_toward_zero():
    a = const(-7)
    b = const(2)
    division = instr("div", [a.result, b.result])
    block = mkblock("entry", [a, b, division], IRInstr("ret", [division.result]))
    func = mkfunc(block)

    assert mkopt(func)._constant_folding() is True
    assert division.op == "const" and division.args == [-3]


def test_sccp_uses_top_for_undef_invalid_and_failed_folds():
    bad = const("abc", "String")
    zero = const(0)
    one = const(1)
    undef = IRInstr("undef", [], result=new_value())
    neg_bad = instr("neg", [bad.result], "String")
    pos = instr("pos", [one.result])
    logical_not = instr("not", [one.result], "Bool")
    add_bad = instr("add", [bad.result, bad.result], "String")
    div_zero = instr("div", [one.result, zero.result])
    block = mkblock(
        "entry",
        [bad, zero, one, undef, neg_bad, pos, logical_not, add_bad, div_zero],
        IRInstr("ret", [pos.result]),
    )
    func = mkfunc(block)

    assert mkopt(func)._sccp() is True
    assert neg_bad.op == "neg"
    assert add_bad.op == "add"
    assert div_zero.op == "div"
    assert pos.op == "const" and pos.args == [1]
    assert logical_not.op == "const" and logical_not.args == [False]


def test_sccp_respects_debug_mode_for_float_unary_folding():
    a = const(1.5, "Float32")
    neg = instr("neg", [a.result], "Float32")
    block = mkblock("entry", [a, neg], IRInstr("ret", [neg.result]))
    func = mkfunc(block, return_type="Float32")

    assert mkopt(func, debug_mode=True)._sccp() is True
    assert neg.op == "const" and neg.args == [-1.5]


def test_value_reads_phi_skips_non_ssa_and_repeated_values():
    target = new_value()
    source = new_value()
    opt = mkopt()

    assert opt._value_reads_phi(42, target) is False

    self_phi = IRPhi(source, [("latch", source), ("latch", source)])
    source.def_instr = self_phi
    assert opt._value_reads_phi(source, target) is False

    cycle_phi = IRPhi(source, [("latch", target)])
    source.def_instr = cycle_phi
    assert opt._value_reads_phi(source, target) is True


def test_sccp_keeps_loop_carried_phi_cycles_nonconstant():
    x = new_value()
    y = new_value()
    a = new_value()
    b = new_value()
    phi_a = IRPhi(a, [("entry", x), ("latch", b)])
    phi_b = IRPhi(b, [("entry", y), ("latch", a)])
    cond = const(True, "Bool")
    entry = mkblock("entry", [], IRInstr("br", ["header"]))
    header = mkblock(
        "header", [phi_a, phi_b, cond], IRInstr("cond_br", [cond.result, "body", "exit"])
    )
    body = mkblock("body", [], IRInstr("br", ["latch"]))
    latch = mkblock("latch", [], IRInstr("br", ["header"]))
    exit_ = mkblock("exit", [], IRInstr("ret", [a]))
    func = mkfunc(entry, header, body, latch, exit_)

    assert mkopt(func)._sccp() is False
    assert phi_a.op == "phi" and phi_a.args == [x, b]
    assert phi_b.op == "phi" and phi_b.args == [y, a]


# ---------------------------------------------------------------------------
# CFG, local forwarding, if-conversion and branch guards
# ---------------------------------------------------------------------------


def test_replace_terminator_target_updates_second_conditional_target():
    cond = new_value("Bool")
    block = mkblock("entry", [], IRInstr("cond_br", [cond, "left", "old"]))
    func = mkfunc(block)

    mkopt(func)._replace_terminator_target(block, "old", "new")
    assert block.terminator.args == [cond, "left", "new"]


def test_sroa_keeps_struct_with_unknown_field_user():
    x = const(7)
    st = IRInstr("struct_init", ["P", "a", x.result], result=new_value("P"))
    field_a = IRInstr("field", [st.result, "a"], result=new_value())
    field_b = IRInstr("field", [st.result, "b"], result=new_value())
    block = mkblock(
        "entry", [x, st, field_a, field_b], IRInstr("ret", [field_b.result])
    )
    func = mkfunc(block)

    assert mkopt(func)._sroa() is True
    assert field_a not in block.instructions
    assert field_b in block.instructions
    assert st in block.instructions
    assert st.result.users == [field_b]


def test_field_forwarding_stops_at_earlier_definition_of_base():
    src = new_value("P")
    copy = instr("ref_copy", [src], "P")
    field = instr("field", [copy.result, "a"])
    block = mkblock("entry", [copy, field], IRInstr("ret", [field.result]))
    func = mkfunc(block)

    assert mkopt(func)._field_forwarding() is False
    assert field in block.instructions
    assert field in copy.result.users


def test_if_conversion_skips_non_phi_and_incomplete_phis():
    cond = new_value("Bool")
    a = const(1)
    b = const(2)
    merge_const = const(3)
    phi_result = new_value()
    phi = IRPhi(phi_result, [("left", a.result)])
    entry = mkblock("entry", [], IRInstr("cond_br", [cond, "left", "right"]))
    left = mkblock("left", [a], IRInstr("br", ["merge"]))
    right = mkblock("right", [b], IRInstr("br", ["merge"]))
    merge = mkblock("merge", [merge_const, phi], IRInstr("ret", [phi_result]))
    func = mkfunc(entry, left, right, merge)
    func.build_cfg()

    assert mkopt(func)._if_conversion() is False
    assert not any(i.op == "select" for blk in func.blocks for i in blk.instructions)
    assert entry.terminator.op == "cond_br"
    assert phi.incoming == [("left", a.result)]


def test_jump_threading_takes_true_target_for_equal_constants():
    one = const(1)
    cmp_eq = instr("cmp_eq", [one.result, one.result], "Bool")
    entry = mkblock("entry", [one, cmp_eq], IRInstr("cond_br", [cmp_eq.result, "T", "F"]))
    true_block = mkblock("T", [], IRInstr("ret", [one.result]))
    false_block = mkblock("F", [], IRInstr("ret", [one.result]))
    func = mkfunc(entry, true_block, false_block)

    assert mkopt(func)._jump_threading() is True
    assert entry.terminator.op == "br" and entry.terminator.args == ["T"]


def test_remove_unreachable_blocks_filters_their_phi_incoming():
    x = new_value()
    y = new_value()
    phi = IRPhi(new_value(), [("entry", x), ("dead", y)])
    entry = mkblock("entry", [], IRInstr("br", ["merge"]))
    merge = mkblock("merge", [phi], IRInstr("ret", [phi.result]))
    dead = mkblock("dead", [], IRInstr("ret", [y]))
    func = mkfunc(entry, merge, dead)
    func.build_cfg()

    assert mkopt(func)._remove_unreachable_blocks() is True
    assert "dead" not in func.block_map
    assert phi.incoming == [("entry", x)]


def test_licm_recognises_conditional_loop_back_edge():
    cond = new_value("Bool")
    three = const(3)
    entry = mkblock("entry", [], IRInstr("br", ["header"]))
    header = mkblock("header", [], IRInstr("cond_br", [cond, "body", "exit"]))
    body = mkblock("body", [three], IRInstr("br", ["latch"]))
    latch = mkblock("latch", [], IRInstr("cond_br", [cond, "header", "exit"]))
    exit_ = mkblock("exit", [], IRInstr("ret", [three.result]))
    func = mkfunc(entry, header, body, latch, exit_)

    assert mkopt(func)._licm() is True
    assert body.instructions == []
    assert three in entry.instructions


# ---------------------------------------------------------------------------
# Loop analysis guards
# ---------------------------------------------------------------------------


def make_loop_func(**overrides):
    options = {
        "cmp_op": "cmp_lt",
        "body_op": "add",
        "bound": 3,
        "step": 1,
        "unroll_factor": 4,
        "cond_back_edge": False,
        "extra_incoming": False,
        "const_bound": True,
    }
    options.update(overrides)

    init = const(0)
    bound = const(options["bound"]) if options["const_bound"] else new_value("Int32")
    step = const(options["step"])
    phi_result = new_value()
    next_val = instr(options["body_op"], [phi_result, step.result])
    incoming = [("entry", init.result), ("latch", next_val.result)]
    if options["extra_incoming"]:
        incoming.append(("body", init.result))
    phi = IRPhi(phi_result, incoming)
    bound_arg = bound.result if options["const_bound"] else bound
    cmp_instr = instr(options["cmp_op"], [phi_result, bound_arg], "Bool")

    entry = mkblock(
        "entry", [i for i in (init, bound if options["const_bound"] else None, step) if i],
        IRInstr("br", ["header"]),
    )
    header = mkblock(
        "header", [phi, cmp_instr], IRInstr("cond_br", [cmp_instr.result, "body", "exit"])
    )
    body = mkblock("body", [next_val], IRInstr("br", ["latch"]))
    if options["cond_back_edge"]:
        latch = mkblock(
            "latch", [], IRInstr("cond_br", [new_value("Bool"), "header", "exit"])
        )
    else:
        latch = mkblock("latch", [], IRInstr("br", ["header"]))
    exit_ = mkblock("exit", [], IRInstr("ret", [phi_result]))
    func = mkfunc(entry, header, body, latch, exit_)
    return func, mkopt(func, unroll_factor=options["unroll_factor"])


def test_loop_analysis_recognises_conditional_back_edges():
    func, opt = make_loop_func(cond_back_edge=True)
    assert opt._loop_unrolling() is False
    assert func.block_map["latch"].terminator.op == "cond_br"


def test_loop_analysis_rejects_non_simple_phis():
    _, opt = make_loop_func(extra_incoming=True)
    assert opt._loop_unrolling() is False


def test_loop_analysis_rejects_non_add_recurrences():
    _, opt = make_loop_func(body_op="sub")
    assert opt._loop_unrolling() is False


def test_loop_analysis_rejects_unordered_comparisons():
    _, opt = make_loop_func(cmp_op="cmp_eq")
    assert opt._loop_unrolling() is False


def test_loop_analysis_rejects_non_constant_bounds():
    _, opt = make_loop_func(const_bound=False)
    assert opt._loop_unrolling() is False


def test_loop_analysis_rejects_too_large_trip_counts():
    _, opt = make_loop_func(bound=100)
    assert opt._loop_unrolling() is False


def test_loop_analysis_rejects_partial_unrolling():
    _, opt = make_loop_func(bound=3, unroll_factor=2)
    assert opt._loop_unrolling() is False


# ---------------------------------------------------------------------------
# Inlining decisions and void returns
# ---------------------------------------------------------------------------


def test_inline_module_skips_unknown_and_recursive_calls():
    module = IRModule()
    caller = IRFunction("caller", [], "Int32")
    unknown = instr("call", ["missing"], "Int32")
    recursive = instr("call", ["caller"], "Int32")
    entry = mkblock("entry", [unknown, recursive], IRInstr("ret", [unknown.result]))
    caller.add_block(entry)
    module.add_func(caller)

    mkopt()._inline_module(module)
    assert [i.op for i in entry.instructions] == ["call", "call"]


def test_inlining_void_callee_defines_call_result_with_undef():
    ast = Parser().parse(
        """
def noop() -> NoneType
    return
def run() -> NoneType
    noop()
    return
"""
    )
    CombinedChecker().run_all(ast)
    module = SSABuilder().build_from_ast(ast)
    run = module.funcs[1]
    call_result = next(
        i.result for b in run.blocks for i in b.instructions if i.op == "call"
    )

    IROptimizer(inline_threshold=10)._inline_module(module)
    assert not [i for b in run.blocks for i in b.instructions if i.op == "call"]
    undefs = [i for b in run.blocks for i in b.instructions if i.op == "undef"]
    assert len(undefs) == 1
    assert undefs[0].result is call_result
    assert call_result.def_instr is undefs[0]


def test_if_conversion_keeps_branch_value_definitions():
    """If-conversion must move branch definitions into the merge block.

    Otherwise the emitted ``select`` refers to values whose defining
    instructions were removed with the empty branch blocks (LLVM verifier
    error: use of undefined value).
    """
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
    func = module.funcs[0]
    select = next(
        (i for blk in func.blocks for i in blk.instructions if i.op == "select"),
        None,
    )
    assert select is not None
    defined = {
        i.result: i for blk in func.blocks for i in blk.instructions if i.result
    }
    merge_block = next(b for b in func.blocks if select in b.instructions)
    indices = []
    for value in select.args[1:]:
        assert value in defined
        assert defined[value] in merge_block.instructions
        indices.append(merge_block.instructions.index(defined[value]))
    assert max(indices) < merge_block.instructions.index(select)


def test_inline_threshold_uses_original_function_size():
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
    assert not [i for b in inlined.funcs[1].blocks for i in b.instructions if i.op == "call"]

    not_inlined = optimize(source, inline_threshold=4)
    calls = [i for b in not_inlined.funcs[1].blocks for i in b.instructions if i.op == "call"]
    assert len(calls) == 1
