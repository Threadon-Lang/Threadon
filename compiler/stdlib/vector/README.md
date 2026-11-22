# vector

Two- and three-dimensional vectors of `Float64`, built on the `math` module.
`Vec2` and `Vec3` are structs, so they use value semantics and named field
initializers:

```threadon
from vector import Vec2, add2, length2
import vector

def main() -> Int32
    a: Vec2 = Vec2(x=3.0, y=4.0)
    b: Vec2 = add2(a, Vec2(x=1.0, y=2.0))
    print(length2(a))   # 5.000000
    print(b.x)          # 4.000000
    return 0
```

| 2D | 3D | Result |
| --- | --- | --- |
| `vec2(x, y)` | `vec3(x, y, z)` | constructor functions |
| `add2(a, b)` | `add3(a, b)` | component-wise sum |
| `sub2(a, b)` | `sub3(a, b)` | component-wise difference |
| `scale2(a, k)` | `scale3(a, k)` | multiply by a scalar |
| `dot2(a, b)` | `dot3(a, b)` | dot product |
| — | `cross3(a, b)` | cross product |
| `length2(a)` | `length3(a)` | Euclidean length |
| `normalize2(a)` | `normalize3(a)` | unit vector (zero stays zero) |
| `distance2(a, b)` | `distance3(a, b)` | distance between two vectors |

Structs have no methods in Threadon, so every operation is a free function.
Functions return new structs and do not modify their arguments.

Tests: `python3 -m threadon --run-tests compiler/stdlib/vector/test.th`.
