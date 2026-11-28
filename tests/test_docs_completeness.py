"""Completeness checks for the expanded language documentation."""
import html
import importlib.util
import re
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT.parent / "Threadon-Lang.github.io"
GEN_DOCS_PATH = ROOT / "gen_docs.py"

if not DOCS.is_dir():
    pytest.skip("documentation site checkout is not available", allow_module_level=True)
if not GEN_DOCS_PATH.is_file():
    pytest.skip("docs generator fixture (gen_docs.py) is not available", allow_module_level=True)

SPEC = importlib.util.spec_from_file_location("threadon_gen_docs_completeness", GEN_DOCS_PATH)
gen_docs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gen_docs)

NEW_PAGES = ("variadics.html", "comptime.html", "reference.html",
             "testing.html", "runtime.html")


def read(name):
    return (DOCS / name).read_text()


def plain(name):
    """Strip markup and entities for prose assertions."""
    return html.unescape(re.sub(r"<[^>]+>", "", read(name)))


@pytest.mark.parametrize("name", NEW_PAGES)
def test_new_guide_pages_exist(name):
    assert (DOCS / name).is_file()


def test_shared_nav_links_every_new_page():
    nav_text = read("nav.html")
    for name in NEW_PAGES:
        assert f'href="{name}"' in nav_text


def test_generator_main_writes_new_guide_pages(tmp_path, monkeypatch):
    for page in DOCS.glob("*.html"):
        shutil.copy(page, tmp_path / page.name)
    monkeypatch.setattr(gen_docs, "DOCS", tmp_path)

    gen_docs.main()

    generators = {
        "variadics.html": gen_docs.variadics_page,
        "comptime.html": gen_docs.comptime_page,
        "reference.html": gen_docs.reference_page,
        "testing.html": gen_docs.testing_page,
        "runtime.html": gen_docs.runtime_page,
    }
    for name, build in generators.items():
        assert (tmp_path / name).read_text() == build()
    assert "variadics.html" in (tmp_path / "nav.html").read_text()


def test_variadics_page_is_a_complete_reference():
    text = read("variadics.html")
    for heading in ("Declaring <code>*args</code>", "Declaring <code>**kwargs</code>",
                    "Using <code>*args</code> and <code>**kwargs</code> together",
                    "Spreading containers at the call site", "Methods and constructors",
                    "Imports, lazy imports and inlining", "Rules at a glance",
                    "Error messages you may see", "How a variadic call is bound"):
        assert heading in text
    prose = plain("variadics.html")
    for message in ("*args parameter must have type List[T]",
                    "**kwargs parameter must have type Dict[String, T]",
                    "Variadic parameters must come last, *args before **kwargs",
                    "got an unexpected keyword argument",
                    "got multiple values for argument 'a'",
                    "cannot mix extra positional arguments with *arguments",
                    "cannot mix keyword arguments with **keyword arguments",
                    "Builtin 'name' does not accept keyword or spread arguments"):
        assert message in prose


def test_comptime_page_documents_both_forms_and_limits():
    text = read("comptime.html")
    assert "comptime NAME: TYPE = EXPRESSION" in text
    assert "comptime block requires explicit type annotation" in text
    assert "comptime statements are only allowed at module level" in text
    assert "1,000,000" in text
    assert "Function 'f' not available at compile time" in text
    assert "String globals not yet supported" in text


def test_testing_page_documents_the_harness_and_filters():
    prose = plain("testing.html")
    assert "def test_sum() -> Bool" in prose
    assert "setup() -> Bool" in prose and "teardown() -> Bool" in prose
    assert "[PASS]" in prose and "[FAIL]" in prose
    assert "--run-tests" in prose and "-k PATTERN" in prose
    assert "no test.th files found" in prose
    assert "(no tests match 'PATTERN')" in prose


def test_runtime_page_lists_all_check_classes():
    text = read("runtime.html")
    for needle in ("[RUNTIME ERROR]", "always on", "stack overflow detected",
                   "pop on empty list", "too many threads (limit 1024)",
                   "Integer overflow in addition", "Division by zero",
                   "List index out of bounds", "KeyError: dict key not found",
                   "--flag-inf", "Non-finite float value"):
        assert needle in text


def test_reference_page_covers_every_keyword_group_and_builtin():
    text = read("reference.html")
    for word in ("puredef", "break", "continue", "thread", "on", "comptime",
                 "lazyimport", "lazyfrom"):
        assert word in text
    assert "no colon" in text
    assert "Builtin" in text and "Dict[K, V]" in text
    assert "input</code>" in text and "(prompt: String) -> String" in text
    for builtin in ("print", "len", "dict_key", "chr", "thread_exit", "collect"):
        assert f"<code>{builtin}</code>" in text
    for flag in ("--run-tests", "--exe FILE", "--debug", "--flag-inf"):
        assert flag in text
    assert "func_sigs" not in text and "to_llvm_ir" not in text


@pytest.mark.parametrize("name,stale,fresh", [
    ("basics.html", "ends with a colon, like Python", "there is no colon after the <code>)</code>"),
    ("builtins.html", '= input()', 'input(<span class="tok-str">"Name: "</span>)'),
    ("diagnostics.html", "FORCE_COLOR=0</code> does the same", "truthy <code>FORCE_COLOR</code> enables them"),
    ("operators.html", "unary <code>-</code> <code>+</code>", "unary <code>-</code> (lower than <code>**</code>)"),
    ("limits.html", "no exponent with a sign", "<code>1e-3</code> is valid"),
    ("limits.html", "and there are no module-level constants either", "computed module-level constants"),
    ("limits.html", "Runtime checks require <code>--debug</code>", "Many runtime checks require"),
    ("threads.html", "as many module-level threads as you like", "up to 1024 module-level threads"),
    ("types.html", "Threadon has sixteen built-in types.", "twenty type keywords"),
    ("modules.html", "maps a foreign class to a Threadon struct", "to a Threadon class, not a struct"),
    ("debug.html", "Four kinds of checks get added", "Many checks get added"),
    ("exceptions.html", "The full list and the exact messages are on the <a href=\"debug.html\">Debug</a> page",
     "The full list and exact messages are on the <a href=\"runtime.html\">Runtime checks</a> page"),
    ("functions.html", "href=\"variadics.html\"", "href=\"variadics.html\""),
])
def test_outdated_claims_were_corrected(name, stale, fresh):
    text = read(name)
    if stale == fresh:
        assert fresh in text
    else:
        assert stale not in text
        assert fresh in text


def test_cli_page_lists_test_flags():
    prose = plain("cli.html")
    assert "--run-tests" in prose
    assert "-k PATTERN" in prose
    assert "--test-name PATTERN" in prose


def test_index_tour_links_new_pages():
    text = read("index.html")
    for name in NEW_PAGES:
        assert f'href="{name}"' in text
