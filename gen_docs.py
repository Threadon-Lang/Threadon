#!/usr/bin/env python3
"""Generate library docs pages and update navigation for the Threadon docs site."""
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOCS = ROOT.parent / "Threadon-Lang.github.io"

KEYWORDS = {"import", "from", "lazyimport", "lazyfrom", "def", "puredef", "return",
            "if", "elif", "else", "while", "for", "in", "break", "continue",
            "and", "or", "not", "True", "False", "None", "as", "class", "struct",
            "thread", "on", "comptime"}
TYPES = {"Int8", "Int16", "Int32", "Int64", "Int256", "UInt8", "UInt16", "UInt32",
         "UInt64", "UInt256", "Float16", "Float32", "Float64", "Bool", "String",
         "NoneType", "Int", "Float", "Number", "Builtin", "List", "Dict",
         "Vec2", "Vec3", "IntStack", "IntQueue",
         "StackPop", "QueuePop", "IntSet", "StringIntMap", "IntStringMap",
         "IntLookup", "StringLookup"}
TOKEN_RE = re.compile(
    r'(#[^\n]*|"(?:\\.|[^"\\])*"|\b[A-Za-z_][A-Za-z_0-9]*\b|\b\d+(?:\.\d+)?\b)'
)


def code(src: str) -> str:
    out, pos = [], 0
    for m in TOKEN_RE.finditer(src):
        out.append(html.escape(src[pos:m.start()]))
        tok = m.group(0)
        if tok.startswith("#"):
            cls = "tok-cm"
        elif tok.startswith('"'):
            cls = "tok-str"
        elif tok in KEYWORDS:
            cls = "tok-kw"
        elif tok in TYPES:
            cls = "tok-type"
        elif re.fullmatch(r"\d+(?:\.\d+)?", tok):
            cls = "tok-num"
        elif re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", tok):
            cls = "tok-fn"
        out.append(f'<span class="{cls}">{html.escape(tok)}</span>')
        pos = m.end()
    out.append(html.escape(src[pos:]))
    return "".join(out)


NAV_BEFORE = [
    ("index.html", "Home"), ("basics.html", "Basics"), ("strings.html", "Strings"),
    ("types.html", "Types"), ("variables.html", "Variables"), ("operators.html", "Operators"),
    ("casts.html", "Casts"), ("flow.html", "Flow"), ("functions.html", "Functions"),
    ("variadics.html", "Variadics"), ("comptime.html", "Comptime"),
    ("structs.html", "Structs"), ("unions.html", "Unions"), ("references.html", "References"),
    ("classes.html", "Classes"), ("builtins.html", "Builtins"), ("stdlib.html", "Std lib"),
    ("modules.html", "Imports"), ("projects.html", "Projects"),
    ("reference.html", "Reference"), ("cheatsheet.html", "Cheatsheet"),
    ("cookbook.html", "Cookbook"), ("testing.html", "Testing"),
    ("diagnostics.html", "Diagnostics"), ("faq.html", "FAQ"),
]
NAV_AFTER = [
    ("cli.html", "CLI"), ("performance.html", "Performance"),
    ("benchmarks.html", "Benchmarks"), ("debug.html", "Debug"),
    ("runtime.html", "Runtime checks"),
    ("exceptions.html", "Exceptions"), ("gc.html", "GC"),
    ("examples.html", "Examples"), ("limits.html", "Limits"),
    ("threads.html", "Threads"),
]


def nav(current: str) -> str:
    """Mount point for the shared navigation loaded from nav.html."""
    return (
        f'<div id="site-nav" data-current="{current}"></div>\n'
        '<script src="nav.js"></script>'
    )


def nav_fragment() -> str:
    """The one shared copy of the navigation bar."""
    lines = []
    for href, label in NAV_BEFORE:
        lines.append(f'    <a href="{href}">{label}</a>')
    lines.append('    <a href="libraries.html">Libraries</a>')
    for href, label in NAV_AFTER:
        lines.append(f'    <a href="{href}">{label}</a>')
    links = "\n".join(lines)
    return f'''<nav class="toc">
  <div class="wrap links">
{links}
  </div>
</nav>
'''


def nav_loader_js() -> str:
    library_pages = list(dict.fromkeys(
        [f"{lib['key']}.html" for lib in LIBS] + ["lib-strings.html"]
    ))
    pages_json = ", ".join(json.dumps(p) for p in library_pages)
    # The embedded copy is generated from the same source as nav.html, so the
    # full bar works from file:// too, where browsers block fetch().
    markup_json = json.dumps(nav_fragment())
    return f'''// Loads the shared navigation bar and marks the current page.
(function () {{
  const mount = document.getElementById("site-nav");
  if (!mount) return;

  const libraryPages = new Set([{pages_json}]);

  function render(markup) {{
    mount.innerHTML = markup;
    const fromUrl = window.location.pathname.split("/").pop() || "index.html";
    let current = mount.dataset.current || fromUrl;
    if (current === "libraries") current = "libraries.html";
    else if (!current.endsWith(".html")) current += ".html";
    const active = libraryPages.has(current) ? "libraries.html" : current;
    mount.querySelectorAll("a[href]").forEach(function (link) {{
      if (link.getAttribute("href") === active) {{
        link.classList.add("here");
        link.setAttribute("aria-current", "page");
      }}
    }});
  }}

  render({markup_json});

  if (typeof fetch === "function") {{
    fetch("nav.html")
      .then(function (response) {{
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.text();
      }})
      .then(render)
      .catch(function (error) {{
        console.warn("Keeping embedded navigation; could not load nav.html:", error);
      }});
  }}
}})();
'''


def page(title, description, crumb, h1, tag, current, body, back="libraries.html", back_label="Libraries", next_href="libraries.html", next_label="All libraries"):
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Threadon</title>
<meta name="description" content="{description}">
<link rel="stylesheet" href="style.css">
</head>
<body>

<header class="site">
  <div class="wrap">
    <p class="crumb"><a href="index.html" style="color:#8fd8bd">Threadon</a> / {crumb}</p>
    <h1>{h1}</h1>
    <p class="tag">{tag}</p>
  </div>
</header>

{nav(current)}

<main class="wrap">

{body}

<p class="pagenav">
  <a href="{back}">&larr; Back: {back_label}</a>
  <a href="{next_href}">{next_label} &rarr;</a>
</p>

</main>

<footer class="site">
  <div class="wrap">
    <p>Threadon 3.0 &middot; If something here disagrees with the compiler, the compiler wins.</p>
  </div>
</footer>

</body>
</html>
'''


def sec(anchor, title, content):
    return f'<section id="{anchor}">\n  <h2>{title}</h2>\n{content}\n</section>'


def table(headers, rows):
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "\n".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table>\n<tr>{head}</tr>\n{body}\n</table>"


def pre(src):
    return f"<pre><code>{code(src)}</code></pre>"


def out(text):
    return f'<div class="out">{html.escape(text)}</div>'


def bullets(items):
    return "<ul>\n" + "\n".join(f"<li>{i}</li>" for i in items) + "\n</ul>"


def note(text):
    return f'<div class="note">{text}</div>'


LIBS = []

LIBS.append(dict(
    key="math", title="Math", tag="numbers, roots and prime tests",
    desc="Integer and float math helpers: powers, factorials, gcd/lcm, rounding, square roots and constants.",
    intro="<p>Pure-Threadon math helpers. No external toolchain is needed. Integer and float functions have different names because Threadon has no overloading.</p>",
    example='''import math

def main() -> Int32
    print(math.pow_int(2, 10))
    print(math.gcd(48, 18))
    print(math.sqrt_f(81.0))
    print(math.factorial(10))
    return 0''',
    output="1024\n6\n9.000000\n3628800",
    rows=[
        ("<code>abs(n)</code>, <code>iabs(n)</code>", "<code>Int32</code> absolute value; both are pure"),
        ("<code>pow_int(base, exp)</code>", "integer power by repeated squaring; negative exponent gives <code>0</code>"),
        ("<code>factorial(n)</code>", "<code>n!</code> as an <code>Int64</code>"),
        ("<code>gcd(a, b)</code>, <code>lcm(a, b)</code>", "greatest common divisor / least common multiple"),
        ("<code>sign(n)</code>, <code>is_prime(n)</code>, <code>integer_sqrt(n)</code>", "sign, trial-division primality, integer square root"),
        ("<code>trunc_f(x)</code>, <code>floor_f(x)</code>, <code>ceil_f(x)</code>, <code>round_f(x)</code>", "rounding to an <code>Int64</code>"),
        ("<code>sqrt_f(x)</code>, <code>hypot_f(a, b)</code>", "square root and hypotenuse"),
        ("<code>pi()</code>, <code>e()</code>", "constants as <code>Float64</code>"),
        ("<code>to_radians(d)</code>, <code>to_degrees(r)</code>", "angle conversion"),
        ("<code>clamp_f(x, lo, hi)</code>, <code>lerp_f(a, b, t)</code>", "range limit and interpolation"),
    ],
    notes=[
        "<code>round_f</code> rounds half up for positive values; negative halves round towards zero.",
        "<code>sqrt_f</code> uses a fixed number of Newton iterations and returns <code>0.0</code> for non-positive input.",
        "Integer arithmetic wraps in Threadon, so <code>pow_int</code> and <code>factorial</code> can overflow silently.",
    ],
))

LIBS.append(dict(
    key="lib-strings", title="Strings", tag="case, search, split and pad",
    desc="String helpers for case conversion, trimming, searching, splitting, joining, replacing and padding.",
    intro="<p>The language gives strings concatenation, indexing, slicing and comparison. This module adds the everyday helpers. Strings are immutable, so every function returns a new value. Indexes count bytes, just like <code>len(s)</code> and <code>s[i]</code>.</p>",
    example='''import strings

def main() -> Int32
    s: String = strings.trim("  Hello, World!  ")
    print(strings.upper(s))
    parts: List[String] = strings.split(s, ", ")
    print(strings.join(parts, " | "))
    return 0''',
    output="HELLO, WORLD!\nHello | World!",
    rows=[
        ("<code>length(s)</code>, <code>ord(c)</code>", "length as <code>Int64</code>; byte value of a one-byte string"),
        ("<code>upper(s)</code>, <code>lower(s)</code>", "ASCII case conversion"),
        ("<code>trim(s)</code>, <code>ltrim(s)</code>, <code>rtrim(s)</code>", "remove surrounding whitespace"),
        ("<code>index_of(s, needle)</code>, <code>last_index_of(...)</code>", "match position, or <code>-1</code>"),
        ("<code>contains(s, needle)</code>, <code>count(s, needle)</code>", "membership and match count"),
        ("<code>starts_with(s, prefix)</code>, <code>ends_with(s, suffix)</code>", "affix tests"),
        ("<code>replace(s, old, new)</code>", "replace every occurrence"),
        ("<code>split(s, sep)</code>, <code>join(parts, sep)</code>", "split into / join from a <code>List[String]</code>"),
        ("<code>reverse(s)</code>, <code>repeat(s, n)</code>", "reverse or repeat text"),
        ("<code>pad_left(s, width, pad)</code>, <code>pad_right(...)</code>", "pad to a minimum width"),
        ("<code>is_digit(s)</code>, <code>is_alpha(s)</code>, <code>is_alnum(s)</code>", "whole-string character tests"),
    ],
    notes=[
        "Case conversion is ASCII only; Threadon strings are byte strings.",
        "<code>split(s, \"\")</code> returns a one-element list containing <code>s</code>.",
        "<code>ord(c)</code> returns <code>-1</code> for an empty or multi-byte string.",
    ],
))

LIBS.append(dict(
    key="lists", title="Lists", tag="search, sort and aggregate lists",
    desc="Helpers for List[Int32] and List[String]: sums, extremes, searching, sorting, reversing and joining.",
    intro="<p>Threadon lists support <code>append</code>, <code>pop</code>, <code>insert</code>, <code>remove</code> and indexing, but not search or sort. There is no overloading, so each helper has an <code>_int</code> or <code>_str</code> suffix. Lists are passed by value; functions here return new lists and leave their inputs alone.</p>",
    example='''import lists

def main() -> Int32
    xs: List[Int32] = [5, 1, 4, 1, 3]
    print(lists.sort_int(xs))
    print(lists.sum_int(xs))
    print(lists.unique_int(xs))
    return 0''',
    output="[1, 1, 3, 4, 5]\n14\n[5, 1, 4, 3]",
    rows=[
        ("<code>range_list(n)</code>", "<code>[0, 1, ..., n-1]</code>"),
        ("<code>sum_int(xs)</code>", "sum as <code>Int64</code>"),
        ("<code>min_int(xs)</code>, <code>max_int(xs)</code>", "extremes, or <code>0</code> for an empty list"),
        ("<code>contains_int(xs, v)</code>, <code>index_int(xs, v)</code>", "search; <code>index_int</code> returns <code>-1</code> if absent"),
        ("<code>count_int(xs, v)</code>", "number of matches"),
        ("<code>sort_int(xs)</code>, <code>sort_str(xs)</code>", "new ascending list (stable insertion sort)"),
        ("<code>reverse_int(xs)</code>, <code>reverse_str(xs)</code>", "new reversed list"),
        ("<code>unique_int(xs)</code>", "first copy of each value"),
        ("<code>extend_int(xs, more)</code>", "new list with <code>more</code> appended"),
        ("<code>join_int(xs, sep)</code>", "text such as <code>1-2-3</code>"),
        ("<code>contains_str</code>, <code>index_str</code>, <code>count_str</code>", "string-list equivalents"),
    ],
    notes=[
        "Passing a list to a function copies it. A helper cannot resize the caller's list.",
        "Sorting and reversing allocate a new list; large lists cost time and memory.",
    ],
))

LIBS.append(dict(
    key="random", title="Random", tag="deterministic pseudo-random numbers",
    desc="A reproducible linear-congruential generator: seeds, integer and float draws, dice, choices and shuffles.",
    intro="<p>A small pseudo-random generator written entirely in Threadon. It uses a 31-bit linear congruential generator. The same seed always produces the same stream, which makes simulations and tests reproducible. It is not cryptographically secure and reads no entropy from the operating system.</p>",
    example='''import random

def main() -> Int32
    random.seed(42)
    print(random.randint(1, 6))
    print(random.rand_float())
    return 0''',
    output="4\n0.519819",
    rows=[
        ("<code>seed(value)</code>", "reset the module-level state"),
        ("<code>next_int()</code>", "next <code>Int64</code> in <code>[0, 2**31)</code>"),
        ("<code>randint(lo, hi)</code>", "inclusive <code>Int32</code> range; reversed bounds are swapped"),
        ("<code>rand_float()</code>", "<code>Float64</code> in <code>[0, 1)</code>"),
        ("<code>chance(percent)</code>", "true with the given probability"),
        ("<code>choice_int(xs)</code>", "one element of a <code>List[Int32]</code>, or <code>0</code> when empty"),
        ("<code>shuffle_int(xs)</code>", "Fisher-Yates shuffle of a copy of the list"),
        ("<code>dice(sides)</code>", "roll from <code>1</code> to <code>sides</code>"),
    ],
    notes=[
        "The state is module-level, so all importers share one stream.",
        "The default seed is <code>42</code>; call <code>seed()</code> if you need a different sequence.",
        "Do not use this module for keys, tokens or anything security-sensitive.",
    ],
))

LIBS.append(dict(
    key="bitops", title="Bitops", tag="bitwise operations for UInt32",
    desc="AND, OR, XOR, NOT, shifts and bit counting for UInt32, built from division and modulo.",
    intro="<p>Threadon has no <code>&amp;</code>, <code>|</code>, <code>~</code>, <code>&lt;&lt;</code> or <code>&gt;&gt;</code> operators. This module implements them for <code>UInt32</code> by peeling bits off with division and modulo. The results are correct but slower than hardware instructions.</p>",
    example='''import bitops

def main() -> Int32
    print(bitops.band(UInt32(12), UInt32(10)))
    print(bitops.shl(UInt32(1), 5))
    print(bitops.bnot(UInt32(0)))
    return 0''',
    output="8\n32\n4294967295",
    rows=[
        ("<code>band(a, b)</code>, <code>bor(a, b)</code>, <code>bxor(a, b)</code>", "bitwise AND, OR, XOR over 32 bits"),
        ("<code>bnot(a)</code>", "bitwise NOT"),
        ("<code>shl(a, n)</code>, <code>shr(a, n)</code>", "shift left/right by <code>n</code> bits"),
        ("<code>pow2(n)</code>, <code>full()</code>", "power of two; all bits set"),
        ("<code>popcount(a)</code>", "number of set bits, as <code>Int32</code>"),
        ("<code>bit(a, n)</code>", "is bit <code>n</code> set?"),
        ("<code>set_bit</code>, <code>clear_bit</code>, <code>toggle_bit</code>", "return a new <code>UInt32</code> with one bit changed"),
        ("<code>trailing_zeros(a)</code>", "count of trailing zero bits (<code>32</code> for zero)"),
    ],
    notes=[
        "All arguments and results are <code>UInt32</code>; write <code>UInt32(...)</code> explicitly.",
        "Shifts wrap: bits shifted past the top are discarded.",
    ],
))

LIBS.append(dict(
    key="stats", title="Stats", tag="descriptive statistics",
    desc="Means, medians, variance and standard deviation for integer and float lists.",
    intro="<p>Descriptive statistics built on the <code>lists</code> and <code>math</code> modules. Variance is the population variance (divide by <em>N</em>, not <em>N-1</em>). Every function returns zero for an empty list.</p>",
    example='''import stats

def main() -> Int32
    xs: List[Int32] = [2, 4, 4, 4, 5, 5, 7, 9]
    print(stats.mean_int(xs))
    print(stats.stddev_int(xs))
    return 0''',
    output="5.000000\n2.000000",
    rows=[
        ("<code>mean_int(xs)</code>, <code>mean_float(xs)</code>", "arithmetic mean"),
        ("<code>median_int(xs)</code>", "median; average of the two middle values when even"),
        ("<code>variance_int(xs)</code>, <code>variance_float(xs)</code>", "population variance"),
        ("<code>stddev_int(xs)</code>, <code>stddev_float(xs)</code>", "square root of the variance"),
        ("<code>range_int(xs)</code>", "largest minus smallest, as <code>Int32</code>"),
        ("<code>sum_float(xs)</code>, <code>min_float(xs)</code>, <code>max_float(xs)</code>", "sum and extremes for float lists"),
    ],
    notes=[
        "<code>median_int</code> sorts a copy, so the input list is unchanged.",
        "Results are <code>Float64</code>, except <code>range_int</code> which is <code>Int32</code>.",
    ],
))

LIBS.append(dict(
    key="csv", title="CSV", tag="comma-separated values in strings",
    desc="Parse and encode CSV rows held in strings, with quoted fields and escaped quotes.",
    intro="<p>A tiny RFC-4180-style CSV reader and writer. Threadon has no file I/O, so these functions work on strings from <code>input()</code> or literals. Fields are comma-separated; fields containing a comma, quote or newline are wrapped in quotes, and quotes inside them are doubled.</p>",
    example='''import csv

def main() -> Int32
    fields: List[String] = csv.parse_line("\\"Doe, Jane\\",10")
    print(fields[0])
    print(csv.encode_line(fields))
    return 0''',
    output="Doe, Jane\n\"Doe, Jane\",10",
    rows=[
        ("<code>parse_line(line)</code>", "split one line into a <code>List[String]</code>"),
        ("<code>encode_field(s)</code>", "quote one field only when needed"),
        ("<code>encode_line(fields)</code>", "join encoded fields with commas"),
        ("<code>split_lines(text)</code>", "split a multiline string on <code>\\n</code>"),
        ("<code>get_field(line, index)</code>", "one field, or <code>\"\"</code> when out of range"),
    ],
    notes=[
        "A trailing newline in <code>split_lines</code> does not create an extra empty row.",
        "Quoted fields may contain commas and doubled quotes; unquoted fields may not.",
    ],
))

LIBS.append(dict(
    key="path", title="Path", tag="POSIX path string helpers",
    desc="Basename, dirname, extension, join and normalize for path strings — no filesystem access.",
    intro="<p>String utilities for POSIX-style paths, built on the <code>strings</code> module. They never touch the disk and never check whether a path exists.</p>",
    example='''import path

