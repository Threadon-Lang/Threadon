"""Compile and run the code examples in the documentation.

Every ``<pre><code>`` block followed by an ``out`` div is accounted for.  The
registry below marks examples that are not standalone programs, examples that
document an error, and examples that are currently broken.  The tests check both
directions: normal examples must keep working, and registered examples must
keep being non-runnable/broken, so fixing one forces the registry to be updated.
"""
import hashlib
import html
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from compile_test import run_llvm
from compiler.threadon.compiler import compile_source
from compiler.threadon.importer import Importer

DOCS = Path(__file__).resolve().parents[2] / "Threadon-Lang.github.io"
BLOCK_RE = re.compile(r"<pre><code>(.*?)</code></pre>", re.S)
OUT_RE = re.compile(r'\s*<div class="out">(.*?)</div>', re.S)


def examples():
    """Yield (page, index) -> (source, expected output) for every doc example."""
    for page in sorted(DOCS.glob("*.html")):
        text = page.read_text()
        index = 0
        for block in BLOCK_RE.finditer(text):
            out = OUT_RE.match(text, block.end())
            if out is None:
                continue
            source = html.unescape(re.sub(r"<[^>]+>", "", block.group(1))).strip("\n")
            expected = html.unescape(re.sub(r"<[^>]+>", "", out.group(1))).strip("\n")
            yield (page.name, index), source, expected
            index += 1


EXAMPLES = dict((key, (source, expected)) for key, source, expected in examples())


def fingerprint(source):
    return hashlib.sha1(source.encode()).hexdigest()[:8]


# Fragments that can be run by wrapping the shown lines in a main function.
WRAPPED = {
    ("builtins.html", 0): ("8984c569", "print() with mixed value types"),
    ("builtins.html", 1): ("4663be54", "print() with spaces"),
    ("builtins.html", 4): ("990d07b9", "len() on a list"),
    ("builtins.html", 5): ("ceee41eb", "dict_key()"),
    ("builtins.html", 6): ("c80593a0", "chr()"),
}

# Thread examples: all expected lines must appear, order is scheduler-dependent.
UNORDERED = {
    ("threads.html", 0): ("491ddec3", "main/thread print order is scheduler-dependent"),
    ("threads.html", 1): ("10522cf7", "thread_exit() print order varies"),
    ("threads.html", 3): ("09808486", "three threads plus main, print order varies"),
}

# Examples that document a compiler error; the expected output is the message.
EXPECTED_ERRORS = {
    ("types.html", 0): ("291d5eff", "out of range for type 'Int8'"),
    ("unions.html", 3): ("aa948526", "Type mismatch in arithmetic"),
    ("unions.html", 5): ("0d0926cd", "expects type Int32, got Float32"),
    ("unions.html", 6): ("56e50164", "expects type Int32, got Union"),
}

# Examples that should work but currently fail to compile.
COMPILE_BROKEN = {
    ("classes.html", 0): ("3acfc17d", "Point has no length() method"),
    ("classes.html", 1): ("23dbb223", "snippet references Point without defining it"),
    ("examples.html", 2): ("730223df", "math.clamp does not exist (std.clamp is auto-imported)"),
    ("examples.html", 3): ("4f821f59", "geom module is not bundled"),
    ("examples.html", 9): ("3904ff5f", "cadd native module not present in this checkout"),
    ("examples.html", 10): ("92fe67dd", "cpppow native module not present in this checkout"),
    ("examples.html", 11): ("695b4e69", "rsum native module not present in this checkout"),
    ("examples.html", 12): ("ef84c0ed", "PyAdd native module not present in this checkout"),
    ("examples.html", 14): ("3b8adbc6", "PyVec3 native module not present in this checkout"),
    ("functions.html", 0): ("8ee0a3de", "calls undefined add()"),
    ("modules.html", 0): ("730223df", "math.clamp does not exist"),
    ("structs.html", 0): ("9a396abe", "snippet references Point without defining it"),
}

# Examples that compile but fail while running, usually due to a compiler bug.
RUNTIME_BROKEN = {
    ("functions.html", 4): ("56ecfd7e", "union arithmetic emits invalid LLVM shl"),
    ("unions.html", 8): ("2310b3ff", "union arithmetic emits invalid LLVM shl"),
}

# Examples that run but print something different from the documented output.
OUTPUT_BROKEN = {
    ("functions.html", 1): ("2da3ee02", "docs expect 'Joep', the example prints 'John'"),
}

