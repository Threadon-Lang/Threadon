"""Native/manifest plumbing tests for the importer."""
import subprocess
import sys
from pathlib import Path

import pytest

from compiler.threadon import importer as imp
from compiler.threadon.importer import (
    Importer,
    ImporterError,
    ThType,
    _python_include_dirs,
    _python_link_flags,
    build_native,
    default_torch_root,
    expand_native_flags,
    parse_manifest,
    parse_type,
    toolchain_for,
)


# --- types ---------------------------------------------------------------

def th(s):
    return parse_type(s)


def test_toolchains():
    assert toolchain_for("threadon") is None
    for lang in ["c", "cpp", "c++", "rust", "python"]:
        tc = toolchain_for(lang)
        assert tc is not None and tc.name == lang
        assert tc.compiler and tc.shared_args and tc.object_args
    assert toolchain_for("python").cxx is True
    assert toolchain_for("rust").object_ext == "a"
    with pytest.raises(ImporterError, match="unknown language"):
        toolchain_for("cobol")


def test_th_type_helpers():
    assert repr(th("Int32")) == "Int32"
    assert repr(th("List[Int32]")) == "List[Int32]"
    assert repr(th("Dict[String,List[Int32]]")) == "Dict[String, List[Int32]]"
    assert th("Int32").is_scalar and not th("Int32").is_list
    assert th("List[Int32]").is_list and not th("List[Int32]").is_scalar
    assert th("Dict[String,Int32]").is_dict
    assert th("List[Int32]").elem().kind == "Int32"
    assert th("Dict[String,Int32]").key_type().kind == "String"
    assert th("Dict[String,Int32]").value_type().kind == "Int32"
    assert th("Dict[String,List[Int32]]").manifest_token() == "Dict[String,List[Int32]]"
    with pytest.raises(ImporterError, match="is not a List"):
        th("Int32").elem()
    with pytest.raises(ImporterError, match="is not a Dict"):
        th("Int32").key_type()
    with pytest.raises(ImporterError, match="is not a Dict"):
        th("Int32").value_type()

    # the custom ThType constructor path (not via parse_type)
    assert ThType("Custom").manifest_token() == "Custom"
    with pytest.raises(ImporterError, match="no native C type"):
        Importer()._c_type_for(ThType("Custom"))


@pytest.mark.parametrize("token,needle", [
    ("", "unknown type"),
    ("Custom", "unknown type"),
    ("List[ ]", "needs type parameter"),
    ("Dict[Int32]", "exactly two type parameters"),
    ("Dict[Int32,Int32,Int32]", "exactly two type parameters"),
    ("Dict[List[Int32],Int32]", "Dict key type must be a scalar"),
    ("List[Int32]]", "unknown type"),
    ("Dict[String,List[Int32]", "unbalanced brackets"),
])
def test_parse_type_errors(token, needle):
    with pytest.raises(ImporterError, match=needle):
        parse_type(token, "manifest")


def test_split_top_level_commas():
    assert imp._split_top_level_commas("Int32, List[Dict[String,Int32]], Bool", "m") == [
        "Int32", "List[Dict[String,Int32]]", "Bool"
    ]
    with pytest.raises(ImporterError, match="unbalanced brackets"):
        imp._split_top_level_commas("Int32]", "m")


# --- manifest ------------------------------------------------------------

def test_parse_manifest_directives():
    man = parse_manifest("""
# comment
module foo
lang cpp
source foo.cpp
flag -std=c++17 -O2
link m pthread
export f Float64 Int32 List[Float64]
export g NoneType
class Box init Int32
class Box method area Int32 -> Float64
class Box method noop -> NoneType
""", "manifest")
    assert man.module == "foo" and man.lang == "cpp" and man.source == "foo.cpp"
    assert man.flags == ["-std=c++17", "-O2"]
    assert man.links == ["m", "pthread"]
    assert man.exports == [
        ("f", "Float64", ["Int32", "List[Float64]"]),
        ("g", "NoneType", []),
    ]
    assert man.classes["Box"]["init_args"] == ["Int32"]
    assert man.classes["Box"]["methods"] == [
        ("area", ["Int32"], "Float64"),
        ("noop", [], "NoneType"),
    ]


@pytest.mark.parametrize("line,needle", [
    ("module", "module' needs a name"),
    ("lang", "lang' needs a value"),
    ("lang compiler", "unknown language"),
    ("type native", "was replaced by 'lang'"),
    ("source", "source' needs a file"),
    ("export", "export' needs a name"),
    ("export f Bad", "unknown type"),
    ("class", "class' needs a name"),
    ("class Box wat Int32", "unknown class declaration"),
    ("class Box method", "method needs"),
    ("wat", "unknown directive"),
])
def test_parse_manifest_errors(line, needle):
    with pytest.raises(ImporterError, match=needle):
        parse_manifest(line, "manifest")


