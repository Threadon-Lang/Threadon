"""Tests for the threadon.toml project/package system."""
import json
import os
import sys
from pathlib import Path

import pytest

from compiler.threadon import __main__ as cli
from compiler.threadon import project
from compiler.threadon.importer import Importer


class FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


# --- config parsing ---------------------------------------------------------

def test_parse_simple_toml_subset(tmp_path):
    text = '''\
# comment
[project]
name = "demo"
version = "1.2.3"
main = "src/main.th"

[dependencies]
"util.lib" = "../util"

[paths]
include = ["src", "lib"]
test = "tests"
'''
    config_path = tmp_path / project.CONFIG_FILENAME
    data = project._parse_simple_toml(text, config_path)
    assert data == {
        "project": {"name": "demo", "version": "1.2.3", "main": "src/main.th"},
        "dependencies": {"util.lib": "../util"},
        "paths": {"include": ["src", "lib"], "test": "tests"},
    }

    with pytest.raises(project.ProjectError, match="inline tables"):
        project._parse_simple_toml('[project]\nmeta = { name = "x" }\n', config_path)
    with pytest.raises(project.ProjectError, match="unsupported value"):
        project._parse_simple_toml('[project]\nname = bare\n', config_path)


def test_parse_project_text_and_validation(tmp_path):
    root = tmp_path / "demo"
    config = project.parse_project_text(
        '''\
[project]
name = "demo"
version = "2.0"
main = "app.th"
test = ["spec"]

[dependencies]
util = "../util"

[paths]
include = ["src"]
''',
        root,
    )
    assert config.name == "demo"
    assert config.version == "2.0"
    assert config.main_path == root / "app.th"
    assert config.test_paths == [root / "spec"]
    assert config.dependencies == {"util": "../util"}

    with pytest.raises(project.ProjectError, match="unknown section"):
        project.parse_project_text("[bogus]\nname = 'x'\n", root)
    with pytest.raises(project.ProjectError, match="unknown \\[project\\] key"):
        project.parse_project_text("[project]\nbogus = 'x'\n", root)
    with pytest.raises(project.ProjectError, match="must be a path string"):
        project.parse_project_text("[dependencies]\nutil = 3\n", root)


def test_find_and_load_project_from_subdirectory(tmp_path):
    root = tmp_path / "app"
    write(root / project.CONFIG_FILENAME, '[project]\nname = "app"\n')
    nested = root / "src" / "deep"
    nested.mkdir(parents=True)
    assert project.find_config(nested) == root / project.CONFIG_FILENAME
    assert project.load_project(nested).name == "app"
    assert project.load_project(tmp_path, required=False) is None


# --- init, dependencies, lockfile ------------------------------------------

def test_init_project_creates_skeleton_and_lock(tmp_path):
    root = tmp_path / "demo"
    config = project.init_project(root, "demo")
    assert (root / project.CONFIG_FILENAME).is_file()
    assert (root / "src" / "main.th").is_file()
    assert (root / "tests" / "test.th").is_file()
    assert config.name == "demo"
    assert config.version == "0.1.0"
    assert config.main == "src/main.th"

    lock = project.read_lock(root)
    assert lock["version"] == 1
    assert lock["project"] == "demo"
    assert lock["dependencies"] == []
    assert project.read_lock(root) == json.loads((root / project.LOCK_FILENAME).read_text())

    with pytest.raises(project.ProjectError, match="already exists"):
        project.init_project(root, "other")
    project.init_project(root, "other", force=True)
    assert project.load_project(root).name == "other"


