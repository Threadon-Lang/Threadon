"""Coverage for SSABuilder lowering paths that ordinary functions do not reach.

The tests in this file lower real Threadon source (or real AST nodes produced
by the parser) and assert on the resulting high-level IR: emitted operations,
SSA result types, CFG edges, phi incoming values and thread structure.
"""
import pytest

from compiler.threadon.checker import CombinedChecker
from compiler.threadon.lexer import Token, TokenType
from compiler.threadon.nodes import (
    Assign,
    BinaryExpr,
    CallExpr,
    ComptimeStmt,
    ExprStmt,
    FieldAccessExpr,
    ListLiteralExpr,
    DictLiteralExpr,
    IndexExpr,
    LiteralExpr,
    RefExpr,
    ReturnStmt,
    SliceExpr,
    ThreadNode,
    VarDecl,
    VarExpr,
)
from compiler.threadon.parser import Parser
from compiler.threadon.to_high_ir import (
    IRBlock,
    IRFunction,
    IRInstr,
    IRPhi,
    SSAValue,
    SSABuilder,
)


def build_module(source):
    ast = Parser().parse(source)
    CombinedChecker().run_all(ast)
    return SSABuilder().build_from_ast(ast)


def get_func(module, name):
    return next(f for f in module.funcs if f.name == name)


def ops(block):
    return [i.op for i in block.instructions]


def num(value, type_="Int32"):
    return LiteralExpr(Token(TokenType.NUMBER, value), type_)


def fresh_builder():
    """A builder with an entry block and one environment frame."""
    builder = SSABuilder()
    func = IRFunction("f", [], "Int32")
    builder.module.add_func(func)
    builder.current_func = func
    block = IRBlock("entry")
    func.add_block(block)
    builder.current_block = block
    builder.push_env()
    return builder, func, block


# ---------------------------------------------------------------------------
# Module variables
# ---------------------------------------------------------------------------


def test_module_variable_literal_kinds_and_global_assignments():
    module = build_module(
        """
flag: Bool = True
off: Bool = False
name: String = "hello"
raw: UInt8
none_val: NoneType = None
computed: Int32 = 1 + 2
counter: Int32 = 0
other: Int32 = 1
big: Int256 = 0
msg: String = "x"

def f(x: Int32) -> Int32
    counter = other + 1
    counter += 1
    big += 1
    msg += "y"
    y: Int32 = counter
    return y
"""
    )
    assert module.module_vars == [
        ("flag", "Bool", True),
        ("off", "Bool", False),
        ("name", "String", "hello"),
        ("raw", "UInt8", None),
        ("none_val", "NoneType", "None"),
        ("computed", "Int32", None),
        ("counter", "Int32", 0),
        ("other", "Int32", 1),
        ("big", "Int256", 0),
        ("msg", "String", "x"),
    ]

    f = get_func(module, "f")
    entry = f.block_map["entry"]
    assert ops(entry) == [
        "param",  # x
        "global_load",  # other
        "const",
        "add",
        "global_store",  # counter = other + 1  (not an RMW)
        "const",
        "global_rmw",  # counter += 1
        "global_load",  # big
        "const",
        "add",
        "global_store",  # big is too wide for atomicrmw
        "global_load",  # msg
        "const",
        "str_concat",
        "global_store",  # strings are not atomic integer RMWs
        "global_load",
    ]
    assert [i.args[0] for i in entry.instructions if i.op == "global_rmw"] == ["counter"]
    assert entry.terminator.args[0].def_instr.op == "global_load"


