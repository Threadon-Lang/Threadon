import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

from .checker import CombinedChecker
from .errors import (
    ThreadonDiagnostic,
    ThreadonError,
    capture_diagnostics,
    error_text,
    flush_diagnostics,
)
from .importer import Importer
from .optimalise_ir import IROptimizer
from .test_harness import generate_test_harness
from .to_high_ir import SSABuilder
from .to_llvm_ir import LLVMIRCompiler


def _flush_stray_output(buf):
    """Forward any legacy raw prints to stderr instead of stdout."""
    text = buf.getvalue().rstrip()
    if text:
        sys.stderr.write(text + "\n")


def compile_source(source, importer=None, inline_threshold=0, debug_mode=False, flag_inf=False):
    """Compile a Threadon source string (plus its imports) to LLVM IR."""
    importer = importer or Importer()
    stray = io.StringIO()

    try:
        with capture_diagnostics() as diagnostics, redirect_stdout(stray):
            ast = importer.load_main(source)
            merged = ast + [
                node
                for mod in importer.modules()
                if mod.ast is not None
                for node in mod.ast
            ]
            native_functions = set()
            global_vars = set()
            for mod in importer.modules():
                if mod.is_native:
                    native_functions.update(mod.func_sigs)
                global_vars.update(
                    f"{mod.name}.{name}" for name in mod.var_exports
                )
            CombinedChecker().run_all(
                merged,
                native_functions=native_functions,
                global_vars=global_vars,
            )
            native_sigs = {}
            native_exports = []
            native_types = []
            for mod in importer.modules():
                if not mod.is_native:
                    continue
                for export_name, ret, args in mod.exports:
                    qname = f"{mod.name}.{export_name}"
                    params = [(f"a{i}", t, None) for i, t in enumerate(args)]
                    native_sigs[qname] = (params, ret)
                    native_exports.append(
                        {"module": mod.name, "name": export_name, "ret": ret, "args": args}
                    )
                for type_name, fields in mod.class_defs.items():
                    native_types.append(
                        (type_name, [(f.name, f.var_type) for f in fields])
                    )
            module = SSABuilder().build_from_ast(
                merged, native_sigs=native_sigs, native_types=native_types
            )
            IROptimizer(inline_threshold=inline_threshold, debug_mode=debug_mode).optimize(module)
    except ThreadonDiagnostic as e:
        # abort() already rendered this through the central diagnostics.
        flush_diagnostics(diagnostics)
        _flush_stray_output(stray)
        raise ThreadonError(error_text(str(e)), printed=True) from e
    except Exception as e:
        flush_diagnostics(diagnostics, severities=("warning", "note"))
        _flush_stray_output(stray)
        msg = str(e)
        if not msg.strip():
            msg = str(e.__cause__ or e)
        raise ThreadonError(error_text(msg)) from e

    flush_diagnostics(diagnostics)
    _flush_stray_output(stray)

    try:
        return LLVMIRCompiler(debug_mode=debug_mode, flag_inf=flag_inf).compile(
            module, native_exports=native_exports
        )
    except ThreadonDiagnostic:
        # _error() rendered this already through the central diagnostics.
        raise
    except Exception as e:
        msg = str(e)
        if not msg.strip():
            msg = str(e.__cause__ or e)
        raise ThreadonError(error_text(msg)) from e


def compile_file(path, importer=None, inline_threshold=0, debug_mode=False, flag_inf=False, test_filter=None):
    """Compile a Threadon file (plus its imports) to LLVM IR."""
    path = Path(path)
    importer = importer or Importer()
    importer.add_search_path(path.parent)
    source = path.read_text()
    if path.name == "test.th":
        source = generate_test_harness(source, test_filter=test_filter)
    return compile_source(
        source,
        importer=importer,
        inline_threshold=inline_threshold,
        debug_mode=debug_mode,
        flag_inf=flag_inf
    )