# Snippets, shell commands and demos that are not standalone runnable programs.
FRAGMENTS = {
    ("basics.html", 0): ("2040cca9", "shell command"),
    ("builtins.html", 3): ("9ad2886a", "needs stdin input"),
    ("classes.html", 4): ("6ca891a7", "native torch example, needs the native toolchain"),
    ("cli.html", 0): ("12b2d03a", "shell command"),
    ("examples.html", 5): ("53bed9a9", "needs stdin input"),
    ("examples.html", 6): ("cd087df1", "expression fragment; expected Bool output is stale"),
    ("examples.html", 7): ("3a0da0a7", "shell command"),
    ("examples.html", 8): ("c2179afd", "stack-overflow demo, no main and a runtime error"),
    ("index.html", 1): ("2040cca9", "shell command"),
    ("operators.html", 1): ("5acea36e", "needs stdin input"),
    ("types.html", 1): ("d8c17b48", "needs stdin input"),
    ("types.html", 4): ("140c6658", "fragment references undefined name"),
}

REGISTRIES = {
    "WRAPPED": WRAPPED,
    "UNORDERED": UNORDERED,
    "EXPECTED_ERRORS": EXPECTED_ERRORS,
    "COMPILE_BROKEN": COMPILE_BROKEN,
    "RUNTIME_BROKEN": RUNTIME_BROKEN,
    "OUTPUT_BROKEN": OUTPUT_BROKEN,
    "FRAGMENTS": FRAGMENTS,
}

REGISTERED = set().union(*(set(registry) for registry in REGISTRIES.values()))
NORMAL = sorted(set(EXAMPLES) - REGISTERED)


def test_all_documentation_examples_are_discovered():
    assert len(EXAMPLES) >= 111, "docs markup changed or examples were removed"
    assert not (REGISTERED - set(EXAMPLES)), "a registered example disappeared from the docs"


@pytest.mark.parametrize("registry_name", sorted(REGISTRIES))
def test_registry_fingerprints_are_current(registry_name):
    for key, (expected_hash, reason) in REGISTRIES[registry_name].items():
        source, _ = EXAMPLES[key]
        assert fingerprint(source) == expected_hash, (
            f"{key} changed ({reason}); update its fingerprint and classification"
        )


@pytest.mark.parametrize("key", NORMAL, ids=lambda key: f"{key[0]}:{key[1]}")
def test_doc_example_runs_and_prints_expected_output(key):
    source, expected = EXAMPLES[key]
    result = run_llvm(compile_source(source, importer=Importer()))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip("\n") == expected


@pytest.mark.parametrize("key", sorted(WRAPPED), ids=lambda key: f"{key[0]}:{key[1]}")
def test_wrapped_doc_fragment_runs_and_prints_expected_output(key):
    source, expected = EXAMPLES[key]
    wrapped = "def main() -> Int32\n" + "".join(
        "    " + line + "\n" if line else "\n" for line in source.splitlines()
    ) + "    return 0\n"
    result = run_llvm(compile_source(wrapped, importer=Importer()))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip("\n") == expected


@pytest.mark.parametrize("key", sorted(UNORDERED), ids=lambda key: f"{key[0]}:{key[1]}")
def test_thread_doc_example_prints_all_expected_lines(key):
    source, expected = EXAMPLES[key]
    result = run_llvm(compile_source(source, importer=Importer()))
    assert result.returncode == 0, result.stderr
    assert sorted(result.stdout.splitlines()) == sorted(expected.splitlines())


@pytest.mark.parametrize("key", sorted(EXPECTED_ERRORS), ids=lambda key: f"{key[0]}:{key[1]}")
def test_doc_example_documents_a_compile_error(key):
    source, _ = EXAMPLES[key]
    needle = EXPECTED_ERRORS[key][1]
    with pytest.raises(RuntimeError) as excinfo:
        compile_source(source, importer=Importer())
    assert needle in str(excinfo.value)


@pytest.mark.parametrize("key", sorted(COMPILE_BROKEN), ids=lambda key: f"{key[0]}:{key[1]}")
def test_known_broken_doc_example_still_fails_to_compile(key):
    source, _ = EXAMPLES[key]
    with pytest.raises(Exception) as excinfo:
        compile_source(source, importer=Importer())
    assert str(excinfo.value)


@pytest.mark.parametrize("key", sorted(RUNTIME_BROKEN), ids=lambda key: f"{key[0]}:{key[1]}")
def test_known_broken_doc_example_still_fails_at_runtime(key):
    source, _ = EXAMPLES[key]
    result = run_llvm(compile_source(source, importer=Importer()))
    assert result.returncode != 0


@pytest.mark.parametrize("key", sorted(OUTPUT_BROKEN), ids=lambda key: f"{key[0]}:{key[1]}")
def test_known_broken_doc_example_still_prints_wrong_output(key):
    source, expected = EXAMPLES[key]
    result = run_llvm(compile_source(source, importer=Importer()))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip("\n") != expected


@pytest.mark.parametrize("key", sorted(FRAGMENTS), ids=lambda key: f"{key[0]}:{key[1]}")
def test_fragment_doc_example_is_still_not_a_standalone_program(key):
    source, _ = EXAMPLES[key]
    assert (
        "def main" not in source
        or "input(" in source
        or source.lstrip().startswith(("python3", "THREADON", "sudo"))
    )