def main() -> Int32
    p: String = "/home/user/notes.txt"
    print(path.basename(p))
    print(path.extension(p))
    print(path.join("a", "b"))
    return 0''',
    output="notes.txt\n.txt\na/b",
    rows=[
        ("<code>basename(p)</code>", "last component"),
        ("<code>dirname(p)</code>", "everything before the last slash; <code>.</code> when there is none"),
        ("<code>extension(p)</code>", "suffix including the dot, or <code>\"\"</code>"),
        ("<code>stem(p)</code>", "file name without extension"),
        ("<code>with_extension(p, ext)</code>", "replace the extension"),
        ("<code>join(a, b)</code>", "join with one slash; an absolute <code>b</code> replaces <code>a</code>"),
        ("<code>is_absolute(p)</code>", "does <code>p</code> start with <code>/</code>?"),
        ("<code>normalize(p)</code>", "collapse repeated slashes and drop a trailing slash"),
    ],
    notes=[
        "Use forward slashes; Windows drive letters and backslashes are not handled.",
        "<code>normalize</code> does not resolve <code>..</code> segments.",
    ],
))

LIBS.append(dict(
    key="hash", title="Hash", tag="non-cryptographic hashes and checksums",
    desc="Deterministic polynomial and djb2 hashes for strings, integers and integer lists.",
    intro="<p>Simple, deterministic hashes for strings and integers. The arithmetic stays in <code>Int64</code> by reducing modulo the prime 1,000,000,007. They are useful for buckets, quick comparisons and checksums, but they are not cryptographic.</p>",
    example='''import hash

def main() -> Int32
    print(hash.string_hash("hello"))
    print(hash.checksum16("hello"))
    return 0''',
    output="299566379\n1323",
    rows=[
        ("<code>string_hash(s)</code>", "polynomial rolling hash, multiplier 31, starting at 7"),
        ("<code>djb2(s)</code>", "djb2-style hash, multiplier 33"),
        ("<code>checksum16(s)</code>", "16-bit reduction of <code>string_hash</code>"),
        ("<code>hash_int(x)</code>", "hash of one <code>Int32</code>"),
        ("<code>hash_pair(a, b)</code>", "order-sensitive hash of two integers"),
        ("<code>hash_list_int(xs)</code>", "order-sensitive hash of an integer list"),
    ],
    notes=[
        "Equal inputs always hash equally, but collisions are possible and easy to force.",
        "Character codes come from <code>strings.ord</code>; only byte strings are supported.",
    ],
))

LIBS.append(dict(
    key="vector", title="Vector", tag="2D and 3D vectors",
    desc="Vec2 and Vec3 structs with addition, dot and cross products, lengths, normalization and distances.",
    intro="<p>Two- and three-dimensional vectors of <code>Float64</code>. <code>Vec2</code> and <code>Vec3</code> are structs, so they use named field initializers and value semantics. Structs have no methods in Threadon, so operations are plain functions that return new vectors.</p>",
    example='''from vector import Vec2, add2, length2

def main() -> Int32
    a: Vec2 = Vec2(x=3.0, y=4.0)
    b: Vec2 = add2(a, Vec2(x=1.0, y=2.0))
    print(length2(a))
    print(b.x)
    return 0''',
    output="5.000000\n4.000000",
    rows=[
        ("<code>vec2(x, y)</code>, <code>vec3(x, y, z)</code>", "constructor functions"),
        ("<code>add2</code>, <code>sub2</code>, <code>scale2</code>", "2D sum, difference, scalar multiple"),
        ("<code>dot2</code>, <code>length2</code>, <code>normalize2</code>, <code>distance2</code>", "2D products and measures"),
        ("<code>add3</code>, <code>sub3</code>, <code>scale3</code>", "3D sum, difference, scalar multiple"),
        ("<code>dot3</code>, <code>cross3</code>, <code>length3</code>, <code>normalize3</code>, <code>distance3</code>", "3D products and measures"),
    ],
    notes=[
        "Normalizing the zero vector returns the zero vector.",
        "Built on <code>math.sqrt_f</code>; results are approximate like any float.",
    ],
))

LIBS.append(dict(
    key="containers", title="Containers", tag="functional stacks, queues and maps",
    desc="Functional stacks, queues and Dict-backed maps with String keys and values, built for Threadon's value semantics.",
    intro="<p>Stacks and queues hold <code>Int32</code> in a list; the maps add <code>Dict</code>-backed key/value storage with <code>String</code> keys, <code>Int32</code> values, and the reverse. Threadon passes classes by value and a method call gets a copy of <code>self</code>, so methods either only <strong>read</strong> the container or return a <strong>new</strong> one. Reassign the result. The old module-style functions are still available as aliases.</p>",
    example='''import containers

def main() -> Int32
    ages: containers.StringIntMap = containers.empty_string_int_map()
    ages = ages.put("ann", 30)
    ages = ages.put("bob", 40)
    found: containers.IntLookup = ages.get("bob")
    print(found.found)
    print(found.value)
    print(ages.size())
    return 0''',
    output="True\n40\n2",
    rows=[
        ("<code>empty_stack()</code>, <code>empty_queue()</code>", "new empty containers"),
        ("<code>s.size()</code>, <code>q.size()</code>", "number of items"),
        ("<code>s.is_empty()</code>, <code>q.is_empty()</code>", "emptiness test"),
        ("<code>s.peek()</code>, <code>q.front()</code>", "next value, or <code>0</code> when empty"),
        ("<code>s.pushed(v)</code>, <code>q.enqueued(v)</code>", "new container with the value added"),
        ("<code>pop(s)</code>, <code>dequeue(q)</code>", "a <code>StackPop</code> / <code>QueuePop</code> with <code>value</code> and the updated container"),
        ("<code>s.contains(v)</code>, <code>q.contains(v)</code>", "membership test"),
        ("<code>s.to_list()</code>, <code>q.to_list()</code>", "copy in bottom-to-top / oldest-to-newest order"),
        ("<code>empty_string_int_map()</code>, <code>empty_int_string_map()</code>", "new empty maps"),
        ("<code>m.put(k, v)</code>", "new map with a key set to a value"),
        ("<code>m.get(k)</code>", "<code>IntLookup</code> / <code>StringLookup</code> with <code>found</code> and <code>value</code>"),
        ("<code>m.has(k)</code>", "membership test"),
        ("<code>m.remove(k)</code>", "new map without a key"),
        ("<code>m.size()</code>", "number of entries"),
        ("<code>m.keys()</code>", "list of keys"),
    ],
    notes=[
        "Stacks are LIFO; queues are FIFO. Popping an empty one returns <code>0</code> and the same container.",
        "A missing key gives <code>found=False</code> and the zero value (<code>0</code> or <code>\"\"</code>), never a <code>KeyError</code>.",
        "Put replaces an existing value; removing a missing key returns the same map.",
        "Every operation copies the underlying list or dict, so these are meant for small collections.",
        "The free functions <code>queue_size(q)</code>, <code>push(s, v)</code>, <code>string_int_put(m, k, v)</code> and friends still work; they simply call these methods.",
    ],
))

LIBS.append(dict(
    key="intset", title="IntSet", tag="a set of Int32 values",
    desc="A functional set with add, remove, union, intersection and difference.",
    intro="<p>A set of <code>Int32</code> values backed by a list and wrapped in an <code>IntSet</code> class. Like <a href=\"containers.html\">Containers</a>, it uses a functional API: every operation returns a new set and leaves the input untouched.</p>",
    example='''import intset

def main() -> Int32
    a: intset.IntSet = intset.from_list([1, 2, 3])
    b: intset.IntSet = intset.from_list([3, 4])
    print(intset.size(intset.union(a, b)))
    print(intset.contains(a, 2))
    return 0''',
    output="4\nTrue",
    rows=[
        ("<code>empty_set()</code>", "a new empty set"),
        ("<code>from_list(xs)</code>", "set of the distinct values in an integer list"),
        ("<code>to_list(s)</code>", "values as a <code>List[Int32]</code>, in insertion order"),
        ("<code>contains(s, v)</code>, <code>size(s)</code>", "membership and size"),
        ("<code>add(s, v)</code>, <code>remove(s, v)</code>", "new sets with the value added or removed"),
        ("<code>union(a, b)</code>, <code>intersection(a, b)</code>, <code>difference(a, b)</code>", "new sets from two sets"),
    ],
    notes=[
        "There is only an <code>Int32</code> set; Threadon has no overloading or user-defined generics.",
        "Membership is a linear scan, so large sets are slow.",
    ],
))

LIBS.append(dict(
    key="format", title="Format", tag="numbers as text",
    desc="Hex and binary strings, zero padding, fixed decimals, percentages and thousands separators.",
    intro="<p>Threadon prints floats with six decimals and has no <code>printf</code>-style formatting. This module adds hex and binary strings, zero padding, fixed-decimal rendering and thousands separators. Built on <code>strings</code> and <code>math</code>.</p>",
    example='''import format

def main() -> Int32
    print(format.hex32(UInt32(255)))
    print(format.fixed(3.14159, 2))
    print(format.commas(1234567))
    return 0''',
    output="ff\n3.14\n1,234,567",
    rows=[
        ("<code>hex32(x)</code>, <code>bin32(x)</code>", "lowercase hex / binary text for a <code>UInt32</code>"),
        ("<code>pad_int(v, width, pad)</code>, <code>pad_float(v, width, pad)</code>", "pad to a minimum width"),
        ("<code>fixed(x, decimals)</code>", "float with a chosen number of decimals"),
        ("<code>percent(x, decimals)</code>", "<code>x * 100</code> with a percent sign"),
        ("<code>commas(n)</code>", "integer with thousands separators"),
    ],
    notes=[
        "<code>fixed</code> rounds half up; negative halves round towards zero, following <code>math.round_f</code>.",
        "Padding uses the first byte of the <code>pad</code> string.",
    ],
))


LIBS.append(dict(
    key="base64", title="Base64", tag="encode bytes as ASCII",
    desc="RFC 4648 base64 encoding and decoding for strings and byte lists, written in pure Threadon.",
    intro="<p>Base64 turns bytes into printable ASCII. Threadon strings are byte strings, so this module works on one-byte characters and on <code>List[Int32]</code> values in the range 0..255. Encoding adds <code>=</code> padding; decoding ignores whitespace and stops at the first <code>=</code>.</p>",
    example='''import base64

def main() -> Int32
    print(base64.encode("hello") == "aGVsbG8=")
    print(base64.decode("aGVsbG8=") == "hello")
    return 0''',
    output="True\nTrue",
    rows=[
        ("<code>encode(s)</code>", "base64 text for a String"),
        ("<code>decode(s)</code>", "decoded String; invalid characters become byte 0"),
        ("<code>encode_bytes(xs)</code>", "base64 text for a <code>List[Int32]</code> of bytes"),
        ("<code>decode_bytes(s)</code>", "bytes as a <code>List[Int32]</code>"),
    ],
    notes=[
        "Use the byte helpers when the data contains zero bytes: <code>len()</code> stops at the first NUL in a String.",
        "This is encoding, not encryption: anybody can decode it.",
    ],
))

LIBS.append(dict(
    key="url", title="URL", tag="percent encoding and query strings",
    desc="Percent-encode strings, decode them again, and build or parse application/x-www-form-urlencoded query strings.",
    intro="<p>URLs and form bodies need characters such as spaces and ampersands escaped. This module provides <code>quote</code>/<code>unquote</code> for single values and <code>encode_form</code>/<code>parse_query</code> for dictionaries of text values.</p>",
    example='''import url

def main() -> Int32
    print(url.quote("a b&c") == "a%20b%26c")
    print(url.unquote("a+b%2Fc") == "a+b/c")
    return 0''',
    output="True\nTrue",
    rows=[
        ("<code>quote(s)</code>", "percent-encode all but <code>A-Za-z0-9-._~</code>"),
        ("<code>unquote(s)</code>", "decode <code>%HH</code>; <code>+</code> stays a plus"),
        ("<code>encode_form(d)</code>", "query string from a <code>Dict[String, String]</code>"),
        ("<code>parse_query(q)</code>", "query string to a <code>Dict[String, String]</code>"),
    ],
    notes=[
        "Malformed percent escapes are kept literally instead of raising an error.",
        "<code>encode_form</code> uses the dictionary's <code>dict_key</code> order, not sorted order.",
    ],
))

LIBS.append(dict(
    key="checksum", title="Checksum", tag="small non-cryptographic digests",
    desc="FNV-1a, Adler-32 and CRC-8 checksums for strings and byte lists, with deterministic integer results.",
    intro="<p>Checksums detect accidental changes to text or bytes. These are small, dependency-free implementations that stay in safe integer ranges by masking and reducing modulo fixed constants. They are <em>not</em> message authentication codes.</p>",
    example='''import checksum

def main() -> Int32
    print(checksum.fnv1a("hello") == checksum.fnv1a("hello"))
    print(checksum.adler32("hello") > 0)
    return 0''',
    output="True\nTrue",
    rows=[
        ("<code>fnv1a(s)</code>", "32-bit FNV-1a as an <code>Int64</code>"),
        ("<code>adler32(s)</code>", "Adler-32 reduced modulo 65521"),
        ("<code>crc8(s)</code>", "8-bit CRC with polynomial <code>0x07</code>"),
        ("<code>checksum_bytes(xs)</code>", "FNV-1a over a byte <code>List[Int32]</code>"),
    ],
    notes=[
        "Different inputs can collide; these functions are for quick sanity checks, not security.",
        "There is no bitwise XOR operator in Threadon, so the implementations use division and modulo instead.",
    ],
))

LIBS.append(dict(
    key="complex", title="Complex", tag="complex-number arithmetic",
    desc="A Complex struct plus add, subtract, multiply, scale, conjugate, magnitude and text conversion helpers.",
    intro="<p>Threadon has no complex-number type, but a struct of two <code>Float64</code> fields and a set of functions gets you most of the way. The functions return new values, so they compose naturally.</p>",
    example='''import complex

def main() -> Int32
    z: complex.Complex = complex.make(3.0, 4.0)
    print(complex.norm(z) == 25.0)
    w: complex.Complex = complex.mul(z, z)
    print(complex.norm(w) == 625.0)
    return 0''',
    output="True\nTrue",
    rows=[
        ("<code>make(re, im)</code>", "build a <code>Complex</code>"),
        ("<code>add(a, b)</code>, <code>sub(a, b)</code>", "sum and difference"),
        ("<code>mul(a, b)</code>, <code>scale(a, k)</code>", "product and scalar multiple"),
        ("<code>conj(a)</code>", "complex conjugate"),
        ("<code>norm(a)</code>, <code>abs(a)</code>", "squared magnitude and magnitude"),
        ("<code>to_string(a)</code>", "human-readable <code>re+imi</code> text"),
    ],
    notes=[
        "There is no operator overloading here: use the functions instead of <code>+</code> and <code>*</code>.",
        "<code>to_string</code> trims the language's fixed six-decimal float output to one decimal.",
    ],
))

LIBS.append(dict(
    key="fraction", title="Fraction", tag="exact rational arithmetic",
    desc="A Fraction struct that reduces and normalises results, with the four arithmetic operations and float/text conversion.",
    intro="<p>Fractions keep arithmetic exact by storing a numerator and denominator and reducing them with the greatest common divisor. The denominator is always positive, and a zero denominator is normalised to one.</p>",
    example='''import fraction

def main() -> Int32
    a: fraction.Fraction = fraction.make(1, 2)
    b: fraction.Fraction = fraction.make(1, 3)
    print(fraction.to_string(fraction.add(a, b)) == "5/6")
    return 0''',
    output="True",
    rows=[
        ("<code>make(n, d)</code>", "normalised fraction; <code>d == 0</code> becomes <code>1</code>"),
        ("<code>add(a, b)</code>, <code>sub(a, b)</code>", "sum and difference"),
        ("<code>mul(a, b)</code>, <code>div(a, b)</code>", "product and quotient"),
        ("<code>to_float(a)</code>", "approximate <code>Float64</code> value"),
        ("<code>to_string(a)</code>", "<code>n/d</code>, or just <code>n</code> for whole numbers"),
    ],
    notes=[
        "Arithmetic uses <code>Int64</code> and can overflow for large operands; keep values modest.",
        "Division by a zero fraction returns <code>0/1</code>, since an invalid denominator cannot be represented.",
    ],
))

LIBS.append(dict(
    key="heap", title="Heap", tag="functional min-heap and heapsort",
    desc="A binary min-heap over Int32 values with push, pop, peek and an ascending heapsort. Every operation returns a new value.",
    intro="<p>A heap gives fast access to the smallest element without sorting the whole collection. This implementation stores the heap in a flat <code>List[Int32]</code> and returns a new <code>Heap</code> after each change, matching Threadon's value semantics.</p>",
    example='''import heap

def main() -> Int32
    out: List[Int32] = heap.sort([3, 1, 2])
    print(out[0] == 1 and out[2] == 3)
    return 0''',
    output="True",
    rows=[
        ("<code>empty()</code>", "a new empty heap"),
        ("<code>from_list(xs)</code>", "heap containing every value in a list"),
        ("<code>size(h)</code>, <code>peek(h)</code>", "item count and smallest value (<code>0</code> when empty)"),
        ("<code>push(h, v)</code>", "new heap with <code>v</code> added"),
        ("<code>pop(h)</code>", "new heap without the smallest value"),
        ("<code>sort(xs)</code>", "ascending list via heapsort"),
    ],
    notes=[
        "To read the value you are about to remove, call <code>peek(h)</code> before <code>pop(h)</code>.",
        "Popping an empty heap returns it unchanged.",
    ],
))

LIBS.append(dict(
    key="strset", title="String set", tag="sets of strings",
    desc="A functional set of String values with add, remove, membership and the usual union, intersection and difference operations.",
    intro="<p>The <a href=\"intset.html\">intset</a> module covers integers; this one does the same job for strings. A <code>StringSet</code> keeps insertion order and all operations return a new set, leaving their arguments untouched.</p>",
    example='''import strset

def main() -> Int32
    s: strset.StringSet = strset.from_list(["a", "b", "a"])
    print(strset.size(s) == 2 and strset.contains(s, "b"))
    return 0''',
    output="True",
    rows=[
        ("<code>empty_set()</code>", "a new empty set"),
        ("<code>from_list(xs)</code>", "set of the distinct strings in a list"),
        ("<code>to_list(s)</code>, <code>size(s)</code>", "values in insertion order, and item count"),
        ("<code>contains(s, value)</code>", "membership test"),
        ("<code>add(s, value)</code>, <code>remove(s, value)</code>", "new sets with the value added or removed"),
        ("<code>union(a, b)</code>, <code>intersection(a, b)</code>, <code>difference(a, b)</code>", "set operations, always returning a new set"),
    ],
    notes=[
        "Comparison is byte-for-byte: <code>\"A\"</code> and <code>\"a\"</code> are different values.",
        "Classes and lists have value semantics in Threadon, so a mutating method would not update the caller's set; functions are used instead.",
    ],
))

LIBS.append(dict(
    key="date", title="Date", tag="Gregorian calendar arithmetic",
    desc="Leap years, month lengths, civil-date conversion, weekdays and ISO date strings, all computed without a clock.",
    intro="<p>Dates are surprisingly fiddly. This module uses the standard civil-calendar algorithms to convert between <code>YYYY-MM-DD</code> strings and a count of days since 1970-01-01, then builds weekdays and date arithmetic on top. Years must be 1 or greater.</p>",
    example='''import date

def main() -> Int32
    print(date.is_leap(2000) and not date.is_leap(1900))
    print(date.add_days("2024-02-28", 1) == "2024-02-29")
    return 0''',
    output="True\nTrue",
    rows=[
        ("<code>is_leap(year)</code>", "is it a Gregorian leap year?"),
        ("<code>days_in_month(year, month)</code>", "28..31, or <code>0</code> for a bad month"),
        ("<code>days_from_civil(y, m, d)</code>", "days since 1970-01-01 as <code>Int64</code>"),
        ("<code>civil_from_days(z)</code>", "ISO <code>YYYY-MM-DD</code> text"),
        ("<code>weekday(y, m, d)</code>", "0 = Monday, 6 = Sunday"),
        ("<code>add_days(s, delta)</code>, <code>days_between(a, b)</code>", "shift a date and measure a gap"),
    ],
    notes=[
        "There is no clock or timezone here; use the native <a href=\"libraries.html\">time</a> module if you need real time.",
        "Invalid ISO strings in <code>add_days</code> are treated as 1970-01-01.",
    ],
))

LIBS.append(dict(
    key="units", title="Units", tag="conversions and formatting",
    desc="Distance, mass, temperature and data-size conversions, plus a small duration formatter.",
    intro="<p>A collection of the conversions that come up most often: kilometres and miles, kilograms and pounds, Celsius and Fahrenheit, mebibytes and bytes, and seconds to <code>H:MM:SS</code>. Everything is plain arithmetic, with no lookup tables or external calls.</p>",
    example='''import units

