## Objective
- Threadon 3.0 compiler. Class support (parsing, checks, IR, tests) is complete; `print` works for structs and classes (fields, or `__str__` when defined). Latest addition: `__str__` is now INHERITED — a subclass without its own `__str__` uses the parent's. All 573 tests pass. The user's `test.th` compiles and runs; `print(du)` for `du: DMW(Car)` now yields `Car(brand=DMW)` via the inherited `__str__`.

## Important Details
- Value semantics (user-confirmed): `self` passed by value; `c.bump()` mutates only a local copy.
- `pass` is NOT a keyword — use empty bodies or self-field statements in tests.
- Pre-existing rule: functions must return on all paths; NoneType functions/methods need `return None`; `__init__` exempt via implicit `return self`.
- Print format decided: struct/class (no `__str__`) → `{field: value, ...}`, empty → `{}`, nested structs recurse, lists use existing `__threadon_list_str_{tag}` helper. Class WITH `__str__` → `print` calls `@{Class}.__str__` and prints its String result. `__str__` lookup walks the inheritance chain via `module.class_bases`; when the owner differs from the value type, the value is upcast field-by-field (`_upcast_struct`) to the owner's struct type before the call.
- Class method func naming: `func_name = f"{self.current_class}.{method_name}"` (parser.py:1021), so `_class_str_function` checks `f"{tname}.__str__"` against `self.func_name_set`.
- `__str__` validation happens AFTER return-type inference (parser.py:1167), so inferred `String` returns work; explicit `-> Int32` or extra params are parse errors.
- LLVM quirk (CRITICAL, fixed): short static strings get merged into `.rodata.str1.1` (alignment 1) by the backend, ignoring the IR `align 8`, so they land at ODD addresses. The template tagged-pointer scheme (`__threadon_tmpl_read`, low bit 1 = template object) then misinterprets them and crashes (`call *(%rax)` on garbage). Fix: pad every string global size to a multiple of 8 (→ `.rodata.cst8`/`.cst16`, guaranteed 8-aligned). This blocked the user's `test.th`.
- LLVM helper emission order in compile(): struct/list print helpers are emitted in a fixed-point loop (so helpers referencing helpers work); `_emit_bigint_helpers` runs AFTER the loop because `_emit_snprintf_value` can add `used_bigint_helpers` (e.g. Int256 fields). LLVM allows forward references, so order is safe.
- All temp/result names in emitted helpers must be unique (LLVM rejects duplicate `%name` definitions) — `_emit_struct_str_helper`/`_emit_snprintf_value` use a `fresh()` counter for every name.
- struct field defaults are a PRE-EXISTING BUG (verified via git stash): `struct Point: x: Int8 = 2` then `Point()` yields 0, not 2 — defaults are parsed but never applied in `struct_init` emission (to_high_ir.py:2189 emits only explicitly-passed fields). Reproduces without any print changes. NOT fixed (out of scope).
- Interpolating a METHOD CALL inside an f-string is a PRE-EXISTING BUG: `f"{c.get_brand()}"` emits `call i32 @None(...)` because the template render-function re-emission loses method resolution (to_high_ir.py `_build_render_function`). Works for fields/vars (`f"{self.brand}"`). NOT fixed (out of scope).

## Work State
### Completed (this session)
- **`__str__` inheritance** (user request "zorg dat __str__ ook wordt overgeërfd"):
  - to_high_ir.py: `IRModule.__init__` now has `self.class_bases = {}`; `build_from_ast` records `module.class_bases[node.name] = node.base` for each `ClassDef`.
  - to_llvm_ir.py: `_class_str_function(tname)` now walks the base chain (`cls = self.module.class_bases.get(cls)`) with a seen-set, returning the first `{cls}.__str__` present in `self.func_name_set`; returns None if none. New `_upcast_struct(lines, value, src_type, dst_type, fresh)` extracts each dst field by name from the src struct (same flattened indices, since base fields are a prefix) and rebuilds a `%struct.{dst}` via insertvalue chain; `_emit_print`'s struct branch uses it when `owner != arg.type` (unique names via a per-arg fresh closure).
  - tests: `test_print_inherited_str` (DMW(Car) → `Car(brand=DMW)`), `test_print_inherited_str_extra_fields` (Truck adds `capacity`; upcast path), `test_print_overridden_str` (Boat overrides → `Boat(brand=Sunseeker)`). 570 → 573.
