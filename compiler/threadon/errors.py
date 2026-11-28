"""Central diagnostic system for the Threadon compiler.

Every user-facing compiler diagnostic is rendered, emitted, and raised through
this module.  Runtime errors produced by generated programs are different: they
are emitted by LLVM code and intentionally keep their own message strings.

The two exception types serve different layers:

* :class:`ThreadonDiagnostic` is for parser/checker/IR-builder failures.  It
  derives from ``SystemExit`` because that is what those layers historically
  raised, while still carrying a useful message and exit code.
* :class:`ThreadonError` is for compile pipeline failures.  It derives from
  ``RuntimeError`` so existing API users see a normal exception.
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterable, Optional, TextIO


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"", "0", "false", "no", "off"}


def use_color(color: Optional[bool] = None) -> bool:
    """Return whether diagnostics should use ANSI colors.

    Colors are enabled for interactive terminals only; ``FORCE_COLOR=1`` can
    turn them on in pipes and ``NO_COLOR=1`` turns them off everywhere.
    """
    if color is not None:
        return color
    if _env_flag("NO_COLOR", False):
        return False
    if _env_flag("FORCE_COLOR", False):
        return True
    return sys.stderr.isatty()


RED = "\033[91m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
RESET = "\033[0m"

_SEVERITY_LABELS = {
    "error": "Error",
    "warning": "Warning",
    "note": "Note",
}


class ThreadonDiagnostic(SystemExit):
    """A diagnostic already printed to the console.

    Inheriting from ``SystemExit`` keeps compatibility with parser/checker unit
    tests, but unlike a bare ``SystemExit`` it carries a useful message and an
    exit code of 1.  The code is an ``int``, so Python does not print the
    message a second time when the process exits.
    """

    def __init__(self, message: str, severity: str = "error", code: int = 1):
        super().__init__(code)
        self.message = message
        self.severity = severity
        self.code = code

    def __str__(self) -> str:
        return self.message


class ThreadonError(RuntimeError):
    """A compile-time exception with a consistently formatted message.

    ``printed`` records whether the diagnostic text was already emitted.  The
    CLI uses it to avoid printing the same error twice.
    """

    def __init__(self, message: str, line: Optional[int] = None, printed: bool = False):
        super().__init__(message)
        self.message = message
        self.line = line
        self.printed = printed


@dataclass(frozen=True)
class Diagnostic:
    severity: str
    message: str
    line: Optional[int] = None
    col: Optional[int] = None
    source_line: Optional[str] = None

    @property
    def label(self) -> str:
        return _SEVERITY_LABELS.get(self.severity, self.severity.capitalize())

    def _clean_message(self) -> str:
        message = self.message
        prefix = self.label + ":"
        if message.startswith(prefix):
            return message[len(prefix):].lstrip()
        return message

    def plain(self) -> str:
        text = f"{self.label}: {self._clean_message()}"
        if self.line is not None:
            text += f" at line {self.line}"
        return text

    def render(self, color: Optional[bool] = None) -> str:
        label = self.label
        if use_color(color):
            paint = RED if self.severity == "error" else YELLOW
            head = f"{paint}{BOLD}{label}:{RESET}"
        else:
            head = f"{label}:"

        text = f"{head} {self._clean_message()}"
        if self.line is not None:
            text += f" at line {self.line}"

        lines = [text]
        if self.source_line is not None:
            lines.append(f"  {self.source_line}")
            if self.col is not None:
                caret_pos = max(0, self.col - 1)
            else:
                caret_pos = len(self.source_line) - len(self.source_line.lstrip(" "))
            lines.append("  " + " " * caret_pos + "^")
        return "\n".join(lines)


@dataclass(frozen=True)
class DiagnosticRecord:
    diagnostic: Diagnostic
    rendered: str


@dataclass
class DiagnosticSink:
    """Temporary collector used by the compile pipeline."""

    records: list[DiagnosticRecord] = field(default_factory=list)

    def texts(self, severities: Optional[Iterable[str]] = None) -> list[str]:
        wanted = set(severities) if severities is not None else None
        return [
            record.rendered for record in self.records
            if wanted is None or record.diagnostic.severity in wanted
        ]


_active_sink: Optional[DiagnosticSink] = None


@contextmanager
def capture_diagnostics():
    """Collect diagnostics instead of printing them inside this block.

    The compiler uses this to keep warnings and errors separate from LLVM IR
    written to stdout.  Direct parser/checker calls still print normally.
    """
    global _active_sink
    previous = _active_sink
    sink = DiagnosticSink()
    _active_sink = sink
    try:
        yield sink
    finally:
        _active_sink = previous


def format_diagnostic(
    severity: str,
    message: str,
    line: Optional[int] = None,
    col: Optional[int] = None,
    source_line: Optional[str] = None,
    *,
    color: Optional[bool] = None,
) -> str:
    """Render a diagnostic without emitting it."""
    return Diagnostic(severity, message, line, col, source_line).render(color)


def error_text(message: str, line: Optional[int] = None) -> str:
    """Plain-text version of an error, suitable for exception messages."""
    return Diagnostic("error", message, line).plain()


def warning_text(message: str, line: Optional[int] = None) -> str:
    """Plain-text version of a warning."""
    return Diagnostic("warning", message, line).plain()


def emit_diagnostic(
    severity: str,
    message: str,
    line: Optional[int] = None,
    col: Optional[int] = None,
    source_line: Optional[str] = None,
    *,
    file: Optional[TextIO] = None,
    color: Optional[bool] = None,
) -> None:
    """Print one diagnostic. The compile pipeline flushes to stderr; direct
    parser/checker calls keep the historical stdout default for compatibility.
    """
    diagnostic = Diagnostic(severity, message, line, col, source_line)
    rendered = diagnostic.render(color)
    if _active_sink is not None:
        _active_sink.records.append(DiagnosticRecord(diagnostic, rendered))
        return
    print(rendered, file=file or sys.stdout)


def report_error(
    message: str,
    line: Optional[int] = None,
    col: Optional[int] = None,
    source_line: Optional[str] = None,
    *,
    file: Optional[TextIO] = None,
    color: Optional[bool] = None,
) -> None:
    emit_diagnostic(
        "error", message, line=line, col=col, source_line=source_line,
        file=file, color=color,
    )


def report_warning(
    message: str,
    line: Optional[int] = None,
    col: Optional[int] = None,
    source_line: Optional[str] = None,
    *,
    file: Optional[TextIO] = None,
    color: Optional[bool] = None,
) -> None:
    emit_diagnostic(
        "warning", message, line=line, col=col, source_line=source_line,
        file=file, color=color,
    )


def flush_diagnostics(
    sink: DiagnosticSink,
    *,
    severities: Optional[Iterable[str]] = None,
    file: Optional[TextIO] = None,
) -> None:
    """Emit collected diagnostics, optionally only selected severities."""
    global _active_sink
    wanted = set(severities) if severities is not None else None
    selected = [
        record for record in sink.records
        if wanted is None or record.diagnostic.severity in wanted
    ]
    if not selected:
        return

    selected_ids = {id(record) for record in selected}
    sink.records = [r for r in sink.records if id(r) not in selected_ids]

    previous = _active_sink
    _active_sink = None
    try:
        out = file or sys.stderr
        for record in selected:
            print(record.rendered, file=out)
    finally:
        _active_sink = previous


def abort(
    message: str,
    line: Optional[int] = None,
    col: Optional[int] = None,
    source_line: Optional[str] = None,
    *,
    file: Optional[TextIO] = None,
    color: Optional[bool] = None,
) -> None:
    """Print an error and raise a diagnostic exception."""
    report_error(
        message, line=line, col=col, source_line=source_line,
        file=file, color=color,
    )
    raise ThreadonDiagnostic(Diagnostic("error", message, line).plain())


def fail(*args, **kwargs) -> None:
    """Alias for :func:`abort`."""
    abort(*args, **kwargs)


def compile_error(
    message: str,
    line: Optional[int] = None,
    *,
    printed: bool = False,
) -> ThreadonError:
    """Build a compile-time exception with a consistent ``Error:`` prefix."""
    return ThreadonError(error_text(message, line), line=line, printed=printed)


def tool_error(message: str) -> None:
    """Print a toolchain/CLI error to stderr and abort."""
    abort(message, file=sys.stderr)
