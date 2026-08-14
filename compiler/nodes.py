from dataclasses import dataclass

from .lexer import Token


@dataclass
class Node:
    pass
@dataclass
class Expr(Node):
    pass
@dataclass
class FunctionDef(Node):
    name: str
    params: list[tuple[str, str, Expr | None]]
    return_type: str
    body: list[list]

    def __repr__(self):
        return (
            f"FunctionDef(name={self.name}, "
            f"params={self.params}, "
            f"return_type={self.return_type}, "
            f"body_len={len(self.body)}), "
            f"body={self.body}"
        )
@dataclass
class ReturnStmt(Node):
    return_type: str
    value: list[Token] | None

@dataclass
class VarDecl:
    name: str
    var_type: str
    expr: list[Expr]


@dataclass
class LiteralExpr(Expr):
    value: Token
    type: str

@dataclass
class InterpolatedStringExpr(Expr):
    kind: str
    parts: list[tuple]
    type: str = "String"

@dataclass
class VarExpr(Expr):
    name: str

@dataclass
class CallExpr(Expr):
    func_name: str
    args: list

@dataclass
class ExprStmt(Node):
    expr: Expr

@dataclass
class BinaryExpr(Expr):
    left: Expr
    op: str
    right: Expr
@dataclass
class UnaryExpr(Expr):
    op: str
    expr: Expr
@dataclass
class IfStmt:
    condition: any
    body: list
    elif_blocks: list
    else_body: list | None
@dataclass
class WhileStmt:
    condition: any
    body: list
@dataclass
class Assign:
    name: str
    expr: list[Expr]
@dataclass
class IndexAssign:
    target: Expr
    index: Expr
    value: Expr
@dataclass
class FieldAssign:
    name: str
    field: str
    expr: Expr
@dataclass
class StructDef:
    name: str
    fields: any
@dataclass
class FieldAccessExpr:
    obj: Expr
    field: str
@dataclass
class StructInitExpr:
    struct_name: str
    fields: any

@dataclass
class RefExpr(Expr):
    inner: Expr

@dataclass
class ListLiteralExpr(Expr):
    elements: list

@dataclass
class IndexExpr(Expr):
    obj: Expr
    index: Expr

@dataclass
class ImportStmt(Node):
    module: str
    names: list
    lazy: bool = False
    is_from: bool = True
class CastExpr:
    def __init__(self, target_type, expr):
        self.target_type = target_type
        self.expr = expr