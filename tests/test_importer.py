import io
from contextlib import redirect_stdout

import pytest

from compiler.importer import Importer, ImporterError, parse_manifest
from compiler.nodes import ImportStmt

MATH_SOURCE = """
def abs(x: Int32) -> Int32
    result: Int32 = x
    if x < 0:
        result *= -1
    return result

struct Point:
    x: Int32
    y: Int32
"""

NATIVE_MANIFEST = """
module vecmath
lang cpp
source vecmath.cpp
flag -std=c++17
flag -O2
link m

export length Float64 Float64 Float64
export clamp Int32 Int32 Int32 Int32
"""


def load_main(importer, source):
    with redirect_stdout(io.StringIO()):
        return importer.load_main(source)


class TestFindSource:
    def test_registered_source(self):
        imp = Importer()
        imp.register_source("std.math", MATH_SOURCE)
        assert imp.find_source("std.math") == MATH_SOURCE

    def test_file_search_dotted_path(self, tmp_path):
        mod_dir = tmp_path / "lib" / "sub"
        mod_dir.mkdir(parents=True)
        (mod_dir / "util.th").write_text(MATH_SOURCE)

        imp = Importer()
        imp.add_search_path(tmp_path)
        assert imp.find_source("lib.sub.util") == MATH_SOURCE

    def test_search_path_ordering(self, tmp_path):
        (tmp_path / "m.th").write_text("first")
        other = tmp_path / "other"
        other.mkdir()
        (other / "m.th").write_text("second")

        imp = Importer()
        imp.add_search_path(other)
        imp.add_search_path(tmp_path)
        assert imp.find_source("m") == "first"

    def test_missing_module_returns_none(self):
        imp = Importer()
        assert imp.find_source("does.not.exist") is None


class TestLoad:
    def test_load_populates_exports(self):
        imp = Importer()
        imp.register_source("std.math", MATH_SOURCE)
        mod = imp.load("std.math")
        assert mod.name == "std.math"
        assert "abs" in mod.func_exports
        assert "Point" in mod.struct_exports
        assert "std.math.abs" in mod.func_sigs
        assert "std.math.Point" in mod.struct_defs

    def test_load_caches(self):
        imp = Importer()
        imp.register_source("std.math", MATH_SOURCE)
        assert imp.load("std.math") is imp.load("std.math")

    def test_missing_module_raises(self):
        imp = Importer()
        with pytest.raises(ImporterError):
            imp.load("no.such.module")

    def test_circular_import_detected(self):
        imp = Importer()
        imp.register_source("a", "from b import g\n")
        imp.register_source("b", "from a import f\n")
        with pytest.raises(SystemExit):
            imp.load("a")

    def test_load_main_and_modules(self):
        imp = Importer()
        imp.register_source("std.math", MATH_SOURCE)
        ast = load_main(imp, "from std.math import abs\ndef run() -> Int32\n    return abs(-1)\n")
        assert any(type(n).__name__ == "ImportStmt" for n in ast)
        assert [m.name for m in imp.modules()] == ["std", "std.math"]


