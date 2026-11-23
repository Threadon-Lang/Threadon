# graph

Small directed-graph helpers: fixed node indices, directed edges and
breadth-first traversal. A `Graph` has value semantics, so `add_edge` and
`remove_edge` return a new graph and never modify their argument.

```threadon
import graph

def main() -> Int32
    g: graph.Graph = graph.empty(4)
    g = graph.add_edge(g, 0, 1)
    g = graph.add_edge(g, 1, 2)
    print(graph.bfs(g, 0))
    print(graph.has_path(g, 0, 2))
    return 0
```

| Function | Result |
| --- | --- |
| `empty(n)` | graph with nodes `0 .. n-1` and no edges |
| `neighbors(g, u)` | outgoing edges of `u`, or `[]` when out of range |
| `add_edge(g, u, v)` | new graph with `u -> v` (duplicates ignored) |
| `remove_edge(g, u, v)` | new graph without that edge |
| `has_edge(g, u, v)` | is the direct edge present? |
| `bfs(g, start)` | shortest distances from `start`, `-1` when unreachable |
| `has_path(g, start, goal)` | is `goal` reachable from `start`? |
| `reachable(g, start)` | reachable nodes in ascending index order |

Traversal is iterative (an explicit queue), so deep graphs do not exhaust the
call stack. Out-of-range node indices are always ignored.

Tests: `python3 -m threadon --run-tests compiler/stdlib/graph/test.th`.