def test_manifest_lookup_and_errors(tmp_path):
    root = tmp_path / "lib"
    moddir = root / "m"
    moddir.mkdir(parents=True)
    (moddir / "manifest").write_text("module m\nlang threadon\nsource m.th\n")
    (moddir / "m.th").write_text("def f():\n    return 1\n")

    importer = Importer([root])
    assert importer._find_manifest_path("m") == moddir / "manifest"
    assert importer.find_source("m") == (moddir / "m.th").read_text()
    assert importer._load_manifest("m").module == "m"
    assert importer._find_manifest_path("registered") is None
    importer.register_source("registered", "x")
    assert importer.find_source("registered") == "x"

    (moddir / "manifest").write_text("module other\nlang threadon\n")
    with pytest.raises(ImporterError, match="declares module 'other'"):
        importer._load_manifest("m")

    (moddir / "manifest").write_text("module m\nlang cpp\nsource x.cpp\n")
    assert importer.find_source("m") is None
    (moddir / "manifest").write_text("module m\nlang threadon\nsource missing.th\n")
    assert importer.find_source("m") is None


# --- python config / torch -----------------------------------------------

def test_python_include_dirs(monkeypatch, tmp_path):
    monkeypatch.setattr(imp.subprocess, "check_output", lambda *a, **kw: "-I/found")
    assert imp._python_include_dirs() == ["-I/found"]
    monkeypatch.setattr(imp.subprocess, "check_output", lambda *a, **kw: (_ for _ in ()).throw(
        OSError("missing python3-config")
    ))
    header = tmp_path / "include" / "Python.h"
    header.parent.mkdir(parents=True)
    header.write_text("")
    monkeypatch.setattr(imp.sysconfig, "get_paths", lambda: {"include": str(header.parent)})
    dirs = imp._python_include_dirs()
    assert dirs == [
        f"-I{header.parent}",
        f"-I{header.parent}/cpython",
        f"-I{header.parent}/internal",
    ]
    monkeypatch.setattr(imp.sysconfig, "get_paths", lambda: {"include": "/nope"})
    monkeypatch.setattr(imp.Path, "exists", lambda self: self == imp.Path("/usr/include/python3.13"))
    assert imp._python_include_dirs()[0] == "-I/usr/include/python3.13"
    monkeypatch.setattr(imp.Path, "exists", lambda self: False)
    with pytest.raises(ImporterError, match="Cannot locate Python.h"):
        imp._python_include_dirs()


@pytest.mark.parametrize("embed_ok,plain_ok,expected", [
    (True, True, ["-lembed"]),
    (False, True, ["-lplain"]),
    (False, False, []),
])
def test_importer_python_link_flags(monkeypatch, embed_ok, plain_ok, expected):
    def fake(cmd, **kwargs):
        if cmd[1] == "--embed":
            if embed_ok:
                return "-lembed"
            raise subprocess.CalledProcessError(1, cmd)
        if plain_ok:
            return "-lplain"
        raise FileNotFoundError
    monkeypatch.setattr(imp.subprocess, "check_output", fake)
    assert _python_link_flags() == expected


def test_default_torch_root(monkeypatch, tmp_path):
    class FakeTorch:
        __file__ = str(tmp_path / "torch" / "__init__.py")

    include = tmp_path / "torch" / "include"
    lib = tmp_path / "torch" / "lib"
    include.mkdir(parents=True)
    lib.mkdir()
    monkeypatch.setitem(sys.modules, "torch", FakeTorch())
    assert default_torch_root() == str(tmp_path / "torch")
    monkeypatch.setitem(sys.modules, "torch", None)
    assert default_torch_root().endswith("site-packages/torch")


def test_expand_native_flags(monkeypatch):
    monkeypatch.delenv("TORCH_ROOT", raising=False)
    mod = type("M", (), {"flags": [], "links": []})()
    assert expand_native_flags(mod) == ([], [])
    assert "TORCH_ROOT" not in imp.os.environ

    monkeypatch.setenv("TORCH_ROOT", "/opt/torch")
    mod = type("M", (), {
        "flags": ["-I$TORCH_ROOT/include"],
        "links": ["-L${TORCH_ROOT}/lib", "-lm"],
    })()
    assert expand_native_flags(mod) == (
        ["-I/opt/torch/include"], ["-L/opt/torch/lib", "-lm"]
    )