def test_comptime_statements_are_registered_as_module_variables():
    module = build_module(
        """
comptime base: Int32 = 2 + 3
comptime text: String = "ab" + "cd"
none_val: NoneType = None
computed: Int32 = 1 + 2

def f() -> Int32
    return base
"""
    )
    assert module.module_vars[:2] == [("base", "Int32", 5), ("text", "String", "abcd")]
    assert module.module_vars[2] == ("none_val", "NoneType", "None")
    assert module.module_vars[3] == ("computed", "Int32", None)

    f = get_func(module, "f")
    load = f.block_map["entry"].instructions[0]
    assert load.op == "global_load"
    assert load.args == ["base"]
    assert load.result.type == "Int32"
    assert f.block_map["entry"].terminator.args[0] is load.result


def test_comptime_evaluation_failure_aborts_with_diagnostic(capsys):
    builder = SSABuilder()
    bad = ComptimeStmt("x", "Int32", [], CallExpr("nope", []))

    with pytest.raises(SystemExit) as excinfo:
        builder._eval_comptime(bad)

    assert excinfo.value.code == 1
    assert "Error evaluating comptime 'x'" in capsys.readouterr().out
    assert builder.module.module_vars == []


def test_unknown_module_variable_type_defaults_to_int32():
    assert SSABuilder()._type_of_module_var("never_declared") == "Int32"


def test_global_rmw_casts_rhs_to_global_width():
    builder, func, block = fresh_builder()
    builder.module_var_names = {"counter"}
    builder.module.module_vars.append(("counter", "Int32", 0))

    builder.emit_assign(
        Assign("counter", BinaryExpr(VarExpr("counter"), "+", CallExpr("len", [])))
    )

    assert ops(block) == ["call", "cast", "global_rmw"]
    cast = block.instructions[1]
    assert cast.args[1] == "Int32"
    assert cast.result.type == "Int32"
    rmw = block.instructions[2]
    assert rmw.args[:2] == ["counter", "add"]
    assert rmw.args[2] is cast.result


# ---------------------------------------------------------------------------
# References / allocas
# ---------------------------------------------------------------------------


def test_reference_declarations_promote_uninitialized_and_parameter_variables():
    module = build_module(
        """
def f(x: Int32) -> Int32
    r: Int32
    y: Int32 = r^
    z: Int32 = x^
    return y + z
"""
    )
    f = get_func(module, "f")
    entry = f.block_map["entry"]
    assert ops(entry) == [
        "param",  # x
        "alloca",
        "store",  # x is a ref var, promoted on entry
        "undef",  # r
        "alloca",
        "store",  # r is promoted at its declaration
        "load",
        "load",
        "add",
    ]
    assert entry.instructions[2].args[0] is entry.instructions[0].result
    assert entry.instructions[5].args[0] is entry.instructions[3].result
    assert entry.terminator.args[0].def_instr.op == "add"


def test_ref_declaration_promotes_unpromoted_source_variable():
    builder, func, block = fresh_builder()
    source = builder.new_temp("Int32")
    builder.env_stack[-1]["src"] = source

    builder.emit_var_decl(VarDecl("r", "Int32", RefExpr(VarExpr("src"))))

    assert ops(block) == ["alloca", "store"]
    assert block.instructions[1].args[0] is source
    assert builder.ptr_vars["r"] is builder.ptr_vars["src"]


def test_ref_declaration_of_non_variable_inner_emits_ref_copy():
    builder, func, block = fresh_builder()
    point = builder.new_temp("Point")
    builder.module.types["Point"] = {"x": "Int32"}
    builder.env_stack[-1]["p"] = point

    builder.emit_var_decl(
        VarDecl("r", "Int32", RefExpr(FieldAccessExpr(VarExpr("p"), "x")))
    )

    assert ops(block) == ["field", "ref_copy"]
    assert block.instructions[0].args[1] == "x"
    assert block.instructions[1].args[0] is block.instructions[0].result
    assert builder.env_stack[-1]["r"] is block.instructions[1].result


def test_ref_expression_in_expression_position_is_lowered():
    builder, func, block = fresh_builder()
    value = builder.new_temp("Int32")
    builder.env_stack[-1]["n"] = value

    result = builder.emit_expr(RefExpr(VarExpr("n")))

    assert ops(block) == ["ref_copy"]
    assert block.instructions[0].args == [value]
    assert result is block.instructions[0].result
    assert result.type == "Int32"


