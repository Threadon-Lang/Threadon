# containers

Functional stacks, queues and maps. The stacks and queues hold `Int32`; the
maps add `Dict`-backed key/value storage with `String` keys, `Int32` values,
and the reverse.

Threadon classes have value semantics: a method call receives a copy of
`self`, so a method cannot change the caller's object. Methods therefore
either only **read** the container or **return a new one**. Reassign the
result:

```threadon
import containers

def main() -> Int32
    ages: containers.StringIntMap = containers.empty_string_int_map()
    ages = ages.put("ann", 30)
    ages = ages.put("bob", 40)
    found: containers.IntLookup = ages.get("bob")
    print(found.found)   # True
    print(found.value)   # 40
    print(ages.size())   # 2
    return 0
```

The original module-style functions (`containers.queue_size(q)`,
`containers.push(s, v)`, `containers.string_int_put(m, k, v)`, ...) are kept
as thin aliases. Prefer the methods below in new code.

## Stacks and queues

Create them with `empty_stack()` / `empty_queue()` or with the exported
classes `IntStack` / `IntQueue`.

| Method | Meaning |
| --- | --- |
| `s.size()` | number of items |
| `s.is_empty()` | `Bool` |
| `s.peek()` / `q.front()` | next value, or `0` when empty |
| `s.pushed(v)` / `q.enqueued(v)` | **new** container with `v` added |
| `s.contains(v)` | membership test |
| `s.to_list()` | copy; bottom-to-top / oldest-to-newest |

`containers.pop(s)` and `containers.dequeue(q)` remain free functions because
their `StackPop` / `QueuePop` results refer to the container classes.

## Maps

Create them with `empty_string_int_map()` / `empty_int_string_map()` or with
the exported classes `StringIntMap` / `IntStringMap`.

| `StringIntMap` | `IntStringMap` | Meaning |
| --- | --- | --- |
| `m.size()` | `m.size()` | number of entries |
| `m.get(k)` | `m.get(k)` | `IntLookup` / `StringLookup` with `found` and `value` |
| `m.has(k)` | `m.has(k)` | `Bool` membership test |
| `m.put(k, v)` | `m.put(k, v)` | **new** map with `k` set to `v` |
| `m.remove(k)` | `m.remove(k)` | **new** map without `k` |
| `m.keys()` | `m.keys()` | `List[String]` / `List[Int32]` of keys |

A missing key gives `found=False` and the zero value (`0` or `""`), so lookup
never raises a `KeyError`. Put replaces an existing value; remove of a missing
key returns the same map. All operations copy the underlying `Dict`, so they
are meant for small collections.

Tests: `python3 -m threadon --run-tests compiler/stdlib/containers/test.th`.