# --- build_native --------------------------------------------------------

def test_build_native_rust(monkeypatch, tmp_path):
    src = tmp_path / "lib.rs"
    src.write_text("//")
    module = type("M", (), {
        "toolchain": toolchain_for("rust"),
        "flags": [], "links": [], "native_source": src,
        "extra_sources": [], "manifest_dir": tmp_path, "name": "rusty",
    })()
    calls = []
    monkeypatch.setattr(imp.subprocess, "check_call", lambda cmd, **kw: calls.append(cmd))
    out = build_native(module)
    assert out == tmp_path / "rusty.so"
    assert calls[0][:3] == ["rustc", "--crate-type=cdylib", str(src)]


def test_build_native_c_and_python(monkeypatch, tmp_path):
    src = tmp_path / "a.c"
    extra = tmp_path / "b.c"
    src.write_text("//")
    extra.write_text("//")
    calls = []

    def fake_check_call(cmd, **kw):
        calls.append(cmd)

    monkeypatch.setattr(imp.subprocess, "check_call", fake_check_call)
    monkeypatch.setattr(imp, "_python_include_dirs", lambda: ["-I/py"])
    monkeypatch.setattr(imp, "_python_link_flags", lambda: ["-lpython"])
    module = type("M", (), {
        "toolchain": toolchain_for("c"),
        "flags": ["-O2"], "links": ["m", "-pthread"],
        "native_source": src, "extra_sources": [extra],
        "manifest_dir": tmp_path, "name": "clib",
    })()
    out = build_native(module)
    assert out == tmp_path / "clib.so"
    assert calls[0][0] == "gcc" and "-c" in calls[0]
    assert len(calls) == 3
    assert calls[-1][0] == "gcc" and "-shared" in calls[-1]
    assert "-lm" in calls[-1] and "-pthread" in calls[-1] and "-ldl" in calls[-1]

    py = type("M", (), {
        "toolchain": toolchain_for("python"),
        "flags": [], "links": [], "native_source": src,
        "extra_sources": [], "manifest_dir": tmp_path, "name": "py",
    })()
    build_native(py)
    assert "-I/py" in calls[-2] and "-lpython" in calls[-1]


# --- wrapper emitters ----------------------------------------------------

@pytest.fixture
def wrapper():
    return Importer()


def counter():
    n = [0]

    def fresh(base):
        n[0] += 1
        return f"_{base}{n[0]}"

    return fresh


def test_c_type_names_and_compound_collection(wrapper):
    assert wrapper._c_type_for(th("Int32")) == "int32_t"
    assert wrapper._c_type_for(th("String")) == "char*"
    assert wrapper._c_type_for(th("NoneType")) == "void"
    assert wrapper._c_type_for(th("List[Int32]")) == "ThList_Int32"
    assert wrapper._c_type_for(th("Dict[String,Int64]")) == "ThDict_String_Int64"
    assert wrapper._list_struct_name(th("List[List[Int32]]")) == "ThList_ThList_Int32"
    assert wrapper._dict_struct_name(th("Dict[String,Int32]")) == "ThDict_String_Int32"
    assert wrapper._type_name_part(th("Int32")) == "Int32"
    assert wrapper._type_name_part(th("List[Int32]")) == "ThList_Int32"
    assert wrapper._type_name_part(th("Dict[String,Int32]")) == "ThDict_String_Int32"

    lines, compounds = wrapper._emit_list_struct_defs([
        th("List[Int32]"), th("List[List[Float64]]"),
        th("Dict[String,List[Int32]]"), th("Int32"),
    ])
    assert "struct ThList_Int32 { long long len; int32_t* data; };" in lines
    assert "struct ThList_ThList_Float64" in " ".join(lines)
    assert "struct ThDict_String_ThList_Int32" in " ".join(lines)
    assert set(compounds) == {
        "List[Int32]", "List[Float64]", "List[List[Float64]]",
        "Dict[String,List[Int32]]",
    }
    assert wrapper._emit_list_struct_defs([th("Int32")])[1] == {}


@pytest.mark.parametrize("kind,needle", [
    ("Float64", "PyFloat_AsDouble"),
    ("Int64", "PyLong_AsLongLong"),
    ("Bool", "PyObject_IsTrue"),
    ("String", "PyUnicode_AsUTF8"),
])
def test_py_to_native_scalars(wrapper, kind, needle):
    out = []
    wrapper._emit_py_to_native_scalar(out, "dst", "obj", th(kind), counter())
    assert needle in out[0]
    with pytest.raises(ImporterError, match="cannot marshal scalar type"):
        wrapper._emit_py_to_native_scalar([], "dst", "obj", th("Int32"), counter())


