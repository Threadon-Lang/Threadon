import pytest

from compiler.checker import CombinedChecker
from compiler.parser import Parser
from compiler.to_high_ir import IRPhi, SSABuilder


def build_module(source):
    ast = Parser().parse(source)
    CombinedChecker().run_all(ast)
    return SSABuilder().build_from_ast(ast)


def get_func(module, name):
    return next(f for f in module.funcs if f.name == name)


def block_ops(func, label):
    block = func.block_map[label]
    return [i.op for i in block.instructions]


def entry_instrs(func, op):
    return [i for i in func.block_map["entry"].instructions if i.op == op]


def test_module_has_function_and_types():
    module = build_module(
        """
struct Point:
    x: Int32
    y: Int32
def add(a: Int32, b: Int32) -> Int32
    return a + b
"""
    )
    assert [f.name for f in module.funcs] == ["add"]
    assert module.types["Point"] == {"x": "Int32", "y": "Int32"}
    add = get_func(module, "add")
    assert add.return_type == "Int32"
    assert add.params == [("a", "Int32", None), ("b", "Int32", None)]


def test_parameters_produce_param_instructions():
    module = build_module(
        """
def add(a: Int32, b: Float32) -> Float32
    return b
"""
    )
    add = get_func(module, "add")
    params = entry_instrs(add, "param")
    assert [p.args[0] for p in params] == ["a", "b"]
    assert [p.result.type for p in params] == ["Int32", "Float32"]


def test_constants():
    module = build_module(
        """
def f() -> Int32
    x: Int32 = 42
    return x
"""
    )
    f = get_func(module, "f")
    consts = entry_instrs(f, "const")
    assert len(consts) == 1
    assert consts[0].args == ["42"]
    assert consts[0].result.type == "Int32"


@pytest.mark.parametrize(
    "source_op,ir_op,result_type",
    [
        ("+", "add", "Int32"),
        ("-", "sub", "Int32"),
        ("*", "mul", "Int32"),
        ("/", "div", "Int32"),
        ("//", "floordiv", "Int32"),
        ("%", "mod", "Int32"),
        ("**", "pow", "Int32"),
        ("<", "cmp_lt", "Bool"),
        (">", "cmp_gt", "Bool"),
        ("<=", "cmp_le", "Bool"),
        (">=", "cmp_ge", "Bool"),
        ("==", "cmp_eq", "Bool"),
        ("!=", "cmp_ne", "Bool"),
    ],
)
def test_binary_operator_mapping(source_op, ir_op, result_type):
    module = build_module(
        f"""
def f(a: Int32, b: Int32) -> {result_type}
    c: {result_type} = a {source_op} b
    return c
"""
    )
    f = get_func(module, "f")
    instrs = entry_instrs(f, ir_op)
    assert len(instrs) == 1
    left, right = instrs[0].args
    assert left.name == "%t0"
    assert right.name == "%t1"


def test_unary_neg_and_not():
    module = build_module(
        """
def f(a: Int32) -> Int32
    b: Int32 = -a
    return b
"""
    )
    f = get_func(module, "f")
    negs = entry_instrs(f, "neg")
    assert len(negs) == 1
    assert negs[0].args[0].name == "%t0"

    module = build_module(
        """
def f(a: Bool) -> Bool
    b: Bool = not a
    return b
"""
    )
    f = get_func(module, "f")
    nots = entry_instrs(f, "not")
    assert len(nots) == 1
    assert nots[0].args[0].name == "%t0"


