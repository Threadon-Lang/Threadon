# Threadon garbage collector

Threadon manages heap memory automatically. There is no `free` in the
language, and you do not need to call one from native modules for values the
compiler allocates.

## What is collected

Every allocation emitted by the compiler goes through `__threadon_gc_alloc`:

- string concatenation, slicing and `chr`
- list and dictionary backing arrays
- thread closures
- template payload/objects

String literals are static constants and are not collected. Memory owned by
native modules (C/C++/Rust/Python objects) is still owned by those modules.

## How it works

Each heap object has a 48-byte header (magic, size, mark epoch, links)
followed by the payload pointer returned to generated code. Payload words are
scanned **conservatively** — a word is treated as a pointer if it points at a
live header. This avoids emitting type descriptors for every container type.

Collection runs on a **background thread**:

1. The collector increments the snapshot generation. Mutator threads publish
   a snapshot of their stack the next time they allocate. A thread only pauses
   for the few microseconds needed to copy its own root words; other threads
   keep running.
2. The collector marks module globals and all published stack snapshots.
3. It asks for a second snapshot to catch pointers stored into locals during
   step 2, and marks again.
4. It sweeps unmarked objects. Objects allocated during the cycle are marked
   as live by the allocator, and pointer stores into heap objects call a write
   barrier that marks the new value.

So there is **no stop-the-world pause**. Marking and sweeping run concurrently
with the program; the only synchronization is a short per-thread stack
snapshot and a small spinlock around heap bookkeeping.

## Tuning

Set `THREADON_GC_THRESHOLD` to change the allocation threshold (in bytes):

```bash
THREADON_GC_THRESHOLD=16777216 python3 -m threadon app.th --run
```

The default is 4 MiB. A smaller value collects more often (more CPU, less
memory); a larger value collects less often. `THREADON_GC_THRESHOLD=0` disables
collection entirely — allocations still use the GC allocator, but no collector
thread is started. That is useful for very small, bounded heaps, but memory is
then never reclaimed.

To see what the collector is doing, set `THREADON_GC_STATS=1`:

```bash
THREADON_GC_STATS=1 THREADON_GC_THRESHOLD=1048576 python3 -m threadon app.th --run
```

At exit it prints a line like:

```
[gc] collections=428 snapshots=856 snapshot_max=2us snapshot_avg=0us mark_max=1550us sweep_max=857us collector_total=491.0ms
```

`snapshot_*` is the per-thread pause while publishing roots; `mark_max` and
`sweep_max` are the longest background phases. `collector_total` includes time
waiting for snapshots, so it is not the same as pause time.

## Implementation notes

`gc_runtime.c` in this directory is the collector. Rebuild its IR with:

```bash
./build_gc_runtime.sh
```

The script strips module/target lines and renames clang's private `@.str.*`
constants so they cannot collide with string constants in generated modules.

The generated IR is appended to a module only when it actually allocates, so
compute-only programs do not pay for the collector at JIT startup. Keeping the
runtime in IR means `lli` and native executables behave identically.

### Known limitations

- Conservative scanning can keep an object alive for one extra cycle if an
  integer happens to look like a heap pointer.
- A thread that is blocked forever (or never allocates again) keeps its last
  published stack snapshot. The collector proceeds after a short timeout.
- The collector does not move objects, so native pointers into Threadon
  strings/lists remain valid while the object is live.
- This is a **soft real-time** design, not a hard 1 ms guarantee. Mutator
  threads are not globally stopped, but each thread briefly pauses for its own
  stack snapshot, and the background marker/sweeper competes for CPU and the
  heap lock. In a stress run with a 4 MiB heap, `mark_max` reached ~4 ms; with a
  1 MiB threshold it stayed around ~1.5 ms. For a hard deadline, keep the
  deadline path allocation-free (compute-only code has no GC runtime in the IR)
  or use `THREADON_GC_THRESHOLD=0` with a bounded heap.
