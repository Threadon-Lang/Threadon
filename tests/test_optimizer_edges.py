"""Edge-case tests for the IR optimizer passes.

The tests build small, explicit IR fragments and drive individual optimizer
passes (or the whole optimizer) so that rarely taken branches of each pass are
exercised, while still asserting the concrete IR transformation performed.
"""

import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from compiler.threadon.optimalise_ir import IROptimizer
from compiler.threadon.to_high_ir import (
    IRBlock,
    IRFunction,
    IRInstr,
    IRPhi,
    SSAValue,
)


_counter = itertools.count()


def new_value(type_="Int32"):
    return SSAValue(f"%edge{next(_counter)}", type_)


def const(value_, type_="Int32"):
    return IRInstr("const", [value_], result=new_value(type_))


def instr(op, args, type_="Int32"):
    return IRInstr(op, list(args), result=new_value(type_))


def mkblock(label, instructions=(), terminator=None):
    b = IRBlock(label)
    for i in instructions:
        b.add_instr(i)
    if terminator is not None:
        b.set_terminator(terminator)
    return b


def mkfunc(*blocks, name="f", params=(), return_type="Int32"):
    f = IRFunction(name, list(params), return_type)
    for b in blocks:
        f.add_block(b)
    return f


def mkopt(func=None, **kwargs):
    opt = IROptimizer(**kwargs)
    if func is not None:
        opt.func = func
    return opt


def fold_binary(op, left, right, type_="Int32", debug_mode=False):
    """Build a block whose only interesting instruction is a binary op."""
    a = const(left, type_)
    b = const(right, type_)
    op_instr = instr(op, [a.result, b.result], type_)
    ret = IRInstr("ret", [op_instr.result])
    blk = mkblock("entry", [a, b, op_instr], ret)
    func = mkfunc(blk, return_type=type_)
    opt = mkopt(func, debug_mode=debug_mode)
    changed = opt._constant_folding()
    return func, op_instr, changed


# ---------------------------------------------------------------------------
# _int_bounds / _fold_number / _constant_folding
# ---------------------------------------------------------------------------


def test_unsigned_bounds_allow_max_value_in_debug_mode():
    opt = mkopt(debug_mode=True)
    assert opt._int_bounds("UInt8") == (0, 255)
    func, op_instr, changed = fold_binary("add", 200, 55, "UInt8", debug_mode=True)
    assert changed is True
    assert op_instr.op == "const" and op_instr.args == [255]
    assert func.block_map["entry"].terminator.args == [op_instr.result]


def test_integer_division_and_modulo_by_zero_are_not_folded():
    for op in ("div", "floordiv", "mod"):
        func, op_instr, changed = fold_binary(op, 7, 0)
        assert changed is False
        assert op_instr.op == op
        assert op_instr.args[0].def_instr.args == [7]
        assert op_instr.args[1].def_instr.args == [0]


def test_debug_mode_rejects_out_of_range_integer_results():
    cases = [
        ("div", -128, -1),
        ("floordiv", -128, -1),
        ("add", 100, 100),
        ("sub", -100, 100),
        ("mul", 100, 2),
        ("pow", 12, 2),
    ]
    for op, left, right in cases:
        func, op_instr, changed = fold_binary(op, left, right, "Int8", debug_mode=True)
        assert changed is False, op
        assert op_instr.op == op
    # Negative exponents are never folded for integer results.
    func, op_instr, changed = fold_binary("pow", 2, -1, "Int32")
    assert changed is False and op_instr.op == "pow"


def test_float_division_modulo_and_invalid_power_are_not_folded():
    for op, left, right in [
        ("div", 1.0, 0.0),
        ("floordiv", 1.0, 0.0),
        ("mod", 1.0, 0.0),
        ("pow", 0.0, -1.0),
    ]:
        func, op_instr, changed = fold_binary(op, left, right, "Float32")
        assert changed is False, op
        assert op_instr.op == op