def test_if_else_phi_merge():
    module = build_module(
        """
def f(x: Int32) -> Int32
    if x > 0:
        r: Int32 = 1
    else:
        r: Int32 = 2
    return r
"""
    )
    f = get_func(module, "f")
    labels = [b.label for b in f.blocks]
    assert labels == ["entry", "merge", "ifcond0", "ifbody0", "elsebody"]

    phis = [i for i in f.block_map["merge"].instructions if isinstance(i, IRPhi)]
    assert len(phis) == 1
    incoming_labels = [blk for blk, _ in phis[0].incoming]
    assert incoming_labels == ["ifbody0", "elsebody"]

    entry = f.block_map["entry"]
    assert entry.terminator.op == "br"
    assert entry.terminator.args[0] == "ifcond0"

    ifcond = f.block_map["ifcond0"]
    assert ifcond.terminator.op == "cond_br"
    cond, t1, t2 = ifcond.terminator.args
    assert cond.def_instr.op == "cmp_gt"
    assert t1 == "ifbody0"
    assert t2 == "elsebody"


def test_if_without_else_has_fallthrough():
    module = build_module(
        """
def f(x: Int32) -> Int32
    if x > 0:
        y: Int32 = x + 1
    return x
"""
    )
    f = get_func(module, "f")
    assert "fallthrough" in f.block_map
    fallthrough = f.block_map["fallthrough"]
    assert fallthrough.terminator.op == "br"
    assert fallthrough.terminator.args[0] == "merge"
    merge = f.block_map["merge"]
    phis = [i for i in merge.instructions if isinstance(i, IRPhi)]
    assert len(phis) == 1
    incoming_blocks = [blk for blk, _ in phis[0].incoming]
    assert incoming_blocks == ["ifbody0", "fallthrough"]


def test_elif_chain_produces_ifcond_blocks():
    module = build_module(
        """
def f(x: Int32) -> Int32
    if x > 0:
        r: Int32 = 1
    elif x < 0:
        r: Int32 = 2
    else:
        r: Int32 = 3
    return r
"""
    )
    f = get_func(module, "f")
    assert "ifcond0" in f.block_map
    assert "ifcond1" in f.block_map
    ifcond0 = f.block_map["ifcond0"]
    assert ifcond0.terminator.args[2] == "ifcond1"

    phis = [i for i in f.block_map["merge"].instructions if isinstance(i, IRPhi)]
    assert len(phis) == 1
    incoming_labels = [blk for blk, _ in phis[0].incoming]
    assert incoming_labels == ["ifbody0", "ifbody1", "elsebody"]


def test_struct_init_and_field_access():
    module = build_module(
        """
struct Point:
    x: Int32
    y: Int32
def f() -> Int32
    p: Point = Point(x=1, y=2)
    q: Point = Point(x=p.x, y=p.y)
    return q.x
"""
    )
    f = get_func(module, "f")
    struct_inits = [i for i in f.block_map["entry"].instructions if i.op == "struct_init"]
    assert len(struct_inits) == 2
    assert struct_inits[0].args[0] == "Point"
    fields = struct_inits[0].args[1:]
    assert fields[::2] == ["x", "y"]
    assert struct_inits[0].result.type == "Point"

    field_instrs = [i for i in f.block_map["entry"].instructions if i.op == "field"]
    assert len(field_instrs) == 3
    assert field_instrs[0].args[1] == "x"
    assert field_instrs[0].result.type == "Int32"


def test_call_instruction():
    module = build_module(
        """
def inc(a: Int32) -> Int32
    return a + 1
def f(x: Int32) -> Int32
    y: Int32 = inc(x)
    return y
"""
    )
    f = get_func(module, "f")
    calls = entry_instrs(f, "call")
    assert len(calls) == 1
    call = calls[0]
    assert call.args[0] == "inc"
    assert call.args[1].name == "%t0"
    assert call.result.type == "Int32"


def test_ref_expr_emits_ref_copy():
    module = build_module(
        """
def f(x: Int32) -> Int32
    r: Int32 = x^
    return r
"""
    )
    f = get_func(module, "f")

    allocas = entry_instrs(f, "alloca")
    stores = entry_instrs(f, "store")
    assert len(allocas) == 1
    assert len(stores) == 1