def test_promote_to_alloca_is_idempotent():
    builder, func, block = fresh_builder()
    value = builder.new_temp("Int32")

    first = builder._promote_to_alloca("x", "Int32", value)
    second = builder._promote_to_alloca("x", "Int32", value)

    assert first is second
    assert ops(block) == ["alloca", "store"]


def test_set_var_wraps_concrete_value_for_union_pointer():
    builder, func, block = fresh_builder()
    builder.ptr_vars["u"] = SSAValue("%p", "Union[Int32|Int64]*")
    value = builder.new_temp("Int32")

    builder.set_var("u", value)

    assert ops(block) == ["union_init", "store"]
    assert block.instructions[0].args[1] == "Int32"
    assert block.instructions[1].args[0] is block.instructions[0].result
    assert block.instructions[1].args[1] is builder.ptr_vars["u"]


# ---------------------------------------------------------------------------
# Union handling
# ---------------------------------------------------------------------------


def test_if_merge_retags_subset_union_and_initializes_concrete_values():
    source = """
def f(c: Bool, x: Int64) -> Int32
    if c:
        x = 1
    return 0
"""
    node = Parser().parse(source)[0].body[0]

    builder, func, _block = fresh_builder()
    narrow = builder.new_temp("Union[Int32|Int64]")
    condition = builder.new_temp("Bool")
    builder.env_stack[-1]["x"] = narrow
    builder.env_stack[-1]["c"] = condition
    declared = "Union[Float32|Int32|Int64]"
    builder.var_types["x"] = declared

    builder.emit_if(node)

    merge = func.block_map["merge"]
    phi = next(i for i in merge.instructions if isinstance(i, IRPhi))
    assert phi.result.type == declared
    assert [label for label, _ in phi.incoming] == ["ifbody0", "fallthrough"]
    assert phi.incoming[0][1].def_instr.op == "union_init"
    assert phi.incoming[1][1].def_instr.op == "union_retag"
    assert ops(func.block_map["fallthrough"]) == ["union_retag"]


def test_wrap_union_in_block_without_union_target_is_identity():
    builder, func, block = fresh_builder()
    value = builder.new_temp("Bool")

    assert builder._wrap_union_in_block(block, value, "Int32") is value
    assert builder._wrap_union_in_block(
        block, value, "Union[Int32|Int64]"
    ) is value
    assert ops(block) == []


def test_union_variable_declaration_retags_subset_union():
    builder, func, block = fresh_builder()
    narrow = builder.new_temp("Union[Int32|Int64]")
    builder.env_stack[-1]["n"] = narrow

    builder.emit_var_decl(
        VarDecl("y", "Union[Float32|Int32|Int64]", VarExpr("n"))
    )

    assert ops(block) == ["union_retag"]
    assert block.instructions[0].args[1] is narrow
    assert builder.env_stack[-1]["y"] is block.instructions[0].result


def test_while_break_wraps_union_values_on_latch_and_merge_edges():
    module = build_module(
        """
def f(n: Int32) -> Int32
    x: Int32 | Float = 1
    while n > 0:
        x = 2.5
        if n == 2:
            break
        n = n - 1
    return 0
"""
    )
    f = get_func(module, "f")
    cond = f.block_map["whilecond"]
    x_phi = next(
        i for i in cond.instructions
        if isinstance(i, IRPhi) and i.result.type.startswith("Union[")
    )
    back = next(value for label, value in x_phi.incoming if label == "whilelatch")
    assert back.def_instr.op == "union_init"
    concrete = back.def_instr.args[2]
    assert concrete.def_instr.op == "const"
    assert x_phi in concrete.users
    assert f.block_map["ifbody1_0"].instructions[-1].op == "union_init"

    merge = f.block_map["whilemerge"]
    merge_phi = next(
        i for i in merge.instructions
        if isinstance(i, IRPhi) and i.result.type.startswith("Union[")
    )
    break_value = next(
        value for label, value in merge_phi.incoming if label == "ifbody1_0"
    )
    assert break_value.def_instr.op == "union_init"
    assert merge_phi in break_value.users


