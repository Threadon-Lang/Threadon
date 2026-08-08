from compiler.to_high_ir import *
if __name__ == "__main__":
    code = """
struct Z:
    z: Int32
struct Point:
    x: Int32 = 0
    y: Int32 = 0
    z: Z = Z(z=0)
def add(x: Int32, y: Int32) -> Int32
    if x < 2:
        result: Int32 = x + y * 2
    else: 
        result: Int32 = x + y ** 2
    MyPoint: Point = Point(x=0,y=0,z=Z(z=0))
    result += 2 ** 3 - MyPoint.z.z
    return result
value: Int32 = add(10,87)
value2: Int32 = value^
"""

    parser = Parser()
    ast = parser.parse(code)
    
    checker = CombinedChecker()
    checker.run_all(ast)
    
    builder = SSABuilder()
    ir_module = builder.build_from_ast(ast)

    print(ir_module)