@pytest.mark.parametrize("kind,needle", [
    ("Float64", "PyFloat_FromDouble"),
    ("Int64", "PyLong_FromLongLong"),
    ("Bool", "PyBool_FromLong"),
    ("String", "PyUnicode_FromString"),
])
def test_native_to_py_scalars(wrapper, kind, needle):
    out = []
    wrapper._emit_native_to_py_scalar(out, "obj", "src", th(kind))
    assert needle in out[0]
    with pytest.raises(ImporterError, match="cannot marshal scalar type"):
        wrapper._emit_native_to_py_scalar([], "obj", "src", th("Int32"))


def test_list_and_dict_marshalling(wrapper):
    out = []
    wrapper._emit_py_to_native_list(out, "dst", "obj", th("List[List[Int64]]"), counter())
    text = "\n".join(out)
    assert "PySequence_Size" in text and "PySequence_GetItem" in text
    assert "malloc" in text and "Py_DECREF" in text
    assert "PyList_ThList_Int64" in text or "ThList_Int64" in text

    out = []
    wrapper._emit_py_to_native_list(out, "dst", "obj", th("List[Dict[String,Int64]]"), counter())
    assert "PyDict_Size" in "\n".join(out)

    out = []
    wrapper._emit_native_to_py_list(out, "obj", "src", th("List[List[Int64]]"), counter())
    assert "PyList_New" in out[0] and "PyList_SetItem" in "\n".join(out)
    out = []
    wrapper._emit_native_to_py_list(out, "obj", "src", th("List[Dict[String,Int64]]"), counter())
    assert "PyDict_New" in "\n".join(out)

    out = []
    wrapper._emit_py_to_native_dict(out, "dst", "obj", th("Dict[String,Dict[String,Int64]]"), counter())
    text = "\n".join(out)
    assert "PyDict_Items" in text and "PyDict_Size" in text
    out = []
    wrapper._emit_py_to_native_dict(out, "dst", "obj", th("Dict[String,List[Int64]]"), counter())
    assert "PySequence_Size" in "\n".join(out)

    out = []
    wrapper._emit_native_to_py_dict(out, "obj", "src", th("Dict[String,Dict[String,Int64]]"), counter())
    text = "\n".join(out)
    assert "PyDict_New" in text and "PyDict_SetItem" in text
    assert "Py_DECREF" in text
    out = []
    wrapper._emit_native_to_py_dict(out, "obj", "src", th("Dict[String,List[Int64]]"), counter())
    assert "PyList_New" in "\n".join(out)


def test_export_thunks(wrapper):
    fresh = counter()
    code = wrapper._emit_export_thunk("f", th("Float64"), [], "mod", fresh)
    assert "PyObject* args = nullptr" in code
    assert "PyImport_ImportModule(\"mod\")" in code
    assert "PyObject_CallObject" in code and "return _out" in code

    code = wrapper._emit_export_thunk("f", th("NoneType"), [th("Float64"), th("List[Int64]")], "mod", fresh)
    assert "PyTuple_New(2)" in code
    assert "PyFloat_FromDouble(a0)" in code
    assert "PyList_New(a1.len)" in code
    assert "void f(" in code and "return;" in code

    code = wrapper._emit_export_thunk("f", th("List[Int64]"), [], "mod", fresh)
    assert "PySequence_Size(r)" in code and "return out" in code

    code = wrapper._emit_export_thunk(
        "f", th("Float64"), [th("Dict[String,Int64]")], "mod", fresh
    )
    assert "ThDict_String_Int64* a0" in code
    assert "PyDict_New()" in code and "(*a0).len" in code
    assert "PyDict_New()" in code

    code = wrapper._emit_export_thunk("f", th("Dict[String,Int64]"), [], "mod", fresh)
    assert "ThDict_String_Int64* _sret_out" in code
    assert "PyDict_Size" in code and "return;" in code


def test_class_thunks(wrapper):
    info = {"init_args": ["Int64"], "methods": [("area", ["Int64"], "Float64")]}
    fresh = counter()
    code = wrapper._emit_class_init_thunk("Box", info, "mod", fresh)
    assert "Box Box___init__(Box self, int64_t a0)" in code
    assert "PyTuple_New(1)" in code and "PyImport_ImportModule(\"mod\")" in code
    code = wrapper._emit_class_method_thunk("Box", "area", info, "mod", fresh)
    assert "double Box___area(Box self, int64_t a0)" in code
    assert "PyObject_GetAttrString" in code and "PyFloat_AsDouble" in code