def test_while_continue_wraps_union_value_before_back_edge():
    module = build_module(
        """
def f(n: Int32) -> Int32
    x: Int32 | Float = 1
    while n > 0:
        x = 2.5
        if n % 2 == 0:
            continue
        n = n - 1
    return 0
"""
    )
    f = get_func(module, "f")
    latch = f.block_map["whilelatch"]
    latch_phis = [i for i in latch.instructions if isinstance(i, IRPhi)]
    assert len(latch_phis) == 2  # one per loop variable, two back edges
    assert all(len(phi.incoming) == 2 for phi in latch_phis)

    fallthrough_block = f.block_map["merge1_"]
    wrapped = next(i for i in fallthrough_block.instructions if i.op == "union_init")
    assert wrapped.result.type.startswith("Union[")
    assert any(
        value is wrapped.result
        for phi in latch_phis
        for _, value in phi.incoming
    )


# ---------------------------------------------------------------------------
# CFG edge cases
# ---------------------------------------------------------------------------


def test_for_loop_break_leaves_latch_without_back_edge():
    module = build_module(
        """
def f() -> Int32
    for i in range(3):
        break
    return 0
"""
    )
    f = get_func(module, "f")
    latch = f.block_map["whilelatch"]
    assert latch.instructions == []
    assert latch.terminator is None

    f.build_cfg()
    assert latch.predecessors == []
    assert latch.successors == []
    dom = f.compute_dominators()
    assert "whilelatch" in dom["whilelatch"]
    f.build_cfg()
    assert "preds: []" in str(f)


def test_if_with_only_returning_branches_has_empty_merge_values():
    module = build_module(
        """
def f(x: Int32) -> Int32
    if x > 0:
        return 1
    else:
        return 2
"""
    )
    f = get_func(module, "f")
    merge = f.block_map["merge"]
    assert merge.instructions == []
    assert f.block_map["ifbody0"].terminator.op == "ret"
    assert f.block_map["elsebody"].terminator.op == "ret"


def test_thread_lowering_skips_terminated_parent_block():
    builder, func, block = fresh_builder()
    block.set_terminator(IRInstr("ret_void", []))
    thread = ThreadNode("t", VarExpr("flag"), [])

    builder.emit_thread(thread)

    assert [f.name for f in builder.module.funcs] == ["f"]
    assert builder.current_block is block
    assert ops(block) == []


def test_thread_inside_function_captures_local_variables():
    source = """
def worker(x: Int32) -> NoneType
    print(x)

def run(flag: Bool) -> NoneType
    x: Int32 = 7
    print(x)
"""
    ast = Parser().parse(source)
    run = get_func_ast(ast, "run")
    run.body.insert(
        1,
        ThreadNode(
            "w",
            VarExpr("flag"),
            [ExprStmt(CallExpr("worker", [VarExpr("x")]))],
        ),
    )

    module = SSABuilder().build_from_ast(ast)

    thread_func = get_func(module, "__thread_0_w")
    assert thread_func.params == [("x", "Int32", None)]
    assert ops(thread_func.block_map["entry"]) == ["param", "call"]
    assert thread_func.block_map["entry"].terminator.op == "ret_void"

    parent = get_func(module, "run")
    assert parent.block_map["entry"].terminator.op == "cond_br"
    spawn = parent.block_map["thread0_spawn"]
    assert spawn.instructions[0].op == "thread_spawn"
    assert spawn.instructions[0].args[:3] == ["0", "w", "__thread_0_w"]
    assert spawn.instructions[0].args[3].def_instr.op == "const"
    assert spawn.terminator.op == "br"
    assert spawn.terminator.args == ["thread0_after"]


