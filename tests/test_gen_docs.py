"""Behavioral tests for the documentation generator and its legacy migration."""
import importlib.util
import shutil
from pathlib import Path

import pytest

GEN_DOCS_PATH = Path(__file__).resolve().parents[1] / "gen_docs.py"
if not GEN_DOCS_PATH.is_file():
    pytest.skip("docs generator fixture (gen_docs.py) is not available", allow_module_level=True)
SPEC = importlib.util.spec_from_file_location("threadon_gen_docs_test", GEN_DOCS_PATH)
gen_docs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gen_docs)


def test_generator_writes_every_docs_page(tmp_path, monkeypatch, capsys):
    source_docs = gen_docs.DOCS
    for page in source_docs.glob("*.html"):
        shutil.copy(page, tmp_path / page.name)
    monkeypatch.setattr(gen_docs, "DOCS", tmp_path)

    gen_docs.main()

    assert (tmp_path / "nav.html").read_text() == gen_docs.nav_fragment()
    assert (tmp_path / "nav.js").read_text() == gen_docs.nav_loader_js()
    hub = (tmp_path / "libraries.html").read_text()
    for lib in gen_docs.LIBS:
        assert f'href="{lib["key"]}.html"' in hub
        assert (tmp_path / f"{lib['key']}.html").exists()
    gc = (tmp_path / "gc.html").read_text()
    assert "collect()" in gc
    assert "THREADON_GC_STATS" in gc
    assert "wrote" in capsys.readouterr().out


def test_migrate_existing_nav_replaces_one_inline_bar(tmp_path, monkeypatch):
    monkeypatch.setattr(gen_docs, "DOCS", tmp_path)
    (tmp_path / "nav.html").write_text('<nav class="toc">shared</nav>')
    old = (
        '<nav class="toc"><div class="wrap links">'
        '<a href="index.html">Home</a>'
        '<a class="here" href="basics.html">Basics</a>'
        '</div></nav>\n<main>Basics body</main>'
    )
    (tmp_path / "basics.html").write_text(old)
    plain = "<main>No navigation here</main>"
    (tmp_path / "plain.html").write_text(plain)

    assert gen_docs.migrate_existing_nav() == 1

    migrated = (tmp_path / "basics.html").read_text()
    assert '<nav class="toc">' not in migrated
    assert '<div id="site-nav" data-current="basics.html"></div>' in migrated
    assert '<script src="nav.js"></script>' in migrated
    assert "<main>Basics body</main>" in migrated
    assert (tmp_path / "plain.html").read_text() == plain


def test_patch_existing_modernizes_legacy_pages(tmp_path, monkeypatch):
    monkeypatch.setattr(gen_docs, "DOCS", tmp_path)
    (tmp_path / "index.html").write_text(
        '<p>Threadon is a compiled programming language. It compiles down to '
        'LLVM IR, the intermediate language written by the LLVM project. That '
        'means no interpreter, no virtual machine, no garbage collector. The '
        'code you write is turned straight into native machine code.</p>\n'
        '  </div>\n</section>\n\n<section id="setup">'
    )
    (tmp_path / "stdlib.html").write_text('<p class="pagenav">next</p>')
    (tmp_path / "modules.html").write_text('<section id="rules">rules</section>')
    (tmp_path / "limits.html").write_text("\n".join([
        "<li><strong>No math library.</strong> No <code>sqrt</code>, <code>sin</code>, <code>cos</code>, <code>log</code>, <code>floor</code>, or <code>random</code>. Operators <code>+ - * / // % **</code> plus the standard library's <code>abs</code>, <code>max</code>, <code>min</code>, <code>clamp</code>, <code>is_even</code>, and <code>is_odd</code> are the whole arithmetic toolbox. See <a href=\"stdlib.html\">Std lib</a>.</li>",
        "<li><strong>No random numbers.</strong> There's no clock and no entropy source; generate any randomness yourself from arithmetic.</li>",
        "Missing: <code>len</code>, iteration, searching, replacing, case conversion, trimming, splitting, and any formatting. Characters are read-only",
        "<li><strong>No garbage collector and no <code>free</code>.</strong> Strings, lists, and dicts allocate heap memory that is never reclaimed while the process runs. A long-running program can only grow.</li>",
    ]))
    (tmp_path / "builtins.html").write_text(
        '<section id="casting-builtins">casts</section>\n'
        'It only takes a <code>List</code> or a <code>Dict</code> &mdash; passing '
        'a <code>String</code> fails to compile with <code>Function \'len\' '
        'expects a List or Dict, got String</code> (strings have no length '
        'function yet; the workaround is a manual loop, described on the '
        '<a href="strings.html#whats-missing">Strings</a> page).'
    )
    (tmp_path / "strings.html").write_text("\n".join([
        "<li><strong>No <code>len</code>.</strong> <code>len(s)</code> is a compile error &mdash; <code>len</code> accepts <code>List</code> and <code>Dict</code> only. See <a href=\"builtins.html#len\">Builtins</a>.</li>",
        "<li><strong>No searching, replacing, splitting, trimming, or case conversion.</strong> The standard library has no string methods.</li>",
    ]))
    (tmp_path / "types.html").write_text(
        "What you can't do with a string: there's no <code>len</code>, no "
        "iterating with <code>for</code>, no editing of individual characters, "
        "and no searching or splitting."
    )

    gen_docs.patch_existing()

    index = (tmp_path / "index.html").read_text()
    assert "explicit <a href=\"gc.html\"><code>collect()</code></a>" in index
    assert 'href="libraries.html">Libraries</a></h3>' in index
    assert 'id="more"' in (tmp_path / "stdlib.html").read_text()
    assert 'id="bundled"' in (tmp_path / "modules.html").read_text()
    limits = (tmp_path / "limits.html").read_text()
    assert "No built-in math functions." in limits
    assert "No true random numbers." in limits
    assert "len(s)</code> works now" in limits
    assert "Call the <a href=\"gc.html\"><code>collect()</code></a>" in limits
    builtins = (tmp_path / "builtins.html").read_text()
    assert 'id="collect"' in builtins
    assert "It takes a <code>String</code>, <code>List</code> or <code>Dict</code>." in builtins
    strings = (tmp_path / "strings.html").read_text()
    assert "No built-in string methods." in strings
    assert "The <a href=\"lib-strings.html\">strings</a> module provides" in strings
    assert "What you can't do with a string in the language itself:" in (
        tmp_path / "types.html"
    ).read_text()


