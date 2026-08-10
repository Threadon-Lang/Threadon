import io
from contextlib import redirect_stdout

import pytest

from compiler.importer import Importer, ImporterError
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
