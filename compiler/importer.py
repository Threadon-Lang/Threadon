from pathlib import Path
import subprocess
import shlex
import sysconfig
import os
import re

MODULE_EXTENSION = ".th"
MANIFEST_FILENAME = "manifest"
STDLIB_DIR = Path(__file__).resolve().parent.parent / "stdlib"


class ImporterError(Exception):
    pass


class Toolchain:

    def __init__(self, name, compiler, shared_args, object_args,
                 object_ext="o", cxx=False):
        self.name = name
        self.compiler = compiler
        self.shared_args = list(shared_args)
        self.object_args = list(object_args)
        self.object_ext = object_ext
        self.cxx = cxx

LANGUAGES = {
    "threadon": None,
    "c": Toolchain("c", "gcc", ["-shared", "-fPIC"], ["-c"], object_ext="o"),
    "cpp": Toolchain("cpp", "g++", ["-shared", "-fPIC"], ["-c"], object_ext="o", cxx=True),
    "c++": Toolchain("c++", "g++", ["-shared", "-fPIC"], ["-c"], object_ext="o", cxx=True),
    "rust": Toolchain(
        "rust",
        "rustc",
        ["--crate-type", "cdylib"],
        ["--crate-type", "staticlib"],
        object_ext="a",
    ),
    "python": Toolchain(
        "python",
        "g++",
        ["-shared", "-fPIC"],
        ["-c", "-fPIC"],
        object_ext="so",
        cxx=True,
    ),
}


def toolchain_for(lang):
    if lang in LANGUAGES:
        return LANGUAGES[lang]
    raise ImporterError(f"unknown language '{lang}'")


SCALAR_TYPES = {
    "Int8", "Int16", "Int32", "Int64", 
    "UInt8", "UInt16", "UInt32", "UInt64", 
    "Float16", "Float32", "Float64", 
    "Bool", "String", "NoneType"
}

C_SCALAR_TYPES = {
    "Int8": "int8_t",
    "Int16": "int16_t",
    "Int32": "int32_t",
    "Int64": "int64_t",
    "UInt8": "uint8_t",
    "UInt16": "uint16_t",
    "UInt32": "uint32_t",
    "UInt64": "uint64_t",
    "Float16": "_Float16",
    "Float32": "float",
    "Float64": "double",
    "Bool": "bool",
    "String": "char*",
    "NoneType": "void",
}


class ThType:


    def __init__(self, kind, params=None):
        self.kind = kind
        self.params = params or []

    def __repr__(self):
        if not self.params:
            return self.kind
        return f"{self.kind}[{', '.join(repr(p) for p in self.params)}]"

    @property
    def is_list(self):
        return self.kind == "List"

    @property
    def is_dict(self):
        return self.kind == "Dict"

    @property
    def is_scalar(self):
        return self.kind in SCALAR_TYPES

    def manifest_token(self):

        if not self.params:
            return self.kind
        return f"{self.kind}[{','.join(p.manifest_token() for p in self.params)}]"

    def elem(self):

        if self.kind != "List":
            raise ImporterError(f"'{self!r}' is not a List type")
        return self.params[0]

    def key_type(self):
        if self.kind != "Dict":
            raise ImporterError(f"'{self!r}' is not a Dict type")
        return self.params[0]

    def value_type(self):
        if self.kind != "Dict":
            raise ImporterError(f"'{self!r}' is not a Dict type")
        return self.params[1]


_COMPOUND_RE = re.compile(r"^(List|Dict)\[(.+)\]$")


def _split_top_level_commas(s, path):

    parts, depth, cur = [], 0, []
    for ch in s:
        if ch == "[":
            depth += 1
            cur.append(ch)
        elif ch == "]":
            depth -= 1
            if depth < 0:
                raise ImporterError(f"Manifest '{path}': unbalanced brackets in type")
            cur.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if depth != 0:
        raise ImporterError(f"Manifest '{path}': unbalanced brackets in type")
    parts.append("".join(cur))
    return [p.strip() for p in parts]