def main() -> Int32
    print(units.seconds_to_hms(3661) == "1:01:01")
    print(units.c_to_f(100.0) == 212.0)
    return 0''',
    output="True\nTrue",
    rows=[
        ("<code>km_to_miles(v)</code>, <code>miles_to_km(v)</code>", "distance conversions"),
        ("<code>cm_to_inches(v)</code>", "centimetres to inches"),
        ("<code>kg_to_pounds(v)</code>, <code>pounds_to_kg(v)</code>", "mass conversions"),
        ("<code>c_to_f(v)</code>, <code>f_to_c(v)</code>", "temperature conversions"),
        ("<code>seconds_to_hms(n)</code>", "duration as <code>H:MM:SS</code>"),
        ("<code>mib_to_bytes(v)</code>, <code>bytes_to_mib(n)</code>", "binary data-size conversions"),
    ],
    notes=[
        "<code>MiB</code> means 1,048,576 bytes, not one million bytes.",
        "Results are <code>Float64</code> unless the signature says otherwise; rounding is left to the caller.",
    ],
))

LIBS.append(dict(
    key="color", title="Color", tag="RGB values and hex colors",
    desc="An RGB struct with clamping, hex parsing and formatting, brightness, mixing and a dark/light test.",
    intro="<p>Colors are just three integers, but the small details (clamping, hex text, perceived brightness) come up repeatedly. This module wraps them in a <code>RGB</code> struct and pure functions that always return values in the 0..255 range.</p>",
    example='''import color

def main() -> Int32
    c: color.RGB = color.from_hex("#336699")
    print(color.to_hex(c) == "#336699")
    return 0''',
    output="True",
    rows=[
        ("<code>make(r, g, b)</code>", "clamp three channels into an <code>RGB</code>"),
        ("<code>from_hex(s)</code>", "parse <code>#RRGGBB</code> or <code>RRGGBB</code>; invalid text is black"),
        ("<code>to_hex(c)</code>", "lowercase <code>#rrggbb</code> text"),
        ("<code>brightness(c)</code>", "weighted brightness from 0 to 255"),
        ("<code>mix(a, b, t)</code>", "linear blend with <code>t</code> in 0..1"),
        ("<code>is_dark(c)</code>", "is the brightness below 128?"),
    ],
    notes=[
        "All inputs are clamped, so an out-of-range channel cannot produce invalid hex output.",
        "No color space conversion is attempted; this is plain sRGB-style arithmetic.",
    ],
))

LIBS.append(dict(
    key="table", title="Table", tag="plain-text tables and bars",
    desc="Render aligned text tables with automatic column widths, row/separator helpers and fixed-width progress bars.",
    intro="<p>Terminal output often needs aligned columns. <code>table()</code> measures every cell, pads each column and inserts a separator after the header row. The lower-level <code>row</code>, <code>separator</code>, <code>pad_cell</code> and <code>bar</code> helpers are available when you need more control.</p>",
    example='''import table

def main() -> Int32
    print(table.separator([1, 2]) == "+---+----+")
    return 0''',
    output="True",
    rows=[
        ("<code>pad_cell(s, width)</code>", "left-aligned cell; long values end in <code>..</code>"),
        ("<code>row(cells, widths)</code>", "one <code>| a | b |</code> row"),
        ("<code>separator(widths)</code>", "matching <code>+---+---+</code> rule"),
        ("<code>bar(value, maximum, width, ch)</code>", "fixed-width progress bar"),
        ("<code>table(rows)</code>", "whole grid, with a separator after row 0"),
    ],
    notes=[
        "Widths are byte counts, matching the language's <code>len()</code> and slicing.",
        "Short rows get empty cells and extra cells are ignored.",
    ],
))

LIBS.append(dict(
    key="validate", title="Validate", tag="string format checks",
    desc="Bool-returning checks for integers, floats, IPv4 addresses, hex colors, email-like strings and Luhn check digits.",
    intro="<p>Input from <code>input()</code> or a native module arrives as text. These helpers answer the narrow question \"does this string have the right shape?\" before you try to use it. They never throw and never modify the string.</p>",
    example='''import validate

def main() -> Int32
    print(validate.is_ipv4("127.0.0.1"))
    print(validate.luhn("4111111111111111"))
    return 0''',
    output="True\nTrue",
    rows=[
        ("<code>is_int_string(s)</code>", "optional sign, then digits only"),
        ("<code>is_float_string(s)</code>", "sign, one dot, digits before the dot"),
        ("<code>is_ipv4(s)</code>", "four 0..255 octets without leading zeros"),
        ("<code>is_hex_color(s)</code>", "<code>#</code> plus six hex digits"),
        ("<code>is_email_like(s)</code>", "one <code>@</code>, a dot in the domain, no spaces"),
        ("<code>luhn(s)</code>", "digits only, length at least 2, checksum passes"),
    ],
    notes=[
        "These are format checks, not proof that an address exists or that a number is in range for a cast.",
        "<code>is_email_like</code> is deliberately permissive; it does not implement RFC 5322.",
    ],
))

LIBS.append(dict(
    key="graph", title="Graph", tag="directed graphs and BFS",
    desc="A small directed graph type with edge insertion/removal, neighbours, reachability and breadth-first distances.",
    intro="<p>Graphs are useful for routes, dependencies and many other puzzles. A <code>Graph</code> has a fixed number of nodes numbered <code>0..n-1</code>, directed edges, and value semantics: adding an edge returns a new graph. Traversal is iterative, so it does not use the call stack.</p>",
    example='''import graph

def main() -> Int32
    g: graph.Graph = graph.empty(3)
    g = graph.add_edge(g, 0, 1)
    g = graph.add_edge(g, 1, 2)
    print(graph.has_path(g, 0, 2))
    return 0''',
    output="True",
    rows=[
        ("<code>empty(n)</code>", "graph with <code>n</code> nodes and no edges"),
        ("<code>add_edge(g, u, v)</code>, <code>remove_edge(g, u, v)</code>", "new graph with the edge added or removed"),
        ("<code>neighbors(g, u)</code>, <code>has_edge(g, u, v)</code>", "outgoing edges and direct-edge test"),
        ("<code>bfs(g, start)</code>", "shortest distances; <code>-1</code> when unreachable"),
        ("<code>has_path(g, start, goal)</code>", "is the goal reachable?"),
        ("<code>reachable(g, start)</code>", "reachable node indices in ascending order"),
    ],
    notes=[
        "Out-of-range node indices are ignored rather than treated as errors.",
        "Edges are stored as two flat lists (<code>from</code> and <code>to</code>) to keep the generated IR simple.",
    ],
))


BENCHMARK_CASES = [
    dict(
        name="bubblesort", ratio=0.81, checksum="3065",
        workload="Repeated bubble sort of a 24-element integer list; five reps, with list indexing and swaps.",
        rows=[
            ("C++ (g++ -O2)", "0.235s", "0.004s", "0.004s", "baseline"),
            ("Threadon (JIT/lli)", "0.312s", "0.101s", "0.099s", "23.17x slower"),
            ("Threadon (native exe)", "0.497s", "0.004s", "0.003s", "0.81x faster"),
            ("Python 3", "-", "0.018s", "0.018s", "4.09x slower"),
        ],
    ),
    dict(
        name="collatz", ratio=0.77, checksum="22938602",
        workload="Sum Collatz stopping times for starting values 1..200000; integer branches and modulo.",
        rows=[
            ("C++ (g++ -O2)", "0.069s", "0.047s", "0.045s", "baseline"),
            ("Threadon (JIT/lli)", "0.248s", "0.081s", "0.081s", "1.73x slower"),
            ("Threadon (native exe)", "0.307s", "0.036s", "0.036s", "0.77x faster"),
            ("Python 3", "-", "2.259s", "2.195s", "48.18x slower"),
        ],
    ),
    dict(
        name="dotint", ratio=1.00, checksum="506996752750",
        workload="Integer dot product of two 4096-element lists, repeated 500 times; tight Int64 loop.",
        rows=[
            ("C++ (g++ -O2)", "0.228s", "0.005s", "0.005s", "baseline"),
            ("Threadon (JIT/lli)", "0.314s", "0.098s", "0.097s", "18.17x slower"),
            ("Threadon (native exe)", "0.445s", "0.005s", "0.005s", "1.00x slower"),
            ("Python 3", "-", "0.153s", "0.150s", "28.41x slower"),
        ],
    ),
    dict(
        name="fibmod", ratio=0.84, checksum="815776844",
        workload="Two million iterations of an Int64 Fibonacci recurrence modulo 1000000007.",
        rows=[
            ("C++ (g++ -O2)", "0.069s", "0.013s", "0.012s", "baseline"),
            ("Threadon (JIT/lli)", "0.291s", "0.056s", "0.055s", "4.34x slower"),
            ("Threadon (native exe)", "0.294s", "0.011s", "0.011s", "0.84x faster"),
            ("Python 3", "-", "0.189s", "0.186s", "14.65x slower"),
        ],
    ),
    dict(
        name="mandelbrot", ratio=0.98, checksum="4591641",
        workload="256x256 escape-time count with at most 255 Float64 iterations per pixel.",
        rows=[
            ("C++ (g++ -O2)", "0.088s", "0.024s", "0.023s", "baseline"),
            ("Threadon (JIT/lli)", "0.265s", "0.069s", "0.067s", "2.92x slower"),
            ("Threadon (native exe)", "0.335s", "0.023s", "0.022s", "0.98x faster"),
            ("Python 3", "-", "0.668s", "0.639s", "28.08x slower"),
        ],
    ),
    dict(
        name="matmul", ratio=0.81, checksum="50921856",
        workload="Integer matrix multiply over list-backed matrices (current n = 32), then a checksum over the result.",
        rows=[
            ("C++ (g++ -O2)", "0.243s", "0.004s", "0.004s", "baseline"),
            ("Threadon (JIT/lli)", "0.334s", "0.101s", "0.099s", "24.49x slower"),
            ("Threadon (native exe)", "0.493s", "0.003s", "0.003s", "0.81x faster"),
            ("Python 3", "-", "0.022s", "0.021s", "5.23x slower"),
        ],
    ),
    dict(
        name="primes", ratio=1.03, checksum="2262",
        workload="Count primes below 20000 by trial division with an early-exit inner loop.",
        rows=[
            ("C++ (g++ -O2)", "0.076s", "0.006s", "0.006s", "baseline"),
            ("Threadon (JIT/lli)", "0.240s", "0.051s", "0.050s", "8.33x slower"),
            ("Threadon (native exe)", "0.347s", "0.006s", "0.006s", "1.03x slower"),
            ("Python 3", "-", "0.047s", "0.043s", "7.61x slower"),
        ],
    ),
    dict(
        name="sieve", ratio=0.75, checksum="1229",
        workload="Sieve of Eratosthenes up to 10000 over a List[Bool], then count the survivors.",
        rows=[
            ("C++ (g++ -O2)", "0.243s", "0.004s", "0.004s", "baseline"),
            ("Threadon (JIT/lli)", "0.305s", "0.100s", "0.097s", "24.59x slower"),
            ("Threadon (native exe)", "0.459s", "0.003s", "0.003s", "0.75x faster"),
            ("Python 3", "-", "0.021s", "0.017s", "5.04x slower"),
        ],
    ),
]

BENCHMARK_RUN = dict(
    date="2026-11-26", runs=3, inline_threshold=0,
    environment="core dumps disabled by benchmark/run.py",
)

EARLIER_BENCHMARK_RATIOS = [
    ("collatz", 0.75), ("dotint", 0.99), ("fibmod", 0.98),
    ("mandelbrot", 0.92), ("matmul", 0.77), ("sieve", 0.92),
    ("bubblesort", 1.20), ("primes", 1.06),
]


def library_page(lib, idx):
    body = sec("what", "What it does", lib["intro"])
    body += "\n" + sec("example", "Example", f"<p>A short program using the module:</p>\n{pre(lib['example'])}\n{out(lib['output'])}")
    body += "\n" + sec("api", "API", table(("Function", "Result"), lib["rows"]))
    body += "\n" + sec("notes", "Notes and gotchas", bullets(lib["notes"]))
    nxt = LIBS[(idx + 1) % len(LIBS)]
    return page(
        title=lib["title"], description=lib["desc"], crumb=f"Libraries / {lib['title']}",
        h1=lib["title"], tag=lib["tag"], current="libraries", body=body,
        back="libraries.html", back_label="Libraries",
        next_href=f"{nxt['key']}.html", next_label=nxt["title"],
    )


def gc_page():
    example = '''def main() -> Int32
    s: String = ""
    i: Int32 = 0
    while i < 8000:
        s = s + "x"
        if i % 100 == 0:
            collect()
        i += 1
    print(len(s))
    collect()
    return 0'''
    shell_cmd = "THREADON_GC_STATS=1 python3 -m threadon app.th --run"
    stats_line = ("[gc] collections=81 snapshots=162 snapshot_max=0us snapshot_avg=0us "
                  "mark_max=52us sweep_max=812us collector_total=8.4ms")

    what = ("<p>Threadon has an explicit, manual garbage collector. There is no <code>free</code> "
            "in the language. The built-in <code>collect()</code> function runs a full collection "
            "<strong>synchronously</strong> on the calling thread before returning. It takes no "
            "arguments and returns <code>NoneType</code>.</p>\n"
            "<p>Nothing is collected automatically. There is no background collector thread, no "
            "allocation threshold and no <code>THREADON_GC_THRESHOLD</code> environment variable. "
            "A program that never calls <code>collect()</code> never runs a collection, even if it "
            "allocates heavily. The collector is <strong>conservative</strong> and "
            "<strong>non-moving</strong>: payload words are scanned without type descriptors and "
            "live objects never change address.</p>")

    collected = ("<p>Every heap allocation emitted by the compiler goes through "
                 "<code>__threadon_gc_alloc</code>:</p>\n" + bullets([
                     "string concatenation, slicing and <code>chr</code>",
                     "list and dictionary backing arrays",
                     "thread closure structs",
                     "template payloads and template objects",
                 ]) + "\n<p>String literals are static constants and are not collected. Memory owned "
                 "by native modules (C/C++/Rust/Python objects) stays owned by those modules. "
                 "Structs and list/dict descriptors themselves are LLVM aggregate values; only "
                 "their heap backing arrays are GC blocks.</p>\n"
                 "<p>Call <code>collect()</code> at points where you know a batch of temporary "
                 "values has become garbage: between loop iterations, after dropping a large list, "
                 "or before a memory-sensitive phase. Allocations between calls are not reclaimed "
                 "until the next call.</p>")

    example_sec = ("<p>This loop builds a new string on every iteration; the old buffers become "
                    "garbage. Calling <code>collect()</code> periodically keeps memory bounded:</p>\n"
                    + pre(example) + "\n" + out("8000"))

    roots = ("<p>Each block has a 48-byte header (magic, size, mark epoch, links) followed by the "
             "payload pointer handed to generated code. The payload is scanned word by word: a word "
             "counts as a pointer when it looks like a valid heap header. That avoids emitting "
             "precise type descriptors for every container type.</p>\n"
             "<p>Roots come from three places:</p>\n" + bullets([
                 "module globals, registered by the generated <code>main</code> wrapper",
                 "per-thread stack snapshots, scanned conservatively up to a high-water mark",
                 "heap slots, handled by a write barrier after pointer stores into GC objects",
             ]) + "\n<p>There are no LLVM stack maps and no shadow stack.</p>\n"
             "<p>One <code>collect()</code> call has four phases, all on the calling thread:</p>\n"
             "<ol>\n"
             "<li>It bumps the mark epoch and snapshot generation, then snapshots the calling "
             "thread's stack. Other threads use snapshots they published when they last "
             "allocated.</li>\n"
             "<li>It marks module globals and all published snapshots, following pointers found "
             "inside marked payloads.</li>\n"
             "<li>It takes a second snapshot generation to catch pointers written into locals "
             "during step 2, then marks again.</li>\n"
             "<li>It sweeps unmarked blocks. Blocks allocated during the cycle are born already "
             "marked, and pointer stores into heap objects mark the new value, preserving the "
             "tri-color invariant.</li>\n"
             "</ol>")

    tuning = ("<p>There is nothing to tune for triggering: collection happens only when you call "
               "<code>collect()</code>. One optional environment variable controls diagnostics:</p>\n"
               + table(("Variable", "Default", "Effect"), [
                   ("<code>THREADON_GC_STATS</code>", "off",
                    "any value except exactly <code>0</code> prints timing stats at exit"),
               ]) + "\n"
               + f'<pre><code>{html.escape(shell_cmd)}</code></pre>\n'
               + "<p>With stats enabled, the program prints a line like this at exit (timings vary "
               "per run):</p>\n" + out(stats_line) + "\n"
               + "<p><code>collections</code> is the number of explicit <code>collect()</code> "
               "calls. <code>snapshot_*</code> is the time spent publishing root snapshots; "
               "<code>mark_max</code> and <code>sweep_max</code> are the longest single phases; "
               "<code>collector_total</code> is the sum of all collection time.</p>")

    internals = ("<p>The collector lives in <code>gc_runtime.c</code> next to the compiler sources. "
                  "<code>build_gc_runtime.sh</code> compiles it with clang to "
                  "<code>gc_runtime.ll</code>, strips module/target lines and renames private string "
                  "constants so they cannot collide with generated ones. The IR is appended to a "
                  "module when it allocates or calls <code>collect()</code>, which keeps "
                  "<code>lli</code> and native executables identical.</p>\n"
                  "<p>The longer design note is <code>GC.md</code> in the same directory.</p>")

    notes = bullets([
        "Conservative scanning can keep an object alive for one extra cycle if an integer happens "
        "to look like a heap pointer.",
        "A <code>collect()</code> call pauses the calling thread for the whole mark-and-sweep "
        "cycle; there is no background marker or sweeper.",
        "Other threads keep running, but briefly lock around heap bookkeeping and snapshot "
        "publication. New allocations during a cycle are safe.",
        "A thread that blocks forever or never allocates again keeps its last published snapshot; "
        "a collection proceeds with whatever snapshots are available.",
        "The collector does not move objects, so native pointers into live Threadon strings or "
        "lists remain valid.",
        "Fixed caps: 128 registered threads, 8192 snapshot words per thread and 256 global roots. "
        "Entries past those caps are ignored.",
    ])

    body = "\n".join([
        sec("what", "What it does", what),
        sec("collected", "What is collected", collected),
        sec("example", "Example", example_sec),
        sec("how", "How collection works", roots),
        sec("tuning", "Stats", tuning),
        sec("internals", "Implementation notes", internals),
        sec("notes", "Notes and gotchas", notes),
    ])
    return page(
        title="Garbage collector", description="Threadon's explicit, conservative, non-moving garbage collector: what it reclaims, how collect() works, and how to read its stats.",
        crumb="Garbage collector", h1="Garbage collector",
        tag="explicit, conservative, non-moving", current="gc.html", body=body,
        back="exceptions.html", back_label="Exceptions",
        next_href="examples.html", next_label="Examples",
    )


def hub_page():
    cards = []
    for lib in LIBS:
        cards.append(f'''    <div class="card">
      <h3><a href="{lib['key']}.html">{lib['title']}</a></h3>
      <p>{lib['desc']}</p>
    </div>''')
    body = sec("what", "Bundled libraries", "<p>Besides the <a href=\"stdlib.html\">small std lib</a> that is imported automatically, Threadon ships a set of opt-in modules. They are ordinary <code>.th</code> files in <code>stdlib/</code>, so no external toolchain is needed. Import one by name and call its functions qualified:</p>\n" + pre('''import math
import strings

def main() -> Int32
    print(math.gcd(48, 18))
    print(strings.upper("hello"))
    return 0''') + "\n" + out("6\nHELLO") + "\n<p>Each page below documents one module. Every module also has a <code>README.md</code> next to its source and a <code>test.th</code> suite in the repository.</p>")
    body += "\n" + sec("all", "All libraries", '    <div class="cards">\n' + "\n".join(cards) + "\n    </div>")
    body += "\n" + sec("using", "Using a module", "<p>The importer searches the <code>-I</code> directories, then the main file's folder, then the bundled <code>stdlib/</code> directory. All four import forms work:</p>\n" + pre('''import math
import math as m
from math import gcd, is_prime
lazyimport random
lazyfrom stats import mean_int''') + "\n<p>Only functions, structs and classes can be imported. See <a href=\"modules.html\">Imports</a> for the full rules. A library can import other libraries: <code>stats</code>, for example, uses <code>lists</code> and <code>math</code>.</p>")
    return page(
        title="Libraries", description="The 26 bundled Threadon libraries: math, strings, data structures, encoding, dates, units, colors, tables, validation, graphs and more.",
        crumb="Libraries", h1="Libraries", tag="bundled modules, opt in with import",
        current="libraries", body=body, back="stdlib.html", back_label="Std lib",
        next_href="math.html", next_label="Math",
    )


CONFIG_TEXT = '''[project]
name = "myapp"
version = "0.1.0"
main = "src/main.th"

[dependencies]

