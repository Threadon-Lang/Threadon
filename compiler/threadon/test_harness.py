"""Pytest-style runner generation for ``test.th`` modules.

A file named ``test.th`` is the unittest suite of a Threadon module. It must
not define ``main``: the compiler appends a synthetic ``main`` that runs every
module-level ``def test_*()`` function, prints a ``[PASS]`` / ``[FAIL]`` line
per test and a summary, then returns the number of failed tests as the process
exit code.

If the suite defines module-level ``setup()`` / ``teardown()`` functions they
are called once before the first / after the last test; a failing ``setup()``
aborts the suite, a failing ``teardown()`` counts as one failed test.

The synthetic ``main`` is plain Threadon source glued onto the end of the
user's ``test.th`` before parsing, so no extra compiler support is needed.
"""

import re

_TEST_FUNC_RE = re.compile(r"^def\s+(test_[A-Za-z0-9_]+)\s*\(")
_HAS_MAIN_RE = re.compile(r"^def\s+main\s*\(", re.MULTILINE)


def find_test_functions(source):
    """Return the module-level ``def test_*`` function names, in source order."""
    names = []
    for line in source.splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = _TEST_FUNC_RE.match(line)
        if m:
            names.append(m.group(1))
    return names


def _has_function(source, name):
    return re.search(rf"^def\s+{re.escape(name)}\s*\(", source, re.MULTILINE) is not None


def generate_test_harness(source, test_filter=None):
    """Append a synthetic ``main`` that runs matching test functions.

    Returns the original source unchanged if the file already defines
    ``main``. Otherwise appends a generated ``main`` that calls each
    ``test_*`` function (only those containing ``test_filter`` when given) in
    order, reports [PASS]/[FAIL], prints a pytest-style summary and returns
    the failure count as the exit code.
    """
    if _HAS_MAIN_RE.search(source):
        return source

    names = find_test_functions(source)
    if test_filter:
        names = [n for n in names if test_filter in n]

    has_setup = _has_function(source, "setup")
    has_teardown = _has_function(source, "teardown")

    lines = ["def main() -> Int32"]
    lines.append(f"    __t_total: Int32 = {len(names)}")
    lines.append("    __t_failed: Int32 = 0")
    if has_setup:
        lines += [
            "    __t_ok: Bool = setup()",
            "    if not __t_ok:",
            '        print("[FAIL] setup")',
            '        print("--------------")',
            "        print(__t_total, \"tests\", __t_total, \"failed\")",
            "        return __t_total",
        ]

    declared = has_setup
    for name in names:
        if declared:
            lines.append(f"    __t_ok = {name}()")
        else:
            lines.append(f"    __t_ok: Bool = {name}()")
            declared = True
        lines += [
            "    if __t_ok:",
            f'        print("[PASS]", "{name}")',
            "    else:",
            "        __t_failed = __t_failed + 1",
            f'        print("[FAIL]", "{name}")',
        ]

    if has_teardown:
        lines += [
            "    __t_ok = teardown()",
            "    if not __t_ok:",
            "        __t_failed = __t_failed + 1",
            '        print("[FAIL] teardown")',
        ]

    lines.append('    print("--------------")')
    lines.append("    print(__t_total, \"tests\", __t_failed, \"failed\")")
    if not names and not has_setup:
        lines.append('    print("(no test functions found)")')
    lines.append("    return __t_failed")
    lines.append("")
    return source + "\n" + "\n".join(lines)