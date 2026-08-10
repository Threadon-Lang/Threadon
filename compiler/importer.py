from pathlib import Path

MODULE_EXTENSION = ".th"
STDLIB_DIR = Path(__file__).resolve().parent.parent / "stdlib"


class ImporterError(Exception):
    pass


class Module:


    def __init__(self, name: str, source: str, ast=None):
        self.name = name
        self.source = source
        self.ast = ast
        self.func_sigs = {}
        self.struct_defs = {}
        self.func_exports = set()
        self.struct_exports = set()
        self.var_exports = set()

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

    def find_source(self, name):
        if name in self.sources:
            return self.sources[name]

        rel = Path(*name.split("."))
        candidates = [rel.with_suffix(MODULE_EXTENSION)]

        for base in self.search_paths:
            for candidate in candidates:
                path = base / candidate
                if path.is_file():
                    return path.read_text()

        return None

    def load(self, name):
        if name in self.cache:
            return self.cache[name]

        if name in self._loading:
            chain = " -> ".join(self._loading + [name])
            raise ImporterError(f"Circular import detected: {chain}")

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
        module.func_exports = set(parser.qfunc.keys())
        module.struct_exports = set(parser.qstruct.keys())
        module.var_exports = {
            node.name for node in ast if type(node).__name__ == "VarDecl"
        }

        self.cache[name] = module
        return module

    def load_main(self, source, module_name=""):
        from .parser import Parser

        self._main_parser = Parser(importer=self, module_name=module_name)
        return self._main_parser.parse(source)

    def modules(self):
        return list(self.cache.values())