def test_ref_copy_instruction_in_declaration():
    module = build_module(
        """
def f(x: Int32) -> Int32
    r: Int32 = x^
    return r
"""
    )
    f = get_func(module, "f")

    allocas = entry_instrs(f, "alloca")
    assert len(allocas) == 1
    stores = entry_instrs(f, "store")
    assert len(stores) == 1
    assert stores[0].args[0].name == "%t0" 

def test_return_void():
    module = build_module(
        """
def f() -> NoneType
    return
"""
    )
    f = get_func(module, "f")
    assert f.block_map["entry"].terminator.op == "ret_void"


def test_cfg_successors_and_predecessors():
    module = build_module(
        """
def f(x: Int32) -> Int32
    if x > 0:
        r: Int32 = 1
    else:
        r: Int32 = 2
    return r
"""
    )
    f = get_func(module, "f")
    f.build_cfg()
    entry = f.block_map["entry"]
    assert entry.successors == ["ifcond0"]
    assert entry.predecessors == []
    ifcond = f.block_map["ifcond0"]
    assert set(ifcond.successors) == {"ifbody0", "elsebody"}
    assert ifcond.predecessors == ["entry"]
    merge = f.block_map["merge"]
    assert set(merge.predecessors) == {"ifbody0", "elsebody"}
    assert merge.successors == []


def test_dominators_entry_dominates_all():
    module = build_module(
        """
def f(x: Int32) -> Int32
    if x > 0:
        r: Int32 = 1
    else:
        r: Int32 = 2
    return r
"""
    )
    f = get_func(module, "f")
    f.build_cfg()
    dom = f.compute_dominators()
    entry = "entry"
    for block in f.blocks:
        assert entry in dom[block.label]


def test_phi_omitted_when_value_identical_in_all_branches():
    module = build_module(
        """
def f(x: Int32) -> Int32
    if x > 0:
        r: Int32 = x
    else:
        r: Int32 = x
    return r
"""
    )
    f = get_func(module, "f")
    phis = [i for b in f.blocks for i in b.instructions if isinstance(i, IRPhi)]
    assert phis == []


def test_nested_struct_chain():
    module = build_module(
        """
struct Z:
    z: Int32
struct Point:
    x: Int32
    y: Z
def f() -> Int32
    p: Point = Point(x=1, y=Z(z=2))
    return p.y.z + p.x
"""
    )
    f = get_func(module, "f")
    inits = [i for i in f.block_map["entry"].instructions if i.op == "struct_init"]
    assert len(inits) == 2
    assert inits[0].args[0] == "Z"
    assert inits[1].args[0] == "Point"
    assert inits[1].args[4] == inits[0].result

    fields = [i for i in f.block_map["entry"].instructions if i.op == "field"]
    assert len(fields) == 3
    outer, inner, xfield = fields
    assert outer.args[1] == "y"
    assert outer.result.type == "Z"
    assert inner.args[0] == outer.result
    assert inner.args[1] == "z"
    assert xfield.args[1] == "x"


def test_condition_value_reused_across_elif():
    module = build_module(
        """
def f(x: Int32) -> Int32
    if x > 0:
        r: Int32 = 1
    elif x > 0:
        r: Int32 = 2
    else:
        r: Int32 = 3
    return r
"""
    )
    f = get_func(module, "f")
    cmp_ops = [i.op for b in f.blocks for i in b.instructions]
    assert cmp_ops.count("cmp_gt") == 2


def test_param_value_is_returned_directly():
    module = build_module(
        """
def f(x: Int32) -> Int32
    return x
"""
    )
    f = get_func(module, "f")
    params = entry_instrs(f, "param")
    assert len(params) == 1
    assert f.block_map["entry"].terminator.args[0] == params[0].result


def test_bool_true_and_false_constants():
    module = build_module(
        """
def f() -> Bool
    return True
def g() -> Bool
    return False
"""
    )
    f = get_func(module, "f")
    g = get_func(module, "g")
    f_consts = entry_instrs(f, "const")
    g_consts = entry_instrs(g, "const")
    assert f_consts[0].args == ["True"]
    assert g_consts[0].args == ["False"]
    assert f_consts[0].result.type == "Bool"