def test_patch_existing_warns_when_insertion_markers_are_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gen_docs, "DOCS", tmp_path)
    for name in (
        "index.html", "stdlib.html", "modules.html", "limits.html",
        "builtins.html", "strings.html", "types.html",
    ):
        (tmp_path / name).write_text("<main>legacy page</main>")

    gen_docs.patch_existing()

    warnings = capsys.readouterr().out
    assert "WARN: index cards marker not found" in warnings
    assert "WARN: builtins collect marker not found" in warnings


def test_generator_removes_legacy_source_browser(tmp_path, monkeypatch):
    source_docs = gen_docs.DOCS
    for page in source_docs.glob("*.html"):
        shutil.copy(page, tmp_path / page.name)
    index = tmp_path / "index.html"
    text = index.read_text()
    stale_card = (
        '    <div class="card">\n'
        '      <h3><a href="source.html">Source</a></h3>\n'
        '      <p>Line-numbered compiler, library, benchmark and test sources '
        'generated from this checkout.</p>\n'
        '    </div>\n'
    )
    marker = '  </div>\n</section>\n\n<section id="setup">'
    assert marker in text
    index.write_text(text.replace(marker, stale_card + marker, 1))
    (tmp_path / "source.html").write_text("old source hub")
    (tmp_path / "src-compiler-old.html").write_text("old source page")

    monkeypatch.setattr(gen_docs, "DOCS", tmp_path)
    gen_docs.main()

    assert not (tmp_path / "source.html").exists()
    assert not list(tmp_path.glob("src-*.html"))
    assert "source.html" not in index.read_text()
    assert "source.html" not in (tmp_path / "nav.html").read_text()
    assert "source.html" not in (tmp_path / "nav.js").read_text()
    assert 'href="benchmarks.html">Benchmarks</a>' in (tmp_path / "nav.html").read_text()


def test_generator_publishes_benchmark_results(tmp_path, monkeypatch):
    source_docs = gen_docs.DOCS
    for page in source_docs.glob("*.html"):
        shutil.copy(page, tmp_path / page.name)
    monkeypatch.setattr(gen_docs, "DOCS", tmp_path)

    gen_docs.main()

    bench = (tmp_path / "benchmarks.html").read_text()
    assert "Headline results" in bench
    assert "Earlier recorded ratios" in bench
    assert "ulimit" not in bench
    assert "MALLOC_ARENA_MAX" not in bench
    for case in gen_docs.BENCHMARK_CASES:
        assert f'id="case-{case["name"]}"' in bench
        assert f'<code>{case["checksum"]}</code>' in bench
    for name in ("performance.html", "cli.html", "limits.html", "index.html"):
        assert 'href="benchmarks.html"' in (tmp_path / name).read_text()
