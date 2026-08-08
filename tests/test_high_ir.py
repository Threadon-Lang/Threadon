import pytest

from compiler.checker import CombinedChecker
from compiler.parser import Parser
from compiler.to_high_ir import IRPhi, IRInstr, SSABuilder


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
    assert add.params == [("a", "Int32"), ("b", "Int32")]


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
    copies = entry_instrs(f, "ref_copy")
    assert len(copies) == 1
    assert copies[0].args[0].name == "%t0"
    assert copies[0].result.type == "Int32"


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