def test_negative_number_literal():
    module = build_module(
        """
def f() -> Int32
    a: Int32 = -3
    return a
"""
    )
    f = get_func(module, "f")
    ops = [i.op for i in f.block_map["entry"].instructions]
    assert ops == ["const", "neg"]
    neg = next(i for i in f.block_map["entry"].instructions if i.op == "neg")
    assert neg.args[0].def_instr.op == "const"


def test_float_constant_emitted():
    module = build_module(
        """
def f() -> Float32
    a: Float32 = 2.5
    return a
"""
    )
    f = get_func(module, "f")
    consts = entry_instrs(f, "const")
    assert consts[0].args == ["2.5"]
    assert consts[0].result.type == "Float32"


def test_call_with_multiple_arguments():
    module = build_module(
        """
def add3(a: Int32, b: Int32, c: Int32) -> Int32
    return a + b + c
def run() -> Int32
    return add3(1, 2, 3)
"""
    )
    run = get_func(module, "run")
    calls = entry_instrs(run, "call")
    assert len(calls) == 1
    call = calls[0]
    assert call.args[0] == "add3"
    assert [a.name for a in call.args[1:]] == ["%t0", "%t1", "%t2"]


def test_call_result_used_in_arithmetic():
    module = build_module(
        """
def g(x: Int32) -> Int32
    return x
def h(x: Int32) -> Int32
    return g(x) + 1
"""
    )
    h = get_func(module, "h")
    ops = [i.op for i in h.block_map["entry"].instructions]
    assert ops == ["param", "call", "const", "add"]
    add = next(i for i in h.block_map["entry"].instructions if i.op == "add")
    assert add.args[0].def_instr.op == "call"


def test_module_function_order_preserved():
    module = build_module(
        """
def first() -> Int32
    return 1
def second() -> Int32
    return 2
def third() -> Int32
    return 3
"""
    )
    assert [f.name for f in module.funcs] == ["first", "second", "third"]


def test_parameter_types():
    module = build_module(
        """
def f(x: Int32, y: Float32, b: Bool) -> Float32
    return y
"""
    )
    f = get_func(module, "f")
    params = entry_instrs(f, "param")
    assert [(p.args[0], p.result.type) for p in params] == [
        ("x", "Int32"),
        ("y", "Float32"),
        ("b", "Bool"),
    ]


def test_elif_else_chain_structure():
    module = build_module(
        """
def f(x: Int32) -> Int32
    if x > 0:
        r: Int32 = 1
    elif x < 0:
        r: Int32 = 2
    else:
        r: Int32 = 3
    return r
"""
    )
    f = get_func(module, "f")
    assert [b.label for b in f.blocks] == [
        "entry",
        "merge",
        "ifcond0",
        "ifbody0",
        "ifcond1",
        "ifbody1",
        "elsebody",
    ]
    ifcond0 = f.block_map["ifcond0"]
    assert ifcond0.terminator.op == "cond_br"
    assert ifcond0.terminator.args[2] == "ifcond1"
    merge = f.block_map["merge"]
    phis = [i for i in merge.instructions if isinstance(i, IRPhi)]
    assert len(phis) == 1
    assert [blk for blk, _ in phis[0].incoming] == ["ifbody0", "ifbody1", "elsebody"]


def test_return_of_comparison():
    module = build_module(
        """
def f(x: Int32) -> Bool
    return x > 0
"""
    )
    f = get_func(module, "f")
    entry = f.block_map["entry"]
    term = entry.terminator
    assert term.op == "ret"
    assert term.args[0].def_instr.op == "cmp_gt"



