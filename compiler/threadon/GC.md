# Threadon garbage collector

Threadon has an explicit, manual garbage collector. There is no `free` in the
language; instead the built-in `collect()` function runs a full collection
synchronously before returning:

```threadon
def work() -> NoneType
    s: String = ""
    i: Int32 = 0
    while i < 1000:
        s = s + "garbage"
        i += 1
    collect()  # reclaim the discarded intermediate strings here
```

`collect()` takes no arguments and returns `NoneType`. Nothing is collected
automatically: there is no background collector thread, no allocation
threshold and no `THREADON_GC_THRESHOLD` environment variable. A program that
never calls `collect()` never runs a collection, even if it allocates heavily.

## What is collected

Every allocation emitted by the compiler goes through `__threadon_gc_alloc`:

- string concatenation, slicing and `chr`
- list and dictionary backing arrays
- thread closures
- template payload/objects

String literals are static constants and are not collected. Memory owned by
native modules (C/C++/Rust/Python objects) is still owned by those modules.

A collection reclaims blocks that are unreachable from the current roots. The
compiler does not insert collection calls for you, so call `collect()` at
points where you know a batch of temporary values has become garbage — for
example between iterations of a long loop, or after dropping a large list.

## How it works

Each heap object has a 48-byte header (magic, size, mark epoch, links)
followed by the payload pointer returned to generated code. Payload words are
scanned **conservatively** — a word is treated as a pointer if it points at a
live header. This avoids emitting type descriptors for every container type.

A call to `collect()` performs these steps synchronously, on the calling
thread:

1. It bumps the mark epoch and snapshot generation, then snapshots the calling
   thread's stack directly. Mutator threads publish a snapshot of their stack
   whenever they allocate; those published snapshots are used as roots too.
2. It marks module globals and all published stack snapshots, following every
   pointer found inside marked payloads.
3. It takes a second snapshot generation to catch pointers stored into locals
   while the first marking pass was running, and marks again.
4. It sweeps unmarked objects. Objects allocated *during* a collection are
   marked immediately, and pointer stores into heap objects call a write
   barrier that marks the new value. Together these preserve the tri-color
   invariant without precise per-field barriers.

Collection pauses the calling thread for the whole mark-and-sweep cycle. Other
threads keep running, but they briefly lock around heap bookkeeping and stack
snapshot publication. New allocations during a cycle are safe.

## Stats

Set `THREADON_GC_STATS` to any value other than `0` to get timing info:

```bash
THREADON_GC_STATS=1 python3 -m threadon app.th --run
```

At exit it prints a line like:

```
[gc] collections=2 snapshots=4 snapshot_max=0us snapshot_avg=0us mark_max=11us sweep_max=179us collector_total=0.2ms
```

`collections` counts explicit `collect()` calls. `snapshot_*` is the time spent
publishing root snapshots, `mark_max` and `sweep_max` are the longest single
mark/sweep phases, and `collector_total` is the sum of all collection time.

## Implementation notes

`gc_runtime.c` in this directory is the collector. Rebuild its IR with:

```bash
./build_gc_runtime.sh
```

The script strips module/target lines and renames clang's private `@.str.*`
constants so they cannot collide with string constants in generated modules.

The generated IR is appended to a module when it allocates **or** calls
`collect()`, so compute-only programs do not pay for the collector at JIT
startup. Keeping the runtime in IR means `lli` and native executables behave
identically.

### Known limitations

- Conservative scanning can keep an object alive for one extra cycle if an
  integer happens to look like a heap pointer.
- A thread that is blocked forever (or never allocates again) keeps its last
  published stack snapshot. An explicit `collect()` proceeds with whatever
  snapshots are available.
- The collector does not move objects, so native pointers into Threadon
  strings/lists remain valid while the object is live.
- Collection time grows with the number of live, reachable blocks. Long
  mark/sweep pauses are possible on large heaps; tune where you call
  `collect()` accordingly.
- Fixed caps: 128 registered threads, 8192 snapshot words per thread and 256
  global roots.