class TestManifest:
    def test_parse_manifest(self):
        man = parse_manifest(NATIVE_MANIFEST, "manifest")
        assert man.module == "vecmath"
        assert man.lang == "cpp"
        assert man.source == "vecmath.cpp"
        assert man.flags == ["-std=c++17", "-O2"]
        assert man.links == ["m"]
        assert man.exports == [
            ("length", "Float64", ["Float64", "Float64"]),
            ("clamp", "Int32", ["Int32", "Int32", "Int32"]),
        ]

    def test_parse_manifest_defaults(self):
        man = parse_manifest("module util\nsource util.th\n", "manifest")
        assert man.lang == "threadon"
        assert man.flags == []
        assert man.links == []
        assert man.exports == []

    def test_parse_manifest_unknown_directive(self):
        with pytest.raises(ImporterError, match="unknown directive"):
            parse_manifest("module x\nbogus foo\n", "manifest")

    def test_parse_manifest_bad_lang(self):
        with pytest.raises(ImporterError, match="unknown language"):
            parse_manifest("module x\nlang banana\n", "manifest")

    def test_parse_manifest_type_replaced(self):
        with pytest.raises(ImporterError, match="replaced by 'lang'"):
            parse_manifest("module x\ntype native\n", "manifest")

    def test_parse_manifest_export_needs_return_type(self):
        with pytest.raises(ImporterError, match="export"):
            parse_manifest("module x\nsource x.cpp\nexport foo\n", "manifest")

    def test_find_source_via_manifest(self, tmp_path):
        mod_dir = tmp_path / "lib" / "util"
        mod_dir.mkdir(parents=True)
        (mod_dir / "manifest").write_text("module lib.util\nsource util.th\n")
        (mod_dir / "util.th").write_text(MATH_SOURCE)

        imp = Importer()
        imp.add_search_path(tmp_path)
        assert imp.find_source("lib.util") == MATH_SOURCE

    def test_find_source_native_without_th(self, tmp_path):
        mod_dir = tmp_path / "time"
        mod_dir.mkdir(parents=True)
        (mod_dir / "manifest").write_text("module time\nlang cpp\nsource time.cpp\n")
        (mod_dir / "time.cpp").write_text("// noop")

        imp = Importer()
        imp.add_search_path(tmp_path)
        assert imp.find_source("time") is None

    def test_load_native_module(self, tmp_path):
        mod_dir = tmp_path / "vecmath"
        mod_dir.mkdir(parents=True)
        (mod_dir / "manifest").write_text(NATIVE_MANIFEST)
        (mod_dir / "vecmath.cpp").write_text("// noop")

        imp = Importer()
        imp.add_search_path(tmp_path)
        mod = imp.load("vecmath")

        assert mod.is_native is True
        assert mod.lang == "cpp"
        assert mod.toolchain is not None
        assert mod.toolchain.name == "cpp"
        assert mod.ast is None
        assert mod.source is None
        assert mod.native_source == mod_dir / "vecmath.cpp"
        assert mod.flags == ["-std=c++17", "-O2"]
        assert mod.links == ["m"]
        assert "length" in mod.func_exports
        assert "clamp" in mod.func_exports
        assert mod.func_sigs["vecmath.length"] == (
            [("a0", "Float64", None), ("a1", "Float64", None)],
            "Float64",
        )
        assert mod.func_sigs["vecmath.clamp"] == (
            [("a0", "Int32", None), ("a1", "Int32", None), ("a2", "Int32", None)],
            "Int32",
        )

    def test_load_c_module_toolchain(self, tmp_path):
        mod_dir = tmp_path / "cadd"
        mod_dir.mkdir(parents=True)
        (mod_dir / "manifest").write_text(
            "module cadd\nlang c\nsource cadd.c\nflag -O2\n"
        )
        (mod_dir / "cadd.c").write_text("int add(int a, int b) { return a + b; }\n")

        imp = Importer()
        imp.add_search_path(tmp_path)
        mod = imp.load("cadd")

        assert mod.is_native is True
        assert mod.lang == "c"
        assert mod.toolchain.name == "c"
        assert mod.toolchain.compiler == "gcc"
        assert mod.toolchain.cxx is False
        assert mod.toolchain.object_ext == "o"

    def test_load_rust_module_toolchain(self, tmp_path):
        mod_dir = tmp_path / "rsum"
        mod_dir.mkdir(parents=True)
        (mod_dir / "manifest").write_text(
            "module rsum\nlang rust\nsource rsum.rs\nflag -C opt-level=2\n"
        )
        (mod_dir / "rsum.rs").write_text("// noop")

        imp = Importer()
        imp.add_search_path(tmp_path)
        mod = imp.load("rsum")

        assert mod.is_native is True
        assert mod.lang == "rust"
        assert mod.toolchain.name == "rust"
        assert mod.toolchain.compiler == "rustc"
        assert mod.toolchain.object_ext == "a"

    def test_load_cpp_alias_language(self, tmp_path):
        mod_dir = tmp_path / "x"
        mod_dir.mkdir(parents=True)
        (mod_dir / "manifest").write_text("module x\nlang c++\nsource x.cpp\n")
        (mod_dir / "x.cpp").write_text("// noop")

        imp = Importer()
        imp.add_search_path(tmp_path)
        mod = imp.load("x")

        assert mod.lang == "c++"
        assert mod.toolchain.name == "c++"
        assert mod.toolchain.cxx is True

    def test_load_native_module_name_mismatch(self, tmp_path):
        mod_dir = tmp_path / "wrong"
        mod_dir.mkdir(parents=True)
        (mod_dir / "manifest").write_text("module right\nsource x.cpp\n")

        imp = Importer()
        imp.add_search_path(tmp_path)
        with pytest.raises(ImporterError, match="imported as 'wrong'"):
            imp.load("wrong")

    def test_load_threadon_module_with_manifest(self, tmp_path):
        mod_dir = tmp_path / "util"
        mod_dir.mkdir(parents=True)
        (mod_dir / "manifest").write_text("module util\nsource util.th\n")
        (mod_dir / "util.th").write_text(MATH_SOURCE)

        imp = Importer()
        imp.add_search_path(tmp_path)
        mod = imp.load("util")

        assert mod.is_native is False
        assert mod.manifest_dir == mod_dir
        assert "abs" in mod.func_exports
        assert "std" not in [m.name for m in imp.modules()]


class TestParserImportNode:
    def parse(self, imp, code):
        from compiler.parser import Parser

        return Parser(importer=imp).parse(code)

    def test_import_module_node(self):
        imp = Importer()
        imp.register_source("std.math", MATH_SOURCE)
        ast = self.parse(imp, "import std.math\n")
        stmt = ast[0]
        assert isinstance(stmt, ImportStmt)
        assert stmt.module == "std.math"
        assert stmt.names == [(None, "std")]
        assert stmt.lazy is False
        assert stmt.is_from is False

    def test_import_module_with_alias_node(self):
        imp = Importer()
        imp.register_source("std.math", MATH_SOURCE)
        ast = self.parse(imp, "import std.math as m\n")
        stmt = ast[0]
        assert stmt.names == [(None, "m")]

    def test_from_import_node(self):
        imp = Importer()
        imp.register_source("std.math", MATH_SOURCE)
        ast = self.parse(imp, "from std.math import abs\n")
        stmt = ast[0]
        assert stmt.is_from is True
        assert stmt.names == [("abs", None)]

    def test_from_import_alias_node(self):
        imp = Importer()
        imp.register_source("std.math", MATH_SOURCE)
        ast = self.parse(imp, "from std.math import abs as absolute\n")
        stmt = ast[0]
        assert stmt.names == [("abs", "absolute")]

    def test_from_import_multiple_names(self):
        imp = Importer()
        imp.register_source("std.math", MATH_SOURCE)
        ast = self.parse(imp, "from std.math import abs, Point\n")
        stmt = ast[0]
        assert stmt.names == [("abs", None), ("Point", None)]

    def test_import_missing_member_fails(self):
        imp = Importer()
        imp.register_source("std.math", MATH_SOURCE)
        with pytest.raises(SystemExit):
            self.parse(imp, "from std.math import missing\n")

    def test_import_unknown_module_fails(self):
        imp = Importer()
        with pytest.raises(SystemExit):
            self.parse(imp, "from no.module import x\n")
