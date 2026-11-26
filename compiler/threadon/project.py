"""Project and local-package support for Threadon.

A Threadon project is identified by a ``threadon.toml`` file.  The format is
deliberately small and C-like: a project has a name, a main source file, include
paths, and path dependencies.  There is no registry and no remote fetch step;
a dependency is simply another directory, optionally with its own
``threadon.toml``.

The standard library is an implicit dependency and is handled by ``Importer``,
so it never has to be listed in the config file.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .errors import ThreadonError, error_text

CONFIG_FILENAME = "threadon.toml"
LOCK_FILENAME = "threadon.lock"
CACHE_ENV_VAR = "THREADON_CACHE_DIR"
BUILD_DIR_NAME = ".threadon"
PACKAGE_METADATA = ".threadon-package.json"

_SKIP_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules",
    "__pycache__", "build", "dist", "target", ".threadon",
}
_HASH_SUFFIXES = {
    ".th", ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".rs", ".py", ".ll",
}
_HASH_NAMES = {"manifest", CONFIG_FILENAME, LOCK_FILENAME}


class ProjectError(ThreadonError):
    """A project configuration/package problem."""

    def __init__(self, message: str):
        super().__init__(error_text(message))


@dataclass
class ProjectConfig:
    """Parsed ``threadon.toml`` contents."""

    root: Path
    name: str
    version: str = "0.1.0"
    main: Optional[str] = "src/main.th"
    include: List[str] = field(default_factory=lambda: ["src"])
    test: List[str] = field(default_factory=lambda: ["tests"])
    dependencies: Dict[str, str] = field(default_factory=dict)
    source_file: Optional[Path] = None

    @property
    def main_path(self) -> Path:
        main = self.main or "src/main.th"
        return (self.root / main).resolve()

    @property
    def include_paths(self) -> List[Path]:
        return [_resolve_path(self.root, item) for item in self.include]

    @property
    def test_paths(self) -> List[Path]:
        return [_resolve_path(self.root, item) for item in self.test]

    @property
    def config_hash(self) -> str:
        if self.source_file is not None and self.source_file.is_file():
            return hash_tree(self.source_file)
        return ""


@dataclass
class DependencyInfo:
    """A resolved dependency, used for both import paths and the lockfile."""

    name: str
    path: Path
    version: str
    digest: str
    config: Optional[ProjectConfig] = None

    def lock_entry(self, root: Path) -> Dict[str, str]:
        return {
            "name": self.name,
            "path": _relative_path(root, self.path),
            "version": self.version,
            "hash": self.digest,
        }


# --- small TOML reader ------------------------------------------------------

def _strip_comment(line: str) -> str:
    quote = None
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote == '"':
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
        elif char == "#":
            return line[:index]
    return line


def _parse_toml_string(value: str, line_no: int, path: Path) -> str:
    value = value.strip()
    if len(value) < 2 or value[0] not in "\"'" or value[-1] != value[0]:
        raise ProjectError(f"{path} line {line_no}: expected a quoted string")
    if value[0] == "'":
        return value[1:-1]
    try:
        parsed = json.loads(value)
    except Exception:
        raise ProjectError(f"{path} line {line_no}: invalid string literal")
    if not isinstance(parsed, str):
        raise ProjectError(f"{path} line {line_no}: expected a quoted string")
    return parsed


def _split_toml_array(body: str, line_no: int, path: Path) -> List[str]:
    items: List[str] = []
    current: List[str] = []
    quote = None
    escaped = False
    for char in body:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\" and quote == '"':
            current.append(char)
            escaped = True
            continue
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
            current.append(char)
        elif char == ",":
            item = "".join(current).strip()
            if item:
                items.append(item)
            current = []
        else:
            current.append(char)
    if quote is not None:
        raise ProjectError(f"{path} line {line_no}: unterminated string in array")
    item = "".join(current).strip()
    if item:
        items.append(item)
    return items


def _parse_simple_toml(text: str, path: Path) -> Dict[str, Any]:
    """Parse the small TOML subset used by ``threadon.toml``.

    Supports sections, quoted strings, arrays of strings, integers, and
    booleans.  Inline tables and nested sections are intentionally rejected;
    they are not part of the project config format.
    """
    data: Dict[str, Any] = {}
    section = data
    for line_no, raw in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw).strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1].strip()
            if not name or name in data:
                raise ProjectError(f"{path} line {line_no}: invalid section '{name}'")
            if "." in name:
                raise ProjectError(f"{path} line {line_no}: nested sections are not supported")
            section = {}
            data[name] = section
            continue
        if "=" not in line:
            raise ProjectError(f"{path} line {line_no}: expected 'key = value'")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and key[0] in "\"'":
            key = _parse_toml_string(key, line_no, path)
        elif not re.fullmatch(r"[A-Za-z0-9_-]+", key):
            raise ProjectError(f"{path} line {line_no}: invalid key '{key}'")
        if value.startswith("{") or value.startswith("[["):
            raise ProjectError(f"{path} line {line_no}: inline tables are not supported")
        if value.startswith("["):
            if not value.endswith("]"):
                raise ProjectError(f"{path} line {line_no}: unterminated array")
            section[key] = [
                _parse_toml_string(item, line_no, path)
                for item in _split_toml_array(value[1:-1], line_no, path)
            ]
        elif value and value[0] in "\"'":
            section[key] = _parse_toml_string(value, line_no, path)
        elif value in ("true", "false"):
            section[key] = value == "true"
        elif re.fullmatch(r"-?\d+", value):
            section[key] = int(value)
        else:
            raise ProjectError(
                f"{path} line {line_no}: unsupported value '{value}' "
                "(use strings and string arrays)"
            )
    return data


def _load_toml(text: str, path: Path) -> Dict[str, Any]:
    try:
        import tomllib  # type: ignore
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore
        except ImportError:
            return _parse_simple_toml(text, path)

    try:
        data = tomllib.loads(text)
    except Exception as exc:
        raise ProjectError(f"{path}: invalid TOML ({exc})")
    return data


# --- config loading and writing --------------------------------------------

def _resolve_path(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def _relative_path(root: Path, path: Path) -> str:
    return Path(os.path.relpath(str(path), str(root))).as_posix()


def _string_list(value: Any, label: str, path: Path) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value):
        return list(value)
    raise ProjectError(f"{path}: '{label}' must be a string or an array of strings")


def _validate_toml(data: Dict[str, Any], path: Path) -> None:
    allowed_sections = {"project", "dependencies", "paths"}
    for key in data:
        if key not in allowed_sections:
            raise ProjectError(f"{path}: unknown section '{key}'")
    project = data.get("project", {})
    paths = data.get("paths", {})
    dependencies = data.get("dependencies", {})
    if not isinstance(project, dict):
        raise ProjectError(f"{path}: '[project]' must be a table")
    if not isinstance(paths, dict):
        raise ProjectError(f"{path}: '[paths]' must be a table")
    if not isinstance(dependencies, dict):
        raise ProjectError(f"{path}: '[dependencies]' must be a table")
    for key in project:
        if key not in {"name", "version", "main", "test"}:
            raise ProjectError(f"{path}: unknown [project] key '{key}'")
    for key in paths:
        if key not in {"include", "test"}:
            raise ProjectError(f"{path}: unknown [paths] key '{key}'")
    for name, value in dependencies.items():
        if not isinstance(value, str):
            raise ProjectError(
                f"{path}: dependency '{name}' must be a path string "
                "(there is no package registry)"
            )


def parse_project_text(text: str, root: Path, path: Optional[Path] = None) -> ProjectConfig:
    """Parse ``threadon.toml`` text into a :class:`ProjectConfig`."""
    path = path or root / CONFIG_FILENAME
    data = _load_toml(text, path)
    _validate_toml(data, path)

    project = data.get("project", {})
    paths = data.get("paths", {})
    dependencies = data.get("dependencies", {})

    name = project.get("name", root.name)
    version = project.get("version", "0.1.0")
    if not isinstance(name, str) or not name:
        raise ProjectError(f"{path}: 'name' must be a non-empty string")
    if not isinstance(version, str) or not version:
        raise ProjectError(f"{path}: 'version' must be a non-empty string")
    main = project.get("main", "src/main.th")
    if main is not None and not isinstance(main, str):
        raise ProjectError(f"{path}: 'main' must be a string")

    include = _string_list(paths.get("include", ["src"]), "paths.include", path)
    test_value = paths.get("test", project.get("test", ["tests"]))
    test = _string_list(test_value, "paths.test", path)

    return ProjectConfig(
        root=root.resolve(),
        name=name,
        version=version,
        main=main,
        include=include,
        test=test,
        dependencies=dict(dependencies),
        source_file=path,
    )


def find_config(start: Optional[Path] = None) -> Optional[Path]:
    """Find the nearest ``threadon.toml`` at or above ``start``."""
    start = Path(start or Path.cwd()).resolve()
    if start.is_file():
        start = start.parent
    home = Path.home().resolve()
    for candidate in [start, *start.parents]:
        config = candidate / CONFIG_FILENAME
        if config.is_file():
            return config
        if candidate == candidate.parent or candidate == home:
            break
    return None


def load_project(start: Optional[Path] = None, required: bool = True) -> Optional[ProjectConfig]:
    """Load the project config for ``start`` (a file or directory)."""
    config_path = find_config(start)
    if config_path is None:
        if required:
            origin = Path(start or Path.cwd()).resolve()
            raise ProjectError(f"no {CONFIG_FILENAME} found in {origin} or its parent directories")
        return None
    return parse_project_text(config_path.read_text(), config_path.parent, config_path)


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _toml_string_array(values: Sequence[str]) -> str:
    return "[" + ", ".join(_toml_string(v) for v in values) + "]"


def render_project(config: ProjectConfig) -> str:
    """Render a deterministic ``threadon.toml`` for ``config``."""
    lines = [
        "# Threadon project configuration",
        "[project]",
        f"name = {_toml_string(config.name)}",
        f"version = {_toml_string(config.version)}",
    ]
    if config.main:
        lines.append(f"main = {_toml_string(config.main)}")
    lines.extend(["", "[dependencies]"])
    for name in sorted(config.dependencies):
        lines.append(f"{_toml_string(name)} = {_toml_string(config.dependencies[name])}")
    lines.extend([
        "",
        "[paths]",
        f"include = {_toml_string_array(config.include)}",
        f"test = {_toml_string_array(config.test)}",
        "",
    ])
    return "\n".join(lines)


def write_project(config: ProjectConfig) -> Path:
    """Write ``config`` back to its ``threadon.toml``."""
    root = config.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = config.source_file or root / CONFIG_FILENAME
    path.write_text(render_project(config))
    config.source_file = path
    return path


def _write_if_missing(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(text)


def init_project(root: Path, name: Optional[str] = None, force: bool = False) -> ProjectConfig:
    """Create a new project skeleton in ``root``."""
    root = root.resolve()
    config_path = root / CONFIG_FILENAME
    if config_path.exists() and not force:
        raise ProjectError(f"{config_path} already exists")

    config = ProjectConfig(
        root=root,
        name=name or root.name,
        version="0.1.0",
        main="src/main.th",
        include=["src"],
        test=["tests"],
        source_file=config_path,
    )
    write_project(config)
    _write_if_missing(
        root / "src" / "main.th",
        'def main() -> Int32\n    print("Hello, Threadon!")\n    return 0\n',
    )
    _write_if_missing(
        root / "tests" / "test.th",
        "import unittest\n\ndef test_smoke() -> Bool\n"
        "    return unittest.assert_true(1 + 1 == 2)\n",
    )
    write_lock(config)
    return config


# --- dependencies -----------------------------------------------------------

def module_cache_dir() -> Path:
    """Directory holding cached dependency snapshots."""
    override = os.environ.get(CACHE_ENV_VAR)
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".cache" / "threadon" / "modules").resolve()


def build_cache_dir(root: Path) -> Path:
    return (root.resolve() / BUILD_DIR_NAME / "cache").resolve()


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)


def cached_dependency_dir(name: str, source: Path) -> Path:
    source = source.resolve()
    digest = hash_tree(source)[:12] or "empty"
    return module_cache_dir() / f"{_safe_name(name)}-{digest}"


def _copy_ignore(_dir: str, names: List[str]) -> set:
    return {name for name in names if name in _SKIP_DIRS or name == PACKAGE_METADATA}


def cache_dependency(name: str, source: Path) -> Path:
    """Copy a local dependency into the user module cache."""
    source = Path(source).resolve()
    if not source.is_dir():
        raise ProjectError(f"dependency '{name}' is not a directory: {source}")
    target = cached_dependency_dir(name, source)
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, ignore=_copy_ignore)
    metadata = {
        "name": name,
        "source": str(source),
        "hash": hash_tree(source),
    }
    (target / PACKAGE_METADATA).write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n"
    )
    return target


def list_cached_modules() -> List[Dict[str, str]]:
    """Return metadata for cached dependencies, sorted by name."""
    base = module_cache_dir()
    if not base.is_dir():
        return []
    entries = []
    for child in base.iterdir():
        metadata_path = child / PACKAGE_METADATA
        if not child.is_dir() or not metadata_path.is_file():
            continue
        try:
            metadata = json.loads(metadata_path.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(metadata, dict) and isinstance(metadata.get("name"), str):
            entries.append(metadata)
    return sorted(entries, key=lambda item: (item["name"], item.get("source", "")))


def clear_module_cache() -> bool:
    """Remove the user module cache.  Return whether anything was removed."""
    base = module_cache_dir()
    if not base.exists():
        return False
    shutil.rmtree(base)
    return True


def clear_compile_cache(root: Path) -> bool:
    """Remove the project-local compile cache."""
    base = build_cache_dir(root)
    if not base.exists():
        return False
    shutil.rmtree(base)
    return True


def _find_cached_dependency(name: str, source: Path) -> Optional[Path]:
    wanted = str(source.resolve())
    base = module_cache_dir()
    if not base.is_dir():
        return None
    for child in base.iterdir():
        metadata_path = child / PACKAGE_METADATA
        if not child.is_dir() or not metadata_path.is_file():
            continue
        try:
            metadata = json.loads(metadata_path.read_text())
        except (OSError, ValueError):
            continue
        if (
            isinstance(metadata, dict)
            and metadata.get("name") == name
            and metadata.get("source") == wanted
        ):
            return child
    return None


def resolve_dependency(config: ProjectConfig, name: str, value: str) -> Path:
    """Resolve a dependency path, falling back to a cached snapshot."""
    local = _resolve_path(config.root, value)
    if local.exists():
        return local.resolve()
    cached = _find_cached_dependency(name, local)
    if cached is not None:
        return cached.resolve()
    raise ProjectError(f"dependency '{name}' not found: {local}")


def collect_dependencies(config: ProjectConfig) -> List[DependencyInfo]:
    """Resolve direct and transitive path dependencies."""
    infos: List[DependencyInfo] = []
    seen: set = set()

    def visit(owner: ProjectConfig) -> None:
        for name, value in owner.dependencies.items():
            path = resolve_dependency(owner, name, value)
            if path in seen:
                continue
            seen.add(path)
            dep_config = load_project(path, required=False)
            if dep_config is not None:
                digest = dep_config.config_hash or hash_tree(path)
                version = dep_config.version
            else:
                digest = hash_tree(path)
                version = ""
            infos.append(DependencyInfo(name, path, version, digest, dep_config))
            if dep_config is not None:
                visit(dep_config)

    visit(config)
    return infos


def dependency_roots(config: ProjectConfig) -> List[Path]:
    """Import directories contributed by dependencies, low priority first."""
    roots: List[Path] = []
    seen = set()
    for info in collect_dependencies(config):
        candidates = [info.path]
        if info.config is not None:
            candidates.extend(info.config.include_paths)
        for path in candidates:
            path = path.resolve()
            if path not in seen:
                seen.add(path)
                roots.append(path)
    return roots


def importer_paths(config: ProjectConfig, extra: Optional[Iterable[Path]] = None) -> List[Path]:
    """Search paths in low-to-high priority order for ``Importer.add_search_path``."""
    paths: List[Path] = []
    seen = set()
    for path in [*dependency_roots(config), *config.include_paths, *(extra or [])]:
        path = Path(path).resolve()
        if path not in seen:
            seen.add(path)
            paths.append(path)
    return paths


def apply_to_importer(
    config: ProjectConfig,
    importer: Any,
    extra: Optional[Iterable[Path]] = None,
) -> List[Path]:
    """Add project dependency/include paths to an ``Importer``.

    ``Importer.add_search_path`` inserts at the front, so adding low-priority
    paths first leaves project includes ahead of dependencies and explicit
    ``-I`` paths ahead of both.  The caller can add the source file's own
    directory last to give it top priority.
    """
    paths = importer_paths(config, extra)
    for path in paths:
        importer.add_search_path(path)
    return paths


# --- lockfile ---------------------------------------------------------------

def write_lock(config: ProjectConfig) -> Path:
    """Write ``threadon.lock`` for ``config``."""
    root = config.root.resolve()
    data = {
        "version": 1,
        "project": config.name,
        "config_hash": config.config_hash,
        "dependencies": [
            info.lock_entry(root) for info in collect_dependencies(config)
        ],
    }
    path = root / LOCK_FILENAME
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return path


def read_lock(root: Path) -> Optional[Dict[str, Any]]:
    path = Path(root) / LOCK_FILENAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def add_dependency(config: ProjectConfig, name: str, path: Path) -> Tuple[ProjectConfig, Path]:
    """Record and cache a local path dependency."""
    if not name or not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise ProjectError(f"invalid dependency name '{name}'")
    path = Path(path).expanduser().resolve()
    if not path.is_dir():
        raise ProjectError(f"dependency path is not a directory: {path}")
    config.dependencies[name] = _relative_path(config.root, path)
    write_project(config)
    cached = cache_dependency(name, path)
    write_lock(config)
    return config, cached


# --- hashing and compile cache ---------------------------------------------

def _iter_hash_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    if not path.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(str(path)):
        dirnames[:] = [d for d in sorted(dirnames) if d not in _SKIP_DIRS]
        for filename in sorted(filenames):
            if filename in _HASH_NAMES or Path(filename).suffix in _HASH_SUFFIXES:
                yield Path(dirpath) / filename


def hash_tree(path: Path) -> str:
    """Stable SHA-256 over the relevant source files under ``path``."""
    digest = hashlib.sha256()
    root = Path(path).resolve()
    digest.update(str(root).encode("utf-8"))
    found = False
    for item in _iter_hash_files(root):
        found = True
        try:
            rel = item.resolve().relative_to(root).as_posix()
        except ValueError:
            rel = item.name
        content = item.read_bytes()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(content)).encode("ascii"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    if not found and root.is_file():
        digest.update(root.read_bytes())
    return digest.hexdigest()


def compile_key(
    paths: Iterable[Path],
    options: Optional[Dict[str, Any]] = None,
) -> str:
    """Build a cache key from source/include paths and compile options."""
    digest = hashlib.sha256()
    seen = set()
    for path in paths:
        path = Path(path).resolve()
        if path in seen:
            continue
        seen.add(path)
        digest.update(str(path).encode("utf-8"))
        digest.update(hash_tree(path).encode("ascii"))
    digest.update(json.dumps(options or {}, sort_keys=True, default=str).encode("utf-8"))
    return digest.hexdigest()


def compile_cache_files(root: Path, name: str) -> Tuple[Path, Path]:
    safe = _safe_name(name)
    base = build_cache_dir(root)
    return base / f"{safe}.ll", base / f"{safe}.json"


def load_compile_cache(root: Path, name: str, key: str) -> Optional[str]:
    """Return cached LLVM IR when ``key`` matches and no native modules were used."""
    llvm_path, meta_path = compile_cache_files(root, name)
    if not llvm_path.is_file() or not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text())
    except (OSError, ValueError):
        return None
    if meta.get("key") != key or meta.get("native") is not False:
        return None
    return llvm_path.read_text()


def save_compile_cache(
    root: Path,
    name: str,
    key: str,
    llvm: str,
    *,
    native: bool = False,
) -> Optional[Path]:
    """Store LLVM IR in the project cache unless native modules are present."""
    if native:
        return None
    llvm_path, meta_path = compile_cache_files(root, name)
    llvm_path.parent.mkdir(parents=True, exist_ok=True)
    llvm_path.write_text(llvm)
    meta_path.write_text(
        json.dumps({"key": key, "native": False, "name": name}, indent=2, sort_keys=True)
        + "\n"
    )
    return llvm_path
