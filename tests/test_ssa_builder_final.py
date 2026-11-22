"""Behavioural tests for SSA users bookkeeping on loop latch phis.

A latch phi merges the values carried by the fallthrough and ``continue``
back edges. Builder-created phis must appear exactly once in each incoming
value's ``users`` list, including when the same value arrives on both edges.
"""
from compiler.threadon.parser import Parser
from compiler.threadon.to_high_ir import IRPhi, SSAValue, SSABuilder


def build_function(source):
    module = SSABuilder().build_from_ast(Parser().parse(source))
    return next(func for func in module.funcs if func.name == "f")


def latch_phis(func):
    return [
        instr
        for instr in func.block_map["whilelatch"].instructions
        if isinstance(instr, IRPhi)
    ]


def test_latch_phi_records_a_repeated_incoming_value_only_once():
    func = build_function(
        """
def f() -> Int32
    for i in range(3):
        if i == 1:
            continue
        print(i)
    return 0
"""
    )

    phis = latch_phis(func)
    assert len(phis) == 2  # the induction variable and the iterator

    for phi in phis:
        assert [label for label, _ in phi.incoming] == [
            "merge1_",
            "ifbody1_0",
        ]

        values = [value for _, value in phi.incoming]
        assert values[0] is values[1]
        assert phi.args == values
        assert isinstance(values[0], SSAValue)
        assert phi in values[0].users
        assert values[0].users.count(phi) == 1


def test_latch_phi_records_distinct_back_edge_values_as_users():
    func = build_function(
        """
def f(n: Int32) -> Int32
    while n > 0:
        if n == 2:
            continue
        n = n - 1
    return 0
"""
    )

    (phi,) = latch_phis(func)
    assert [label for label, _ in phi.incoming] == [
        "merge1_",
        "ifbody1_0",
    ]

    fallthrough_value, continue_value = (
        value for _, value in phi.incoming
    )
    assert fallthrough_value is not continue_value
    assert phi.args == [fallthrough_value, continue_value]

    for value in (fallthrough_value, continue_value):
        assert isinstance(value, SSAValue)
        assert phi in value.users
        assert value.users.count(phi) == 1

    cond_phi = next(
        instr
        for instr in func.block_map["whilecond"].instructions
        if isinstance(instr, IRPhi)
    )
    latch_value = next(
        value
        for label, value in cond_phi.incoming
        if label == "whilelatch"
    )
    assert latch_value is phi.result
    assert cond_phi in phi.result.users