def test_fold_number_returns_none_for_unhandled_operators():
    opt = mkopt()
    assert opt._fold_number("bit_and", 1, 2, "Int32") is None
    assert opt._fold_number("bit_and", 1.0, 2.0, "Float32") is None


def test_comparison_and_unary_constant_folding():
    a = const(1)
    b = const(2)
    t = const(True, "Bool")
    ops = [
        instr("cmp_le", [a.result, b.result], "Bool"),
        instr("cmp_ge", [a.result, b.result], "Bool"),
        instr("cmp_eq", [a.result, b.result], "Bool"),
        instr("cmp_ne", [a.result, b.result], "Bool"),
        instr("neg", [a.result]),
        instr("pos", [a.result]),
        instr("not", [t.result], "Bool"),
    ]
    ret = IRInstr("ret", [ops[-1].result])
    func = mkfunc(mkblock("entry", [a, b, t, *ops], ret))
    opt = mkopt(func)

    assert opt._constant_folding() is True
    assert [i.op for i in func.block_map["entry"].instructions] == ["const"] * 10
    assert [i.args[0] for i in ops] == [True, False, False, True, -1, 1, False]


def test_debug_mode_skips_out_of_range_negation():
    a = const(-128, "Int8")
    neg = instr("neg", [a.result], "Int8")
    func = mkfunc(mkblock("entry", [a, neg], IRInstr("ret", [neg.result])))
    opt = mkopt(func, debug_mode=True)
    assert opt._constant_folding() is False
    assert neg.op == "neg"


# ---------------------------------------------------------------------------
# _sccp
# ---------------------------------------------------------------------------


def test_sccp_on_function_without_blocks():
    assert mkopt(mkfunc())._sccp() is False


def test_sccp_does_not_fold_unknown_unary_or_select_conditions():
    x = new_value()
    neg = instr("neg", [x])
    t = const(10)
    f = const(20)
    cond = new_value("Bool")
    sel = instr("select", [cond, t.result, f.result])
    func = mkfunc(mkblock("entry", [neg, t, f, sel], IRInstr("ret", [sel.result])))
    opt = mkopt(func)

    opt._sccp()
    assert neg.op == "neg"
    assert sel.op == "select"
    assert func.block_map["entry"].terminator.args == [sel.result]


def test_sccp_folds_select_with_constant_condition():
    for condition, expected in [(True, 10), (False, 20)]:
        c = const(condition, "Bool")
        t = const(10)
        f = const(20)
        sel = instr("select", [c.result, t.result, f.result])
        func = mkfunc(mkblock("entry", [c, t, f, sel], IRInstr("ret", [sel.result])))
        opt = mkopt(func)
        assert opt._sccp() is True
        assert sel.op == "const"
        assert sel.args == [expected]
        assert func.block_map["entry"].terminator.args == [sel.result]


def test_sccp_debug_mode_keeps_overflowing_negation():
    c = const(-128, "Int8")
    neg = instr("neg", [c.result], "Int8")
    func = mkfunc(mkblock("entry", [c, neg], IRInstr("ret", [neg.result])))
    opt = mkopt(func, debug_mode=True)
    opt._sccp()
    assert neg.op == "neg"
    assert neg.args == [c.result]


# ---------------------------------------------------------------------------
# _strength_reduction
# ---------------------------------------------------------------------------


def test_mul_with_power_of_two_on_left_becomes_shift():
    c = const(8)
    x = new_value()
    mul = instr("mul", [c.result, x])
    func = mkfunc(mkblock("entry", [c, mul], IRInstr("ret", [mul.result])))
    opt = mkopt(func)
    assert opt._strength_reduction() is True
    assert mul.op == "shl"
    assert mul.args == [x, 3]
    assert func.block_map["entry"].terminator.args == [mul.result]