def parse_type(token, path="<manifest>"):

    token = token.strip()
    m = _COMPOUND_RE.match(token)
    if not m:
        if token not in SCALAR_TYPES:
            raise ImporterError(
                f"Manifest '{path}': unknown type '{token}' "
                f"(known scalars: {', '.join(sorted(SCALAR_TYPES))}, "
                "or List[T] / Dict[K,V])"
            )
        return ThType(token)

    kind, inner = m.group(1), m.group(2)
    inner = inner.strip()
    if not inner:
        raise ImporterError(f"Manifest '{path}': '{kind}[...]' needs type parameter(s)")

    if kind == "List":
        return ThType("List", [parse_type(inner, path)])

    parts = _split_top_level_commas(inner, path)
    if len(parts) != 2:
        raise ImporterError(
            f"Manifest '{path}': 'Dict[...]' takes exactly two type parameters "
            "(key,value), e.g. Dict[String,Float64]"
        )
    key_t = parse_type(parts[0], path)
    val_t = parse_type(parts[1], path)
    if not key_t.is_scalar:
        raise ImporterError(
            f"Manifest '{path}': Dict key type must be a scalar, got '{key_t!r}'"
        )
    return ThType("Dict", [key_t, val_t])


class Manifest:

    def __init__(self, module=None, lang="threadon", source=None, flags=None,
                 links=None, exports=None):
        self.module = module
        self.lang = lang
        self.source = source
        self.flags = flags or []
        self.links = links or []
        self.exports = exports or []


def parse_manifest(text, path):
    man = Manifest()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        directive = parts[0]
        if directive == "module":
            if len(parts) < 2:
                raise ImporterError(f"Manifest '{path}': 'module' needs a name")
            man.module = parts[1]
        elif directive == "lang":
            if len(parts) < 2:
                raise ImporterError(f"Manifest '{path}': 'lang' needs a value")
            if parts[1] not in LANGUAGES:
                raise ImporterError(
                    f"Manifest '{path}': unknown language '{parts[1]}' "
                    f"(known: {', '.join(LANGUAGES)})"
                )
            man.lang = parts[1]
        elif directive == "type":
            raise ImporterError(
                f"Manifest '{path}': directive 'type' was replaced by 'lang' "
                "(e.g. 'lang cpp' instead of 'type native')"
            )
        elif directive == "source":
            if len(parts) < 2:
                raise ImporterError(f"Manifest '{path}': 'source' needs a file")
            man.source = parts[1]
        elif directive == "flag":
            man.flags.extend(parts[1:])
        elif directive == "link":
            man.links.extend(parts[1:])
        elif directive == "export":
            if len(parts) < 3:
                raise ImporterError(
                    f"Manifest '{path}': 'export' needs a name and return type"
                )
            name, ret = parts[1], parts[2]
            parse_type(ret, path)
            for arg in parts[3:]:
                parse_type(arg, path)
            man.exports.append((name, ret, parts[3:]))
        else:
            raise ImporterError(
                f"Manifest '{path}': unknown directive '{directive}'"
            )
    return man


class Module:

    def __init__(self, name: str, source: str, ast=None):
        self.name = name
        self.source = source
        self.ast = ast
        self.func_sigs = {}
        self.struct_defs = {}
        self.class_defs = {}
        self.class_ast = {}
        self.class_method_map = {}
        self.func_exports = set()
        self.struct_exports = set()
        self.class_exports = set()
        self.var_exports = set()
        self.lang = "threadon"
        self.toolchain = None
        self.manifest_dir = None
        self.flags = []
        self.links = []
        self.exports = []
        self.native_source = None
        self.is_native = False
        self.extra_sources = []

    def __repr__(self):
        return f"Module({self.name!r})"


def _python_include_dirs():
    try:
        out = subprocess.check_output(
            ["python3-config", "--includes"], text=True
        ).strip()
        flags = shlex.split(out)
        if flags:
            return flags
    except Exception:
        pass

    include_dir = sysconfig.get_paths().get("include")
    if include_dir and (Path(include_dir) / "Python.h").exists():
        return [
            f"-I{include_dir}",
            f"-I{include_dir}/cpython",
            f"-I{include_dir}/internal",
        ]

    for cand in [
        "/usr/include/python3.13",
        "/usr/include/python3.13/cpython",
        "/usr/include/python3.13/internal",
    ]:
        if Path(cand).exists():
            return [
                "-I/usr/include/python3.13",
                "-I/usr/include/python3.13/cpython",
                "-I/usr/include/python3.13/internal",
            ]

    raise ImporterError("Cannot locate Python.h for python native module")


