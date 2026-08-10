

BUILTIN_SIGS = {
    "print": ([("value", "poly")], "NoneType"),
    "input": ([("prompt", "String")], "String"),
    "to_int": ([("value", "poly")], "Int32"),
    "to_float": ([("value", "poly")], "Float32"),
    "to_bool": ([("value", "poly")], "Bool"),
}

PRINTABLE_TYPES = ("Int32", "Float32", "Bool", "String")
CONVERTIBLE_TO_INT = ("Float32", "Bool", "String")
CONVERTIBLE_TO_FLOAT = ("Int32", "String")
CONVERTIBLE_TO_BOOL = ("Int32", "Float32", "String")


def builtin_return_type(func_name, arg_types):

    params, ret = BUILTIN_SIGS[func_name]

    if len(arg_types) != len(params):
        n = len(params)
        raise ValueError(
            f"Function '{func_name}' expects {n} argument"
            f"{'' if n == 1 else 's'}, got {len(arg_types)}"
        )

    for (arg_type, (param_name, param_type)) in zip(arg_types, params):
        if param_type == "poly":
            continue
        if arg_type != param_type:
            raise ValueError(
                f"Function '{func_name}' argument '{param_name}' "
                f"expects type {param_type}, got {arg_type}"
            )

    if func_name == "print":
        arg_type = arg_types[0]
        if arg_type not in PRINTABLE_TYPES:
            raise ValueError(
                f"Function 'print' cannot print a value of type {arg_type}"
            )
        return "NoneType"

    if func_name == "to_int":
        arg_type = arg_types[0]
        if arg_type not in CONVERTIBLE_TO_INT:
            raise ValueError(
                f"Function 'to_int' expects Float32, Bool or String, got {arg_type}"
            )
        return "Int32"

    if func_name == "to_float":
        arg_type = arg_types[0]
        if arg_type not in CONVERTIBLE_TO_FLOAT:
            raise ValueError(
                f"Function 'to_float' expects Int32 or String, got {arg_type}"
            )
        return "Float32"

    if func_name == "to_bool":
        arg_type = arg_types[0]
        if arg_type not in CONVERTIBLE_TO_BOOL:
            raise ValueError(
                f"Function 'to_bool' expects Int32, Float32 or String, got {arg_type}"
            )
        return "Bool"

    return ret
