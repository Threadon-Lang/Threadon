# heap

A functional binary min-heap of `Int32` values backed by a `List[Int32]`.
`Heap` is a struct with value semantics: `push` and `pop` return a new heap and
leave the original alone. The smallest item can be read with `peek`.

```threadon
import heap

def main() -> Int32
    h: heap.Heap = heap.empty()
    h = heap.push(h, 5)
    h = heap.push(h, 1)
    h = heap.push(h, 3)
    print(heap.peek(h))   # 1
    h = heap.pop(h)
    print(heap.peek(h))   # 3
    print(heap.sort([5, 1, 3, 1]))  # [1, 1, 3, 5]
    return 0
```

| Function | Result |
| --- | --- |
| `empty()` | a new heap with no items |
| `from_list(xs)` | heap built from a copy of `xs` (bottom-up heapify) |
| `size(h)` | number of items as `Int32` |
| `peek(h)` | smallest item, or `0` when empty |
| `push(h, v)` | a new heap containing `v` in addition to `h`'s items |
| `pop(h)` | a new heap without the smallest item; empty heaps are unchanged |
| `sort(xs)` | ascending heapsort of a copy of `xs` |
| `copy_ints(xs)` | helper: explicit copy of an `Int32` list |
| `sift_up(items, start)` | helper: restore order upwards, returns the list |
| `sift_down(items, start, n)` | helper: restore order in `items[0:n]` downwards |

Caveats:

- `pop` removes the minimum but does not return it separately; call `peek`
  before `pop` when you need the value.
- `peek` returns `0` for an empty heap, so `0` is not a useful sentinel when
  zero can be stored; check `size(h) > 0` first.
- Duplicate values are kept, and sorting is stable only in the sense that the
  multiset of values is preserved; equal values are not guaranteed to keep
  their original order.
- Every operation copies its list, so copies are cheap for small heaps but
  cost O(n) each; `sort` is O(n log n) comparisons with O(n) copying per pop.

Tests: `python3 -m threadon --run-tests compiler/stdlib/heap/test.th`.