def test_pow_two_and_three_become_multiplications():
    x = new_value()
    two = const(2)
    three = const(3)
    p2 = instr("pow", [x, two.result])
    p3 = instr("pow", [x, three.result])
    func = mkfunc(mkblock("entry", [two, three, p2, p3], IRInstr("ret", [p3.result])))
    opt = mkopt(func)
    assert opt._strength_reduction() is True
    body = func.block_map["entry"].instructions
    assert [i.op for i in body] == ["const", "const", "mul", "mul", "mul"]
    assert p2.op == "mul" and p2.args == [x, x]
    assert p3.op == "mul"
    squared = p3.args[1]
    assert isinstance(squared, SSAValue)
    assert squared.def_instr.op == "mul" and squared.def_instr.args == [x, x]


# ---------------------------------------------------------------------------
# _algebraic_simplification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("args,expected", [([None, 1], 0), ([1, None], 1)])
def test_mul_by_one_on_either_side_is_removed(args, expected):
    x = new_value()
    one = const(1)
    mul_args = [x if a is None else one.result for a in args]
    mul = instr("mul", mul_args)
    func = mkfunc(mkblock("entry", [one, mul], IRInstr("ret", [mul.result])))
    opt = mkopt(func)
    assert opt._algebraic_simplification() is True
    assert func.block_map["entry"].instructions == [one]
    assert func.block_map["entry"].terminator.args == [x]


def test_ref_copy_of_ref_copy_collapses_to_original():
    x = new_value()
    first = instr("ref_copy", [x])
    second = instr("ref_copy", [first.result])
    func = mkfunc(mkblock("entry", [first, second], IRInstr("ret", [second.result])))
    opt = mkopt(func)
    assert opt._algebraic_simplification() is True
    assert func.block_map["entry"].instructions == [first]
    assert func.block_map["entry"].terminator.args == [x]


# ---------------------------------------------------------------------------
# _peephole
# ---------------------------------------------------------------------------


def test_peephole_comparisons_with_boolean_constants():
    x = new_value("Bool")
    t = const(True, "Bool")
    f = const(False, "Bool")

    eq_true = instr("cmp_eq", [x, t.result], "Bool")
    b1 = mkblock("b1", [t, eq_true], IRInstr("ret", [eq_true.result]))
    eq_left_true = instr("cmp_eq", [t.result, x], "Bool")
    b2 = mkblock("b2", [t, eq_left_true], IRInstr("ret", [eq_left_true.result]))
    ne_false = instr("cmp_ne", [x, f.result], "Bool")
    b3 = mkblock("b3", [f, ne_false], IRInstr("ret", [ne_false.result]))
    ne_left_false = instr("cmp_ne", [f.result, x], "Bool")
    b4 = mkblock("b4", [f, ne_left_false], IRInstr("ret", [ne_left_false.result]))
    eq_false = instr("cmp_eq", [x, f.result], "Bool")
    b5 = mkblock("b5", [f, eq_false], IRInstr("ret", [eq_false.result]))

    func = mkfunc(b1, b2, b3, b4, b5, return_type="Bool")
    opt = mkopt(func)
    assert opt._peephole() is True
    for blk in func.blocks[:-1]:
        assert [i.op for i in blk.instructions] == ["const"]
        assert blk.terminator.args == [x]
    assert [i.op for i in func.blocks[-1].instructions] == ["const", "not"]
    assert func.blocks[-1].terminator.args == [eq_false.result]

    assert eq_false.op == "not"
    assert eq_false.args == [x]
    assert opt is not None


def test_peephole_add_and_sub_cancellations():
    x = new_value()
    y = new_value()

    sub = instr("sub", [x, y])
    add1 = instr("add", [sub.result, y])
    b1 = mkblock("b1", [sub, add1], IRInstr("ret", [add1.result]))

    sub2 = instr("sub", [x, y])
    add2 = instr("add", [y, sub2.result])
    b2 = mkblock("b2", [sub2, add2], IRInstr("ret", [add2.result]))

    add3 = instr("add", [x, y])
    sub3 = instr("sub", [add3.result, y])
    b3 = mkblock("b3", [add3, sub3], IRInstr("ret", [sub3.result]))

    add4 = instr("add", [x, y])
    sub4 = instr("sub", [add4.result, x])
    b4 = mkblock("b4", [add4, sub4], IRInstr("ret", [sub4.result]))

    func = mkfunc(b1, b2, b3, b4)
    opt = mkopt(func)
    assert opt._peephole() is True
    assert [i.op for i in func.block_map["b1"].instructions] == ["sub"]
    assert [i.op for i in func.block_map["b2"].instructions] == ["sub"]
    assert [i.op for i in func.block_map["b3"].instructions] == ["add"]
    assert [i.op for i in func.block_map["b4"].instructions] == ["add"]
    assert [b.terminator.args for b in func.blocks] == [[x], [x], [x], [y]]