[paths]
include = ["src"]
test = ["tests"]'''


def projects_page():
    what = ("<p>A Threadon project is any directory with a <code>threadon.toml</code> file. "
            "The config is deliberately small: a name, a main file, include paths, test paths "
            "and local path dependencies. There is no registry, no network fetch and no "
            "<code>pip</code>-style install step. A dependency is just another directory on "
            "disk.</p>\n"
            "<p>The standard library is implicit. You never list it as a dependency.</p>")

    start = ("<p>Create a project and run its generated entry point:</p>\n"
             + pre("python3 -m threadon init myapp\ncd myapp\npython3 -m threadon run")
             + "<p><code>init</code> writes <code>threadon.toml</code>, <code>src/main.th</code> "
               "and a <code>tests/</code> directory. Pass <code>--force</code> to overwrite an "
               "existing config. Pass <code>--dir DIR</code> to initialise somewhere other "
               "than the current directory.</p>")

    config = ("<p>The generated file uses a narrow TOML subset: sections, quoted strings and "
              "arrays of strings. The parser works on Python 3.9 as well as newer versions; "
              "it uses <code>tomllib</code> when present and falls back to its own reader "
              "otherwise. Inline tables and nested sections are rejected on purpose.</p>\n"
              + pre(CONFIG_TEXT)
              + "<p>Paths are relative to the config file. <code>main</code> selects the "
                "source used by <code>run</code> and <code>build</code>; <code>include</code> "
                "is added to the import search path; <code>test</code> is where "
                "<code>threadon test</code> looks for <code>test.th</code> suites.</p>")

    commands = table(("Command", "What it does"), [
        ("<code>python3 -m threadon init [NAME]</code>",
         "Write a new <code>threadon.toml</code> and a minimal source tree."),
        ("<code>python3 -m threadon add NAME PATH</code>",
         "Record a local path dependency and cache a snapshot of its files."),
        ("<code>python3 -m threadon build [FILE.th]</code>",
         "Compile the project source to LLVM IR and write the cache artefact."),
        ("<code>python3 -m threadon run [FILE.th]</code>",
         "Compile if needed, then execute with <code>lli</code>."),
        ("<code>python3 -m threadon test [-k PATTERN]</code>",
         "Compile and run each discovered <code>test.th</code>; <code>-k</code> filters names."),
        ("<code>python3 -m threadon clean</code>",
         "Remove the project compile cache under <code>.threadon/cache</code>."),
        ("<code>python3 -m threadon cache path</code>",
         "Print the user module cache directory."),
        ("<code>python3 -m threadon cache list</code>",
         "List cached module snapshots."),
        ("<code>python3 -m threadon cache clear [--modules]</code>",
         "Clear the project cache; with <code>--modules</code>, also clear the user cache."),
    ])

    deps = ("<p>Add a dependency with a name and a directory. The name is how you import "
            "it; the path is stored relative to your project so the folder can move as a "
            "unit.</p>\n"
            + pre("python3 -m threadon add util ../util\npython3 -m threadon run")
            + "<p>The dependency's own <code>threadon.toml</code> is read if it has one, so "
              "its version and include paths travel with it. Its source files are copied into "
              "the user module cache as a snapshot. You can still pass explicit "
              "<code>-I DIR</code> flags; those are searched alongside project includes.</p>\n"
              + note("<p>No dependency ever downloads code. If a path does not exist, the "
                     "compiler reports a project error rather than trying a registry.</p>"))

    locks = ("<p><code>threadon.lock</code> is plain JSON. It records a hash of the config "
             "plus a name, path, version and content hash for each dependency. Commit it if "
             "you want that resolution in version control. It is not an enforcement file "
             "yet: the compiler does not currently read it to reject a changed dependency.</p>\n"
             "<p>The compile cache lives in <code>&lt;root&gt;/.threadon/cache</code>. Its "
             "metadata records whether native modules were present: when a project switches "
             "to or away from a native module, the cached IR is skipped and rebuilt. Cached "
             "runs print <code>cached ...</code> so you can tell what happened.</p>")

    compat = bullets([
        "Python 3.9 or newer. <code>tomllib</code> is optional; the small parser handles the config format itself.",
        "Project discovery walks up from the current directory to find the nearest <code>threadon.toml</code>.",
        "If you pass a source file, its directory is used too, so invoking the compiler from outside the project still finds its imports.",
        "The bundled standard library is always searched last and cannot be shadowed by an accidental local <code>math.th</code>.",
        "Set <code>THREADON_CACHE_DIR</code> to move the user module cache away from <code>~/.cache/threadon/modules</code>.",
    ])

    trouble = table(("Symptom", "Fix"), [
        ("<code>no threadon.toml found</code>",
         "Run the command from inside the project, or pass <code>--dir</code> to <code>init</code>."),
        ("A dependency import is missing",
         "Check the name in <code>[dependencies]</code>, then run <code>cache clear</code> to refresh its snapshot."),
        ("A native module changed but the old result is used",
         "Run <code>clean</code>; native projects deliberately bypass the IR cache."),
        ("Tests from another project are picked up",
         "List the exact directories in <code>[paths] test</code> and use <code>-k</code> to filter."),
    ])

    body = "\n".join([
        sec("why", "Why projects", what),
        sec("create", "Create one", start),
        sec("config", "threadon.toml", config),
        sec("commands", "Commands", commands),
        sec("deps", "Local dependencies", deps),
        sec("cache", "Lockfile and caches", locks),
        sec("compat", "Compatibility", compat),
        sec("trouble", "Troubleshooting", trouble),
    ])
    return page(
        title="Projects", description="Local Threadon projects: threadon.toml, path dependencies, compile cache, lockfile and the init/add/build/run/test/clean/cache commands.",
        crumb="Projects", h1="Projects", tag="no registry, no network, just local paths",
        current="projects.html", body=body, back="modules.html", back_label="Imports",
        next_href="cheatsheet.html", next_label="Cheatsheet",
    )


def cheatsheet_page():
    skeleton = ("<p>Every executable program has one <code>main</code>. Indentation defines "
                "blocks; there are no braces and no semicolons.</p>\n"
                + pre('''def main() -> Int32
    name: String = "world"
    print(f"hello {name}")
    return 0'''))

    types = table(("Family", "Types", "Notes"), [
        ("Signed integers", "<code>Int8</code> ... <code>Int64</code>, <code>Int256</code>",
         "Wrap on overflow; choose the width explicitly."),
        ("Unsigned integers", "<code>UInt8</code> ... <code>UInt64</code>, <code>UInt256</code>",
         "Needed for casts such as <code>UInt32(255)</code>."),
        ("Floats", "<code>Float16</code>, <code>Float32</code>, <code>Float64</code>",
         "Printed with six decimals. <code>--flag-inf</code> rejects non-finite values."),
        ("Other", "<code>Bool</code>, <code>String</code>, <code>NoneType</code>",
         "Strings are immutable byte strings."),
        ("Collections", "<code>List[T]</code>, <code>Dict[K, V]</code>",
         "Passed by value; helpers return new values."),
        ("User types", "<code>struct</code>, <code>class</code>, <code>union</code>",
         "Structs and classes have value semantics; unions are closed polymorphism."),
    ])

    vars_flow = pre('''x: Int32 = 1          # declare
x += 2                # assign
s: String = "abc"
b: Bool = x > 2 and len(s) == 3

if b:
    print("yes")
elif x == 3:
    print("three")
else:
    print("no")

i: Int32 = 0
while i < 10:
    if i == 5:
        break
    i += 1

for v in range(0, 3):
    print(v)''')

    funcs = ("<p>Use <code>puredef</code> when a function must not print, read input, write "
             "globals, call a native module or start a thread. Purity is checked at compile "
             "time.</p>\n"
             + pre('''def add(a: Int32, b: Int32) -> Int32
    return a + b

puredef square(x: Int32) -> Int32
    return x * x

class Counter:
    n: Int32

    def __init__(self, start: Int32)
        self.n = start

    def next(self) -> Int32
        self.n += 1
        return self.n'''))

    collections = pre('''xs: List[Int32] = [3, 1, 2]
xs.append(4)
xs[0] = 9
print(len(xs))

d: Dict[String, Int32] = {"a": 1, "b": 2}
d["c"] = 3
print(d["b"])
print(dict_key(d, 0))''')

    imports = pre('''import math
import math as m
from math import gcd, is_prime
lazyimport random
lazyfrom stats import mean_int''')

    unions = ("<p>A union value is one of its listed types. It is <em>not</em> an "
              "<code>Any</code> escape hatch: the compiler checks every member. There are no "
              "traits and no user-defined generics in the language.</p>\n"
              + pre('''from unions import Number

def show(v: Number)
    if isinstance(v, Int32):
        print(v + 1)
    elif isinstance(v, String):
        print(strings.upper(v))

show(Int32(7))
show("tiny")'''))

    builtins = table(("Builtin", "Use"), [
        ("<code>print(...)</code>", "Print values separated by spaces."),
        ("<code>input()</code>", "Read one line as a String."),
        ("<code>len(x)</code>", "Byte length of a String, or item count of a List/Dict."),
        ("<code>chr(n)</code>, <code>ord(s)</code>", "Single-byte character conversion."),
        ("<code>dict_key(d, i)</code>", "Key at position i."),
        ("<code>collect()</code>", "Run one explicit garbage collection."),
        ("<code>thread</code>, <code>thread_exit()</code>", "Start or leave a thread."),
    ])

    body = "\n".join([
        sec("skeleton", "Program skeleton", skeleton),
        sec("types", "Types", types),
        sec("vars", "Variables and flow", vars_flow),
        sec("functions", "Functions, purity and classes", funcs),
        sec("collections", "Lists and dicts", collections),
        sec("imports", "Imports", imports),
        sec("unions", "Unions", unions),
        sec("builtins", "Builtins", builtins),
    ])
    return page(
        title="Cheatsheet", description="A one-page Threadon reference: types, declarations, flow, functions, collections, imports, unions, builtins and the C-like design rules.",
        crumb="Cheatsheet", h1="Cheatsheet", tag="the syntax on one page",
        current="cheatsheet.html", body=body, back="projects.html", back_label="Projects",
        next_href="cookbook.html", next_label="Cookbook",
    )


def cookbook_page():
    intro = ("<p>This page collects the short example from every bundled library in one "
             "place. Each recipe links to the full page with its API table and output. The "
             "snippets are the same ones used to generate the library documentation, so they "
             "stay in sync with the reference.</p>")
    recipes = []
    for lib in LIBS:
        link = f'<a href="{lib["key"]}.html">{lib["title"]}</a>'
        recipes.append(
            f'<h3 id="recipe-{lib["key"]}">{lib["title"]}</h3>\n'
            f'<p>{lib["desc"]} Full reference: {link}. The documented output is on that page.</p>\n'
            f'{pre(lib["example"])}'
        )
    body = sec("intro", "How to use this page", intro) + "\n" + sec(
        "recipes", "Recipes", "\n".join(recipes)
    )
    return page(
        title="Cookbook", description="Runnable Threadon recipes for math, strings, lists, encoding, dates, units, graphs, tables, validation and more.",
        crumb="Cookbook", h1="Cookbook", tag="small programs you can copy",
        current="cookbook.html", body=body, back="cheatsheet.html", back_label="Cheatsheet",
        next_href="diagnostics.html", next_label="Diagnostics",
    )


def diagnostics_page():
    shape = ("<p>All compiler diagnostics go through <code>compiler/threadon/errors.py</code>. "
             "A compile-time error has one plain shape:</p>\n"
             "<pre class=\"msg\"><code>Error: MESSAGE at line N</code></pre>\n"
             "<p>With a known source position the renderer adds the source line and a caret. "
             "Warnings use <code>Warning:</code> and notes use <code>Note:</code>. The "
             "compiler prints the message once; it does not dump LLVM IR, Python tracebacks "
             "or duplicate <code>Error:</code> prefixes.</p>")

    colors = ("<p>Colors are optional. <code>NO_COLOR=1</code> disables them; "
              "<code>FORCE_COLOR=0</code> does the same. On a terminal the label is colored "
              "and bold, but the text is otherwise identical. Redirecting output should not "
              "change what a script can parse.</p>")

    common = table(("Message", "Meaning"), [
        ("<code>Error: Cannot redefine builtin/standard library function 'collect'</code>",
         "A program tried to declare a function such as <code>collect</code>, <code>input</code> or <code>print</code>. Builtins and auto-imported stdlib functions are reserved."),
        ("<code>Error: ... at line 12</code>",
         "A parser, checker or IR-builder error. Fix the reported line first; later errors are often consequences."),
        ("<code>Error: no function 'main' found in the compiled module</code>",
         "The source compiled, but there is no entry point to run or link."),
        ("<code>Error: Type mismatch ...</code>",
         "The checker rejected an operation. Threadon does not insert implicit conversions; use an explicit cast."),
        ("<code>Error: invalid TOML ...</code>",
         "The project config used unsupported syntax. Keep to sections, strings and string arrays."),
    ])

    runtime = ("<p>Runtime errors from a generated program are emitted by LLVM code and keep "
               "their own message strings. They are deliberately not wrapped in "
               "<code>Error:</code>, because they are not compiler diagnostics. Use "
               "<a href=\"debug.html\">debug mode</a> to turn some silent undefined behavior "
               "into explicit runtime checks, and <code>--flag-inf</code> for non-finite "
               "floats.</p>")

    report = bullets([
        "Copy the whole diagnostic, including the line number and caret line.",
        "Include the smallest source file that reproduces it.",
        "Say which command you ran and whether you used the repo compiler or an installed package.",
        "For benchmark or cache problems, include the relevant <code>threadon.toml</code> and <code>threadon.lock</code>.",
    ])

    body = "\n".join([
        sec("shape", "Message shape", shape),
        sec("color", "Color and scripts", colors),
        sec("common", "Common messages", common),
        sec("runtime", "Compile-time versus runtime", runtime),
        sec("report", "Reporting a problem", report),
    ])
    return page(
        title="Diagnostics", description="How Threadon formats compiler errors: clean Error: MESSAGE at line N output, warnings, color rules, common messages and runtime-error differences.",
        crumb="Diagnostics", h1="Diagnostics", tag="one clean line, once",
        current="diagnostics.html", body=body, back="cookbook.html", back_label="Cookbook",
        next_href="faq.html", next_label="FAQ",
    )


def faq_page():
    answers = [
        ("Why no traits, generics or Any?",
         "Threadon is deliberately C-like. Concrete types and <a href=\"unions.html\">unions</a> keep the generated IR simple and the diagnostics predictable. A union is closed polymorphism: the compiler knows every member and checks every use. There is no open-ended <code>Any</code> union and no user-defined generics."),
        ("Is pattern matching on unions coming?",
         "It is the next planned language feature after the project system. Until then, narrow a union with explicit type tests, as shown on the <a href=\"cheatsheet.html#unions\">cheatsheet</a> and the <a href=\"unions.html\">Unions</a> page."),
        ("Why is <code>collect()</code> explicit?",
         "There is no background collector and no allocation threshold. A call runs a full conservative mark-and-sweep on the calling thread. That makes pauses visible and keeps the runtime small; see <a href=\"gc.html\">Garbage collector</a>."),
        ("Why is the JIT so much slower than the native executable?",
         "The benchmark times fresh processes. A JIT run pays Python compiler startup plus <code>lli -O2</code> startup on every launch. The native executable pays compilation once and then runs generated machine code directly. Compare the rows on <a href=\"benchmarks.html\">Benchmarks</a>."),
        ("Why are lists copied when passed to a function?",
         "Value semantics make ownership obvious: a helper cannot resize your list behind your back. Functions in the bundled libraries return new lists. For tight loops, keep the work in one function so no copies are made."),
        ("Why byte strings instead of Unicode strings?",
         "String indexing and <code>len(s)</code> count bytes, which matches the LLVM representation. The <a href=\"lib-strings.html\">strings</a> module is ASCII-oriented. Non-ASCII text can be stored, but there is no UTF-8 iteration layer."),
        ("Why no catchable exceptions?",
         "There is no exception unwinding in the generated IR. Errors are either compile-time diagnostics or explicit runtime checks; see <a href=\"exceptions.html\">Exceptions</a>."),
        ("Where do dependencies come from?",
         "Only local directories listed in <code>threadon.toml</code>. There is no registry and no network fetch. <a href=\"projects.html\">Projects</a> explains the cache and lockfile."),
        ("Can I call C, C++, Rust or Python code?",
         "Yes. Native modules are declared in manifests and built by the importer; Python classes use the embedded bridge. See <a href=\"classes.html\">Classes</a> and <a href=\"modules.html\">Imports</a>."),
        ("Which compiler should I use for docs examples?",
         "Use the repository compiler with <code>PYTHONPATH=compiler python3 -m threadon</code>. An installed package can be older than the checkout and may give different diagnostics."),
    ]
    items = "\n".join(
        f'<h3 id="q{i}">{question}</h3>\n<p>{answer}</p>'
        for i, (question, answer) in enumerate(answers, 1)
    )
    body = sec("answers", "Questions and answers", items)
    return page(
        title="FAQ", description="Why Threadon is C-like, why unions replace traits and generics, when pattern matching arrives, how GC and native builds work, and where dependencies come from.",
        crumb="FAQ", h1="FAQ", tag="short answers to the common questions",
        current="faq.html", body=body, back="diagnostics.html", back_label="Diagnostics",
        next_href="cli.html", next_label="CLI",
    )


def performance_page():
    modes = table(("Mode", "Command", "Cost profile"), [
        ("IR only", "<code>python3 -m threadon app.th -o app.ll</code>",
         "Fastest feedback when you only want to inspect generated code."),
        ("JIT / lli", "<code>python3 -m threadon --run app.th</code>",
         "Convenient, but each launch includes Python compiler startup and <code>lli</code> startup."),
        ("Native exe", "<code>python3 -m threadon --exe app app.th</code>",
         "Compiles once via <code>llc</code> and <code>gcc</code>; best run-time performance."),
        ("Project build", "<code>python3 -m threadon build</code>",
         "Caches IR per config and source hash; skips the cache when native modules are involved."),
    ])

    tuning = table(("Knob", "Effect", "When to use it"), [
        ("<code>-O N</code>", "Inline threshold; <code>0</code> means no inlining.",
         "Try small values first. More inlining is not always faster and increases compile time."),
        ("<code>--exe</code>", "Produces a native executable instead of using <code>lli</code>.",
         "For anything where startup or steady-state speed matters."),
        ("<code>collect()</code>", "Runs one explicit garbage collection.",
         "Between batches of temporary strings, lists or dicts; see <a href=\"gc.html\">GC</a>."),
        ("Local lists", "Pass-by-value copies data across calls.",
         "Keep hot loops in one function rather than calling a helper per element."),
        ("Project cache", "Reuses IR when sources, includes and options are unchanged.",
         "Large projects with many incremental runs; clear it after changing native modules."),
        ("<code>--debug</code>", "Adds runtime checks.",
         "Development only; remove it for measurements."),
    ])

    method = ("<p>The <a href=\"benchmarks.html\">benchmark results</a> time fresh "
              "processes, not an in-process loop. That is deliberate: startup is part of what "
              "a user pays when running <code>threadon --run</code>. Compilation is reported "
              "separately so it does not pollute execution numbers. Every case prints a "
              "checksum and the runner verifies that C++, Threadon and Python agree.</p>\n"
              "<p><code>vs C++</code> is <code>median / C++ median</code>. Values below 1 are "
              "faster; values above 1 are slower. Timings move between machines, so treat "
              "differences near 1 as parity rather than a win.</p>")

    checklist = bullets([
        "Measure the native executable if you care about runtime speed; measure <code>--run</code> if you care about edit-and-run latency.",
        "Use the same <code>-O</code> value for every run you compare.",
        "Keep debug checks and <code>THREADON_GC_STATS</code> off for timing runs.",
        "Run enough samples that the median is stable; the shipped runner defaults to 5 and the recorded table used 3.",
        "Compare against the repo compiler, not an older installed package.",
    ])

    body = "\n".join([
        sec("modes", "Ways to run", modes),
        sec("tuning", "Tuning checklist", tuning),
        sec("method", "How the numbers are measured", method),
        sec("checklist", "Before you benchmark", checklist),
    ])
    return page(
        title="Performance", description="Threadon performance modes, optimizer and GC tuning, project caches, and the methodology behind the benchmark results.",
        crumb="Performance", h1="Performance", tag="measure the mode you actually run",
        current="performance.html", body=body, back="cli.html", back_label="CLI",
        next_href="benchmarks.html", next_label="Benchmarks",
    )


def benchmark_verdict(ratio: float) -> str:
    if ratio < 1:
        return f"{ratio:.2f}x faster"
    if ratio == 1:
        return "tie"
    return f"{ratio:.2f}x slower"


def benchmarks_page():
    headline = []
    for case in BENCHMARK_CASES:
        label = benchmark_verdict(case["ratio"])
        if case["ratio"] < 1:
            cell = f'<span class="good">{label}</span>'
        elif case["ratio"] > 1:
            cell = f'<span class="bad">{label}</span>'
        else:
            cell = label
        headline.append((
            f'<a href="#case-{case["name"]}"><code>{case["name"]}</code></a>',
            cell, f'<code>{case["checksum"]}</code>', case["workload"],
        ))

    summary = ("<p>Recorded run: " + BENCHMARK_RUN["date"] + ", "
               + str(BENCHMARK_RUN["runs"]) + " fresh-process samples per case, Threadon "
                 "compiled from the repository with <code>-O "
               + str(BENCHMARK_RUN["inline_threshold"]) + "</code>. The headline column is "
               "the native executable versus <code>g++ -O2</code>. Six of eight cases are "
               "faster, one is a tie and one is slightly slower.</p>")

    details = []
    for case in BENCHMARK_CASES:
        rows = [
            (impl, compile_s, median, best, f'<code>{case["checksum"]}</code>', verdict)
            for impl, compile_s, median, best, verdict in case["rows"]
        ]
        details.append(
            f'<h3 id="case-{case["name"]}">{case["name"]}</h3>\n'
            f'<p>{case["workload"]} The matching program is in '
            f'<code>benchmark/cases/{case["name"]}/</code> as '
            f'<code>{case["name"]}.th</code>, <code>.cpp</code> and <code>.py</code>.</p>\n'
            + table(("Implementation", "Compile", "Median", "Best", "Result", "vs C++"), rows)
        )

    method = ("<p>Reproduce the table from the <code>Threadon/</code> directory. "
              "The runner uses the compiler sources in <code>compiler/</code>, not the "
              "installed package. Core dumps are disabled by the runner itself.</p>\n"
              + pre("cd Threadon\npython3 benchmark/run.py --runs 3")
              + "<p>Useful variants:</p>\n"
              + pre("python3 benchmark/run.py --list\n"
                    "python3 benchmark/run.py --cases mandelbrot\n"
                    "python3 benchmark/run.py --langs cpp threadon-jit\n"
                    "python3 benchmark/run.py --runs 10\n"
                    "python3 benchmark/run.py --inline-threshold 1000\n"
                    "python3 benchmark/run.py --installed"))

    reading = bullets([
        "<code>compile</code> is wall time to build the artefact once; <code>-</code> means an interpreted language has no build step.",
        "<code>median</code> and <code>best</code> are wall times over fresh process launches, so JIT startup is included in the <code>Threadon (JIT/lli)</code> rows.",
        "<code>result</code> is the checksum printed by the program. Every implementation agreed in every case.",
        "<code>vs C++</code> is median divided by the C++ median. The C++ row is the baseline.",
        "Small arithmetic cases such as <code>dotint</code> and <code>matmul</code> are dominated by ~0.1s of JIT startup, which is why the JIT ratio looks much worse there than in <code>collatz</code>.",
        "Differences around 1.00x are noise on this machine. Re-run with <code>--runs 10</code> before drawing conclusions.",
    ])

    earlier_rows = []
    for name, ratio in EARLIER_BENCHMARK_RATIOS:
        label = benchmark_verdict(ratio)
        cls = "good" if ratio < 1 else "bad" if ratio > 1 else ""
        cell = f'<span class="{cls}">{label}</span>' if cls else label
        earlier_rows.append((f"<code>{name}</code>", cell))
    earlier = ("<p>An earlier recorded run of the same cases produced these Threadon-native "
               "ratios. It is kept here because timings move between runs and machines: the "
               "ordering is stable, but the last decimal is not. Both runs put six cases at "
               "or below 1.00x and two slightly above it.</p>\n"
               + table(("Case", "Threadon native vs C++"), earlier_rows))

    body = "\n".join([
        sec("summary", "Headline results", summary
            + table(("Case", "Threadon native vs C++", "Checksum", "Workload"), headline)),
        sec("full", "Full tables", "\n".join(details)),
        sec("earlier", "Earlier recorded ratios", earlier),
        sec("method", "Reproducing the run", method),
        sec("reading", "Reading the columns", reading),
    ])
    return page(
        title="Benchmark results", description="Recorded Threadon benchmark results against C++ and Python: medians, best times, checksums and ratios for eight numeric workloads.",
        crumb="Benchmarks", h1="Benchmark results", tag="fresh processes, matching checksums",
        current="benchmarks.html", body=body, back="performance.html", back_label="Performance",
        next_href="examples.html", next_label="Examples",
    )


def variadics_page():
    """Full guide to *args / **kwargs: syntax, calls, rules and error messages."""
    body = "\n".join([
        sec("why", "Why variadics", '''
