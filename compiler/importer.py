from pathlib import Path

MODULE_EXTENSION = ".th"
MANIFEST_FILENAME = "manifest"
STDLIB_DIR = Path(__file__).resolve().parent.parent / "stdlib"


class ImporterError(Exception):
    pass


class Toolchain:
    """How to build a native module written in a given language.

    A toolchain knows the compiler to invoke, the extra arguments needed to
    build a shared library (``--run``/``lli -load``) and an object/archive
    file (``--exe``), and the object file extension.  ``cxx`` marks languages
    whose objects must be linked with ``g++``.
    """

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
    "c": Toolchain("c", "gcc", ["-shared", "-fPIC"], ["-c"]),
    "cpp": Toolchain("cpp", "g++", ["-shared", "-fPIC"], ["-c"], cxx=True),
    "c++": Toolchain("c++", "g++", ["-shared", "-fPIC"], ["-c"], cxx=True),
    "rust": Toolchain(
        "rust",
        "rustc",
        ["--crate-type", "cdylib"],
        ["--crate-type", "staticlib"],
        object_ext="a",
    ),
    "python":Toolchain(
        "python",
        "g++",
        [
            "-shared",
            "-fPIC",
            "`python3-config --includes`"
        ],
        [
            "-c",
            "`python3-config --includes`"
        ],
        object_ext="so",
        cxx=True
    )
}


def toolchain_for(lang):
    if lang in LANGUAGES:
        return LANGUAGES[lang]
    raise ImporterError(f"unknown language '{lang}'")


class Manifest:
    """Parsed contents of a module's ``manifest`` file.

    A manifest describes a module without (or alongside) its source::

        module math
        lang cpp
        source math.cpp
        flag -std=c++17 -O2
        link m

        export sin Float64 Float64
        export cos Float64 Float64

    ``lang`` names the language of ``source``.  It defaults to ``threadon``
    and can be any language with a registered toolchain (``c``, ``cpp``,
    ``c++``, ``rust``, ...).  For a threadon module the ``source`` field
    points at the ``.th`` file.  For any other language the ``export`` lines
    declare the C symbols the module makes available, ``flag`` lists the
    compile flags and ``link`` lists the libraries to link against.  Adding a
    new language only requires registering a :class:`Toolchain` in
    ``LANGUAGES``.
    """

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

    def __repr__(self):
        return f"Module({self.name!r})"


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
        for export_name, ret, args in man.exports:
            module.func_exports.add(export_name)
            qname = f"{name}.{export_name}"
            params = [(f"a{i}", t, None) for i, t in enumerate(args)]
            module.func_sigs[qname] = (params, ret)
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
