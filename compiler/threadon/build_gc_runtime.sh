#!/bin/sh
# Rebuild the precompiled collector IR appended to generated modules.
#
# The private string constants emitted by clang use names like @.str.1, which
# can collide with string constants in generated Threadon modules. Rename them
# with a gc-specific prefix before the IR is concatenated.
set -eu

cd "$(dirname "$0")"

clang -O2 -fno-builtin-malloc -fno-builtin-free \
  -S -emit-llvm -o gc_runtime.ll gc_runtime.c

sed -i '/^; ModuleID/d; /^source_filename/d; /^target datalayout/d; /^target triple/d' gc_runtime.ll
sed -i 's/@\.str\./@__gc_str_/g; s/@\.str\([^A-Za-z0-9_]\)/@__gc_str\1/g' gc_runtime.ll
