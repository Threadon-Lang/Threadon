from dataclasses import dataclass
from typing import List, Tuple
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
    params: List[Tuple[str, str]]
    return_type: str
    body: List[list]

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
    value: List[Token] | None

@dataclass
class VarDecl:
    name: str
    var_type: str
    expr: List[Expr]


@dataclass
class LiteralExpr(Expr):
    value: Token
    type: str

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
class Assign:
    name: str
    expr: List[Expr]
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
class ImportStmt(Node):
    module: str
    names: list
    lazy: bool = False
    is_from: bool = True