- **Earlier (print for structs/classes + string alignment fix)**:
- **to_llvm_ir.py**:
  - `compile()`: added `self.func_name_set = {f.name for f in module.funcs}`.
  - `compile()` helper loop: fixed-point over both `used_list_print` and `used_struct_print` (emits `__threadon_list_str_{tag}` and `__threadon_struct_str_{tag}`); `_emit_bigint_helpers()` moved after this loop.
  - `_emit_print` (`~line 1372`): added `%struct.` branch — if `_class_str_function(arg.type)` (i.e. `{type}.__str__` in module funcs) call it, else call `__threadon_struct_str_{tag}` and add to `used_struct_print`; removed the old struct-list-element unsupported exception.
  - New `_class_str_function(tname)` helper.
  - New `_emit_struct_str_helper(tname)`: snprintf-based writer → `{name: value, ...}`, Int8/16/32/64 (signed/unsigned via `_is_unsigned`), Int256 (bigint helpers), float/half (fpext→double `%f`), double, Bool (true/false), String `%s`, NoneType ("None"), nested structs, List[]. All names unique via fresh().
  - New `_emit_snprintf_value(out, buf_size, ftype, value, ptr, fresh)`.
  - `_emit_list_str_helper` (`~line 1621`): added struct-element branch.
  - String-global emission: sizes padded to multiple of 8 (`padded = ((size+7)//8)*8` + trailing `\00`) — fixes the odd-address tagged-pointer crash.
- **checker.py**: `InterpolatedStringExpr` now walked in `visit_expr` (UnusedVariableChecker) and `walk_expr` (DeadStoreChecker) — walks `part` for `("expr", ...)` parts; fixes false "Parameter 'self' never used" in `__str__` bodies using f-strings.
- **tests added** (559 → 570):
  - compile_test.py: `test_print_struct` (`{x: 3, y: 4}` + nested `{a: {...}, b: {...}}`), `test_print_struct_field_types` (Empty → `{}`; String/NoneType/Float64/Int256/Bool fields), `test_print_list_of_structs`, `test_print_class_without_str` (`{brand: BMW}`), `test_print_class_with_str` (`Bike(Gazelle)`), `test_print_class_with_str_no_field_use` (also `t.__str__()` explicit call), `test_string_alignment_tagged_pointers` (DMW + f-string template + short "DMW" string regression).
  - test_parser.py: CLASS_OK_SNIPPETS += `__str__` with explicit `-> String` and inferred String; CLASS_BREAK_SNIPPETS += `__str__ -> Int32` and `__str__` with extra param.
- **Earlier session (still present)**: builtins.py `_is_printable`/`builtin_return_type(aggregate_types=None)`; parser.py `_aggregate_types()`, print arg validation, `__str__` validation; checker.py class-aware checkers + ExprStmt dead-store fix + restored local_decl loop; compiler.py warnings→stderr on success; class parsing/checks/IR/tests (559 baseline).

### Active
- (none — `__str__` inheritance is complete)

### Blocked
- (none)

## Next Move
1. (Optional, pre-existing, out of scope) Fix struct field defaults: apply `VarDecl.expr` defaults for missing fields in `struct_init` emission (to_high_ir.py:2189) — user's test.th expects `{x: 2, y: 3}` but prints `{x: 0, y: 0}`.
2. (Optional, pre-existing, out of scope) Fix f-string interpolation of method calls (`@None` bug in `_build_render_function`).
3. No required work remains for the print/`__str__` objective. Run `python3 -m pytest tests/ -q` from `/home/joep/projects/AGI/threadon` to verify (currently 573 passed).

## Relevant Files
- /home/joep/projects/AGI/threadon/compiler/to_llvm_ir.py: all print-struct/class emission + string alignment fix. `_emit_print` ~1372, `_emit_struct_str_helper` ~1487, `_emit_snprintf_value` ~1528, `_emit_list_str_helper` ~1866, `_class_str_function` + `_upcast_struct` ~1475, compile() helper loop ~85, string globals ~150.
- /home/joep/projects/AGI/threadon/compiler/to_high_ir.py: `IRModule.class_bases` (~389), populated in `build_from_ast` ClassDef branch (~549-560).
- /home/joep/projects/AGI/threadon/compiler/checker.py: InterpolatedStringExpr in `visit_expr` (~453) and `walk_expr` (~568).
- /home/joep/projects/AGI/threadon/compiler/builtins.py, parser.py, compiler.py: print validation / `__str__` rules / warnings-to-stderr (done earlier).
- /home/joep/projects/AGI/threadon/tests/compile_test.py: print + alignment + inheritance tests (lines ~900-1100).
- /home/joep/projects/AGI/threadon/tests/test_parser.py: `__str__` ok/break snippets (~1181-1345).
- /home/joep/projects/AGI/threadon/test.th: user scratch file — runs; `print(du)` now gives `Car(brand=DMW)` via inherited `__str__`. Point still prints `{x: 0, y: 0}` due to the pre-existing struct-defaults bug.
