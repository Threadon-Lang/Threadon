import io
from contextlib import redirect_stdout

import pytest

from compiler.threadon.checker import (
    AliasChecker,
    CombinedChecker,
    DeadStoreChecker,
    DuplicateChecker,
    MissingReturnChecker,
    PurityChecker,
    ShadowChecker,
    UnreachableChecker,
    UnusedVariableChecker,
)
from compiler.threadon.parser import Parser


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
    check_ok(
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


def test_unused_variable_only_warned_once(capsys):
    source = build(
        """
def f(a: Int32) -> Int32
    b: Int32 = 1
    return a
"""
    )
    UnusedVariableChecker().check(source)
    DeadStoreChecker().check(source)
    out = capsys.readouterr().out
    assert out.count("Variable 'b'") == 1
    assert "Dead store" not in out


def test_dead_store_overwritten_warning(capsys):
    source = build(
        """
def f(a: Int32) -> Int32
    b: Int32 = a + 1
    b = 5
    return b
"""
    )
    DeadStoreChecker().check(source)
    out = capsys.readouterr().out
    assert "Dead store: 'b' assigned but overwritten before it is read" in out


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


def test_no_dead_store_warning_for_conditional_overwrite(capsys):
    source = build(
        """
def f(a: Int32) -> Int32
    b: Int32 = 1
    if a > 0:
        b = 2
    return b
"""
    )
    DeadStoreChecker().check(source)
    out = capsys.readouterr().out
    assert out == ""


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


def check_pure_ok(source, native_functions=None, global_vars=None):
    PurityChecker(
        native_functions=native_functions,
        global_vars=global_vars,
    ).check(build(source))


def check_pure_error(source, native_functions=None, global_vars=None):
    with pytest.raises(SystemExit):
        check_pure_ok(source, native_functions, global_vars)


def test_purity_allows_calls_to_pure_functions():
    check_pure_ok(
        """
puredef helper(x: Int32) -> Int32
    return x + 1
puredef f(x: Int32) -> Int32
    return helper(x) * 2
"""
    )


def test_purity_allows_pure_builtins_and_local_mutation():
    check_pure_ok(
        """
puredef f() -> Int64
    xs: List[Int32] = []
    xs.append(1)
    return len(xs)
"""
    )


def test_purity_allows_pure_methods():
    check_pure_ok(
        """
class P:
    x: Int32
    puredef twice(self: P) -> Int32
        return self.x * 2
puredef f(p: P) -> Int32
    return p.twice()
"""
    )


def test_purity_rejects_non_pure_calls():
    check_pure_error(
        """
def helper(x: Int32) -> Int32
    return x + 1
puredef f(x: Int32) -> Int32
    return helper(x)
"""
    )


def test_purity_rejects_non_pure_builtins():
    check_pure_error(
        """
puredef f() -> Int32
    print("side effect")
    return 1
"""
    )


def test_purity_rejects_global_writes():
    check_pure_error(
        """
counter: Int32 = 0
puredef f() -> Int32
    counter = 1
    return counter
"""
    )


def test_purity_rejects_mutating_global_lists():
    check_pure_error(
        """
items: List[Int32] = []
puredef f() -> Int64
    items.append(1)
    return len(items)
"""
    )


def test_purity_rejects_non_pure_methods():
    check_pure_error(
        """
class P:
    x: Int32
    def twice(self: P) -> Int32
        return self.x * 2
puredef f(p: P) -> Int32
    return p.twice()
"""
    )


def test_purity_rejects_non_pure_constructors():
    check_pure_error(
        """
class P:
    x: Int32
    def __init__(self: P, x: Int32)
        self.x = x
puredef f() -> P
    return P(1)
"""
    )


def test_purity_rejects_native_functions():
    check_pure_error(
        """
puredef f() -> Int64
    return now()
""",
        native_functions={"time.now"},
    )


def test_purity_rejects_indexing_writes_to_globals():
    check_pure_error(
        """
items: List[Int32] = [1]
puredef f() -> Int64
    items[0] = 2
    return len(items)
"""
    )


def check_pure_error_message(source, needle, native_functions=None, global_vars=None):
    output = io.StringIO()
    with redirect_stdout(output):
        with pytest.raises(SystemExit):
            check_pure_ok(source, native_functions, global_vars)
    assert needle in output.getvalue()


def test_purity_allows_transitive_pure_calls_and_recursion():
    check_pure_ok(
        """
puredef leaf(x: Int32) -> Int32
    return x + 1
puredef middle(x: Int32) -> Int32
    return leaf(x) * 2
puredef top(x: Int32) -> Int32
    return middle(x) - 1
puredef countdown(n: Int32) -> Int32
    if n <= 0:
        return 0
    return countdown(n - 1)
"""
    )


def test_purity_allows_pure_init_and_pure_constructor_call():
    check_pure_ok(
        """
class Point:
    x: Int32
    puredef __init__(self: Point, x: Int32)
        self.x = x
    puredef value(self: Point) -> Int32
        return self.x
puredef make(x: Int32) -> Point
    return Point(x)
"""
    )


def test_purity_rejects_field_writes_to_globals():
    check_pure_error_message(
        """
struct P:
    x: Int32
p: P = P(x=1)
puredef f() -> Int32
    p.x = 2
    return 1
""",
        "may not write global variable 'p'",
    )


def test_purity_rejects_nested_index_writes_to_globals():
    check_pure_error_message(
        """
items: List[List[Int32]] = [[1]]
puredef f() -> Int64
    items[0][0] = 2
    return len(items)
""",
        "may not write global variable 'items'",
    )


def test_purity_rejects_mutating_nested_global_lists():
    check_pure_error_message(
        """
items: List[List[Int32]] = [[1]]
puredef f() -> Int64
    items[0].append(2)
    return len(items)
""",
        "may not write global variable 'items'",
    )


@pytest.mark.parametrize(
    "call", ['print(1)', 'input("x")', "collect()", "thread_exit()"]
)
def test_purity_rejects_io_and_gc_builtins(call):
    builtin = call.split("(", 1)[0]
    check_pure_error_message(
        f"puredef f() -> NoneType\n    {call}\n",
        f"may not call non-pure function '{builtin}'",
    )


def test_purity_allows_pure_builtins_in_expressions():
    check_pure_ok(
        """
puredef f(d: Dict[Int64, Int32]) -> Int64
    return len(chr(65)) + dict_key(d, Int64(0))
"""
    )


@pytest.mark.parametrize(
    "decl",
    [
        'x: String = f"value={impure()}"',
        "x: List[Int32] = [impure()]",
        'x: Dict[String, Int32] = {"a": impure()}',
        "x: String = s[impure_index():1]",
        "x: Box = Box(value=impure())",
        "x: Int32 = (impure())",
        "x: Int32 = -impure()",
    ],
)
def test_purity_checks_calls_nested_in_expressions(decl):
    source = f"""
struct Box:
    value: Int32
def impure() -> Int32
    return 1
def impure_index() -> Int64
    return 0
puredef f(s: String) -> Int32
    {decl}
    return 0
"""
    expected = "impure_index" if "impure_index()" in decl else "impure"
    check_pure_error_message(
        source,
        f"may not call non-pure function '{expected}'",
    )


def test_purity_checks_calls_in_conditions():
    check_pure_error_message(
        """
def impure() -> Bool
    return True
puredef f() -> Int32
    if impure():
        return 1
    while impure():
        return 2
    return 0
""",
        "may not call non-pure function 'impure'",
    )
