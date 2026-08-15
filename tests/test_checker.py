import pytest

from compiler.checker import (
    AliasChecker,
    CombinedChecker,
    DeadStoreChecker,
    DuplicateChecker,
    MissingReturnChecker,
    ShadowChecker,
    UnreachableChecker,
    UnusedVariableChecker,
)
from compiler.parser import Parser


def build(source):
    return Parser().parse(source)


def run_checker(checker, source):
    instance = checker()
    method = instance.run_all if isinstance(instance, CombinedChecker) else instance.check
    method(build(source))


def check_ok(checker, source):
    run_checker(checker, source)


def check_error(checker, source):
    with pytest.raises(SystemExit):
        run_checker(checker, source)


def test_combined_accepts_valid_program():
    check_ok(
        CombinedChecker,
        """
struct Point:
    x: Int32
    y: Int32
def clamp(n: Int32, lo: Int32, hi: Int32) -> Int32
    if n < lo:
        result: Int32 = lo
    elif n > hi:
        result: Int32 = hi
    else:
        result: Int32 = n
    return result
def run() -> Int32
    p: Point = Point(x=1, y=2)
    return clamp(p.x, 0, 100)
""",
    )


def test_duplicate_function_rejected():
    check_error(
        DuplicateChecker,
        """
def f() -> Int32
    return 1
def f() -> Int32
    return 2
""",
    )


def test_param_redeclaration_rejected_by_duplicate_checker():
    check_error(
        DuplicateChecker,
        """
def f(x: Int32) -> Int32
    x: Int32 = 1
    return x
""",
    )


def test_param_redeclaration_rejected_by_shadow_checker():
    check_error(
        ShadowChecker,
        """
def f(x: Int32) -> Int32
    x: Int32 = 1
    return x
""",
    )


def test_reference_to_self_rejected():
    check_error(
        AliasChecker,
        """
def f(x: Int32) -> Int32
    x: Int32 = x^
    return x
""",
    )


def test_combined_rejects_duplicate_functions():
    check_error(
        CombinedChecker,
        """
def f() -> Int32
    return 1
def f() -> Int32
    return 2
""",
    )


def test_combined_rejects_reference_to_self():
    check_error(
        CombinedChecker,
        """
def f(x: Int32) -> Int32
    x: Int32 = x^
    return x
""",
    )


def test_unreachable_merge_block_rejected():
    check_error(
        UnreachableChecker,
        """
def f(x: Int32) -> Int32
    if x < 0:
        return 1
    else:
        return 2
""",
    )


def test_unreachable_checker_ok_when_branch_merges():
    check_ok(
        UnreachableChecker,
        """
def f(x: Int32) -> Int32
    if x < 0:
        y: Int32 = 1
    else:
        y: Int32 = 2
    return y
""",
    )


def test_missing_return_ok_when_all_paths_return():
    check_ok(
        MissingReturnChecker,
        """
def f(x: Int32) -> Int32
    if x < 0:
        return 1
    else:
        return 2
""",
    )


def test_missing_return_ok_with_elif_chain():
    check_ok(
        MissingReturnChecker,
        """
def f(x: Int32) -> Int32
    if x < 0:
        return 1
    elif x > 0:
        return 2
    else:
        return 3
""",
    )


def test_alias_declaration_accepted():
    check_ok(
        AliasChecker,
        """
def f(x: Int32) -> Int32
    a: Int32 = x^
    return a
""",
    )


def test_alias_inside_if_accepted():
    check_ok(
        AliasChecker,
        """
def f(x: Int32) -> Int32
    if x < 0:
        a: Int32 = x^
    else:
        a: Int32 = x
    return a
""",
    )


def test_duplicate_checker_ok_on_normal_program():
    check_ok(
        DuplicateChecker,
        """
def f(x: Int32) -> Int32
    if x < 0:
        y: Int32 = 1
    else:
        y: Int32 = 2
    return y
""",
    )


def test_shadow_checker_ok_on_distinct_branches():
    check_ok(
        ShadowChecker,
        """
def f(x: Int32) -> Int32
    if x < 0:
        y: Int32 = 1
    else:
        y: Int32 = 2
    return y
""",
    )


def test_unused_local_warning(capsys):
    source = build(
        """
def f(a: Int32) -> Int32
    b: Int32 = 1
    return a
"""
    )
    UnusedVariableChecker().check(source)
    out = capsys.readouterr().out
    assert "Variable 'b' in function 'f' declared but never used" in out


def test_unused_parameter_warning(capsys):
    source = build(
        """
def f(a: Int32, b: Int32) -> Int32
    return a
"""
    )
    UnusedVariableChecker().check(source)
    out = capsys.readouterr().out
    assert "Parameter 'b' in function 'f' is never used" in out


