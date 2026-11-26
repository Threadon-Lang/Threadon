"""Tests for the central compiler diagnostic system."""
import io

import pytest

from compiler.threadon import __main__ as cli
from compiler.threadon.compiler import compile_source
from compiler.threadon.errors import (
    abort,
    capture_diagnostics,
    flush_diagnostics,
    format_diagnostic,
    report_warning,
    tool_error,
)
from compiler.threadon.importer import Importer


def test_format_diagnostic_is_plain_and_adds_line():
    text = format_diagnostic("error", "broken thing", line=7, color=False)
    assert text == "Error: broken thing at line 7"
    assert "\033[" not in text


def test_format_diagnostic_does_not_double_the_prefix():
    text = format_diagnostic("error", "Error: broken thing", color=False)
    assert text == "Error: broken thing"
    assert text.count("Error:") == 1


def test_format_diagnostic_includes_source_and_caret():
    text = format_diagnostic(
        "error", "bad name", line=2, col=3, source_line="  x = 1", color=False,
    )
    assert text == "Error: bad name at line 2\n    x = 1\n    ^"


def test_tool_error_uses_stderr_and_raises_diagnostic(monkeypatch, capsys):
    monkeypatch.setenv("NO_COLOR", "1")
    with pytest.raises(SystemExit) as excinfo:
        tool_error("bad tool")
    captured = capsys.readouterr()
    assert "Error: bad tool" in captured.err
    assert captured.out == ""
    assert excinfo.value.code == 1
    assert str(excinfo.value) == "Error: bad tool"


def test_capture_diagnostics_buffers_and_flushes(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    with capture_diagnostics() as sink:
        report_warning("careful")
        with pytest.raises(SystemExit):
            abort("broken")

    assert [record.diagnostic.severity for record in sink.records] == ["warning", "error"]
    err = io.StringIO()
    flush_diagnostics(sink, file=err)
    text = err.getvalue()
    assert "Warning: careful" in text
    assert "Error: broken" in text
    assert text.count("Error:") == 1


BAD_SOURCE = """\
def collect() -> NoneType:
    print("not allowed")
    return None

def main() -> Int32
    collect()
    return 0
"""


def test_compile_source_reports_error_once(monkeypatch, capsys):
    monkeypatch.setenv("NO_COLOR", "1")
    with pytest.raises(RuntimeError) as excinfo:
        compile_source(BAD_SOURCE, importer=Importer())

    captured = capsys.readouterr()
    message = "Cannot redefine builtin/standard library function 'collect'"
    assert captured.err.count("Error:") == 1
    assert message in captured.err
    assert "AST Error" not in captured.err
    assert str(excinfo.value).count("Error:") == 1
    assert message in str(excinfo.value)


def test_cli_prints_compile_error_once(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("NO_COLOR", "1")
    source = tmp_path / "main.th"
    source.write_text(BAD_SOURCE)

    assert cli.main([str(source)]) == 1
    captured = capsys.readouterr()
    message = "Cannot redefine builtin/standard library function 'collect'"
    assert captured.err.count("Error:") == 1
    assert message in captured.err
    assert captured.out == ""