<p>A normal function has a fixed number of parameters. A <strong>variadic</strong>
function also accepts an arbitrary tail of positional values, an arbitrary set of
named values, or both. Threadon collects those extra values into ordinary
containers: a <code>List</code> for <code>*args</code> and a <code>Dict</code> for
<code>**kwargs</code>. There is no new runtime type to learn.</p>
<p>Read the short introduction on the <a href="functions.html#variadic">Functions</a>
page first if you only need a reminder. This page is the complete reference,
including the call-site rules and every compile-time error you can trigger.</p>
'''),
        sec("declaring", "Declaring <code>*args</code>", '''
<p>Put a <code>*</code> in front of the last parameter name and give it a
<code>List[T]</code> type. Every positional argument that does not fit a fixed
parameter is appended to that list.</p>
''' + pre('''def total(*xs: List[Int32]) -> Int32
    s: Int32 = 0
    for x in xs:
        s += x
    return s

def main() -> Int32
    print(total(1, 2, 3))
    return 0
''') + out('6') + '''
<p>The name <code>xs</code> is arbitrary. The parameter is a normal
<code>List[Int32]</code> inside the body: you can iterate it, index it, pass it
on, or call <code>len(xs)</code>. If the caller supplies no extra values, the
list is empty. The compiler inserts the empty list for you.</p>
<p>Only one <code>*args</code> parameter is allowed, and it must come after all
fixed parameters. A second <code>*</code>, a fixed parameter after it, or a
non-<code>List</code> type are all compile-time errors.</p>
'''),
        sec("kwargs", "Declaring <code>**kwargs</code>", '''
<p>Put <code>**</code> in front of the last parameter name and give it a
<code>Dict[String, T]</code> type. Keys must be <code>String</code>; the value
type is whatever you need. Named arguments at the call site become entries in
that dictionary.</p>
''' + pre('''def total(a: Int32, **opts: Dict[String, Int32]) -> Int32
    s: Int32 = a
    for k in opts:
        s += opts[k]
    return s

def main() -> Int32
    print(total(1, x=2, y=3))
    return 0
''') + out('6') + '''
<p>Here <code>opts</code> is a real <code>Dict[String, Int32]</code>. Iterating
a dict yields its keys, so <code>for k in opts</code> visits <code>x</code> and
<code>y</code>, and <code>opts[k]</code> reads the value. A call with no named
arguments gives an empty dict.</p>
<p>You can declare <code>**kwargs</code> without <code>*args</code>, as above.
The key type must be <code>String</code>; <code>Dict[Int32, Int32]</code> is
rejected.</p>
'''),
        sec("both", "Using <code>*args</code> and <code>**kwargs</code> together", '''
<p>When a function has both, the order is fixed: fixed parameters, then
<code>*args</code>, then <code>**kwargs</code>. The fixed parameters are filled
first, the remaining positional values go into the list, and the named values
go into the dict.</p>
''' + pre('''def total(a: Int32, *rest: List[Int32], **opts: Dict[String, Int32]) -> Int32
    s: Int32 = a
    for x in rest:
        s += x
    for k in opts:
        s += opts[k]
    return s

def main() -> Int32
    print(total(1, 2, 3, x=4, y=5))
    return 0
''') + out('15') + '''
<p>The call <code>total(1, 2, 3, x=4, y=5)</code> binds <code>a = 1</code>,
<code>rest = [2, 3]</code> and <code>opts = {"x": 4, "y": 5}</code>, so the
result is <code>1 + 2 + 3 + 4 + 5 = 15</code>. Named arguments may appear in any
order; dictionary iteration order is not something to rely on, but summing the
values is safe.</p>
'''),
        sec("defaults", "Defaults before the variadic parameters", '''
<p>Fixed parameters before the variadic ones may have default values. This is a
common way to make the first argument optional while still accepting a tail.</p>
''' + pre('''def total(a: Int32 = 10, *rest: List[Int32], **opts: Dict[String, Int32]) -> Int32
    s: Int32 = a
    for x in rest:
        s += x
    for k in opts:
        s += opts[k]
    return s

def main() -> Int32
    print(total())
    print(total(1, *[], **{}))
    print(total(1, 2, **{}))
    return 0
''') + out('10\n1\n3') + '''
<p><code>total()</code> uses the default <code>a = 10</code> with an empty list and
an empty dict. The other two calls show that empty spread values are legal.
Variadic parameters themselves cannot have defaults &mdash; they are already
empty when nothing is supplied.</p>
'''),
        sec("spread", "Spreading containers at the call site", '''
<p>Use <code>*</code> before a <code>List</code> expression to pass its elements
as separate positional arguments, and <code>**</code> before a
<code>Dict[String, T]</code> expression to pass its entries as named arguments.
This works with literals (<code>*[]</code>, <code>**{}</code>) and with
variables.</p>
''' + pre('''def total(a: Int32, *rest: List[Int32], **opts: Dict[String, Int32]) -> Int32
    s: Int32 = a
    for x in rest:
        s += x
    for k in opts:
        s += opts[k]
    return s

def main() -> Int32
    xs: List[Int32] = [2, 3]
    opts: Dict[String, Int32] = {"a": 4, "b": 5}
    print(total(1, *xs, **opts))
    return 0
''') + out('15') + '''
<p>This is equivalent to <code>total(1, 2, 3, a=4, b=5)</code>. At most one
<code>*</code> spread and one <code>**</code> spread may appear in a single
call.</p>
<p>Do not combine a spread with extra plain positional values, or a
<code>**</code> spread with plain named arguments. Both combinations are
compile-time errors, because the compiler would have to choose an order:</p>
''' + bullets([
    '<code>f(1, 2, *xs)</code> &rarr; <em>cannot mix extra positional arguments with *arguments</em>',
    '<code>f(x=1, **opts)</code> &rarr; <em>cannot mix keyword arguments with **keyword arguments</em>',
])),
        sec("methods", "Methods and constructors", '''
<p>Variadic parameters work the same way on methods and on <code>__init__</code>.
For a method, the fixed <code>self</code> parameter comes first and is not part of
the variadic tail. For a constructor, the arguments follow the class name.</p>
''' + pre('''class Acc:
    total: Int32
    def __init__(self: Acc, start: Int32, **opts: Dict[String, Int32])
        self.total = start
        for k in opts:
            v: Int32 = opts[k]
            self.total = self.total + v
    def add(self: Acc, *xs: List[Int32]) -> Int32
        for x in xs:
            self.total = self.total + x
        return self.total

def main() -> Int32
    a: Acc = Acc(1, x=2, y=3)
    print(a.add(4, 5))
    return 0
''') + out('15') + '''
<p><code>Acc(1, x=2, y=3)</code> calls <code>__init__</code> with
<code>start = 1</code> and <code>opts = {"x": 2, "y": 3}</code>. Then
<code>a.add(4, 5)</code> passes <code>xs = [4, 5]</code>. Creating a class
without <code>__init__</code> and passing any arguments to it is an error.</p>
'''),
        sec("imports", "Imports, lazy imports and inlining", '''
<p>Variadic signatures are part of a function's signature and travel with
imports. Both eager and lazy imports keep them:</p>
''' + pre('''# lib.th
def total(*xs: List[Int32]) -> Int32
    s: Int32 = 0
    for x in xs:
        s += x
    return s
''') + pre('''# main.th
import lib
lazyimport stats as s
print(lib.total(2, 3, 4))
''') + '''
<p>Inlining (<code>-O N</code>) does not change the behaviour: a variadic call is
bound to plain list/dict arguments before the optimizer sees it, so an inlined
copy receives the same values. The same is true for methods reached through an
imported class.</p>
'''),
        sec("rules", "Rules at a glance", '''
''' + table(
    ["Question", "Answer"],
    [
        ["How many <code>*args</code> parameters?", "At most one."],
        ["How many <code>**kwargs</code> parameters?", "At most one."],
        ["Order of parameters?", "Fixed, then <code>*args</code>, then <code>**kwargs</code>."],
        ["Type of <code>*args</code>?", "<code>List[T]</code>; <code>T</code> is the element type."],
        ["Type of <code>**kwargs</code>?", "<code>Dict[String, T]</code>; the key type must be <code>String</code>."],
        ["Can variadic parameters have defaults?", "No. They default to an empty list/dict automatically."],
        ["Can <code>main</code> be variadic?", "No. The entry point takes no arguments."],
        ["Can builtins be called with <code>*</code> or keywords?", "No."],
        ["Can <code>range()</code> or list mutators be spread?", "No."],
        ["Can I mix extra positional values with <code>*</code>?", "No."],
        ["Can I mix named arguments with <code>**</code>?", "No."],
    ],
) + '''
<p>Keyword names are ordinary identifiers; they become string keys in the dict.
Passing the same fixed parameter twice (positionally and by name) is an error,
even when a <code>**kwargs</code> parameter exists.</p>
'''),
        sec("errors", "Error messages you may see", '''
''' + table(
    ["Error text", "Cause"],
    [
        ["<code>*args parameter must have type List[T]</code>", "The <code>*</code> parameter is not a list."],
        ["<code>**kwargs parameter must have type Dict[String, T]</code>", "The <code>**</code> parameter is not a dict, or its keys are not strings."],
        ["<code>Variadic parameters must come last, *args before **kwargs</code>", "Wrong parameter order, or more than one <code>*</code>/<code>**</code>."],
        ["<code>Variadic parameter 'name' cannot have a default value</code>", "A default was written on a variadic parameter."],
        ["<code>got an unexpected keyword argument 'z'</code>", "A named argument was given to a function with no <code>**kwargs</code>."],
        ["<code>got multiple values for argument 'a'</code>", "A fixed parameter was supplied twice."],
        ["<code>got multiple values for keyword 'z'</code>", "The same keyword appears twice in a <code>**kwargs</code> call."],
        ["<code>cannot mix extra positional arguments with *arguments</code>", "Plain values were added after a <code>*</code> spread."],
        ["<code>cannot mix keyword arguments with **keyword arguments</code>", "Plain named arguments were added after a <code>**</code> spread."],
        ["<code>does not accept *arguments</code>", "A <code>*</code> spread was used on a function without <code>*args</code>."],
        ["<code>does not accept **keyword arguments</code>", "A <code>**</code> spread or keyword was used without <code>**kwargs</code>."],
        ["<code>accepts at most one *arguments value</code>", "Two <code>*</code> spreads in one call."],
        ["<code>accepts at most one **keyword arguments value</code>", "Two <code>**</code> spreads in one call."],
        ["<code>Builtin 'name' does not accept keyword or spread arguments</code>", "For example <code>print(*[1])</code>."],
        ["<code>List method 'name' does not accept keyword or spread arguments</code>", "For example <code>xs.append(*[1])</code>."],
        ["<code>range() does not accept keyword or spread arguments</code>", "For example <code>range(*[2])</code>."],
        ["<code>Class 'C' has no '__init__' taking arguments</code>", "Arguments were passed to a class without <code>__init__</code>."],
        ["<code>function 'main' cannot take parameters</code>", "The entry point was declared with parameters or variadics."],
    ],
) + '''
<p>These are all compile-time errors, reported before any LLVM IR is generated.
There are no variadic-specific runtime errors: after binding, the callee simply
receives normal <code>List</code> and <code>Dict</code> values.</p>
'''),
        sec("internals", "How a variadic call is bound", '''
<p>This is useful to know when an error message surprises you. Binding happens
while the parser type-checks the call, in this order:</p>
''' + bullets([
    "Fill fixed parameters from positional arguments, then from named arguments whose name matches a fixed parameter.",
    "Collect leftover positional arguments (and a <code>*</code> spread) into the <code>List</code> for <code>*args</code>.",
    "Collect unmatched named arguments (and a <code>**</code> spread) into the <code>Dict</code> for <code>**kwargs</code>.",
    "Fill any remaining fixed parameters from their defaults; if a required one is still missing, report the ordinary arity error.",
    "Rewrite the call to an ordinary call with those list/dict values as its last arguments.",
]) + '''
<p>After that, the checker, optimizer and code generator see a plain call. That is
why variadic functions work with <code>puredef</code>, inlining, imports and
methods without any special cases further down the pipeline. The only cost is
the list and dict you asked for by declaring a variadic parameter.</p>
'''),
        sec("summary", "Quick reference", '''
''' + pre('''def name(fixed: T = value, *args: List[E], **kwargs: Dict[String, E2]) -> R
    # fixed   -> a single T
    # args    -> List[E]
    # kwargs  -> Dict[String, E2]

name(value)                             # defaults for the rest
name(value, a, b)                       # args = [a, b]
name(value, key=1)                      # kwargs = {"key": 1}
name(value, *xs, **opts)                # spread both containers
''') + '''
<p>The declaration line above is a pattern, not a compilable program: choose
concrete types and a return type in real code. See the
<a href="reference.html">Language reference</a> for the rest of the syntax.</p>
'''),
    ])
    return page(
        title="Variadic functions",
        description="Complete Threadon guide to variadic functions: *args, **kwargs, spreading, methods, rules and every error message.",
        crumb="Variadics",
        h1="Variadic functions",
        tag="accept any number of arguments, with lists and dicts you already know",
        current="variadics.html",
        body=body,
        back="functions.html", back_label="Functions",
        next_href="comptime.html", next_label="Compile-time values",
    )


def comptime_page():
    """Compile-time constants and blocks, evaluated while the program builds."""
    body = "\n".join([
        sec("idea", "What <code>comptime</code> is", '''
<p>A <code>comptime</code> declaration computes a value while the compiler is
running and stores it as a module variable. The generated program does not
evaluate the expression again: it reads the finished value. Use it for tables,
thresholds, sizes and other constants whose definition is easier to express as
a small calculation than as a literal.</p>
<p>Only module-level declarations are allowed. Putting <code>comptime</code>
inside a function is a compile error:
<code>comptime statements are only allowed at module level, not inside functions</code>.</p>
<p>Ordinary module variables are limited to literal initializers.
<code>comptime</code> is the language's way to compute a module-level value
without a runtime assignment statement.</p>
'''),
        sec("one-line", "One-line constants", '''
<p>The form is <code>comptime NAME: TYPE = EXPRESSION</code>. The colon after the
name is required. If you leave the type out but keep the colon,
<code>Int32</code> is assumed.</p>
''' + pre('''comptime N: Int32 = 2 + 3 * 4

def main() -> Int32
    print(N)
    return 0
''') + out('14') + '''
<p>The same declaration with an implicit type:</p>
''' + pre('''comptime N: = 2 + 3

def main() -> Int32
    print(N)
    return 0
''') + out('5') + '''
<p>Integer, unsigned integer, float and bool types work. Strings, lists, dicts
and user-defined values cannot be stored as module globals, so they cannot be
<code>comptime</code> constants either (<code>String globals not yet supported</code>).
Use a literal inside a function for those.</p>
'''),
        sec("block", "Block form", '''
<p>When a one-line expression is not enough, write a block after the colon. A
block may declare local variables, assign to them, use <code>if</code>/<code>elif</code>/<code>else</code>
and <code>while</code>, and must end with <code>return EXPRESSION</code>. The
block form requires an explicit type.</p>
''' + pre('''comptime N: Int32 = 2 + 3 * 4

comptime M: Int32:
    total: Int32 = 0
    i: Int32 = 0
    while i < 3:
        total = total + i
        i = i + 1
    return total

def main() -> Int32
    print(N)
    print(M)
    return 0
''') + out('14\n3') + '''
<p><code>M</code> is <code>0 + 1 + 2 = 3</code>. Every statement in the block is
evaluated by the compiler; none of it appears in the generated program.</p>
<p>A conditional works the same way:</p>
''' + pre('''comptime LIMIT: Int32:
    n: Int32 = 4
    if n > 2:
        return 10
    return 0

def main() -> Int32
    print(LIMIT)
    return 0
''') + out('10') + '''
<p>The value is cast to the declared type at the end. A result that does not fit
is an error while compiling, reported as
<code>Error evaluating comptime 'NAME': ...</code>.</p>
'''),
        sec("allowed", "What you can call at compile time", '''
<p>The compile-time evaluator is deliberately small. These calls are available,
with or without a <code>std.</code> prefix:</p>
''' + table(["Call", "Meaning"], [
    ["<code>len(x)</code>", "Length of a list or dict."],
    ["<code>print(...)</code>", "Write to the compiler's stdout while building."],
    ["<code>range(...)</code>", "Build a std <code>Iterable</code>."],
    ["<code>abs(x)</code>, <code>max(a, b)</code>, <code>min(a, b)</code>", "The matching std lib functions."],
    ["<code>clamp(x, lo, hi)</code>", "Clamp an <code>Int32</code> to a range."],
    ["<code>is_even(n)</code>, <code>is_odd(n)</code>", "Parity checks from std."],
]) + '''
<p>Anything else is rejected. In particular, you cannot call your own functions
from a <code>comptime</code> expression:</p>
<pre><code>def f() -> Int32
    return 4
comptime X: Int32 = f()   # Function 'f' not available at compile time</code></pre>
<p>There is no runtime input, no native call and no global state to read. Loops
are capped at 1,000,000 iterations so a compile cannot hang forever.</p>
<p><strong>Do not use <code>print()</code> as program output.</strong> It runs in
the compiler process, not in the executable. The declaration is evaluated in
more than one compiler phase, so a compile-time <code>print()</code> can appear
twice. Printing from your program belongs in <code>main</code> or a thread.</p>
'''),
        sec("scope", "Scope and mutation", '''