# ---------------------------------------------------------------------------
# _replace_value, _copy_propagation, _cse, _gvn, _sroa, _simplify_phi
# ---------------------------------------------------------------------------


def test_replace_value_with_itself_keeps_users():
    x = new_value()
    user = instr("add", [x, x])
    opt = mkopt()
    opt._replace_value(x, x)
    assert x.users == [user, user]


def test_copy_propagation_removes_ref_copy_and_runs_dce():
    x = new_value()
    cp = instr("ref_copy", [x])
    blk = mkblock("entry", [cp], IRInstr("ret", [cp.result]))
    func = mkfunc(blk)
    opt = mkopt(func)
    assert opt._copy_propagation() is True
    assert blk.instructions == []
    assert blk.terminator.args == [x]


def test_cse_accepts_pure_instruction_without_result():
    x = new_value()
    y = new_value()
    side = IRInstr("add", [x, y])
    blk = mkblock("entry", [side], IRInstr("ret", [0]))
    func = mkfunc(blk)
    opt = mkopt(func)
    assert opt._cse() is False
    assert blk.instructions == [side]


def test_gvn_accepts_pure_instruction_without_result():
    x = new_value()
    y = new_value()
    side = IRInstr("add", [x, y])
    blk = mkblock("entry", [side], IRInstr("ret", [0]))
    func = mkfunc(blk)
    opt = mkopt(func)
    assert opt._gvn() is False
    assert blk.instructions == [side]


def test_gvn_eliminates_duplicate_expression_in_dominated_block():
    x = new_value()
    y = new_value()
    # GVN compares value names with dominator labels, so use a matching name.
    common = SSAValue("entry", "Int32")
    first = IRInstr("add", [x, y], result=common)
    duplicate = instr("add", [x, y])
    entry = mkblock("entry", [first], IRInstr("br", ["B"]))
    body = mkblock("B", [duplicate], IRInstr("ret", [duplicate.result]))
    func = mkfunc(entry, body)
    opt = mkopt(func)

    assert opt._gvn() is True
    assert body.instructions == []
    assert body.terminator.args == [common]


def test_sroa_removes_dead_struct_init():
    x = new_value()
    st = IRInstr("struct_init", ["P", "a", x], result=new_value("P"))
    blk = mkblock("entry", [st], IRInstr("ret", [0]))
    func = mkfunc(blk)
    opt = mkopt(func)

    assert opt._sroa() is True
    assert blk.instructions == []
    assert blk.terminator.args == [0]
    assert st.result.def_instr is None


def test_simplify_phi_removes_self_referential_phi():
    res = new_value()
    phi = IRPhi(res, [("entry", res), ("loop", res)])
    blk = mkblock("entry", [phi], IRInstr("ret", [res]))
    func = mkfunc(blk)
    opt = mkopt(func)

    assert opt._simplify_phi() is True
    assert blk.instructions == []
    assert blk.terminator.args == [res]
    assert phi not in res.users


def test_simplify_phi_deduplicates_repeated_predecessor_labels():
    x = new_value()
    y = new_value()
    z = new_value()
    phi = IRPhi(new_value(), [("a", x), ("a", y), ("b", z)])
    blk = mkblock("entry", [phi], IRInstr("ret", [phi.result]))
    func = mkfunc(blk)
    opt = mkopt(func)

    assert opt._simplify_phi() is True
    assert phi.incoming == [("a", y), ("b", z)]
    assert blk.instructions == [phi]


