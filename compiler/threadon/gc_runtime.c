/*
 * Threadon manual garbage collector.
 *
 * This file is compiled once to LLVM IR (gc_runtime.ll) and appended to every
 * generated module that allocates or calls collect(). Keeping it in IR rather
 * than a shared library means the same runtime works with `lli` and with
 * native executables.
 *
 * Design:
 *   - Every heap object is a GCBlock header followed by the payload returned
 *     to generated code. Payload words are scanned conservatively, so the
 *     compiler does not need to emit type descriptors for roots/fields.
 *   - Collection is explicit and synchronous: the `collect()` builtin calls
 *     __threadon_gc_collect(), which marks and sweeps before returning. There
 *     is no background thread and no allocation threshold.
 *   - Mutator threads publish a stack snapshot whenever they allocate;
 *     collect() also snapshots the calling thread directly.
 *   - New allocations made during a collection are marked immediately. Stores
 *     of pointers into heap objects call a write barrier, which marks the new
 *     value. Together these preserve the tri-color invariant without the
 *     compiler having to emit precise field barriers.
 *
 * Known limitations (documented in GC.md):
 *   - Conservative: an integer that happens to look like a heap pointer can
 *     keep an object alive for one extra cycle.
 *   - Native module memory (C/C++/Rust/Python objects) is not managed here.
 */

#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <pthread.h>
#include <sched.h>
#include <time.h>

#define GC_HEADER_WORDS 6
#define GC_HEADER_SIZE  ((uint64_t)(GC_HEADER_WORDS * 8)) /* 48, keeps 8-byte payload alignment */
#define GC_MAGIC        0x5448524541444f4eULL            /* "THREADON" */
#define GC_MAX_THREADS  128
#define GC_SNAPSHOT_WORDS 8192
#define GC_MAX_ROOTS    512 /* stored as addr/size pairs */

typedef struct GCBlock {
    uint64_t magic;
    uint64_t size;      /* total bytes, header included */
    uint64_t mark;      /* epoch of last mark */
    uint64_t next;      /* heap list, typed as uintptr_t */
    uint64_t work_next; /* unused placeholder, keeps header 8-byte aligned */
    uint64_t pad;
} GCBlock;

typedef struct {
    uint64_t thread_id;
    uint64_t stack_base;                /* high-water mark for this stack */
    uint64_t snap_gen;                  /* generation of the published snapshot */
    uint64_t snap_count;
    uint64_t snap[GC_SNAPSHOT_WORDS];
} GCThread;

static uint64_t gc_head = 0;
static uint64_t gc_epoch = 1;
static uint64_t gc_collecting = 0;
static uint64_t gc_snap_gen = 0;
static uint64_t gc_min = UINTPTR_MAX;
static uint64_t gc_max = 0;
static uint64_t gc_roots[GC_MAX_ROOTS];
static uint64_t gc_root_count = 0;
static GCThread gc_threads[GC_MAX_THREADS];
static uint64_t gc_thread_count = 0;
static __thread uint64_t gc_my_id = 0;
static volatile char gc_lock = 0;

/* Optional diagnostics: THREADON_GC_STATS=1 prints timing stats at exit. */
static int gc_stats = 0;
static int gc_env_initialized = 0;
static uint64_t gc_collections = 0;
static uint64_t gc_max_snapshot_ns = 0;
static uint64_t gc_sum_snapshot_ns = 0;
static uint64_t gc_snapshot_count = 0;
static uint64_t gc_max_mark_ns = 0;
static uint64_t gc_max_sweep_ns = 0;
static uint64_t gc_sum_collector_ns = 0;

static uint64_t gc_now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

static void gc_init_env(void) {
    if (gc_env_initialized) return;
    const char *stats_env = getenv("THREADON_GC_STATS");
    if (stats_env && strcmp(stats_env, "0") != 0) gc_stats = 1;
    gc_env_initialized = 1;
}

static void gc_lock_acquire(void) {
    while (__atomic_test_and_set(&gc_lock, __ATOMIC_ACQUIRE)) {
        sched_yield();
    }
}

static void gc_lock_release(void) {
    __atomic_clear(&gc_lock, __ATOMIC_RELEASE);
}