def test_dominators_for_if_blocks():
    module = build_module(
        """
def max2(a: Int32, b: Int32) -> Int32
    if a > b:
        r: Int32 = a
    else:
        r: Int32 = b
    return r
"""
    )
    f = get_func(module, "max2")
    f.build_cfg()
    dom = f.compute_dominators()
    assert dom["ifbody0"] == {"entry", "ifcond0", "ifbody0"}
    assert dom["elsebody"] == {"entry", "ifcond0", "elsebody"}
    assert dom["merge"] == {"entry", "ifcond0", "merge"}


def test_liveness_keys_are_block_labels():
    module = build_module(
        """
def max2(a: Int32, b: Int32) -> Int32
    if a > b:
        r: Int32 = a
    else:
        r: Int32 = b
    return r
"""
    )
    f = get_func(module, "max2")
    f.build_cfg()
    live_in, live_out = f.compute_liveness()
    labels = {b.label for b in f.blocks}
    assert set(live_in.keys()) == labels
    assert set(live_out.keys()) == labels
    merge = f.block_map["merge"]
    phis = [i for i in merge.instructions if isinstance(i, IRPhi)]
    assert len(phis) == 1
    phi_result = phis[0].result
    assert phi_result.name in live_in["merge"]


def test_string_constant_emitted():
    module = build_module(
        """
def f() -> String
    s: String = "hi"
    return s
"""
    )
    f = get_func(module, "f")
    consts = entry_instrs(f, "const")
    assert len(consts) == 1
    assert consts[0].args[0] == "hi"


def test_uninitialized_declaration_emits_undef():
    module = build_module(
        """
def f() -> Int32
    x: Int32
    return x
"""
    )
    f = get_func(module, "f")
    ops = block_ops(f, "entry")
    assert ops == ["undef"]
    ret_val = f.block_map["entry"].terminator.args[0]
    assert ret_val.def_instr.op == "undef"


def test_phi_incoming_values_match_branch_definitions():
    module = build_module(
        """
def f(x: Int32) -> Int32
    if x > 0:
        r: Int32 = 1
    else:
        r: Int32 = 2
    return r
"""
    )
    f = get_func(module, "f")
    merge = f.block_map["merge"]
    phis = [i for i in merge.instructions if isinstance(i, IRPhi)]
    assert len(phis) == 1
    incoming = [(blk, value.name) for blk, value in phis[0].incoming]
    assert incoming == [("ifbody0", "%t3"), ("elsebody", "%t4")]


def test_temp_counter_resets_per_function():
    module = build_module(
        """
def f() -> Int32
    return 1
def g() -> Int32
    return 2
"""
    )
    f = get_func(module, "f")
    g = get_func(module, "g")
    f_consts = entry_instrs(f, "const")
    g_consts = entry_instrs(g, "const")
    assert f_consts[0].result.name == "%t0"
    assert g_consts[0].result.name == "%t0"


def test_multiple_phis_for_multi_statement_branches():
    module = build_module(
        """
def f(x: Int32) -> Int32
    if x > 0:
        a: Int32 = x + 1
        b: Int32 = x + 2
        r: Int32 = a + b
    else:
        a: Int32 = x
        b: Int32 = x
        r: Int32 = a + b
    return r
"""
    )
    f = get_func(module, "f")
    merge = f.block_map["merge"]
    phis = [i for i in merge.instructions if isinstance(i, IRPhi)]
    assert len(phis) == 3
    ifbody = f.block_map["ifbody0"]
    assert [i.op for i in ifbody.instructions] == ["const", "add", "const", "add", "add"]


def test_augmented_assign_emits_binary_expression():
    module = build_module(
        """
def run() -> Int32
    x: Int32 = 5
    x += 3
    return x
"""
    )
    f = get_func(module, "run")
    ops = block_ops(f, "entry")
    assert ops == ["const", "const", "add"]
    instrs = f.block_map["entry"].instructions
    add = instrs[-1]
    assert add.op == "add"
    assert add.args[0].name == "%t0"
    assert add.args[1].name == "%t1"
    assert f.block_map["entry"].terminator.args[0].name == "%t2"


