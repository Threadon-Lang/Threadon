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


def builtin_return_type(func_name, arg_types):

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
            if arg_type not in PRINTABLE_TYPES:
                raise ValueError(
                    f"Function 'print' cannot print a value of type {arg_type}"
                )
        return "NoneType"



    return ret