<ul>
  <li>A <code>comptime</code> name is a module variable after it is computed. Functions can read it like any other global.</li>
  <li>Each declaration is evaluated in source order, after the declarations above it and before those below it.</li>
  <li>Locals inside a <code>comptime</code> block live only inside that block.</li>
  <li>A <code>puredef</code> may read a <code>comptime</code> value but may not write any module variable, including it.</li>
  <li>You cannot declare the same name twice, just like any other module variable.</li>
</ul>
<p>See the <a href="reference.html#structure">program structure</a> section of
the language reference for the full list of what may appear at module level.</p>
'''),
        sec("errors", "Common errors", '''
''' + table(["Message", "Cause"], [
    ["<code>comptime statements are only allowed at module level, not inside functions</code>", "The declaration was written in a function or method."],
    ["<code>Expected ':' after variable name in comptime</code>", "The colon after the name is missing."],
    ["<code>comptime block requires explicit type annotation</code>", "A block was written without a type."],
    ["<code>Error evaluating comptime 'X': Function 'f' not available at compile time</code>", "The expression called a user function."],
    ["<code>String globals not yet supported</code>", "A string was used as the comptime type."],
]) + '''
<p>All of these are compile-time diagnostics with a file and line. The
<a href="diagnostics.html">Diagnostics</a> page explains their format.</p>
'''),
        sec("next", "Where to go next", '''
<p>Combine <code>comptime</code> with the <a href="stdlib.html">std lib</a>
functions listed above, or read the <a href="reference.html">language
reference</a> for the rest of the declaration forms. The
<a href="functions.html">Functions</a> page covers ordinary and
<code>puredef</code> functions; the <a href="variadics.html">Variadics</a> page
covers parameter tails.</p>
'''),
    ])
    return page(
        title="Compile-time values",
        description="Threadon comptime declarations: one-line constants, block form, allowed calls, scope rules, limits and error messages.",
        crumb="Comptime",
        h1="Compile-time values",
        tag="compute constants while the compiler runs, then read them as ordinary globals",
        current="comptime.html",
        body=body,
        back="variadics.html", back_label="Variadics",
        next_href="structs.html", next_label="Structs",
    )


def testing_page():
    """The built-in test.th harness, discovery rules and CLI commands."""
    body = "\n".join([
        sec("idea", "Tests without a test framework", '''
<p>Threadon has a built-in test harness. A file named <code>test.th</code> is a
normal module containing module-level functions whose names start with
<code>test_</code>. Each one takes no arguments and returns <code>Bool</code>.
The compiler appends a synthetic <code>main</code> that calls them and reports the
result, so you do not write a runner yourself.</p>
<p>A test function is just a function; you can read it from ordinary code too:</p>
''' + pre('''def test_sum() -> Bool
    xs: List[Int32] = [1, 2, 3]
    total: Int32 = 0
    for x in xs:
        total += x
    return total == 6

def main() -> Int32
    print(test_sum())
    return 0
''') + out('True') + '''
<p>When the file is called <code>test.th</code>, leave out <code>main</code>. If
you define <code>main</code> yourself, the compiler uses yours and does not add
the harness.</p>
'''),
        sec("format", "The test.th format", '''
<pre><code># test.th -- no main() here
def setup() -> Bool
    # runs once before the first test
    return True

def test_add() -> Bool
    return 1 + 2 == 3

def test_list() -> Bool
    xs: List[Int32] = [1, 2]
    xs.append(3)
    return len(xs) == 3

def teardown() -> Bool
    # runs once after the last test
    return True</code></pre>
<p>Rules:</p>
''' + bullets([
    'Only <code>def test_*() -> Bool</code> functions at module level are collected; the name must really start with <code>test_</code>.',
    '<code>setup() -> Bool</code> and <code>teardown() -> Bool</code> are optional. A failed setup stops the suite; a failed teardown counts as one failed test.',
    'Functions are run in source order.',
    'There are no assertion helpers: return a <code>Bool</code> expression. Any value that can be compared works.',
    'Imports, structs, classes, globals and <code>comptime</code> declarations work the same as in any other module.',
]) + '''
<p>The generated runner prints one line per test and a summary:</p>
<pre class="out">[PASS] test_add
[FAIL] test_list
--------------
2 tests 1 failed</pre>
<p>The process exits with the number of failed tests, so a shell script or CI
job can use the exit code directly. An empty suite prints
<code>(no test functions found)</code>.</p>
'''),
        sec("commands", "Discovering and running suites", '''
''' + table(["Command", "What it does"], [
    ["<code>python3 -m threadon test</code>", "Discover and run every <code>test.th</code> in the project and its include paths."],
    ["<code>python3 -m threadon test tests/test.th</code>", "Run the named file or directory."],
    ["<code>python3 -m threadon test -k PATTERN</code>", "Run only tests whose name contains <code>PATTERN</code>, for example <code>-k add</code>."],
    ["<code>python3 -m threadon file.th --run-tests</code>", "Compile <code>file.th</code> and run its generated suite."],
    ["<code>python3 -m threadon file.th --run-tests -k list</code>", "Apply the name filter to that file's suite."],
]) + '''
<p>Discovery looks at explicit files and directories first, then the project
root, every <code>-I DIR</code> path, and the standard library directory. With
no matches, the compiler prints <code>no test.th files found</code>. With a
filter that matches no test name, it prints
<code>(no tests match 'PATTERN')</code>.</p>
<p>All compile flags can be combined with test commands: <code>-I</code>,
<code>-O N</code>, <code>--debug</code> and <code>--flag-inf</code> are passed
through to each suite. The compile cache key includes the test filter, so a
filtered run cannot reuse a different filtered run's IR.</p>
'''),
        sec("projects", "Tests in a project", '''
<p>Inside a project created with <code>threadon init NAME</code>, put tests in
<code>NAME/tests/test.th</code> or keep several suites in separate directories.
The <a href="projects.html">Projects</a> page explains the layout, path
dependencies and the <code>threadon test</code> shortcut.</p>
<pre><code>threadon init demo
cd demo
threadon test</code></pre>
<p>Project commands accept the same <code>-k</code>, <code>-I</code>,
<code>-O</code>, <code>--debug</code> and <code>--flag-inf</code> options as the
module invocation.</p>
'''),
        sec("tips", "Writing useful tests", '''
<ul>
  <li>Return <code>Bool</code>, not a printed message. Keep printing for debugging a failing case.</li>
  <li>Test one behaviour per function: the <code>[PASS]</code> line names the function, so a narrow test tells you what broke.</li>
  <li>Use <code>-k</code> while debugging one case, then run the whole suite before finishing.</li>
  <li>Bad string casts, division by zero, missing keys and out-of-bounds reads are only checked under <code>--debug</code>; run the suite with that flag when you expect valid data.</li>
  <li>See the <a href="runtime.html">Runtime checks</a> page for what each flag turns on.</li>
</ul>
'''),
        sec("next", "Where to go next", '''
<p>Read the <a href="reference.html">language reference</a> for function
declarations and control flow, <a href="cli.html">CLI</a> for every compiler
flag, and <a href="diagnostics.html">Diagnostics</a> for the message format.</p>
'''),
    ])
    return page(
        title="Testing Threadon programs",
        description="Threadon test.th files: test_* functions, setup and teardown, discovery, -k filtering, harness output and project commands.",
        crumb="Testing",
        h1="Testing Threadon programs",
        tag="a tiny built-in harness: write Bool functions, run them, read PASS and FAIL",
        current="testing.html",
        body=body,
        back="cookbook.html", back_label="Cookbook",
        next_href="diagnostics.html", next_label="Diagnostics",
    )


def runtime_page():
    """Every runtime safety check, which flag enables it, and its exact message."""
    body = "\n".join([
        sec("banner", "How a runtime error looks", '''
<p>Compiler diagnostics and runtime failures are different. A diagnostic is
printed before IR is generated and starts with <code>Error:</code>. A failure in
the running program is emitted by generated code with a banner:</p>
<pre class="out">[RUNTIME ERROR]
│ Error: List index out of bounds
├─> Location: main.th:4:9
└─> Process terminated with exit code 1</pre>
<p>The payload usually starts with <code>Error:</code> too, and the process
exits with status 1. The location line names the source position when the
compiler can recover it. These messages are not compiler diagnostics; see
<a href="diagnostics.html">Diagnostics</a> for the compile-time format.</p>
'''),
        sec("always", "Checks that are always on", '''
<p>A few guards exist in every build, with or without <code>--debug</code>:</p>
''' + table(["Situation", "Message / behaviour"], [
    ["Recursion deeper than 10,000 frames (constructor limit 500,000)", "<code>Error: stack overflow detected</code> with context <code>Runtime stack depth exceeded (max 10000)</code>"],
    ["<code>pop()</code> on an empty list", "<code>Error: pop on empty list</code>"],
    ["More than 1,024 module-level threads", "<code>Error: too many threads (limit 1024)</code>"],
    ["Division by a literal zero", "Compile-time error <code>Division by zero</code>; no program is produced"],
    ["Out-of-range integer literal", "Compile-time error <code>Integer literal ... out of range for type 'T'</code>"],
]) + '''
<p>Always-on checks cost a little code size and a branch, but they turn a crash
or silent corruption into a clear message. The thread cap is checked before any
thread starts; all live threads are joined after <code>main</code> returns.</p>
'''),
        sec("debug", "Checks added by <code>--debug</code>", '''
<p>Without <code>--debug</code>, the compiler trusts you and many operations
have undefined behaviour. With it, the generated program checks the following
and prints a runtime error instead of continuing:</p>
''' + table(["Operation", "Exact message"], [
    ["Integer <code>+ - *</code>", "<code>Error: Integer overflow in addition</code>, <code>...subtraction</code>, <code>...multiplication</code>"],
    ["Integer <code>**</code>", "<code>Error: Integer overflow in power operation</code>"],
    ["Integer <code>/ // %</code>", "<code>Error: Division by zero</code>"],
    ["Signed minimum divided by <code>-1</code>", "<code>Error: Signed division overflow (MIN / -1)</code>"],
    ["Unary <code>-</code>", "<code>Error: Integer overflow in negation</code> / <code>Error: Unsigned integer underflow in negation</code>"],
    ["String to int", "<code>Invalid integer conversion</code>"],
    ["String to int out of range", "<code>Error: Integer overflow in string conversion (value out of range for T)</code>"],
    ["String to float", "<code>Invalid float conversion</code>"],
    ["Int to a narrower int", "<code>Error: Integer truncation overflow</code>"],
    ["Float to int", "<code>Error: Float-to-integer overflow</code>"],
    ["Shift amount too large", "<code>Error: Shift amount &gt;= bit-width</code>"],
    ["List or string index", "<code>Error: List index out of bounds</code> / <code>Error: String index out of bounds</code>"],
    ["<code>List.remove</code> missing value", "<code>Error: List.remove: element not found</code>"],
    ["Missing dict key", "<code>Error: KeyError: dict key not found</code>"],
]) + '''
<p>These checks are emitted into your program, so they add branches and make
failure explicit. They do not change the language's types or allow new
operations. A correct program prints exactly the same output with and without
the flag.</p>
<p>A typical safe index guard works in both modes and avoids the error entirely:</p>
''' + pre('''def main() -> Int32
    xs: List[Int32] = [10, 20]
    i: Int64 = 1
    if i < len(xs):
        print(xs[i])
    else:
        print("out of range")
    return 0
''') + out('20') + '''
<p>See the <a href="debug.html">Debug</a> page for a worked example and the
<a href="exceptions.html">Exceptions</a> page for the error-handling story.</p>
'''),
        sec("flag-inf", "Checks added by <code>--flag-inf</code>", '''
<p><code>--flag-inf</code> is independent of <code>--debug</code>. It rejects
non-finite floating-point values:</p>
''' + bullets([
    'A non-finite literal is a compile error: <code>non-finite floating-point constant ... (--flag-inf enabled)</code>.',
    'A value that becomes <code>inf</code> or <code>NaN</code> at runtime raises <code>Error: Non-finite float value (inf or NaN)</code>.',
    'Checks cover float arithmetic, <code>**</code>, <code>//</code>, string-to-float, int-to-float and float narrowing.',
    'Without the flag, non-finite values are allowed and may propagate silently.',
])),
        sec("choosing", "Which mode should I use?", '''
''' + table(["Mode", "Use it when"], [
    ["default", "You want the smallest, fastest program and your indices, divisors and casts are known to be valid."],
    ["<code>--debug</code>", "You are testing untrusted input, user data or code that indexes and converts values."],
    ["<code>--flag-inf</code>", "Floating-point results must stay finite, for example in a division-heavy calculation."],
    ["both", "You want the strictest build; the flags do not conflict."],
]) + '''
<p>Nothing here catches a compiler bug or a native module's memory errors.
Native libraries manage their own memory; see
<a href="modules.html">Imports and native modules</a> and
<a href="gc.html">Garbage collection</a>.</p>
'''),
        sec("next", "Where to go next", '''
<p>The complete language inventory is on the
<a href="reference.html">Language reference</a> page. For the compile-time
message format, read <a href="diagnostics.html">Diagnostics</a>; for the CLI
flags themselves, read <a href="cli.html">CLI</a>.</p>
'''),
    ])
    return page(
        title="Runtime checks",
        description="Threadon runtime safety: always-on guards, every --debug check and message, --flag-inf behaviour, and when to use each mode.",
        crumb="Runtime checks",
        h1="Runtime checks",
        tag="what is checked always, what --debug adds, and what --flag-inf rejects",
        current="runtime.html",
        body=body,
        back="debug.html", back_label="Debug mode",
        next_href="exceptions.html", next_label="Exceptions",
    )


def reference_page():
    """Compact language reference that inventories every construct and links out."""
    body = "\n".join([
        sec("map", "The whole language, in one place", '''
<p>This page is the compact reference: every keyword, declaration form,
expression, builtin and command appears here. Longer pages explain one topic
at a time and are linked from each section. If this page disagrees with the
compiler, the compiler wins; if it disagrees with a detailed page, tell us.</p>
''' + table(["Area", "Detailed page"], [
    ["Names, layout, comments", "<a href=\"basics.html\">Basics</a>"],
    ["Text, interpolation, templates", "<a href=\"strings.html\">Strings</a>"],
    ["Scalar types, groups, ranges", "<a href=\"types.html\">Types</a>"],
    ["Changing values and scope", "<a href=\"variables.html\">Variables</a>"],
    ["Arithmetic and precedence", "<a href=\"operators.html\">Operators</a>"],
    ["Conversions", "<a href=\"casts.html\">Casts</a>"],
    ["Conditions and loops", "<a href=\"flow.html\">Flow</a>"],
    ["Functions and purity", "<a href=\"functions.html\">Functions</a>"],
    ["Star and keyword parameters", "<a href=\"variadics.html\">Variadics</a>"],
    ["Compile-time constants", "<a href=\"comptime.html\">Comptime</a>"],
    ["Records", "<a href=\"structs.html\">Structs</a>"],
    ["Union types", "<a href=\"unions.html\">Unions</a>"],
    ["The <code>^</code> operator", "<a href=\"references.html\">References</a>"],
    ["Classes and operator overloading", "<a href=\"classes.html\">Classes</a>"],
    ["Builtins", "<a href=\"builtins.html\">Builtins</a>"],
    ["Auto-imported std lib", "<a href=\"stdlib.html\">Std lib</a>"],
    ["Opt-in libraries", "<a href=\"libraries.html\">Libraries</a>"],
    ["Imports and native modules", "<a href=\"modules.html\">Imports</a>"],
    ["Projects and caches", "<a href=\"projects.html\">Projects</a>"],
    ["Threads", "<a href=\"threads.html\">Threads</a>"],
    ["Tests", "<a href=\"testing.html\">Testing</a>"],
    ["CLI flags", "<a href=\"cli.html\">CLI</a>"],
    ["Safety checks", "<a href=\"runtime.html\">Runtime checks</a>"],
    ["Garbage collection", "<a href=\"gc.html\">GC</a>"],
    ["What is not supported", "<a href=\"limits.html\">Limits</a>"],
])),
        sec("lexical", "Lexical rules", '''
<p>Identifiers contain letters, digits and underscores and cannot start with a
digit. Comments start with <code>#</code> and run to the end of the line.</p>
<p>These are all reserved words; none can be used as a name:</p>
<pre><code>def puredef if elif else while for in return break continue
and or not None class struct True False
thread on comptime
import from lazyimport lazyfrom as</code></pre>
<p>These are type keywords:</p>
<pre><code>Int8 Int16 Int32 Int64 Int256
UInt8 UInt16 UInt32 UInt64 UInt256
Float16 Float32 Float64
Bool String NoneType
Int Float Number Builtin</code></pre>
<p>The last four are group aliases, not distinct storage types. <code>Int</code>
means any signed or unsigned integer, <code>Float</code> any float,
<code>Number</code> any integer or float, and <code>Builtin</code> any scalar.
<code>List[T]</code> and <code>Dict[K, V]</code> are parameterized containers.
<code>A | B</code> forms a union type.</p>
<p>Number literals may contain underscores between digits, one dot, and an
<code>e</code>/<code>E</code> exponent with an optional sign: <code>1_000</code>,
<code>3.5</code>, <code>1e-3</code>. Hex, binary and octal literals do not exist.
An integer literal defaults to <code>Int32</code>; a dot or exponent makes it
<code>Float32</code>, and an integer literal adapts to an expected integer type.</p>
<p>Strings use double quotes. Plain strings understand <code>\\n</code>,
<code>\\t</code> and <code>\\"</code>; an unknown escape loses its backslash.
<code>f"..."</code> interpolates expressions immediately and
<code>t"..."</code> builds a reusable template object. Both add
<code>\\\\</code>, <code>\\{</code> and <code>\\}</code> escapes. See
<a href="strings.html">Strings</a>.</p>
'''),
        sec("structure", "Program structure", '''
<pre><code>module_variable: TYPE = LITERAL
def function(...) -&gt; TYPE
    ...
puredef function(...) -&gt; TYPE
    ...
struct Name:
    field: TYPE
class Name:
    ...
thread Name() on CONDITION:
    ...
comptime NAME: TYPE = EXPRESSION
import module
from module import name
lazyimport module as alias
lazyfrom module import name</code></pre>
<p>Those are the module-level forms. A module variable initializer must be a
literal; use <a href="comptime.html"><code>comptime</code></a> to compute a
global value. Bare runtime statements at module level are rejected. Execution
always starts at <code>def main() -> Int32</code>; <code>main</code> takes no
parameters and its return value is the process exit code.</p>
<p>Blocks are indented. Function headers end in <code>-> TYPE</code> with
<strong>no colon</strong>. Conditions and iterable headers do end with a colon:
<code>if x:</code>, <code>while x:</code>, <code>for x in xs:</code>,
<code>thread T() on flag:</code>, and
<code>comptime N: TYPE:</code> for the block form.</p>
'''),
        sec("functions", "Functions and calls", '''
<pre><code>def name(param: TYPE = CONSTANT, ...) -&gt; RETURN_TYPE
    ...
puredef name(param: TYPE) -&gt; RETURN_TYPE
    ...</code></pre>
<p>Every parameter has a type. Defaults must be constant expressions, a
parameter without a default cannot follow one with a default, and a trailing
comma in the parameter list is rejected. A function with a non-<code>NoneType</code>
return type must return on every path. Functions must be defined before they
are called; there are no function values, lambdas, closures or name overloading.</p>
<p><code>puredef</code> forbids global writes, native calls, threads and calls
to impure functions. Local variables, including local containers and
<code>self</code>, may still change. Pure builtins are <code>len</code>,
<code>chr</code> and <code>dict_key</code>. A class's <code>__eq__</code> must be pure.</p>
<p>Calls take positional arguments, named arguments such as <code>f(b=2)</code>,
and the spread forms <code>*xs</code> and <code>**opts</code>. A fixed
parameter, a <code>*args: List[T]</code> parameter and a
<code>**kwargs: Dict[String, T]</code> parameter may appear in that order;
there is at most one of each. Builtins, list mutators, <code>range()</code> and
native calls do not accept keywords or spreads. See
<a href="variadics.html">Variadics</a> for the complete rules and messages.</p>
'''),
        sec("types", "Values, casts, unions and references", '''