def _python_link_flags():
    try:
        out = subprocess.check_output(
            ["python3-config", "--embed", "--ldflags"], text=True
        ).strip()
        return shlex.split(out)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    try:
        out = subprocess.check_output(
            ["python3-config", "--ldflags"], text=True
        ).strip()
        return shlex.split(out)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


def build_native(module):
    tc = module.toolchain
    env = os.environ.copy()

    includes = _python_include_dirs() if tc.name == "python" else []
    link_extra = _python_link_flags() if tc.name == "python" else []
    libs = ["-ldl", "-lm"] + shlex.split(" ".join(link_extra))

    if tc.name == "rust":
        src = str(module.native_source)
        out = Path(module.manifest_dir) / f"{module.name}.so"
        cmd = ["rustc", "--crate-type=cdylib", src, "-o", str(out)]
        subprocess.check_call(cmd, env=env)
        return out

    objects = []
    for src in [module.native_source] + module.extra_sources:
        src = Path(src)
        obj = src.with_suffix(".o")
        cmd = [tc.compiler] + tc.object_args + includes + module.flags + [str(src), "-o", str(obj)]
        subprocess.check_call(cmd, env=env)
        objects.append(str(obj))
    link_flags = []
    for lib in module.links:
        if lib.startswith("-l"):
            link_flags.append(lib)
        else:
            link_flags.append(f"-l{lib}")

    out = Path(module.manifest_dir) / f"{module.name}.so"
    cmd = [tc.compiler] + tc.shared_args + objects + libs + link_flags + ["-o", str(out)]

    subprocess.check_call(cmd, env=env)

    return out