def get_func_ast(ast, name):
    return next(node for node in ast if getattr(node, "name", None) == name)


def test_emit_stmt_skips_terminated_block_and_comptime_statements():
    builder, func, block = fresh_builder()
    block.set_terminator(IRInstr("ret_void", []))
    builder.emit_stmt(VarDecl("x", "Int32", num("1")))
    assert ops(block) == []

    builder, func, block = fresh_builder()
    builder.emit_stmt(ComptimeStmt("c", "Int32", [], num("1")))
    assert ops(block) == []
    assert block.terminator is None


def test_break_and_continue_outside_loops_report_ssa_errors():
    builder, func, block = fresh_builder()
    with pytest.raises(Exception, match="'break' outside of a loop"):
        builder.emit_break()
    with pytest.raises(Exception, match="'continue' outside of a loop"):
        builder.emit_continue()
    assert block.terminator is None


def test_return_statement_without_value_node_emits_ret_void():
    builder, func, block = fresh_builder()
    builder.emit_return(ReturnStmt("NoneType", None))
    assert block.terminator.op == "ret_void"
    assert block.terminator.args == []


def test_assign_into_unrecognized_target_returns_value_unchanged():
    builder, func, block = fresh_builder()
    value = builder.new_temp("Int32")
    assert builder.assign_into(num("1"), value) is value
    assert ops(block) == []


# ---------------------------------------------------------------------------
# Expression and helper edge shapes
# ---------------------------------------------------------------------------


def test_list_and_dict_literals_without_annotations_infer_types_from_elements():
    builder, func, block = fresh_builder()

    list_with_elements = ListLiteralExpr([num("1")])
    list_with_elements.type = None
    empty_list = ListLiteralExpr([])
    empty_list.type = None
    odd_dict = DictLiteralExpr([], [])
    odd_dict.type = "Dict[Int32]"
    inferred_dict = DictLiteralExpr([num("1")], [num("2")])
    inferred_dict.type = None
    empty_dict = DictLiteralExpr([], [])
    empty_dict.type = None

    results = [builder.emit_expr(e) for e in (
        list_with_elements, empty_list, odd_dict, inferred_dict, empty_dict
    )]

    assert [r.type for r in results] == [
        "List[Int32]", "List[Unknown]", "Dict[Unknown,Unknown]",
        "Dict[Int32,Int32]", "Dict[Unknown,Unknown]",
    ]
    assert [i.op for i in block.instructions].count("list_init") == 2
    assert [i.op for i in block.instructions].count("dict_init") == 3
    assert block.instructions[6].args[:2] == ["Int32", "Int32"]


def test_nested_dict_types_are_parsed_in_key_lookup_literal_and_index():
    module = build_module(
        """
def key() -> Int32
    d: Dict[List[Int32],Int32] = {}
    k: List[Int32] = dict_key(d, Int64(0))
    print(k)
    return 0

def index() -> Int32
    d: Dict[List[Int32],Int32] = {}
    v: Int32 = d[[1]]
    return v
"""
    )
    key = get_func(module, "key")
    call = next(i for i in key.block_map["entry"].instructions if i.op == "call")
    assert call.args[0] == "dict_key"
    assert call.result.type == "List[Int32]"

    index = get_func(module, "index")
    entry = index.block_map["entry"]
    assert entry.instructions[0].op == "dict_init"
    assert entry.instructions[0].args[:2] == ["List[Int32]", "Int32"]
    assert entry.instructions[-1].op == "dict_get"
    assert entry.instructions[-1].result.type == "Int32"