static void gc_note_max(uint64_t *counter, uint64_t dt) {
    uint64_t old = __atomic_load_n(counter, __ATOMIC_RELAXED);
    while (dt > old && !__atomic_compare_exchange_n(counter, &old, dt, 0,
                                                    __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {}
}

static uint64_t gc_mask(uint64_t p) {
    /* Template values use the low bit as a tag; all GC objects are >= 8 aligned. */
    return p & ~((uint64_t)1);
}

static int gc_is_heap(uint64_t p) {
    p = gc_mask(p);
    if (p == 0 || (p & 7) != 0) return 0;
    if (p < gc_min || p > gc_max || p < GC_HEADER_SIZE) return 0;
    GCBlock *b = (GCBlock *)(uintptr_t)(p - GC_HEADER_SIZE);
    if (b->magic != GC_MAGIC) return 0;
    if (b->size < GC_HEADER_SIZE) return 0;
    if ((uint64_t)(uintptr_t)b + b->size < p) return 0;
    return 1;
}

static void gc_push_candidate(uint64_t **stack, uint64_t *cap, uint64_t *n, uint64_t v) {
    v = gc_mask(v);
    if (!gc_is_heap(v)) return;
    if (*n == *cap) {
        uint64_t grown_cap = *cap * 2;
        uint64_t *grown = (uint64_t *)realloc(*stack, (size_t)(grown_cap * sizeof(uint64_t)));
        if (!grown) return;
        *stack = grown;
        *cap = grown_cap;
    }
    (*stack)[(*n)++] = v;
}

/* Mark a value and everything reachable from it, using a local work stack. */
static void gc_mark_tree(uint64_t p) {
    p = gc_mask(p);
    if (!gc_is_heap(p)) return;

    uint64_t cap = 256, n = 0;
    uint64_t *stack = (uint64_t *)malloc((size_t)(cap * sizeof(uint64_t)));
    if (!stack) return;
    gc_push_candidate(&stack, &cap, &n, p);

    while (n > 0) {
        uint64_t q = gc_mask(stack[--n]);
        if (!gc_is_heap(q)) continue;
        GCBlock *b = (GCBlock *)(uintptr_t)(q - GC_HEADER_SIZE);
        uint64_t epoch = __atomic_load_n(&gc_epoch, __ATOMIC_SEQ_CST);
        uint64_t mark = __atomic_load_n(&b->mark, __ATOMIC_SEQ_CST);
        if (mark == epoch) continue;
        __atomic_store_n(&b->mark, epoch, __ATOMIC_SEQ_CST);

        uint64_t end = (uint64_t)(uintptr_t)b + b->size;
        for (uint64_t w = q; w + 8 <= end; w += 8) {
            gc_push_candidate(&stack, &cap, &n,
                              *(volatile uint64_t *)(uintptr_t)w);
        }
    }
    free(stack);
}

static void gc_mark_roots(void) {
    uint64_t cap = 256, n = 0;
    uint64_t *stack = (uint64_t *)malloc((size_t)(cap * sizeof(uint64_t)));
    if (!stack) return;

    for (uint64_t i = 0; i + 1 < gc_root_count; i += 2) {
        uint64_t addr = gc_roots[i];
        uint64_t bytes = gc_roots[i + 1];
        for (uint64_t off = 0; off + 8 <= bytes; off += 8) {
            gc_push_candidate(&stack, &cap, &n,
                              *(volatile uint64_t *)(uintptr_t)(addr + off));
        }
    }

    /* Other threads refresh their snapshot whenever they allocate. Copy it
       under the lock so a concurrent publish cannot tear the word array. */
    for (uint64_t t = 0; t < gc_thread_count && t < GC_MAX_THREADS; ++t) {
        GCThread *th = &gc_threads[t];
        if (th->stack_base == 0) continue;
        gc_lock_acquire();
        uint64_t count = th->snap_count;
        if (count > GC_SNAPSHOT_WORDS) count = GC_SNAPSHOT_WORDS;
        for (uint64_t i = 0; i < count; ++i) {
            gc_push_candidate(&stack, &cap, &n, th->snap[i]);
        }
        gc_lock_release();
    }

    while (n > 0) {
        uint64_t q = gc_mask(stack[--n]);
        if (!gc_is_heap(q)) continue;
        GCBlock *b = (GCBlock *)(uintptr_t)(q - GC_HEADER_SIZE);
        uint64_t epoch = __atomic_load_n(&gc_epoch, __ATOMIC_SEQ_CST);
        uint64_t mark = __atomic_load_n(&b->mark, __ATOMIC_SEQ_CST);
        if (mark == epoch) continue;
        __atomic_store_n(&b->mark, epoch, __ATOMIC_SEQ_CST);
        uint64_t end = (uint64_t)(uintptr_t)b + b->size;
        for (uint64_t w = q; w + 8 <= end; w += 8) {
            gc_push_candidate(&stack, &cap, &n,
                              *(volatile uint64_t *)(uintptr_t)w);
        }
    }
    free(stack);
}

static void gc_capture_stack(void) {
    uint64_t id = gc_my_id;
    if (id == 0 || id > GC_MAX_THREADS) return;
    GCThread *th = &gc_threads[id - 1];
    uint64_t gen = __atomic_load_n(&gc_snap_gen, __ATOMIC_SEQ_CST);
    gc_lock_acquire();
    if (th->snap_gen == gen) {
        gc_lock_release();
        return; /* already published for this phase */
    }

    uint64_t sp = (uint64_t)(uintptr_t)__builtin_frame_address(0);
    uint64_t top = th->stack_base;
    uint64_t t0 = gc_stats ? gc_now_ns() : 0;
    uint64_t n = 0;
    if (top != 0 && sp < top) {
        for (uint64_t p = sp; p + 8 <= top && n < GC_SNAPSHOT_WORDS; p += 8) {
            uint64_t v = gc_mask(*(volatile uint64_t *)(uintptr_t)p);
            if (gc_is_heap(v)) th->snap[n++] = v;
        }
    }
    th->snap_count = n;
    __atomic_store_n(&th->snap_gen, gen, __ATOMIC_SEQ_CST);
    gc_lock_release();

    if (gc_stats) {
        uint64_t dt = gc_now_ns() - t0;
        __atomic_fetch_add(&gc_sum_snapshot_ns, dt, __ATOMIC_RELAXED);
        __atomic_fetch_add(&gc_snapshot_count, 1, __ATOMIC_RELAXED);
        gc_note_max(&gc_max_snapshot_ns, dt);
    }
}

static void gc_sweep(void) {
    gc_lock_acquire();
    uint64_t epoch = __atomic_load_n(&gc_epoch, __ATOMIC_SEQ_CST);
    uint64_t *link = &gc_head;
    uint64_t cur = gc_head;
    while (cur != 0) {
        GCBlock *b = (GCBlock *)(uintptr_t)cur;
        uint64_t next = b->next;
        uint64_t mark = __atomic_load_n(&b->mark, __ATOMIC_SEQ_CST);
        if (mark != epoch) {
            *link = next;
            free(b);
        } else {
            link = &b->next;
        }
        cur = next;
    }
    gc_lock_release();
}

/* ------------------------------------------------------------------ */
/* Public runtime API called from generated LLVM IR.                    */
/* ------------------------------------------------------------------ */

void *__threadon_gc_alloc(uint64_t size, uint64_t kind) {
    (void)kind;
    gc_init_env();

    uint64_t total = (size + GC_HEADER_SIZE + 7) & ~((uint64_t)7);
    if (total < GC_HEADER_SIZE) total = GC_HEADER_SIZE;

    void *raw = malloc((size_t)total);
    if (raw == 0) abort();
    GCBlock *b = (GCBlock *)raw;

    gc_lock_acquire();
    b->magic = GC_MAGIC;
    b->size = total;
    b->work_next = 0;
    b->pad = 0;
    uint64_t collecting = __atomic_load_n(&gc_collecting, __ATOMIC_SEQ_CST);
    b->mark = collecting ? __atomic_load_n(&gc_epoch, __ATOMIC_SEQ_CST) : 0;
    b->next = gc_head;
    gc_head = (uint64_t)(uintptr_t)raw;
    uint64_t base = (uint64_t)(uintptr_t)raw;
    if (base < gc_min) gc_min = base;
    if (base + total > gc_max) gc_max = base + total;
    gc_lock_release();

    /* Publish a fresh root snapshot for the current generation even when no
       collection is running, so an explicit collect() can use it later. */
    gc_capture_stack();
    return (void *)((char *)raw + GC_HEADER_SIZE);
}

void __threadon_gc_barrier(uint64_t slot, uint64_t size) {
    if (!__atomic_load_n(&gc_collecting, __ATOMIC_SEQ_CST)) return;
    /* Scan the slot after the store. This works for scalars and for aggregate
       values (lists/dicts stored by value) without field descriptors. */
    for (uint64_t off = 0; off + 8 <= size; off += 8) {
        uint64_t v = gc_mask(*(volatile uint64_t *)(uintptr_t)(slot + off));
        if (gc_is_heap(v)) gc_mark_tree(v);
    }
}

void __threadon_gc_add_root(void *addr, uint64_t size) {
    gc_lock_acquire();
    if (gc_root_count + 1 < GC_MAX_ROOTS) {
        gc_roots[gc_root_count++] = (uint64_t)(uintptr_t)addr;
        gc_roots[gc_root_count++] = size;
    }
    gc_lock_release();
}

void __threadon_gc_thread_enter(void *sp) {
    gc_lock_acquire();
    uint64_t id = ++gc_thread_count;
    if (id <= GC_MAX_THREADS) {
        gc_my_id = id;
        gc_threads[id - 1].thread_id = (uint64_t)(uintptr_t)pthread_self();
        gc_threads[id - 1].stack_base = (uint64_t)(uintptr_t)sp;
        gc_threads[id - 1].snap_gen = 0;
        gc_threads[id - 1].snap_count = 0;
    }
    gc_lock_release();
}

void __threadon_gc_thread_exit(void) {
    if (gc_my_id != 0 && gc_my_id <= GC_MAX_THREADS) {
        gc_threads[gc_my_id - 1].stack_base = 0;
        gc_my_id = 0;
    }
}

void __threadon_gc_collect(void) {
    gc_init_env();
    uint64_t t0 = gc_stats ? gc_now_ns() : 0;
    __atomic_fetch_add(&gc_collections, 1, __ATOMIC_RELAXED);

    gc_lock_acquire();
    __atomic_store_n(&gc_collecting, 1, __ATOMIC_SEQ_CST);
    __atomic_fetch_add(&gc_epoch, 1, __ATOMIC_SEQ_CST);
    __atomic_fetch_add(&gc_snap_gen, 1, __ATOMIC_SEQ_CST);
    gc_lock_release();

    uint64_t m0 = gc_stats ? gc_now_ns() : 0;
    gc_capture_stack();
    gc_mark_roots();

    /* Second snapshot generation catches pointers stored into stack slots
       while the first marking pass was running. */
    gc_lock_acquire();
    __atomic_fetch_add(&gc_snap_gen, 1, __ATOMIC_SEQ_CST);
    gc_lock_release();
    gc_capture_stack();
    gc_mark_roots();
    if (gc_stats) gc_note_max(&gc_max_mark_ns, gc_now_ns() - m0);

    uint64_t s0 = gc_stats ? gc_now_ns() : 0;
    gc_sweep();
    if (gc_stats) {
        gc_note_max(&gc_max_sweep_ns, gc_now_ns() - s0);
        __atomic_fetch_add(&gc_sum_collector_ns, gc_now_ns() - t0, __ATOMIC_RELAXED);
    }

    gc_lock_acquire();
    __atomic_store_n(&gc_collecting, 0, __ATOMIC_SEQ_CST);
    gc_lock_release();
}

void __threadon_gc_shutdown(void) {
    if (gc_stats) {
        printf("[gc] collections=%llu snapshots=%llu "
               "snapshot_max=%.0fus snapshot_avg=%.0fus "
               "mark_max=%.0fus sweep_max=%.0fus collector_total=%.1fms\n",
               (unsigned long long)gc_collections,
               (unsigned long long)gc_snapshot_count,
               (double)gc_max_snapshot_ns / 1000.0,
               gc_snapshot_count ? (double)gc_sum_snapshot_ns / (double)gc_snapshot_count / 1000.0 : 0.0,
               (double)gc_max_mark_ns / 1000.0,
               (double)gc_max_sweep_ns / 1000.0,
               (double)gc_sum_collector_ns / 1000000.0);
    }
}