<p>Declare with <code>name: TYPE = expression</code>. Plain assignment is
<code>name = expression</code>; augmented forms are
<code>+= -= *= /= %= //=</code>. Numeric and string types convert only through
an explicit cast, written <code>TYPE(value)</code>. A cast source must be a
number, <code>String</code> or <code>Bool</code>; a union cannot be cast.</p>
<p>Signed integer ranges are <code>-2^(w-1)</code> to <code>2^(w-1)-1</code>,
unsigned ranges are <code>0</code> to <code>2^w-1</code>. Out-of-range literals
are compile errors even without <code>--debug</code>; runtime overflow checks
are described on the <a href="runtime.html">Runtime checks</a> page.</p>
<p>A union variable accepts any listed member. Assigning a concrete value
narrows the variable to that type in the current scope; branches and loops
reset it to the declared union. There is no <code>is Int</code> test &mdash;
narrowing is assignment-based. See <a href="unions.html">Unions</a>.</p>
''' + pre('''def main() -> Int32
    a: Int | Float = 5
    b: Int32 = a
    print(b)
    a = 3.5
    c: Float32 = a
    print(c)
    return 0
''') + out('5\n3.500000') + '''
<p>A reference is created only in a declaration: <code>r: T = x^</code> makes
<code>r</code> and <code>x</code> share storage. <code>x = y^</code> and
<code>(a + b)^</code> are errors. Structs and classes copy on assignment and
when passed to a function, so a reference (or a direct field write) is how a
callee changes a caller's value. See <a href="references.html">References</a>.</p>
''' + pre('''def main() -> Int32
    n: Int32 = Int32("42")
    f: Float64 = Float64(n)
    print(n)
    print(f)
    return 0
''') + out('42\n42.000000') + '''
<p>More conversions and their error messages are on the
<a href="casts.html">Casts</a> page.</p>
'''),
        sec("collections", "Lists, dicts and iteration", '''
<p>List literals use <code>[a, b, c]</code>, dict literals use
<code>{"key": value}</code>. Indexing is <code>xs[0]</code> and a one-colon
slice is <code>xs[1:3]</code>; a step is not supported. Lists and dicts have
mutators such as <code>append</code>, <code>insert</code>, <code>remove</code>,
<code>pop</code>, <code>clear</code>, <code>get</code>, <code>keys</code> and
<code>values</code>; the <a href="containers.html">Containers</a> page lists
every method.</p>
<p><code>for x in xs:</code> visits list elements, dict keys, or a custom class
that provides <code>done()</code>, <code>value()</code> and
<code>advance()</code>. <code>range(n)</code>, <code>range(a, b)</code> and
<code>range(a, b, step)</code> are lowered to the std <code>Iterable</code>.
See <a href="flow.html#for">Flow</a>.</p>
'''),
        sec("operators", "Operators and precedence", '''
<p>From weakest to strongest binding:</p>
''' + table(["Level", "Operators", "Rule"], [
    ["1", "<code>or</code>", "left associative"],
    ["2", "<code>and</code>", "left associative"],
    ["3", "<code>not</code>", "prefix"],
    ["4", "<code>== != &lt; &gt; &lt;= &gt;=</code>", "one comparison split"],
    ["5", "<code>+ -</code>", "left associative"],
    ["6", "<code>* / // %</code>", "left associative"],
    ["7", "unary <code>-</code>", "lower than <code>**</code>: <code>-2 ** 2</code> is <code>-(2 ** 2)</code>"],
    ["8", "<code>**</code>", "right-recursive, but chained powers are rejected"],
    ["9", "calls, casts, parentheses, fields, indexes, slices", "postfix/primary"],
]) + '''
<p>Unary <code>+</code> is rejected. Both operands of an arithmetic or
comparison operator must have the same type. There are no bitwise operators:
<code>&amp;</code>, <code>|</code>, <code>~</code>, <code>&lt;&lt;</code> and
<code>&gt;&gt;</code> are not expressions. <code>|</code> separates union
members, and the opt-in <a href="bitops.html">bitops</a> module provides
<code>band</code>, <code>bor</code>, <code>bxor</code>, <code>bnot</code>,
<code>shl</code> and <code>shr</code> for <code>UInt32</code>.</p>
<p>A class can overload <code>== != &lt; &gt; &lt;= &gt;= + - * / // % **</code>,
unary <code>-</code>, <code>not</code>, and <code>[]</code> reads and writes
with dunder methods. Arithmetic overloads return the receiver's class,
<code>__eq__</code> must be pure, binary overloads are not inherited, and
slices are not overloadable. See <a href="classes.html#operators">Classes</a>.</p>
'''),
        sec("control", "Control flow", '''
<pre><code>if CONDITION:
    ...
elif CONDITION:
    ...
else:
    ...
while CONDITION:
    ...
for ITEM in COLLECTION:
    ...
return VALUE
break
continue</code></pre>
<p><code>return</code>, <code>break</code> and <code>continue</code> are
statements. Conditions must be <code>Bool</code>. Threads are module-level
only, take no parameters, and run while their <code>on</code> condition is
<code>True</code>; at most 1024 may exist and all are joined after
<code>main</code>. See <a href="threads.html">Threads</a>.</p>
'''),
        sec("records", "Structs, classes and operator overloading", '''
<pre><code>struct Point:
    x: Int32
    y: Int32

class Counter:
    n: Int32
    def __init__(self: Counter, start: Int32)
        self.n = start
    def bump(self: Counter) -&gt; Int32
        self.n = self.n + 1
        return self.n</code></pre>
<p>Structs are initialized with named fields: <code>Point(x=3, y=4)</code>.
Classes may have methods, inheritance, <code>__init__</code>,
<code>__str__</code> and operator dunders; the first parameter of a method is
the explicitly typed <code>self</code>. Both copy on assignment and on calls.
These are the verified results of the declarations above:</p>
''' + pre('''class Counter:
    n: Int32
    def __init__(self: Counter, start: Int32)
        self.n = start
    def bump(self: Counter) -> Int32
        self.n = self.n + 1
        return self.n

def main() -> Int32
    c: Counter = Counter(4)
    print(c.bump())
    return 0
''') + out('5') + '''
<p>Native modules can also declare classes. A manifest <code>class</code>
directive creates a real Threadon class with a hidden <code>__handle: String</code>
field, not a struct. See <a href="modules.html">Imports and native modules</a>.</p>
'''),
        sec("imports", "Imports, lazy imports and native modules", '''
<pre><code>import math
import stats as s
from strings import split, join
lazyimport heavy as h
lazyfrom heavy import prepare</code></pre>
<p>Imports are module-level only. Wildcard imports and imported variables are
rejected, and a trailing comma in an import list is rejected. Eager imports
load at compile time; <code>lazyimport</code> and <code>lazyfrom</code> defer
loading until a name from that module is actually used. Signatures, including
variadic ones, travel with the import.</p>
<p>A native module directory contains a file named <code>manifest</code> with
directives such as <code>module NAME</code>, <code>lang c|cpp|c++|rust|python|threadon</code>,
<code>source FILE</code>, <code>flag ...</code>, <code>link ...</code>,
<code>export NAME RET [ARGS...]</code>, <code>class NAME init [ARGS...]</code>
and <code>class NAME method METHOD [ARGS...] -&gt; RET</code>. C uses
<code>gcc</code>, C++ uses <code>g++</code>, Rust uses
<code>rustc --crate-type cdylib</code>, and Python uses a <code>g++</code>
bridge. Native memory is not managed by Threadon's collector. See
<a href="modules.html">Imports</a>.</p>
'''),
        sec("builtins", "Builtins and the auto-imported std lib", '''
<p>These seven functions are built into the language:</p>
''' + table(["Function", "Signature"], [
    ["<code>print</code>", "<code>(values: poly*) -> NoneType</code>"],
    ["<code>input</code>", "<code>(prompt: String) -> String</code>"],
    ["<code>len</code>", "<code>(coll: poly) -> Int64</code>; works on strings, lists and dicts"],
    ["<code>dict_key</code>", "<code>(dict: poly, index: Int64) -> poly</code>"],
    ["<code>chr</code>", "<code>(code: Int32) -> String</code>"],
    ["<code>thread_exit</code>", "<code>() -> NoneType</code>; ends the calling thread"],
    ["<code>collect</code>", "<code>() -> NoneType</code>; runs a full GC cycle"],
]) + '''
<p>The tiny <code>std</code> module is imported automatically. It provides
<code>abs</code>, <code>max</code>, <code>min</code>, <code>clamp</code>,
<code>is_even</code>, <code>is_odd</code>, <code>Iterable</code>,
<code>range</code>, and the <code>_i64</code> variants
<code>abs_i64</code>, <code>max_i64</code>, <code>min_i64</code>,
<code>clamp_i64</code>, plus <code>between</code>, <code>is_multiple</code>,
<code>square_int</code> and <code>diff_int</code>. See
<a href="stdlib.html">Std lib</a>; 26 more modules are opt-in on the
<a href="libraries.html">Libraries</a> page.</p>
'''),
        sec("tools", "Command line, tests and safety", '''
<pre><code>python3 -m threadon FILE.th [options]
python3 -m threadon test [-k PATTERN] [FILE.th ...]
threadon init NAME [--here] [--force] [--dir DIR]
threadon add NAME PATH
threadon build [flags]
threadon run [flags]
threadon test [flags]
threadon clean [--modules]
threadon cache path|list|clear</code></pre>
<p>Compiler options are <code>-o FILE</code>, <code>--run</code>,
<code>--run-tests</code>, <code>-k PATTERN</code>, <code>--exe FILE</code>,
repeatable <code>-I DIR</code>, <code>-O N</code> (default 0),
<code>--debug</code> and <code>--flag-inf</code>. <code>init NAME</code> creates
a new directory; <code>--here</code> keeps the old in-place behaviour. See
<a href="cli.html">CLI</a> and <a href="projects.html">Projects</a>.</p>
<p>A <code>test.th</code> file contains <code>def test_*() -> Bool</code>
functions plus optional <code>setup()</code> and <code>teardown()</code>. The
generated runner prints <code>[PASS]</code>/<code>[FAIL]</code> lines and exits
with the number of failures. See <a href="testing.html">Testing</a>.</p>
<p>Stack depth, empty <code>pop()</code>, the 1024-thread cap and integer
literal ranges are checked regardless of flags. <code>--debug</code> adds
overflow, division, cast, truncation, shift, index and key checks;
<code>--flag-inf</code> rejects non-finite floats. See
<a href="runtime.html">Runtime checks</a>.</p>
'''),
        sec("tour", "A complete program", '''
<p>This one file uses a struct, a typed local, a list loop, a named-field
initializer, a function call and an <code>f</code>-string:</p>
''' + pre('''struct Point:
    x: Int32
    y: Int32

def sq(p: Point) -> Int32
    return p.x * p.x + p.y * p.y

def main() -> Int32
    xs: List[Int32] = [1, 2, 3]
    total: Int32 = 0
    for x in xs:
        total += x
    p: Point = Point(x=3, y=4)
    print(total)
    print(sq(p))
    print(f"sum={total} len={len(xs)}")
    return 0
''') + out('6\n25\nsum=6 len=3') + '''
<p>Compile and run it with
<code>python3 -m threadon --run tour.th</code>, or build a native executable
with <code>python3 -m threadon --exe tour tour.th</code>.</p>
'''),
        sec("limits", "What is deliberately small", '''
<p>The full list is on <a href="limits.html">Limits</a>. The short version:</p>
''' + bullets([
    "No generics of your own, no type inference, no <code>var</code>, no enums and no <code>const</code>.",
    "No function values, lambdas, closures, multiple return values or function-name overloading.",
    "No exceptions or <code>try</code>; failing operations are compile-time diagnostics or explicit runtime errors.",
    "No automatic garbage collection: call <a href=\"gc.html\"><code>collect()</code></a> yourself.",
    "No bitwise operators; use the <a href=\"bitops.html\">bitops</a> module.",
    "No raw pointers or pointer arithmetic; <code>^</code> is the only reference form.",
    "No hex/binary/octal literals, no chained <code>**</code>, no unary <code>+</code> and no slice step.",
]) + '''
<p>That is the language. Every item above has a dedicated page linked from the
<a href="index.html">home page</a> and from the navigation bar.</p>
'''),
    ])
    return page(
        title="Language reference",
        description="Compact Threadon language reference: keywords, types, syntax, operators, declarations, builtins, CLI, tests, runtime checks and limits.",
        crumb="Reference",
        h1="Language reference",
        tag="every keyword, declaration, expression, builtin and command in one page",
        current="reference.html",
        body=body,
        back="projects.html", back_label="Projects",
        next_href="cheatsheet.html", next_label="Cheatsheet",
    )


NAV_BLOCK_RE = re.compile(r'<nav class="toc">.*?</nav>', re.S)


def migrate_existing_nav():
    """Replace inline nav bars with the shared mount point."""
    changed = 0
    for f in sorted(DOCS.glob("*.html")):
        if f.name == "nav.html":
            continue
        text = f.read_text()
        block = NAV_BLOCK_RE.search(text)
        if block is None:
            continue
        current = ""
        for tag in re.findall(r'<a\b[^>]*>', block.group(0)):
            if 'class="here"' in tag:
                m = re.search(r'href="([^"]+)"', tag)
                if m:
                    current = m.group(1)
                break
        mount = (
            f'<div id="site-nav" data-current="{current}"></div>\n'
            '<script src="nav.js"></script>'
        )
        f.write_text(text[:block.start()] + mount + text[block.end():])
        changed += 1
    return changed


def patch_existing():
    """Modernize hand-written pages; pages absent from a test fixture are skipped."""

    def patch_read(path):
        return path.read_text() if path.exists() else ""

    def patch_write(path, text):
        if path.exists():
            path.write_text(text)

    # Index: add a card to the tour and fix the old "no GC" claim.
    index = DOCS / "index.html"
    text = index.read_text()
    legacy_source_card = re.compile(
        r'[ \t]*<div class="card">\s*<h3><a href="source\.html">[^<]*</a></h3>'
        r'.*?</div>\n?',
        re.S,
    )
    text = legacy_source_card.sub("", text)
    text = text.replace(
        '<p>Threadon is a compiled programming language. It compiles down to LLVM IR, the intermediate language written by the LLVM project. That means no interpreter, no virtual machine, no garbage collector. The code you write is turned straight into native machine code.</p>',
        '<p>Threadon is a compiled programming language. It compiles down to LLVM IR, the intermediate language written by the LLVM project. That means no interpreter and no virtual machine. A <a href="gc.html">concurrent garbage collector</a> reclaims compiler-allocated heap memory. The code you write is turned straight into native machine code.</p>')
    text = text.replace(
        '<p>Threadon is a compiled programming language. It compiles down to LLVM IR, the intermediate language written by the LLVM project. That means no interpreter and no virtual machine. A <a href="gc.html">concurrent garbage collector</a> reclaims compiler-allocated heap memory. The code you write is turned straight into native machine code.</p>',
        '<p>Threadon is a compiled programming language. It compiles down to LLVM IR, the intermediate language written by the LLVM project. That means no interpreter and no virtual machine. Heap memory is reclaimed only when you call the explicit <a href="gc.html"><code>collect()</code></a> builtin. The code you write is turned straight into native machine code.</p>')
    new_cards = [
        ("libraries.html", "Libraries",
         "Twenty-six bundled modules for math, strings, data structures, encoding, dates, units, colors, tables, validation, graphs and more."),
        ("projects.html", "Projects",
         "Local <code>threadon.toml</code> projects, path dependencies, caches and the <code>init</code>/<code>build</code>/<code>run</code>/<code>test</code> commands."),
        ("performance.html", "Performance",
         "Which compiler mode to use, what <code>-O</code> changes, and how measurements are taken."),
        ("benchmarks.html", "Benchmarks",
         "Recorded results for eight workloads against C++ and Python, with checksums and full timing tables."),
        ("variadics.html", "Variadics",
         "Complete guide to <code>*args</code> and <code>**kwargs</code>: declaration order, spreading, methods and every error."),
        ("comptime.html", "Comptime",
         "Compute module-level constants while compiling, with one-line values or small block expressions."),
        ("reference.html", "Language reference",
         "Every keyword, type, expression, builtin and command in one compact page."),
        ("testing.html", "Testing",
         "The built-in <code>test.th</code> harness: <code>test_*</code> functions, setup, teardown and <code>-k</code> filtering."),
        ("runtime.html", "Runtime checks",
         "Always-on guards, every <code>--debug</code> check and the independent <code>--flag-inf</code> rule."),
    ]
    cards = "".join(
        f'    <div class="card">\n'
        f'      <h3><a href="{href}">{label}</a></h3>\n'
        f'      <p>{desc}</p>\n'
        f'    </div>\n'
        for href, label, desc in new_cards
        if f'href="{href}">{label}</a></h3>' not in text
    )
    if cards:
        marker = "  </div>\n</section>\n\n<section id=\"setup\">"
        if marker not in text:
            print("WARN: index cards marker not found")
        else:
            text = text.replace(marker, cards + marker, 1)
    index.write_text(text)

    # Std lib page: link to the bigger library collection.
    std = DOCS / "stdlib.html"
    text = std.read_text()
    marker = '<p class="pagenav">'
    extra = '''<section id="more">
  <h2>Beyond the std lib</h2>
  <p><code>std.th</code> is deliberately tiny. The <a href="libraries.html">Libraries</a> page documents twenty-six more bundled modules, from <a href="math.html">math</a> and <a href="lib-strings.html">strings</a> to <a href="base64.html">base64</a>, <a href="date.html">date</a>, <a href="graph.html">graph</a> and <a href="format.html">format</a>. Unlike <code>std</code>, you import them explicitly.</p>
</section>

'''
    if 'id="more"' not in text and marker in text:
        std.write_text(text.replace(marker, extra + marker, 1))

    # Imports page: mention the bundled libraries.
    mod = DOCS / "modules.html"
    text = patch_read(mod)
    marker = '<section id="rules">'
    extra = '''<section id="bundled">
  <h2>Bundled libraries</h2>
  <p>Threadon ships 26 opt-in modules in <code>stdlib/</code>, from <a href="libraries.html">math, strings and lists to base64, graph and validate</a>. They are found on the same search path and imported exactly like your own modules.</p>
  <pre><code><span class="tok-kw">import</span> math
<span class="tok-kw">from</span> strings <span class="tok-kw">import</span> split, join
<span class="tok-kw">import</span> stats <span class="tok-kw">as</span> s</code></pre>
</section>

'''
    if 'id="bundled"' not in text and marker in text:
        mod.write_text(text.replace(marker, extra + marker, 1))

    # Fix claims that are no longer true now that the libraries exist.
    lim = DOCS / "limits.html"
    text = patch_read(lim)
    text = text.replace(
        "<li><strong>No math library.</strong> No <code>sqrt</code>, <code>sin</code>, <code>cos</code>, <code>log</code>, <code>floor</code>, or <code>random</code>. Operators <code>+ - * / // % **</code> plus the standard library's <code>abs</code>, <code>max</code>, <code>min</code>, <code>clamp</code>, <code>is_even</code>, and <code>is_odd</code> are the whole arithmetic toolbox. See <a href=\"stdlib.html\">Std lib</a>.</li>",
        "<li><strong>No built-in math functions.</strong> Operators <code>+ - * / // % **</code> and the tiny <a href=\"stdlib.html\">std lib</a> are in the language itself. The <a href=\"math.html\">math</a>, <a href=\"stats.html\">stats</a> and <a href=\"random.html\">random</a> modules add powers, roots, rounding, statistics and a deterministic generator. There is still no <code>sin</code>, <code>cos</code> or <code>log</code>.</li>")
    text = text.replace(
        "<li><strong>No random numbers.</strong> There's no clock and no entropy source; generate any randomness yourself from arithmetic.</li>",
        "<li><strong>No true random numbers.</strong> There is no clock and no entropy source. The <a href=\"random.html\">random</a> module is a reproducible pseudo-random generator with a fixed default seed, not a source of entropy.</li>")
    text = text.replace(
        "Missing: <code>len</code>, iteration, searching, replacing, case conversion, trimming, splitting, and any formatting. Characters are read-only",
        "<code>len(s)</code> works now, but there is still no iteration. Searching, replacing, case conversion, trimming, splitting and padding live in the <a href=\"lib-strings.html\">strings</a> module, and number formatting in <a href=\"format.html\">format</a>. Characters are read-only")
    text = text.replace(
        "<li><strong>No garbage collector and no <code>free</code>.</strong> Strings, lists, and dicts allocate heap memory that is never reclaimed while the process runs. A long-running program can only grow.</li>",
        "<li><strong>No manual <code>free</code>.</strong> The <a href=\"gc.html\">garbage collector</a> reclaims strings, lists, dicts, thread closures and template objects allocated by the compiler. Memory owned by native modules (C/C++/Rust/Python) is not managed, and there is no user-level finalizer or destructor.</li>")
    text = text.replace(
        "<li><strong>No manual <code>free</code>.</strong> The <a href=\"gc.html\">garbage collector</a> reclaims strings, lists, dicts, thread closures and template objects allocated by the compiler. Memory owned by native modules (C/C++/Rust/Python) is not managed, and there is no user-level finalizer or destructor.</li>",
        "<li><strong>No manual <code>free</code>.</strong> Call the <a href=\"gc.html\"><code>collect()</code></a> builtin to reclaim strings, lists, dicts, thread closures and template objects allocated by the compiler. Nothing is reclaimed automatically. Memory owned by native modules (C/C++/Rust/Python) is not managed, and there is no user-level finalizer or destructor.</li>")
    patch_write(lim, text)

    builtins = DOCS / "builtins.html"
    text = patch_read(builtins)
    collect_section = '''<section id="collect">
  <h2>collect</h2>
  <p><code>collect()</code> takes no arguments and returns <code>NoneType</code>. It runs a full <a href="gc.html">garbage collection</a> synchronously: when it returns, all unreachable compiler-allocated heap memory has been reclaimed. Nothing is collected automatically.</p>