def test_unary_pos_emission():
    module = build_module(
        """
def f(a: Int32) -> Int32
    b: Int32 = +a
    return b
"""
    )
    f = get_func(module, "f")
    poss = entry_instrs(f, "pos")
    assert len(poss) == 1
    assert poss[0].args[0].name == "%t0"


def test_call_with_no_arguments():
    module = build_module(
        """
def f() -> Int32
    return 5
def g() -> Int32
    return f()
"""
    )
    f = get_func(module, "g")
    calls = entry_instrs(f, "call")
    assert len(calls) == 1
    call = calls[0]
    assert call.args == ["f"]


def test_default_params_recorded_on_function():
    module = build_module(
        """
def f(a: Int32, b: Int32 = 5) -> Int32
    return a + b
"""
    )
    f = get_func(module, "f")
    assert f.params[0] == ("a", "Int32", None)
    assert f.params[1][0:2] == ("b", "Int32")

    default = f.params[1][2]
    assert default.type == "Int32"
    assert default.value.value == "5"


def test_call_with_defaults_fills_arguments():
    module = build_module(
        """
def add(a: Int32, b: Int32 = 5, c: Int32 = 10) -> Int32
    return a + b + c
def run() -> Int32
    return add(1)
"""
    )
    run = get_func(module, "run")
    calls = entry_instrs(run, "call")
    assert len(calls) == 1
    call = calls[0]
    assert call.args[0] == "add"
    args = call.args[1:]
    assert len(args) == 3
    assert [a.def_instr.args[0] for a in args] == ["1", "5", "10"]
    assert [a.type for a in args] == ["Int32", "Int32", "Int32"]


def test_call_with_partial_defaults_fills_remaining():
    module = build_module(
        """
def add(a: Int32, b: Int32 = 5, c: Int32 = 10) -> Int32
    return a + b + c
def run() -> Int32
    return add(1, 2)
"""
    )
    run = get_func(module, "run")
    calls = entry_instrs(run, "call")
    call = calls[0]
    args = call.args[1:]
    assert len(args) == 3
    assert [a.def_instr.args[0] for a in args] == ["1", "2", "10"]


def test_call_with_all_arguments_no_defaults_filled():
    module = build_module(
        """
def add(a: Int32, b: Int32 = 5, c: Int32 = 10) -> Int32
    return a + b + c
def run() -> Int32
    return add(1, 2, 3)
"""
    )
    run = get_func(module, "run")
    calls = entry_instrs(run, "call")
    call = calls[0]
    args = call.args[1:]
    assert len(args) == 3
    assert [a.def_instr.args[0] for a in args] == ["1", "2", "3"]


def test_class_type_fields_flattened():
    module = build_module(
        """
class Car:
    def __init__(self: Car, brand: String):
        self.brand: String = brand
class DMW(Car):
    def __init__(self DMW):
        self.brand = "DMW"
def main() -> Int32
    return 0
"""
    )
    assert module.types["Car"] == {"brand": "String"}
    assert module.types["DMW"] == {"brand": "String"}
    names = [f.name for f in module.funcs]
    assert "Car.__init__" in names
    assert "DMW.__init__" in names


def test_class_method_call_dispatch():
    module = build_module(
        """
class Car:
    def __init__(self: Car, brand: String):
        self.brand: String = brand
    def get_brand(self: Car):
        return self.brand
class DMW(Car):
    def __init__(self DMW):
        self.brand = "DMW"
def main() -> Int32
    c: Car = Car("BMW")
    d: DMW = DMW()
    b: String = d.get_brand()
    print(c,d,b)
    return 0
"""
    )
    main = get_func(module, "main")
    calls = entry_instrs(main, "call")
    assert [c.args[0] for c in calls] == ["Car.__init__", "DMW.__init__", "Car.get_brand","print"]
    fields = entry_instrs(main, "field")
    assert fields[0].args[1] == "brand"
    struct_inits = entry_instrs(main, "struct_init")
    assert len(struct_inits) == 1
    assert struct_inits[0].args[0] == "Car"