def test_add_dependency_updates_config_lock_and_cache(monkeypatch, tmp_path):
    monkeypatch.setenv(project.CACHE_ENV_VAR, str(tmp_path / "modules"))
    app = project.init_project(tmp_path / "app", "app")
    util = project.init_project(tmp_path / "util", "util")
    write(util.root / "src" / "util.th", "def twice(x: Int32) -> Int32\n    return x * 2\n")

    config, cached = project.add_dependency(app, "util", util.root)
    assert config.dependencies["util"] == "../util"
    assert '"util" = "../util"' in (app.root / project.CONFIG_FILENAME).read_text()
    assert (cached / project.PACKAGE_METADATA).is_file()
    assert (cached / project.PACKAGE_METADATA).name == project.PACKAGE_METADATA

    lock = project.read_lock(app.root)
    entry = lock["dependencies"][0]
    assert entry["name"] == "util"
    assert entry["path"] == "../util"
    assert entry["version"] == "0.1.0"
    assert entry["hash"]

    entries = project.list_cached_modules()
    assert [item["name"] for item in entries] == ["util"]
    assert project.module_cache_dir() == tmp_path / "modules"
    assert project.clear_module_cache() is True
    assert project.list_cached_modules() == []
    assert project.clear_module_cache() is False


def test_resolve_dependency_falls_back_to_cached_copy(monkeypatch, tmp_path):
    monkeypatch.setenv(project.CACHE_ENV_VAR, str(tmp_path / "modules"))
    app = project.init_project(tmp_path / "app", "app")
    util = project.init_project(tmp_path / "util", "util")
    config, cached = project.add_dependency(app, "util", util.root)

    util.root.rename(util.root.with_name("util-moved"))
    resolved = project.resolve_dependency(config, "util", config.dependencies["util"])
    assert resolved == cached.resolve()

    with pytest.raises(project.ProjectError, match="not found"):
        project.resolve_dependency(config, "missing", "../nowhere")


def test_importer_paths_priority_and_application(monkeypatch, tmp_path):
    monkeypatch.setenv(project.CACHE_ENV_VAR, str(tmp_path / "modules"))
    app = project.init_project(tmp_path / "app", "app")
    util = project.init_project(tmp_path / "util", "util")
    config, _ = project.add_dependency(app, "util", util.root)

    paths = project.importer_paths(config)
    assert paths == [util.root, util.root / "src", app.root / "src"]

    importer = Importer()
    added = project.apply_to_importer(config, importer, [tmp_path / "extra"])
    assert added[-1] == (tmp_path / "extra").resolve()
    assert importer.search_paths[0] == (tmp_path / "extra").resolve()
    assert importer.search_paths[1] == app.root / "src"
    assert importer.search_paths[2] == util.root / "src"


def test_collect_dependencies_is_cycle_safe(monkeypatch, tmp_path):
    monkeypatch.setenv(project.CACHE_ENV_VAR, str(tmp_path / "modules"))
    a = project.init_project(tmp_path / "a", "a")
    b = project.init_project(tmp_path / "b", "b")
    config, _ = project.add_dependency(a, "b", b.root)
    other = project.load_project(b.root)
    project.add_dependency(other, "a", a.root)

    infos = project.collect_dependencies(config)
    names = [info.name for info in infos]
    assert names.count("b") == 1
    assert "a" in names  # transitive dependency is recorded, then cycle stops


# --- hashing and compile cache ---------------------------------------------

def test_hash_and_compile_cache(monkeypatch, tmp_path):
    root = tmp_path / "app"
    source = write(root / "src" / "main.th", "def main() -> Int32\n    return 0\n")
    key = project.compile_key([source], {"debug": False})
    assert key == project.compile_key([source], {"debug": False})
    assert key != project.compile_key([source], {"debug": True})

    llvm = "define i32 @main() { ret i32 0 }"
    llvm_path = project.save_compile_cache(root, "app", key, llvm)
    assert llvm_path.is_file()
    assert project.load_compile_cache(root, "app", key) == llvm
    assert project.load_compile_cache(root, "app", "wrong-key") is None

    meta = json.loads(llvm_path.with_suffix(".json").read_text())
    assert meta["native"] is False
    assert meta["key"] == key

    source.write_text("def main() -> Int32\n    return 1\n")
    assert project.compile_key([source], {"debug": False}) != key
    assert project.save_compile_cache(root, "app", key, llvm, native=True) is None
    assert project.clear_compile_cache(root) is True
    assert project.clear_compile_cache(root) is False


# --- CLI project commands ---------------------------------------------------