<pre><code><span class="tok-kw">def</span> <span class="tok-fn">main</span>() -&gt; <span class="tok-type">Int32</span>
    s: <span class="tok-type">String</span> = <span class="tok-str">""</span>
    i: <span class="tok-type">Int32</span> = <span class="tok-num">0</span>
    <span class="tok-kw">while</span> i &lt; <span class="tok-num">8000</span>:
        s = s + <span class="tok-str">"x"</span>
        <span class="tok-kw">if</span> i % <span class="tok-num">100</span> == <span class="tok-num">0</span>:
            collect()
        i += <span class="tok-num">1</span>
    collect()
    <span class="tok-kw">return</span> <span class="tok-num">0</span></code></pre>
  <p>Call it where you know a batch of temporary values is no longer needed: between loop iterations, after dropping a large list, or before a memory-sensitive phase. The runtime is added to the program only if it allocates or calls <code>collect()</code>. <code>THREADON_GC_STATS=1</code> prints collection statistics at exit.</p>
</section>

'''
    if 'id="collect"' not in text:
        marker = '<section id="casting-builtins">'
        if marker in text:
            text = text.replace(marker, collect_section + marker, 1)
        else:
            print("WARN: builtins collect marker not found")
    text = text.replace(
        "It only takes a <code>List</code> or a <code>Dict</code> &mdash; passing a <code>String</code> fails to compile with <code>Function 'len' expects a List or Dict, got String</code> (strings have no length function yet; the workaround is a manual loop, described on the <a href=\"strings.html#whats-missing\">Strings</a> page).",
        "It takes a <code>String</code>, <code>List</code> or <code>Dict</code>. For a string it returns the number of bytes.")
    patch_write(builtins, text)

    strings = DOCS / "strings.html"
    text = strings.read_text()
    text = text.replace(
        "<li><strong>No <code>len</code>.</strong> <code>len(s)</code> is a compile error &mdash; <code>len</code> accepts <code>List</code> and <code>Dict</code> only. See <a href=\"builtins.html#len\">Builtins</a>.</li>",
        "<li><strong>No built-in string methods.</strong> <code>len(s)</code> works and returns bytes; searching, case conversion, splitting and friends are in the <a href=\"lib-strings.html\">strings</a> library module (a different page from this one) &mdash; see <a href=\"libraries.html\">Libraries</a>.</li>")
    text = text.replace(
        "<li><strong>No searching, replacing, splitting, trimming, or case conversion.</strong> The standard library has no string methods.</li>",
        "<li><strong>Nothing built in for searching, replacing, splitting, trimming or case conversion.</strong> The <a href=\"lib-strings.html\">strings</a> module provides all of those; it is opt-in.</li>")
    strings.write_text(text)

    types = DOCS / "types.html"
    text = patch_read(types)
    text = text.replace(
        "What you can't do with a string: there's no <code>len</code>, no iterating with <code>for</code>, no editing of individual characters, and no searching or splitting.",
        "What you can't do with a string in the language itself: no iterating with <code>for</code>, no editing of individual characters, and no built-in searching or splitting. <code>len(s)</code> works, and the <a href=\"lib-strings.html\">strings</a> module adds the missing helpers.")
    patch_write(types, text)

    # Correct claims that the older hand-written pages got wrong.
    builtins = DOCS / "builtins.html"
    text = patch_read(builtins)
    text = text.replace(
        'name: <span class="tok-type">String</span> = input()',
        'name: <span class="tok-type">String</span> = input(<span class="tok-str">"Name: "</span>)',
    )
    patch_write(builtins, text)

    basics = DOCS / "basics.html"
    text = patch_read(basics)
    text = text.replace(
        '<p>Notice the <code>def</code> line ends with a colon, like Python. The body is indented. Indentation is what groups statements together, not curly braces.</p>',
        '<p>The header is <code>def name(...) -&gt; TYPE</code>: there is no colon after the <code>)</code>. The body is indented. Indentation is what groups statements together, not curly braces. Conditions in <code>if</code>, <code>elif</code>, <code>else</code>, <code>while</code> and <code>for</code> do end with a colon.</p>',
    )
    text = text.replace(
        '''  <p>A <code>.th</code> file is a list of top-level things. In any order:</p>
  <ul>
    <li><code>def</code> and <code>puredef</code> functions</li>
    <li><code>struct</code> types</li>
    <li><code>import</code> statements</li>
  </ul>
  <p>That's it. Code that runs must live inside a function. The only statements that can appear at the top level of a file are function definitions (plain or <code>puredef</code>), struct definitions, and imports.</p>''',
        '''  <p>A <code>.th</code> file is a list of top-level things. In any order:</p>
  <ul>
    <li>typed module variables with literal initializers</li>
    <li><code>def</code> and <code>puredef</code> functions</li>
    <li><code>struct</code> and <code>class</code> declarations</li>
    <li><code>thread</code> declarations and <code>comptime</code> constants</li>
    <li><code>import</code>, <code>from</code>, <code>lazyimport</code> and <code>lazyfrom</code> statements</li>
  </ul>
  <p>Code that runs must live inside a function or a thread body. A bare statement such as <code>x = 99</code> at module level is a compile error. For computed module values, use <a href="comptime.html"><code>comptime</code></a>.</p>''',
    )
    text = text.replace(
        'def if elif else while for in return and or not None class struct True False import from lazyimport lazyfrom as',
        'def puredef if elif else while for in return break continue and or not None class struct True False thread on comptime import from lazyimport lazyfrom as',
    )
    patch_write(basics, text)

    operators = DOCS / "operators.html"
    text = patch_read(operators)
    text = text.replace(
        '''    <tr><td>7</td><td><code>**</code> (right to left)</td></tr>
    <tr><td>8</td><td>unary <code>-</code> <code>+</code></td></tr>
    <tr><td>9</td><td>function calls, casts, parentheses, field access</td></tr>''',
        '''    <tr><td>7</td><td>unary <code>-</code> (lower than <code>**</code>)</td></tr>
    <tr><td>8</td><td><code>**</code> (right-recursive, but chained powers are rejected)</td></tr>
    <tr><td>9</td><td>function calls, casts, parentheses, field access, indexes, slices</td></tr>''',
    )
    text = text.replace(
        '<p>So <code>2 + 3 * 4</code> is <code>2 + (3 * 4)</code>, which is 14. And <code>not a and b</code> means <code>(not a) and b</code>.</p>',
        '<p>So <code>2 + 3 * 4</code> is <code>2 + (3 * 4)</code>, which is 14. And <code>not a and b</code> means <code>(not a) and b</code>. Unary <code>+</code> is rejected; <code>-2 ** 2</code> means <code>-(2 ** 2)</code>. See the <a href="reference.html#operators">language reference</a> for the full table.</p>',
    )
    patch_write(operators, text)

    lim = DOCS / "limits.html"
    text = patch_read(lim)
    text = text.replace(
        '<li><strong>No bitwise operators.</strong> No <code>&amp;</code>, <code>|</code>, <code>~</code>, <code>&lt;&lt;</code>, or <code>&gt;&gt;</code>; there\'s no way to manipulate individual bits.</li>',
        '<li><strong>No bitwise operators.</strong> No <code>&amp;</code>, <code>|</code>, <code>~</code>, <code>&lt;&lt;</code>, or <code>&gt;&gt;</code> in expressions. The opt-in <a href="bitops.html">bitops</a> module provides <code>band</code>, <code>bor</code>, <code>bxor</code>, <code>bnot</code>, <code>shl</code> and <code>shr</code> for <code>UInt32</code>.</li>',
    )
    text = text.replace(
        '<li><strong>No non-decimal literals.</strong> No <code>0x</code>, <code>0b</code>, or <code>0o</code>, and no exponent with a sign (<code>1e-3</code> is invalid). Digits, underscores, a dot, and a plain <code>e</code> are all you get.</li>',
        '<li><strong>No hex, binary or octal literals.</strong> Digits, underscores between digits, one dot, and an <code>e</code>/<code>E</code> exponent with an optional sign are supported, so <code>1e-3</code> is valid.</li>',
    )
    text = text.replace(
        '<li><strong>Integer arithmetic wraps.</strong> No range checks on <code>+</code>, <code>-</code>, <code>*</code>, or shifts (there are no shifts). The only overflow you can catch is a string-to-number cast under <code>--debug</code>. See <a href="types.html#ints">Types</a>.</li>',
        '<li><strong>Integer arithmetic wraps without <code>--debug</code>.</strong> That flag adds add/subtract/multiply/power overflow checks, division checks, cast and truncation checks, shift and negation checks, plus list, string and dict key checks. Some guards are always on; see <a href="runtime.html">Runtime checks</a>.</li>',
    )
    text = text.replace(
        '<li><strong>No enums.</strong> A fixed set of named values has to be spelled with constants written by hand &mdash; and there are no module-level constants either.</li>',
        '<li><strong>No enum type.</strong> A fixed set of named values has to be spelled out by hand, but <a href="comptime.html"><code>comptime</code></a> declarations provide computed module-level constants.</li>',
    )
    text = text.replace(
        '<li><strong>No overloading.</strong> Two functions can\'t share a name, and imported names can collide. A union parameter is the intended substitute. See <a href="unions.html">Unions</a>.</li>',
        '<li><strong>No function-name overloading.</strong> Two functions can\'t share a name, and imported names can collide. A union parameter is the intended substitute. Classes can still overload operators with <code>__add__</code>, <code>__eq__</code> and friends; see <a href="classes.html#operators">Classes</a>.</li>',
    )
    text = text.replace(
        '<li><strong>Runtime checks require <code>--debug</code>.</strong> Division by zero, bad string-to-number casts, out-of-bounds list reads <em>and string index reads</em>, and missing dict keys are undefined behavior without it. See <a href="debug.html">Debug</a>.</li>',
        '<li><strong>Many runtime checks require <code>--debug</code>.</strong> Division by zero, bad casts, out-of-bounds reads and missing dict keys are undefined without it. Stack depth, empty <code>pop()</code> and the 1024-thread cap are always checked, and integer literal ranges are compile errors. <code>--flag-inf</code> independently rejects non-finite floats. See <a href="runtime.html">Runtime checks</a>.</li>',
    )
    patch_write(lim, text)

    threads = DOCS / "threads.html"
    text = patch_read(threads)
    text = text.replace(
        '<p>You can spawn as many module-level threads as you like. They all run concurrently (subject to OS scheduling).</p>',
        '<p>You can spawn up to 1024 module-level threads. They all run concurrently (subject to OS scheduling); exceeding the limit raises <code>Error: too many threads (limit 1024)</code>. See <a href="runtime.html">Runtime checks</a>.</p>',
    )
    patch_write(threads, text)

    types = DOCS / "types.html"
    text = patch_read(types)
    text = text.replace(
        '<p>Threadon has sixteen built-in types.</p>',
        '<p>Threadon recognizes twenty type keywords: sixteen concrete scalar types plus the group aliases <code>Int</code>, <code>Float</code>, <code>Number</code> and <code>Builtin</code>. <code>List[T]</code> and <code>Dict[K, V]</code> are parameterized containers.</p>',
    )
    text = text.replace(
        '<p>If you go past the range of an integer you\'ll get an error if you\'ve enabled --debug and if you\'re using floats you will get an error if you use the flag --flag-inf.</p>',
        '<p>An integer literal outside its declared range is a compile error even without <code>--debug</code>. Runtime overflow and cast checks are added by <code>--debug</code>; float operations can be checked with the independent <code>--flag-inf</code> flag. See <a href="runtime.html">Runtime checks</a>.</p>',
    )
    patch_write(types, text)

    mod = DOCS / "modules.html"
    text = patch_read(mod)
    text = text.replace(
        '<p>C++ (lang cpp or lang c++) modules use g++ and can map external classes to Threadon structs.</p>',
        '<p>C++ (<code>lang cpp</code> or <code>lang c++</code>) modules use <code>g++</code> and can map external classes to Threadon classes with a hidden <code>__handle</code> field.</p>',
    )
    text = text.replace(
        '<p>In any of the backends, a <code>class</code> directive maps a foreign class to a Threadon struct. The struct has one hidden field holding an opaque handle to the foreign object. Calling the class runs the foreign constructor (with the <code>init</code> argument types), and methods declared with <code>class N method M [Args...] -&gt; Ret</code> become ordinary methods:</p>',
        '<p>In any backend, a <code>class</code> directive maps a foreign class to a Threadon class, not a struct. The class has one hidden <code>String</code> field named <code>__handle</code> that holds an opaque handle to the foreign object. Calling the class runs the foreign constructor (with the <code>init</code> argument types), and methods declared with <code>class N method M [Args...] -&gt; Ret</code> become ordinary methods:</p>',
    )
    patch_write(mod, text)

    diag = DOCS / "diagnostics.html"
    text = patch_read(diag)
    text = text.replace(
        '<p>Colors are optional. <code>NO_COLOR=1</code> disables them; <code>FORCE_COLOR=0</code> does the same. On a terminal the label is colored and bold, but the text is otherwise identical. Redirecting output should not change what a script can parse.</p>',
        '<p>Colors are optional. A truthy <code>NO_COLOR</code> disables them; a truthy <code>FORCE_COLOR</code> enables them, and <code>FORCE_COLOR=0</code> is false/off, not a disable switch. The default is whether stderr is a terminal. On a terminal the label is colored and bold, but the text is otherwise identical. Redirecting output should not change what a script can parse.</p>',
    )
    text = text.replace(
        '<p>Runtime errors from a generated program are emitted by LLVM code and keep their own message strings. They are deliberately not wrapped in <code>Error:</code>, because they are not compiler diagnostics. Use <a href="debug.html">debug mode</a> to turn some silent undefined behavior into explicit runtime checks, and <code>--flag-inf</code> for non-finite floats.</p>',
        '<p>Runtime errors from a generated program are emitted by generated code, not by the diagnostic formatter. The formatter prints a <code>[RUNTIME ERROR]</code> banner and normally starts the payload with <code>Error: ...</code>. They are still separate from compiler diagnostics; see <a href="runtime.html">Runtime checks</a>. Use <a href="debug.html">debug mode</a> to turn silent undefined behavior into checks, and <code>--flag-inf</code> for non-finite floats.</p>',
    )
    patch_write(diag, text)

    debug = DOCS / "debug.html"
    text = patch_read(debug)
    text = text.replace(
        '<p>Four kinds of checks get added:</p>',
        '<p>Many checks get added: integer add/subtract/multiply/power overflow, runtime division checks, string and numeric conversion checks, truncation and float-to-int checks, shift and negation checks, and list, string and dict key checks. The complete list is on the <a href="runtime.html">Runtime checks</a> page.</p>',
    )
    patch_write(debug, text)

    exc = DOCS / "exceptions.html"
    text = patch_read(exc)
    text = text.replace(
        '<p>The full list and the exact messages are on the <a href="debug.html">Debug</a> page. Without <code>--debug</code>, most of these checks are absent and the behavior is undefined. <code>--flag-inf</code> is independent of debug mode.</p>',
        '<p>The full list and exact messages are on the <a href="runtime.html">Runtime checks</a> page. Some checks need <code>--debug</code>, some are always on, and integer literal ranges are compile errors. <code>--flag-inf</code> is independent of debug mode.</p>',
    )
    patch_write(exc, text)

    cli = DOCS / "cli.html"
    text = patch_read(cli)
    if '<code>--run-tests</code>' not in text:
        text = text.replace(
            '    <tr><td><code>--run</code></td><td>Execute the program with <code>lli</code> after compiling.</td></tr>',
            '    <tr><td><code>--run</code></td><td>Execute the program with <code>lli</code> after compiling.</td></tr>\n'
            '    <tr><td><code>--run-tests</code></td><td>Build and run every discovered <code>test.th</code> suite.</td></tr>\n'
            '    <tr><td><code>-k PATTERN</code> / <code>--test-name PATTERN</code></td><td>With <code>--run-tests</code> (or on a <code>test.th</code> file), run only tests whose name contains <code>PATTERN</code>.</td></tr>',
        )
    patch_write(cli, text)

    functions = DOCS / "functions.html"
    text = patch_read(functions)
    if 'href="variadics.html"' not in text:
        text = text.replace(
            '<p>At a call site, <code>*xs</code> and <code>**opts</code> pass whole containers of the right type. They cannot be mixed with extra positional values or keyword literals, and only one of each is allowed. Builtins, list mutators, <code>range()</code> and native calls do not accept keyword or spread arguments.</p>',
            '<p>At a call site, <code>*xs</code> and <code>**opts</code> pass whole containers of the right type. They cannot be mixed with extra positional values or keyword literals, and only one of each is allowed. Builtins, list mutators, <code>range()</code> and native calls do not accept keyword or spread arguments. For declaration rules, methods, imports and every error message, see the full <a href="variadics.html">Variadics</a> guide.</p>',
        )
    patch_write(functions, text)

    cli = DOCS / "cli.html"
    if cli.exists():
        text = patch_read(cli)
        marker = '<p class="pagenav">'
        extra = '''<section id="related">
  <h2>Related guides</h2>
  <p>Projects add local packages and a compile cache around this command line. See <a href="projects.html">Projects</a> for <code>init</code>, <code>add</code>, <code>build</code>, <code>run</code>, <code>test</code>, <code>clean</code> and <code>cache</code>.</p>
  <p>For compiler modes, tuning knobs and the recorded timing tables, read <a href="performance.html">Performance</a> and <a href="benchmarks.html">Benchmark results</a>. Compiler messages are standardised; see <a href="diagnostics.html">Diagnostics</a>.</p>
</section>

'''
        if 'id="related"' not in text and marker in text:
            cli.write_text(text.replace(marker, extra + marker, 1))

    lim = DOCS / "limits.html"
    if lim.exists():
        text = patch_read(lim)
        marker = '<p class="pagenav">'
        extra = '''<section id="performance-results">
  <h2>Performance is measured, not guessed</h2>
  <p>The native executable is often as fast as or faster than <code>g++ -O2</code> on numeric loops; the JIT path pays process startup on every run. The exact medians, checksums and ratios are on the <a href="benchmarks.html">Benchmark results</a> page, with the measurement rules on <a href="performance.html">Performance</a>.</p>
</section>

'''
        if 'id="performance-results"' not in text and marker in text:
            lim.write_text(text.replace(marker, extra + marker, 1))


def patch_style():
    """Add styling for generated diagnostic and benchmark tables."""
    css = DOCS / "style.css"
    if not css.exists():
        return
    text = css.read_text()
    old_marker = "/* generated source browser */"
    if old_marker in text:
        text = text[:text.index(old_marker)].rstrip() + "\n"
    marker = "/* generated guide styles */"
    if marker in text:
        css.write_text(text)
        return
    text += '''
''' + marker + '''
pre.msg {
  background: var(--code-bg);
  color: #fca5a5;
}
.good { color: #15803d; font-weight: 600; }
.bad { color: #b91c1c; font-weight: 600; }
'''
    css.write_text(text)


def main():
    for stale in DOCS.glob("src-*.html"):
        stale.unlink()
    legacy_source_hub = DOCS / "source.html"
    if legacy_source_hub.exists():
        legacy_source_hub.unlink()
    (DOCS / "nav.html").write_text(nav_fragment())
    (DOCS / "nav.js").write_text(nav_loader_js())
    (DOCS / "libraries.html").write_text(hub_page())
    for i, lib in enumerate(LIBS):
        (DOCS / f"{lib['key']}.html").write_text(library_page(lib, i))
    (DOCS / "gc.html").write_text(gc_page())
    guides = {
        "variadics.html": variadics_page(),
        "comptime.html": comptime_page(),
        "reference.html": reference_page(),
        "projects.html": projects_page(),
        "testing.html": testing_page(),
        "cheatsheet.html": cheatsheet_page(),
        "cookbook.html": cookbook_page(),
        "diagnostics.html": diagnostics_page(),
        "faq.html": faq_page(),
        "performance.html": performance_page(),
        "runtime.html": runtime_page(),
        "benchmarks.html": benchmarks_page(),
    }
    for name, content in guides.items():
        (DOCS / name).write_text(content)
    migrated = migrate_existing_nav()
    patch_existing()
    patch_style()
    written = 4 + len(LIBS) + len(guides)  # nav.html, nav.js, libraries.html, gc.html
    print(
        f"wrote {written} files; "
        f"replaced inline nav in {migrated} pages"
    )


if __name__ == "__main__":
    main()