class Importer:

    def __init__(self, search_paths=None):
        self.sources = {}
        self.search_paths = [Path(p) for p in (search_paths or [])]
        if STDLIB_DIR.is_dir():
            self.search_paths.append(STDLIB_DIR)
        self.cache = {}
        self._loading = []

    def add_search_path(self, path):
        self.search_paths.insert(0, Path(path))

    def register_source(self, name, source):
        self.sources[name] = source

    def _find_manifest_path(self, name):
        if name in self.sources:
            return None
        rel = Path(*name.split("."))
        for base in self.search_paths:
            path = base / rel / MANIFEST_FILENAME
            if path.is_file():
                return path
        return None

    def _load_manifest(self, name):
        path = self._find_manifest_path(name)
        if path is None:
            return None
        man = parse_manifest(path.read_text(), path)
        if man.module != name:
            raise ImporterError(
                f"Manifest '{path}' declares module '{man.module}', "
                f"but it was imported as '{name}'"
            )
        return man

    def find_source(self, name):
        if name in self.sources:
            return self.sources[name]

        manifest_path = self._find_manifest_path(name)
        if manifest_path is not None:
            man = parse_manifest(manifest_path.read_text(), manifest_path)
            if man.lang != "threadon":
                return None
            source_name = man.source or f"{name.split('.')[-1]}.th"
            source_path = manifest_path.parent / source_name
            if source_path.is_file():
                return source_path.read_text()
            return None

        rel = Path(*name.split("."))
        candidates = [rel.with_suffix(MODULE_EXTENSION)]

        for base in self.search_paths:
            for candidate in candidates:
                path = base / candidate
                if path.is_file():
                    return path.read_text()

        return None

    def _generate_python_wrapper(self, name, man, manifest_path):
        pyfile = manifest_path.parent / man.source
        wrapper = manifest_path.parent / f"{man.module}_pywrap.cpp"

        exports = []
        for export_name, ret, args in man.exports:
            exports.append((export_name, ret, args))

        code = self._emit_python_wrapper(name, pyfile, exports)
        wrapper.write_text(code)
        return wrapper


    def _c_type_for(self, t: ThType):
        if t.is_scalar:
            return C_SCALAR_TYPES[t.kind]
        if t.is_list:
            return self._list_struct_name(t)
        if t.is_dict:
            return self._dict_struct_name(t)
        raise ImporterError(f"no native C type for '{t!r}'")

    def _list_struct_name(self, t: ThType):
        elem = t.elem()
        return f"ThList_{self._type_name_part(elem)}"

    def _dict_struct_name(self, t: ThType):
        k = self._type_name_part(t.key_type())
        v = self._type_name_part(t.value_type())
        return f"ThDict_{k}_{v}"

    def _type_name_part(self, t: ThType):
        if t.is_list:
            return self._list_struct_name(t)
        if t.is_dict:
            return self._dict_struct_name(t)
        return t.kind

    def _collect_compound_types(self, types, out):

        for t in types:
            if t.is_list:
                self._collect_compound_types([t.elem()], out)
                key = t.manifest_token()
                if key not in out:
                    out[key] = t
            elif t.is_dict:
                self._collect_compound_types([t.key_type(), t.value_type()], out)
                key = t.manifest_token()
                if key not in out:
                    out[key] = t

    def _emit_list_struct_defs(self, all_types):
        compound_types = {}
        self._collect_compound_types(all_types, compound_types)

        lines = []
        for t in compound_types.values():
            if t.is_list:
                sname = self._list_struct_name(t)
                elem_c = self._c_type_for(t.elem())
                lines.append(f"struct {sname} {{ long long len; {elem_c}* data; }};")
            elif t.is_dict:
                sname = self._dict_struct_name(t)
                key_c = self._c_type_for(t.key_type())
                val_c = self._c_type_for(t.value_type())
                lines.append(
                    f"struct {sname} {{ long long len; {key_c}* keys; {val_c}* values; }};"
                )
        return lines, compound_types

    def _emit_py_to_native_scalar(self, out, dst, src_pyobj, t: ThType, fresh):
        if t.kind == "Float64":
            out.append(f"    {dst} = PyFloat_AsDouble({src_pyobj});")
        elif t.kind == "Int64":
            out.append(f"    {dst} = PyLong_AsLongLong({src_pyobj});")
        elif t.kind == "Bool":
            out.append(f"    {dst} = PyObject_IsTrue({src_pyobj}) ? true : false;")
        elif t.kind == "String":
            v = fresh("s")
            out.append(f"    const char* {v} = PyUnicode_AsUTF8({src_pyobj});")
            out.append(f"    {dst} = {v} ? strdup({v}) : nullptr;")
        else:
            raise ImporterError(f"cannot marshal scalar type '{t!r}' from Python")

    def _emit_py_to_native_list(self, out, dst_var, src_pyobj, t: ThType, fresh):

        elem_t = t.elem()
        elem_c = self._c_type_for(elem_t)
        n = fresh("n")
        i = fresh("i")
        item = fresh("item")

        out.append(f"    Py_ssize_t {n} = PySequence_Size({src_pyobj});")
        out.append(f"    {dst_var}.len = (long long){n};")
        out.append(f"    {dst_var}.data = ({elem_c}*)malloc(sizeof({elem_c}) * (size_t){n});")
        out.append(f"    for (Py_ssize_t {i} = 0; {i} < {n}; {i}++) {{")
        out.append(f"        PyObject* {item} = PySequence_GetItem({src_pyobj}, {i});")
        if elem_t.is_list:
            self._emit_py_to_native_list(
                out, f"{dst_var}.data[{i}]", item, elem_t, fresh
            )
        elif elem_t.is_dict:
            self._emit_py_to_native_dict(
                out, f"{dst_var}.data[{i}]", item, elem_t, fresh
            )
        else:
            self._emit_py_to_native_scalar(
                out, f"{dst_var}.data[{i}]", item, elem_t, fresh
            )
        out.append(f"        Py_DECREF({item});")
        out.append("    }")

    def _emit_py_to_native_dict(self, out, dst_var, src_pyobj, t: ThType, fresh):

        key_t = t.key_type()
        val_t = t.value_type()
        key_c = self._c_type_for(key_t)
        val_c = self._c_type_for(val_t)

        n = fresh("n")
        items = fresh("items")
        i = fresh("i")
        pair = fresh("pair")
        k = fresh("k")
        v = fresh("v")

        out.append(f"    Py_ssize_t {n} = PyDict_Size({src_pyobj});")
        out.append(f"    {dst_var}.len = (long long){n};")
        out.append(f"    {dst_var}.keys = ({key_c}*)malloc(sizeof({key_c}) * (size_t){n});")
        out.append(f"    {dst_var}.values = ({val_c}*)malloc(sizeof({val_c}) * (size_t){n});")
        out.append(f"    PyObject* {items} = PyDict_Items({src_pyobj});")
        out.append(f"    for (Py_ssize_t {i} = 0; {i} < {n}; {i}++) {{")
        out.append(f"        PyObject* {pair} = PyList_GetItem({items}, {i});")
        out.append(f"        PyObject* {k} = PyTuple_GetItem({pair}, 0);")
        out.append(f"        PyObject* {v} = PyTuple_GetItem({pair}, 1);")
        self._emit_py_to_native_scalar(out, f"{dst_var}.keys[{i}]", k, key_t, fresh)
        if val_t.is_list:
            self._emit_py_to_native_list(out, f"{dst_var}.values[{i}]", v, val_t, fresh)
        elif val_t.is_dict:
            self._emit_py_to_native_dict(out, f"{dst_var}.values[{i}]", v, val_t, fresh)
        else:
            self._emit_py_to_native_scalar(out, f"{dst_var}.values[{i}]", v, val_t, fresh)
        out.append("    }")
        out.append(f"    Py_DECREF({items});")

    def _emit_native_to_py_scalar(self, out, dst_pyobj, src, t: ThType):
        if t.kind == "Float64":
            out.append(f"    PyObject* {dst_pyobj} = PyFloat_FromDouble({src});")
        elif t.kind == "Int64":
            out.append(f"    PyObject* {dst_pyobj} = PyLong_FromLongLong({src});")
        elif t.kind == "Bool":
            out.append(f"    PyObject* {dst_pyobj} = PyBool_FromLong({src} ? 1 : 0);")
        elif t.kind == "String":
            out.append(f"    PyObject* {dst_pyobj} = PyUnicode_FromString({src} ? {src} : \"\");")
        else:
            raise ImporterError(f"cannot marshal scalar type '{t!r}' to Python")

    def _emit_native_to_py_list(self, out, dst_pyobj, src_var, t: ThType, fresh):
        elem_t = t.elem()
        lst = fresh("lst")
        i = fresh("i")
        out.append(f"    PyObject* {lst} = PyList_New({src_var}.len);")
        out.append(f"    for (long long {i} = 0; {i} < {src_var}.len; {i}++) {{")
        if elem_t.is_list:
            sub = fresh("sub")
            self._emit_native_to_py_list(out, sub, f"{src_var}.data[{i}]", elem_t, fresh)
            out.append(f"        PyList_SetItem({lst}, {i}, {sub});")
        elif elem_t.is_dict:
            sub = fresh("sub")
            self._emit_native_to_py_dict(out, sub, f"{src_var}.data[{i}]", elem_t, fresh)
            out.append(f"        PyList_SetItem({lst}, {i}, {sub});")
        else:
            item = fresh("it")
            self._emit_native_to_py_scalar(out, item, f"{src_var}.data[{i}]", elem_t)
            out.append(f"        PyList_SetItem({lst}, {i}, {item});")
        out.append("    }")
        out.append(f"    PyObject* {dst_pyobj} = {lst};")

    def _emit_native_to_py_dict(self, out, dst_pyobj, src_var, t: ThType, fresh):

        key_t = t.key_type()
        val_t = t.value_type()
        d = fresh("d")
        i = fresh("i")
        out.append(f"    PyObject* {d} = PyDict_New();")
        out.append(f"    for (long long {i} = 0; {i} < {src_var}.len; {i}++) {{")
        kobj = fresh("kobj")
        self._emit_native_to_py_scalar(out, kobj, f"{src_var}.keys[{i}]", key_t)
        if val_t.is_list:
            vobj = fresh("vobj")
            self._emit_native_to_py_list(out, vobj, f"{src_var}.values[{i}]", val_t, fresh)
        elif val_t.is_dict:
            vobj = fresh("vobj")
            self._emit_native_to_py_dict(out, vobj, f"{src_var}.values[{i}]", val_t, fresh)
        else:
            vobj = fresh("vobj")
            self._emit_native_to_py_scalar(out, vobj, f"{src_var}.values[{i}]", val_t)
        out.append(f"        PyDict_SetItem({d}, {kobj}, {vobj});")
        out.append(f"        Py_DECREF({kobj});")
        out.append(f"        Py_DECREF({vobj});")
        out.append("    }")
        out.append(f"    PyObject* {dst_pyobj} = {d};")

    def _emit_python_wrapper(self, module_name, pyfile, exports):
        parsed_exports = []
        all_types = []
        for func, ret_tok, arg_toks in exports:
            ret_t = parse_type(ret_tok)
            arg_ts = [parse_type(a) for a in arg_toks]
            parsed_exports.append((func, ret_t, arg_ts))
            all_types.append(ret_t)
            all_types.extend(arg_ts)

        lines = []
        lines.append('#include <Python.h>')
        lines.append('#include <cstdlib>')
        lines.append('#include <cstring>')
        lines.append('extern "C" {')
        lines.append('static bool _py_init = false;')

        pydir = str(pyfile.parent.resolve()).replace('\\', '\\\\').replace('"', '\\"')

        lines.append('static void ensure_init() {')
        lines.append('    if (!_py_init) {')
        lines.append('        Py_Initialize();')
        lines.append(f'        PyRun_SimpleString("import sys; sys.path.insert(0, \\"{pydir}\\")");')
        lines.append('        _py_init = true;')
        lines.append('    }')
        lines.append('}')
        lines.append('} // extern C (init helpers stay C-linkage-free of struct ABI concerns)')
        lines.append('')

        struct_lines, _ = self._emit_list_struct_defs(all_types)
        lines.extend(struct_lines)
        lines.append('')

        lines.append('extern "C" {')

        modname = pyfile.stem
        seq = [0]

        def fresh(base):
            seq[0] += 1
            return f"_{base}{seq[0]}"

        for func, ret_t, arg_ts in parsed_exports:
            lines.append(self._emit_export_thunk(func, ret_t, arg_ts, modname, fresh))

        lines.append("} // extern C")
        return '\n'.join(lines)

    def _emit_export_thunk(self, func, ret_t: ThType, arg_ts, modname, fresh):
        c_ret = self._c_type_for(ret_t)
        dict_ret = ret_t.is_dict
        param_parts = []
        for i, t in enumerate(arg_ts):
            if t.is_dict:
                param_parts.append(f"{self._c_type_for(t)}* a{i}")
            else:
                param_parts.append(f"{self._c_type_for(t)} a{i}")
        if dict_ret:
            param_parts.append(f"{c_ret}* _sret_out")
        params = ", ".join(param_parts)
        nargs = len(arg_ts)

        out = []
        out.append(f"{'void' if dict_ret else c_ret} {func}({params}) {{")
        out.append("    ensure_init();")

        if nargs == 0:
            out.append("    PyObject* args = nullptr;")
        else:
            out.append(f"    PyObject* args = PyTuple_New({nargs});")
            for i, t in enumerate(arg_ts):
                pyv = fresh("pyv")
                src_var = f"(*a{i})" if t.is_dict else f"a{i}"
                if t.is_list:
                    self._emit_native_to_py_list(out, pyv, f"a{i}", t, fresh)
                elif t.is_dict:
                    self._emit_native_to_py_dict(out, pyv, src_var, t, fresh)
                else:
                    self._emit_native_to_py_scalar(out, pyv, f"a{i}", t)
                out.append(f"    PyTuple_SetItem(args, {i}, {pyv});")

        out.append(f'    PyObject* mod = PyImport_ImportModule("{modname}");')
        out.append(f"    if (!mod) {{ {'*_sret_out = ' + self._zero_c_value(ret_t) + ';' if dict_ret else 'return ' + self._zero_c_value(ret_t) + ';'} }}")
        out.append(f'    PyObject* f = PyObject_GetAttrString(mod, "{func}");')
        out.append("    Py_DECREF(mod);")
        out.append(f"    if (!f || !PyCallable_Check(f)) {{ Py_XDECREF(f); {'*_sret_out = ' + self._zero_c_value(ret_t) + ';' if dict_ret else 'return ' + self._zero_c_value(ret_t) + ';'} }}")

        out.append("    PyObject* r = PyObject_CallObject(f, args);")
        out.append("    Py_DECREF(f);")
        if nargs > 0:
            out.append("    Py_DECREF(args);")
        out.append(f"    if (!r) {{ PyErr_Clear(); {'*_sret_out = ' + self._zero_c_value(ret_t) + ';' if dict_ret else 'return ' + self._zero_c_value(ret_t) + ';'} }}")

        if ret_t.is_list:
            out.append(f"    {self._c_type_for(ret_t)} out;")
            self._emit_py_to_native_list(out, "out", "r", ret_t, fresh)
            out.append("    Py_DECREF(r);")
            out.append("    return out;")
        elif ret_t.is_dict:
            out.append(f"    auto& _dout = *_sret_out;")
            self._emit_py_to_native_dict(out, "_dout", "r", ret_t, fresh)
            out.append("    Py_DECREF(r);")
            out.append("    return;")
        else:
            outv = fresh("out")
            self._emit_py_to_native_scalar(out, f"{c_ret} {outv}", "r", ret_t, fresh)
            out.append("    Py_DECREF(r);")
            out.append(f"    return {outv};")

        out.append("}")
        return "\n".join(out)

    def _zero_c_value(self, t: ThType):
        if t.is_list:
            sname = self._list_struct_name(t)
            return f"{sname}{{0, nullptr}}"
        if t.is_dict:
            sname = self._dict_struct_name(t)
            return f"{sname}{{0, nullptr, nullptr}}"
        return {
            "Float64": "0.0",
            "Int64": "0",
            "Bool": "false",
            "String": "nullptr",
        }[t.kind]

    def _build_native_module(self, name, man, manifest_path):
        module = Module(name, None, None)
        module.lang = man.lang
        module.toolchain = toolchain_for(man.lang)
        module.is_native = True
        module.manifest_dir = manifest_path.parent
        module.flags = list(man.flags)
        module.links = list(man.links)
        module.exports = [(n, r, list(a)) for n, r, a in man.exports]

        if man.source:
            module.native_source = manifest_path.parent / man.source

        importer_dir = Path(__file__).resolve().parent

        if man.lang == "python":
            if man.source.endswith(".py"):
                wrapper_cpp = self._generate_python_wrapper(name, man, manifest_path)
                module.native_source = wrapper_cpp

            candidates = [
                manifest_path.parent / "python_bridge.cpp",
                importer_dir / "python_bridge.cpp",
            ]

            bridge_cpp = None
            for c in candidates:
                if c.exists():
                    bridge_cpp = c
                    break

            if bridge_cpp is None:
                raise ImporterError("python_bridge.cpp missing")

            module.extra_sources = [bridge_cpp]

        else:
            module.extra_sources = []

        for export_name, ret, args in man.exports:
            module.func_exports.add(export_name)
            qname = f"{name}.{export_name}"
            params = [(f"a{i}", t, None) for i, t in enumerate(args)]
            module.func_sigs[qname] = (params, ret)

        out = build_native(module)
        module.native_binary = out
        return module

    def load(self, name):
        if name in self.cache:
            return self.cache[name]

        if name in self._loading:
            chain = " -> ".join(self._loading + [name])
            raise ImporterError(f"Circular import detected: {chain}")

        manifest_path = self._find_manifest_path(name)
        man = self._load_manifest(name) if manifest_path is not None else None

        if man is not None and man.lang != "threadon":
            module = self._build_native_module(name, man, manifest_path)
            self.cache[name] = module
            return module

        source = self.find_source(name)
        if source is None:
            raise ImporterError(
                f"Module '{name}' not found"
                f" (searched: {', '.join(str(p) for p in self.search_paths)})"
            )

        self._loading.append(name)

        from .parser import Parser

        try:
            parser = Parser(importer=self, module_name=name)
            ast = parser.parse(source)
        finally:
            self._loading.pop()

        module = Module(name, source, ast)
        module.func_sigs = parser.func_sigs
        module.struct_defs = parser.struct_defs
        module.class_defs = parser.class_defs
        module.class_ast = parser.class_ast
        module.class_method_map = parser.class_method_map
        module.func_exports = set(parser.qfunc.keys())
        module.struct_exports = set(parser.qstruct.keys())
        module.class_exports = set(parser.qclass.keys())
        module.var_exports = {
            node.name for node in ast if type(node).__name__ == "VarDecl"
        }

        if man is not None:
            module.manifest_dir = manifest_path.parent
            module.lang = man.lang
            module.flags = list(man.flags)
            module.links = list(man.links)

        self.cache[name] = module
        return module

    def load_main(self, source, module_name=""):
        from .parser import Parser

        self._main_parser = Parser(importer=self, module_name=module_name)
        return self._main_parser.parse(source)

    def modules(self):
        return list(self.cache.values())