def test_dict_and_unknown_indexing_and_slicing_shapes():
    builder, func, block = fresh_builder()
    odd_dict = builder.new_temp("Dict[Int32]")
    unknown = builder.new_temp("Point")
    union_a = builder.new_temp("Union[Int32|Int32]")
    union_b = builder.new_temp("Union[Int32|Int32]")
    builder.env_stack[-1]["d"] = odd_dict
    builder.env_stack[-1]["p"] = unknown
    builder.env_stack[-1]["a"] = union_a
    builder.env_stack[-1]["b"] = union_b

    dict_get = builder.emit_expr(IndexExpr(VarExpr("d"), num("0")))
    list_get = builder.emit_expr(IndexExpr(VarExpr("p"), num("0")))
    list_slice = builder.emit_expr(SliceExpr(VarExpr("p"), num("0"), num("1")))
    call = builder.emit_expr(
        CallExpr("dict_key", [VarExpr("d"), num("0", "Int64")])
    )
    add = builder.emit_expr(BinaryExpr(VarExpr("a"), "+", VarExpr("b")))
    ref = builder.emit_expr(RefExpr(VarExpr("a")))

    assert dict_get.def_instr.op == "dict_get"
    assert dict_get.type == "Unknown"
    assert list_get.def_instr.op == "list_get"
    assert list_get.type == "Unknown"
    assert list_slice.def_instr.op == "list_slice"
    assert list_slice.type == "Unknown"
    assert call.def_instr.op == "call"
    assert call.type == "Int32"
    assert add.def_instr.op == "add"
    assert add.type == "Int32"
    assert ref.def_instr.op == "ref_copy"
    assert ref.type == "Union[Int32|Int32]"


def test_missing_call_arguments_raise_in_both_lowering_paths():
    builder, func, block = fresh_builder()
    builder.func_params["g"] = [("a", "Int32", None)]

    with pytest.raises(Exception, match="Missing argument for call to 'g'"):
        builder._fill_default_args("g", [], False)
    with pytest.raises(Exception, match="Missing argument for call to 'g'"):
        builder.emit_expr(CallExpr("g", []))


def test_unknown_expression_type_raises():
    builder, func, block = fresh_builder()
    with pytest.raises(Exception, match="Unknown expr type: object"):
        builder.emit_expr(object())


def test_environment_alias_and_lookup_error_contracts():
    with pytest.raises(Exception, match="Environment stack underflow"):
        SSABuilder().pop_env()

    builder = SSABuilder()
    builder.aliases = {"a": "b", "b": "c"}
    assert builder._resolve_alias("a") == "c"
    builder.aliases["c"] = "a"
    assert builder._resolve_alias("a") == "a"

    builder, func, block = fresh_builder()
    with pytest.raises(Exception, match="Unknown variable missing"):
        builder.get_var("missing")

    with pytest.raises(Exception, match="No environment available"):
        SSABuilder().set_var("x", SSAValue("%v", "Int32"))


def test_template_render_function_reused_for_identical_capture_shapes():
    module = build_module(
        """
def f(x: Int32, y: Int32) -> String
    a: String = t"n={x}"
    b: String = t"n={y}"
    return a + b
"""
    )
    f = get_func(module, "f")
    templates = [i for i in f.block_map["entry"].instructions if i.op == "template_new"]
    assert len(templates) == 2
    assert templates[0].args[0] == templates[1].args[0]
    assert templates[0].args[0].startswith("__threadon_render_")
    assert [f.name for f in module.funcs].count(templates[0].args[0]) == 1


def test_attribute_declaration_without_initializer_emits_no_store():
    module = build_module(
        """
class Box:
    def __init__(self: Box):
        self.x: Int32
        self.x = 5
    def get(self: Box) -> Int32:
        return self.x

def f() -> Int32
    b: Box = Box()
    return b.get()
"""
    )
    init = get_func(module, "Box.__init__")
    assert "store_field" in ops(init.block_map["entry"])
    assert len([i for i in init.block_map["entry"].instructions if i.op == "store_field"]) == 1
