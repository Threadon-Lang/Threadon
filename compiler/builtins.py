BUILTIN_SIGS = {
    "print": ([("values", "poly*")], "NoneType"),
    "input": ([("prompt", "String")], "String"),

}

INT_TYPES = ("Int8", "Int16", "Int32", "Int64", "Int256")
UINT_TYPES = ("UInt8", "UInt16", "UInt32", "UInt64", "UInt256")
ALL_INT_TYPES = INT_TYPES + UINT_TYPES
FLOAT_TYPES = ("Float16", "Float32", "Float64")

NUMERIC_TYPES = ALL_INT_TYPES + FLOAT_TYPES

PRINTABLE_TYPES = ALL_INT_TYPES + FLOAT_TYPES + ("Bool", "String", "NoneType")
CONVERTIBLE_TO_INT = FLOAT_TYPES + ALL_INT_TYPES + ("Bool", "String")
CONVERTIBLE_TO_FLOAT = ALL_INT_TYPES + FLOAT_TYPES + ("String",)
CONVERTIBLE_TO_BOOL = ALL_INT_TYPES + FLOAT_TYPES + ("String",)

# A type group is a set of types that a variable may take on. The compiler
# expands a group to its concrete members at parse time and stores a value as a
# tagged union, so every error involving a group is caught at compile time.
GROUP_DEFS = {
    "Int": ALL_INT_TYPES,
    "Float": FLOAT_TYPES,
    "Number": NUMERIC_TYPES,
    "Builtin": ALL_INT_TYPES + FLOAT_TYPES + ("Bool", "String", "NoneType"),
}


def is_group(name):
    return name in GROUP_DEFS


def group_members(name):
    """Concrete member types of a group keyword (or None)."""
    return GROUP_DEFS.get(name)


def union_str(members):
    """Canonical string for a union type, e.g. 'Union[Int32|Int64]'."""
    return "Union[" + "|".join(sorted(members)) + "]"


def union_members(t):
    """Member types of a 'Union[...]' string, or None."""
    if isinstance(t, str) and t.startswith("Union[") and t.endswith("]"):
        inner = t[len("Union["):-1]
        if not inner:
            return ()
        return tuple(sorted(inner.split("|")))
    return None


def is_union_type(t):
    return union_members(t) is not None


def expand_type(t):
    """Concrete members a type annotation can hold.

    Groups and unions expand to their members; any other type is its own
    single member.
    """
    if is_group(t):
        return tuple(group_members(t))
    m = union_members(t)
    if m is not None:
        return m
    return (t,)


def _int_width(t):
    return int(t[4:] if t.startswith("UInt") else t[3:])


def common_numeric_type(a, b):
    """Type used when two numeric types are combined in one operation.

    Returns None when the two types cannot be combined.
    """
    if a in ALL_INT_TYPES and b in ALL_INT_TYPES:
        if a == b:
            return a
        aw, bw = _int_width(a), _int_width(b)
        if aw != bw:
            return a if aw > bw else b
        if a.startswith("UInt") or b.startswith("UInt"):
            return "UInt" + str(aw)
        return a
    if a in FLOAT_TYPES and b in FLOAT_TYPES:
        if a == b:
            return a
        order = {"Float16": 0, "Float32": 1, "Float64": 2}
        return a if order[a] > order[b] else b
    if a in ALL_INT_TYPES and b in FLOAT_TYPES:
        return b
    if a in FLOAT_TYPES and b in ALL_INT_TYPES:
        return a
    return None


def _is_printable(t, aggregate_types=None):
    if t in PRINTABLE_TYPES:
        return True
    if is_union_type(t):
        return all(
            _is_printable(m, aggregate_types) for m in union_members(t)
        )
    if aggregate_types and t in aggregate_types:
        return True
    if isinstance(t, str) and t.startswith("List[") and t.endswith("]"):
        return _is_printable(t[5:-1], aggregate_types)
    if isinstance(t, str) and t.startswith("Dict[") and t.endswith("]"):
        inner = t[5:-1]
        comma_idx = None
        depth = 0
        for ci, ch in enumerate(inner):
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
            elif ch == ',' and depth == 0:
                comma_idx = ci
                break
        if comma_idx is not None:
            key_type = inner[:comma_idx].strip()
            val_type = inner[comma_idx + 1:].strip()
        else:
            key_type = inner.strip()
            val_type = "Unknown"
        return _is_printable(key_type, aggregate_types) and _is_printable(val_type, aggregate_types)
    return False


def builtin_return_type(func_name, arg_types, aggregate_types=None):

    params, ret = BUILTIN_SIGS[func_name]

    n_varargs = sum(1 for _, p in params if p.endswith("*"))
    n_fixed = len(params) - n_varargs
    if len(arg_types) < n_fixed or (n_varargs == 0 and len(arg_types) != len(params)):
        n = len(params)
        raise ValueError(
            f"Function '{func_name}' expects {n} argument"
            f"{'' if n == 1 else 's'}, got {len(arg_types)}"
        )

    for (arg_type, (param_name, param_type)) in zip(arg_types, params):
        if param_type == "poly" or param_type.endswith("*"):
            continue
        if arg_type != param_type:
            raise ValueError(
                f"Function '{func_name}' argument '{param_name}' "
                f"expects type {param_type}, got {arg_type}"
            )

    if func_name == "print":
        for arg_type in arg_types:
            if not _is_printable(arg_type, aggregate_types):
                raise ValueError(
                    f"Function 'print' cannot print a value of type {arg_type}"
                )
        return "NoneType"



    return ret