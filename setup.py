#!/usr/bin/env python3
"""setuptools shim for the Threadon compiler.

The plain pip/PEP 517 wheel build is fully described by pyproject.toml.  This
file adds one thing on top: a ``build_py`` step that runs the standard-library
self-tests (``threadon --run-tests``) whenever the package is built from the
source tree, so ``pip install .`` validates the bundled test suites too.

Skip it, if ever needed, with ``THREADON_SKIP_INSTALL_TESTS=1``.
"""

import os
import subprocess
import sys
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py

_SKIP = os.environ.get("THREADON_SKIP_INSTALL_TESTS", "").strip().lower() in {
    "1", "true", "yes", "on",
}

INSTALL_TESTS = [
    "compiler/stdlib/std/test.th",
    "compiler/stdlib/unittest/test.th",
]


class build_py(_build_py):
    def run(self):
        super().run()
        if _SKIP:
            return
        root = Path(__file__).resolve().parent
        missing = [p for p in INSTALL_TESTS if not (root / p).is_file()]
        if missing:
            self.warn(f"self-tests not found, skipping: {missing}")
            return

        import shutil

        if shutil.which("lli") is None:
            self.warn("lli not found; skipping stdlib self-tests")
            return

        tests = [str(root / p) for p in INSTALL_TESTS]
        env = os.environ.copy()
        compile_dir = str(root / "compiler")
        prev = env.get("PYTHONPATH")
        env["PYTHONPATH"] = compile_dir + (os.pathsep + prev if prev else "")
        self.announce("running stdlib self-tests ...", level=2)
        result = subprocess.run(
            [sys.executable, "-m", "threadon", "--run-tests", *tests],
            env=env,
            cwd=str(root),
        )
        if result.returncode != 0:
            raise RuntimeError(
                "stdlib self-tests failed; use THREADON_SKIP_INSTALL_TESTS=1 "
                "to install anyway"
            )


setup(cmdclass={"build_py": build_py})