def test_class_thunks_without_args(wrapper):
    info = {"init_args": [], "methods": [("noop", [], "Float64")]}
    fresh = counter()
    assert "PyTuple_New(0)" in wrapper._emit_class_init_thunk("Box", info, "mod", fresh)
    assert "PyTuple_New(0)" in wrapper._emit_class_method_thunk(
        "Box", "noop", info, "mod", fresh
    )


def test_zero_c_values(wrapper):
    assert wrapper._zero_c_value(th("Float64")) == "0.0"
    assert wrapper._zero_c_value(th("Int64")) == "0"
    assert wrapper._zero_c_value(th("Bool")) == "false"
    assert wrapper._zero_c_value(th("String")) == "nullptr"
    assert wrapper._zero_c_value(th("NoneType")) == ""
    assert wrapper._zero_c_value(th("List[Int32]")) == "ThList_Int32{0, nullptr}"
    assert wrapper._zero_c_value(th("Dict[String,Int32]")) == (
        "ThDict_String_Int32{0, nullptr, nullptr}"
    )


def test_emit_python_wrapper_full(tmp_path, wrapper):
    pyfile = tmp_path / "lib.py"
    pyfile.write_text("")
    classes = {
        "Box": {
            "init_args": ["Int64"],
            "methods": [("area", ["Int64"], "Float64")],
        }
    }
    code = wrapper._emit_python_wrapper(
        "lib", pyfile,
        [("f", "Float64", ["Int64"]), ("g", "List[Int64]", [])],
        classes,
    )
    assert "#include <Python.h>" in code
    assert "Py_Initialize()" in code
    assert f'sys.path.insert(0, \\"{pyfile.parent.resolve()}\\")' in code
    assert "struct Box {" in code
    assert "double f(int64_t a0)" in code
    assert "ThList_Int64 g()" in code
    assert "Box Box___init__" in code and "Box___area" in code
    assert code.endswith("} // extern C")

    code = wrapper._emit_python_wrapper("lib", pyfile, [("f", "Float64", [])])
    assert "struct Box {" not in code


def test_generate_python_wrapper_writes_file(tmp_path, wrapper):
    pyfile = tmp_path / "lib.py"
    pyfile.write_text("")
    man = parse_manifest(
        "module lib\nlang python\nsource lib.py\nexport f Float64 Int64\n", "manifest"
    )
    path = wrapper._generate_python_wrapper("lib", man, tmp_path / "manifest")
    assert path == tmp_path / "lib_pywrap.cpp"
    assert "double f(int64_t a0)" in path.read_text()


def test_build_native_module_python(tmp_path, monkeypatch):
    moddir = tmp_path / "lib"
    moddir.mkdir()
    (moddir / "manifest").write_text(
        "module lib\nlang python\nsource lib.py\n"
        "export f Float64 Int64\n"
        "class Box init Int64\n"
        "class Box method area Int64 -> Float64\n"
    )
    (moddir / "lib.py").write_text("")
    bridge = moddir / "python_bridge.cpp"
    bridge.write_text("//")
    monkeypatch.setattr(imp, "build_native", lambda module: moddir / "lib.so")
    importer = Importer([tmp_path])
    module = importer.load("lib")
    assert module.is_native and module.name == "lib"
    assert module.native_source == moddir / "lib_pywrap.cpp"
    assert module.extra_sources == [bridge]
    assert "f" in module.func_exports
    assert "Box" in module.class_exports
    assert "lib.Box___init__" in module.func_sigs
    assert "lib.Box___area" in module.func_sigs
    assert module.class_ast["lib.Box"].name == "lib.Box"
    assert module.class_method_map["lib.Box"]["area"] == "lib.Box___area"
    assert {e[0] for e in module.exports} == {
        "f", "Box___init__", "Box___area"
    }


def test_build_native_module_missing_bridge(tmp_path, monkeypatch):
    moddir = tmp_path / "lib"
    moddir.mkdir()
    (moddir / "manifest").write_text("module lib\nlang python\nsource lib.c\n")
    (moddir / "lib.c").write_text("//")
    monkeypatch.setattr(imp, "build_native", lambda module: None)
    monkeypatch.setattr(imp, "__file__", str(tmp_path / "fake" / "importer.py"))
    with pytest.raises(ImporterError, match="python_bridge.cpp missing"):
        Importer([tmp_path]).load("lib")