# ---------------------------------------------------------------------------
# _if_conversion, _tail_call_opt, _branch_simplification, _jump_threading
# ---------------------------------------------------------------------------


def test_if_conversion_ignores_missing_branch_targets():
    cond = new_value("Bool")
    blk = mkblock("entry", [], IRInstr("cond_br", [cond, "missing", "missing2"]))
    func = mkfunc(blk)
    opt = mkopt(func)
    assert opt._if_conversion() is False
    assert blk.terminator.op == "cond_br"
    assert blk.terminator.args == [cond, "missing", "missing2"]


def test_tail_call_opt_ignores_literal_return_value():
    blk = mkblock("entry", [], IRInstr("ret", [42]))
    func = mkfunc(blk)
    opt = mkopt(func)
    assert opt._tail_call_opt() is False
    assert blk.terminator.args == [42]


def test_branch_simplification_does_not_duplicate_existing_phi_incoming_edge():
    x = new_value()
    y = new_value()
    phi = IRPhi(new_value(), [("entry", x), ("jump", y)])
    entry = mkblock("entry", [], IRInstr("br", ["jump"]))
    jump = mkblock("jump", [], IRInstr("br", ["merge"]))
    merge = mkblock("merge", [phi], IRInstr("ret", [phi.result]))
    func = mkfunc(entry, jump, merge)
    func.build_cfg()
    opt = mkopt(func)

    assert opt._branch_simplification() is True
    assert entry.terminator.args == ["merge"]
    assert phi.incoming == [("entry", x), ("jump", y)]


def test_jump_threading_takes_false_edge_for_false_comparison():
    a = const(1)
    b = const(2)
    cmp = instr("cmp_eq", [a.result, b.result], "Bool")
    entry = mkblock(
        "entry", [a, b, cmp], IRInstr("cond_br", [cmp.result, "yes", "no"])
    )
    yes = mkblock("yes", [], IRInstr("ret", [1]))
    no = mkblock("no", [], IRInstr("ret", [2]))
    func = mkfunc(entry, yes, no)
    opt = mkopt(func)

    assert opt._jump_threading() is True
    assert entry.terminator.op == "br"
    assert entry.terminator.args == ["no"]


# ---------------------------------------------------------------------------
# _remove_empty_blocks, _remove_unreachable_blocks
# ---------------------------------------------------------------------------


def test_remove_empty_blocks_keeps_self_referential_trampoline():
    trampoline = mkblock("self", [], IRInstr("br", ["self"]))
    entry = mkblock("entry", [], IRInstr("br", ["exit"]))
    exit_ = mkblock("exit", [], IRInstr("ret", [0]))
    func = mkfunc(entry, trampoline, exit_)
    opt = mkopt(func)
    assert opt._remove_empty_blocks() is False
    assert "self" in func.block_map
    assert trampoline.terminator.args == ["self"]


def test_remove_empty_blocks_keeps_predecessor_that_already_jumps_to_target():
    x = new_value()
    phi = IRPhi(new_value(), [("entry", x)])
    entry = mkblock("entry", [], IRInstr("cond_br", [True, "jump", "merge"]))
    jump = mkblock("jump", [], IRInstr("br", ["merge"]))
    merge = mkblock("merge", [phi], IRInstr("ret", [phi.result]))
    func = mkfunc(entry, jump, merge)
    func.build_cfg()
    opt = mkopt(func)

    assert opt._remove_empty_blocks() is False
    assert "jump" in func.block_map
    assert entry.terminator.args == [True, "jump", "merge"]
    assert phi.incoming == [("entry", x)]


def test_remove_unreachable_blocks_on_empty_function():
    assert mkopt(mkfunc())._remove_unreachable_blocks() is False


