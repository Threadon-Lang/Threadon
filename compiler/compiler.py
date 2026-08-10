import io
from contextlib import redirect_stdout
from pathlib import Path

from .checker import CombinedChecker
from .importer import Importer
from .optimalise_ir import IROptimizer
from .to_high_ir import SSABuilder
from .to_llvm_ir import LLVMIRCompiler


def compile_source(source, importer=None, inline_threshold=0,debug_mode=False):
    """Compile a Threadon source string (plus its imports) to LLVM IR."""
    importer = importer or Importer()
    buf = io.StringIO()

    try:
        with redirect_stdout(buf):
            ast = importer.load_main(source)
            merged = ast + [node for mod in importer.modules() for node in mod.ast]
            CombinedChecker().run_all(merged)
            module = SSABuilder().build_from_ast(merged)
            IROptimizer(inline_threshold=inline_threshold).optimize(module)
    except BaseException as e:
        raise RuntimeError(f"compiler error:\n{buf.getvalue()}") from e

    return LLVMIRCompiler(debug_mode=debug_mode).compile(module)


def compile_file(path, importer=None, inline_threshold=0,debug_mode=False):
    """Compile a Threadon file (plus its imports) to LLVM IR."""
    path = Path(path)
    importer = importer or Importer()
    importer.add_search_path(path.parent)
    return compile_source(
        path.read_text(),
        importer=importer,
        inline_threshold=inline_threshold,
        debug_mode=debug_mode
    )