def test_cli_init_and_duplicate_error(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NO_COLOR", "1")
    assert cli.main(["init", "demo"]) == 0
    out = capsys.readouterr().out
    assert "initialized demo" in out
    assert "threadon.toml" in out

    assert cli.main(["init", "again"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("Error:") == 1
    assert "already exists" in captured.err


def test_cli_build_run_test_and_clean(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv(project.CACHE_ENV_VAR, str(tmp_path / "modules"))
    project.init_project(tmp_path, "demo")

    llvm = "define i32 @main() {\nentry:\n  ret i32 0\n}\n"
    calls = []

    def fake_compile(path, importer=None, **kwargs):
        calls.append((Path(path), kwargs))
        return llvm

    monkeypatch.setattr(cli, "compile_file", fake_compile)
    monkeypatch.setattr(cli, "run_llvm", lambda *a, **kw: FakeCompleted(3))

    assert cli.main(["build"]) == 0
    cache_path, _ = project.compile_cache_files(tmp_path, "demo")
    assert cache_path.is_file()
    assert "built" in capsys.readouterr().out
    assert len(calls) == 1

    assert cli.main(["build"]) == 0
    assert len(calls) == 1  # second build reused the cache

    assert cli.main(["run"]) == 3

    seen = []

    def fake_suite(targets, includes, cwd, inline, debug, flag_inf, test_filter=None):
        seen.append((targets, includes, test_filter))
        return 0

    monkeypatch.setattr(cli, "run_test_suite", fake_suite)
    assert cli.main(["test", "-k", "smoke"]) == 0
    assert seen[0][0] == [tmp_path / "tests"]
    assert seen[0][2] == "smoke"

    assert cli.main(["clean"]) == 0
    assert not cache_path.exists()
    assert "nothing to clean" not in capsys.readouterr().out


def test_cli_cache_commands(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv(project.CACHE_ENV_VAR, str(tmp_path / "modules"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NO_COLOR", "1")

    assert cli.main(["cache", "path"]) == 0
    assert capsys.readouterr().out.strip() == str(tmp_path / "modules")
    assert cli.main(["cache", "list"]) == 0
    assert capsys.readouterr().out.strip() == "(empty)"
    assert cli.main(["cache", "clear"]) == 0
    assert "nothing to clean" in capsys.readouterr().out


def test_cli_build_without_project_reports_once(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NO_COLOR", "1")
    assert cli.main(["build"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("Error:") == 1
    assert "no threadon.toml found" in captured.err


def test_normal_cli_uses_project_include_paths(monkeypatch, tmp_path):
    monkeypatch.setenv(project.CACHE_ENV_VAR, str(tmp_path / "modules"))
    app = project.init_project(tmp_path / "app", "app")
    util = project.init_project(tmp_path / "util", "util")
    write(util.root / "src" / "util.th", "def twice(x: Int32) -> Int32\n    return x * 2\n")
    write(
        app.root / "src" / "main.th",
        "from util import twice\n\ndef main() -> Int32\n    return twice(3)\n",
    )
    config, _ = project.add_dependency(app, "util", util.root)
    # Config discovery follows the source file, even from outside the project.
    monkeypatch.chdir(tmp_path)

    seen = []

    def fake_compile(path, importer=None, **kwargs):
        seen.append(list(importer.search_paths))
        return "ir"

    monkeypatch.setattr(cli, "compile_file", fake_compile)
    assert cli.main([str(app.main_path)]) == 0
    assert app.root / "src" in seen[0]
    assert util.root / "src" in seen[0]
    assert config.dependencies["util"] == "../util"


def test_cli_run_tests_uses_project_test_paths(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    project.init_project(tmp_path, "demo")
    seen = []

    def fake_suite(targets, includes, cwd, inline, debug, flag_inf, test_filter=None):
        seen.append(targets)
        return 0

    monkeypatch.setattr(cli, "run_test_suite", fake_suite)
    assert cli.main(["--run-tests"]) == 0
    assert seen[0] == [tmp_path / "tests"]