def test_remove_unreachable_blocks_cleans_stale_successor_metadata():
    entry = mkblock("entry", [], IRInstr("br", ["exit"]))
    dead = mkblock("dead", [], IRInstr("br", ["exit"]))
    exit_ = mkblock("exit", [], IRInstr("ret", [0]))
    func = mkfunc(entry, dead, exit_)
    func.build_cfg()
    entry.successors.append("dead")
    opt = mkopt(func)

    assert opt._remove_unreachable_blocks() is True
    assert [b.label for b in func.blocks] == ["entry", "exit"]
    assert "dead" not in entry.successors
    assert entry.terminator.args == ["exit"]


# ---------------------------------------------------------------------------
# _licm / _get_or_create_preheader
# ---------------------------------------------------------------------------


def test_licm_moves_invariant_instruction_into_single_entry_predecessor():
    x = new_value()
    phi = IRPhi(new_value(), [("entry", x), ("body", x)])
    entry = mkblock("entry", [], IRInstr("br", ["header"]))
    header = mkblock(
        "header", [phi], IRInstr("cond_br", [True, "body", "exit"])
    )
    inv = instr("add", [x, x])
    body = mkblock("body", [inv], IRInstr("br", ["header"]))
    exit_ = mkblock("exit", [], IRInstr("ret", [phi.result]))
    func = mkfunc(entry, header, body, exit_)
    opt = mkopt(func)

    assert opt._licm() is True
    assert entry.instructions == [inv]
    assert body.instructions == []
    assert header.instructions == [phi]
    assert exit_.terminator.args == [phi.result]


def test_licm_creates_preheader_for_multiple_entry_predecessors():
    x = new_value()
    y = new_value()
    z = new_value()
    phi = IRPhi(
        new_value(), [("A", x), ("B", y), ("body", z)]
    )
    entry = mkblock("entry", [], IRInstr("cond_br", [True, "A", "B"]))
    a = mkblock("A", [], IRInstr("br", ["header"]))
    b = mkblock("B", [], IRInstr("br", ["header"]))
    header = mkblock(
        "header", [phi], IRInstr("cond_br", [True, "body", "exit"])
    )
    inv = instr("add", [x, y])
    body = mkblock("body", [inv], IRInstr("br", ["header"]))
    exit_ = mkblock("exit", [], IRInstr("ret", [phi.result]))
    func = mkfunc(entry, a, b, header, body, exit_)
    opt = mkopt(func)

    assert opt._licm() is True
    pre = func.block_map["pre_header"]
    assert pre.terminator.op == "br" and pre.terminator.args == ["header"]
    assert a.terminator.args == ["pre_header"]
    assert b.terminator.args == ["pre_header"]
    assert set(header.predecessors) == {"pre_header", "body"}
    assert set(pre.predecessors) == {"A", "B"}
    assert [lbl for lbl, _ in phi.incoming] == ["pre_header", "pre_header", "body"]
    assert pre.instructions == [inv]
    assert body.instructions == []


def test_licm_without_non_backedge_predecessor_keeps_instruction_in_place():
    x = new_value()
    inv = instr("add", [x, x])
    entry = mkblock("entry", [inv], IRInstr("br", ["entry"]))
    func = mkfunc(entry)
    opt = mkopt(func)
    assert opt._licm() is False
    assert entry.instructions == [inv]


def test_licm_ignores_block_without_terminator():
    x = new_value()
    inv = instr("add", [x, x])
    entry = mkblock("entry", [inv])
    func = mkfunc(entry)
    opt = mkopt(func)
    assert opt._licm() is False
    assert entry.instructions == [inv]


def test_licm_does_not_hoist_struct_init_out_of_loop():
    st = IRInstr("struct_init", ["P"], result=new_value("P"))
    entry = mkblock("entry", [], IRInstr("br", ["header"]))
    header = mkblock("header", [], IRInstr("cond_br", [True, "body", "exit"]))
    body = mkblock("body", [st], IRInstr("br", ["header"]))
    exit_ = mkblock("exit", [], IRInstr("ret", [0]))
    func = mkfunc(entry, header, body, exit_)
    opt = mkopt(func)

    assert opt._licm() is False
    assert body.instructions == [st]
    assert "pre_header" not in func.block_map


