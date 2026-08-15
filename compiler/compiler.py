import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

from .checker import CombinedChecker
from .importer import Importer
from .optimalise_ir import IROptimizer
from .to_high_ir import SSABuilder
from .to_llvm_ir import LLVMIRCompiler


def compile_source(source, importer=None, inline_threshold=0, debug_mode=False, flag_inf=False):
    """Compile a Threadon source string (plus its imports) to LLVM IR."""
    importer = importer or Importer()
    buf = io.StringIO()

    try:
        with redirect_stdout(buf):
            ast = importer.load_main(source)
            merged = ast + [
                node
                for mod in importer.modules()
                if mod.ast is not None
                for node in mod.ast
            ]
            CombinedChecker().run_all(merged)
            native_sigs = {}
            native_exports = []
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
            module = SSABuilder().build_from_ast(merged, native_sigs=native_sigs)
            IROptimizer(inline_threshold=inline_threshold, debug_mode=debug_mode).optimize(module)
    except BaseException as e:
        raise RuntimeError(f"compiler error:\n{buf.getvalue()}") from e

    warnings = buf.getvalue()
    if warnings:
        sys.stderr.write(warnings)

    return LLVMIRCompiler(debug_mode=debug_mode, flag_inf=flag_inf).compile(
        module, native_exports=native_exports
    )


def compile_file(path, importer=None, inline_threshold=0, debug_mode=False, flag_inf=False):
    """Compile a Threadon file (plus its imports) to LLVM IR."""
    path = Path(path)
    importer = importer or Importer()
    importer.add_search_path(path.parent)
    return compile_source(
        path.read_text(),
        importer=importer,
        inline_threshold=inline_threshold,
        debug_mode=debug_mode,
        flag_inf=flag_inf
    )