def test_dead_store_warning(capsys):
    source = build(
        """
def f(a: Int32) -> Int32
    b: Int32 = 1
    return a
"""
    )
    DeadStoreChecker().check(source)
    out = capsys.readouterr().out
    assert "Dead store: variable 'b' assigned but never used" in out


def test_no_warnings_when_everything_used(capsys):
    source = build(
        """
def f(a: Int32) -> Int32
    b: Int32 = a + 1
    return b
"""
    )
    UnusedVariableChecker().check(source)
    DeadStoreChecker().check(source)
    out = capsys.readouterr().out
    assert out == ""


def test_no_dead_store_warning_when_used_in_expr_stmt(capsys):
    source = build(
        """
def f(a: Int32) -> Int32
    b: Int32 = a + 1
    print(b)
    return a
"""
    )
    DeadStoreChecker().check(source)
    out = capsys.readouterr().out
    assert out == ""


def test_no_dead_store_warning_when_used_in_class_init(capsys):
    source = build(
        """
class A:
    def __init__(self: A, n: Int32):
        self.x: Int32 = n
def f(n: Int32) -> Int32
    a: A = A(n)
    return 0
"""
    )
    UnusedVariableChecker().check(source)
    out = capsys.readouterr().out
    assert "Parameter 'n' in function 'f' is never used" not in out


def test_alias_chain_accepted():
    check_ok(
        AliasChecker,
        """
def f(a: Int32, b: Int32) -> Int32
    x: Int32 = a^
    y: Int32 = x^
    return y
""",
    )


def test_alias_cycle_rejected():
    check_error(
        AliasChecker,
        """
def f(a: Int32) -> Int32
    x: Int32 = a^
    a: Int32 = x^
    return a
""",
    )


def test_same_block_redeclaration_rejected_by_shadow():
    check_error(
        ShadowChecker,
        """
def f(x: Int32) -> Int32
    y: Int32 = 1
    y: Int32 = 2
    return y
""",
    )


def test_variable_in_single_branch_rejected_by_duplicate():
    check_error(
        DuplicateChecker,
        """
def f(x: Int32) -> Int32
    if x > 0:
        y: Int32 = 1
    else:
        z: Int32 = 2
    return y
""",
    )


def test_nested_if_missing_return_rejected():
    check_error(
        MissingReturnChecker,
        """
def f(x: Int32) -> Int32
    if x > 0:
        if x > 10:
            return 1
        y: Int32 = x
    else:
        return 2
""",
    )


def test_statement_after_return_rejected_by_unreachable():
    check_error(
        UnreachableChecker,
        """
def f(x: Int32) -> Int32
    return x
    y: Int32 = 1
""",
    )


def test_dead_store_in_branch_warning(capsys):
    source = build(
        """
def f(a: Int32) -> Int32
    if a > 0:
        b: Int32 = 1
    else:
        b: Int32 = 2
    return a
"""
    )
    DeadStoreChecker().check(source)
    out = capsys.readouterr().out
    assert "Dead store: variable 'b' assigned but never used" in out


def test_unused_variable_in_branch_warning(capsys):
    source = build(
        """
def f(a: Int32) -> Int32
    if a > 0:
        b: Int32 = 1
    else:
        b: Int32 = 2
    return a
"""
    )
    UnusedVariableChecker().check(source)
    out = capsys.readouterr().out
    assert "Variable 'b' in function 'f' declared but never used" in out


def test_missing_return_when_function_has_no_return():
    check_error(
        MissingReturnChecker,
        """
def f() -> Int32
    x: Int32 = 1
""",
    )


def test_combined_rejects_variable_missing_from_else_branch():
    check_error(
        CombinedChecker,
        """
def f(x: Int32) -> Int32
    if x > 0:
        v: Int32 = x
        r: Int32 = v
    else:
        r: Int32 = x
    return r
""",
    )


def test_param_shadowing_in_branches_rejected():
    check_error(
        ShadowChecker,
        """
def f(x: Int32) -> Int32
    if x > 0:
        x: Int32 = 1
    else:
        x: Int32 = 2
    return x
""",
    )


def test_if_returns_without_else_is_reachable():
    check_ok(
        UnreachableChecker,
        """
def f(x: Int32) -> Int32
    if x > 0:
        return 1
    return 0
""",
    )


def test_unreachable_block_when_both_branches_return():
    check_error(
        UnreachableChecker,
        """
def f(x: Int32) -> Int32
    if x > 0:
        return 1
    else:
        return 2
    return 0
""",
    )