# ---------------------------------------------------------------------------
# _loop_unrolling
# ---------------------------------------------------------------------------


def counting_loop(
    cmp_op="cmp_lt",
    init=0,
    bound=3,
    step=1,
    header_cond=None,
    init_const=True,
    bound_const=True,
    step_const=True,
    back_label="body",
    extra_block=False,
):
    """Build a canonical counted loop with an induction phi in the header."""
    init_c = const(init) if init_const else None
    bound_c = const(bound) if bound_const else None
    step_c = const(step) if step_const else None
    init_val = init_c.result if init_c else new_value()
    bound_val = bound_c.result if bound_c else new_value()
    step_val = step_c.result if step_c else new_value()

    i = new_value()
    next_val = instr("add", [i, step_val])
    phi = IRPhi(i, [("entry", init_val), (back_label, next_val.result)])
    cond = new_value("Bool")
    cmp_instr = IRInstr(cmp_op, [i, bound_val], result=cond)

    entry_instrs = [v for v in (init_c, bound_c, step_c) if v is not None]
    entry = mkblock("entry", entry_instrs, IRInstr("br", ["header"]))
    header_instrs = [phi, cmp_instr]
    if header_cond == "br":
        header_term = IRInstr("br", ["body"])
    elif header_cond is not None:
        header_term = IRInstr("cond_br", [header_cond, "body", "exit"])
    else:
        header_term = IRInstr("cond_br", [cond, "body", "exit"])
    header = mkblock("header", header_instrs, header_term)
    body = mkblock("body", [next_val], IRInstr("br", ["header"]))
    exit_ = mkblock("exit", [], IRInstr("ret", [i]))
    blocks = [entry, header, body, exit_]
    if extra_block:
        blocks.append(mkblock("detached", []))
    func = mkfunc(*blocks)
    return func, phi, cmp_instr


def test_loop_unrolling_analyses_cmp_le_loop_without_changing_it():
    func, phi, cmp_instr = counting_loop(cmp_op="cmp_le")
    opt = mkopt(func)
    assert opt._loop_unrolling() is False
    assert cmp_instr.op == "cmp_le"
    assert len(phi.incoming) == 2
    assert func.block_map["body"].instructions[0].op == "add"


def test_loop_unrolling_rejects_trip_count_of_one():
    func, phi, _ = counting_loop(init=0, bound=1, step=1)
    opt = mkopt(func)
    assert opt._loop_unrolling() is False
    assert len(phi.incoming) == 2


def test_loop_unrolling_rejects_zero_step():
    func, _, _ = counting_loop(step=0)
    opt = mkopt(func)
    assert opt._loop_unrolling() is False


def test_loop_unrolling_rejects_header_without_conditional_branch():
    func, _, _ = counting_loop(header_cond="br")
    opt = mkopt(func)
    assert opt._loop_unrolling() is False
    assert func.block_map["header"].terminator.op == "br"


def test_loop_unrolling_rejects_non_ssa_condition():
    func, _, _ = counting_loop(header_cond=True)
    opt = mkopt(func)
    assert opt._loop_unrolling() is False
    assert func.block_map["header"].terminator.args[0] is True


def test_loop_unrolling_rejects_non_constant_initial_value():
    func, _, _ = counting_loop(init_const=False)
    opt = mkopt(func)
    assert opt._loop_unrolling() is False


def test_loop_unrolling_rejects_phi_without_matching_backedge_label():
    func, phi, _ = counting_loop(back_label="unexpected")
    opt = mkopt(func)
    assert opt._loop_unrolling() is False
    assert [lbl for lbl, _ in phi.incoming] == ["entry", "unexpected"]


def test_loop_unrolling_ignores_block_without_terminator():
    func, _, _ = counting_loop(extra_block=True)
    opt = mkopt(func)
    assert opt._loop_unrolling() is False
    assert func.block_map["detached"].terminator is None
