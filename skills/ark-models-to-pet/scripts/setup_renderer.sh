#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 1 ]]; then
  echo "usage: setup_renderer.sh /absolute/runtime-dir" >&2
  exit 2
fi
runtime_dir="$1"
script_dir="$(cd "$(dirname "$0")" && pwd)"
pnpm_bin="${PNPM:-pnpm}"
node_bin="${NODE_BIN:-node}"
mkdir -p "$runtime_dir"
cp "$script_dir/renderer-package.json" "$runtime_dir/package.json"
"$pnpm_bin" --dir "$runtime_dir" install --ignore-scripts
cp "$script_dir/spine-browser.js" "$runtime_dir/spine-browser.js"
modules_dir="$($pnpm_bin --dir "$runtime_dir" root)"
if [[ ! -f "$modules_dir/esbuild/bin/esbuild" ]]; then
  modules_dir="$($pnpm_bin --dir "$runtime_dir" root -w)"
fi
"$node_bin" "$modules_dir/esbuild/bin/esbuild" "$runtime_dir/spine-browser.js" \
  --bundle --format=iife --platform=browser \
  --outfile="$runtime_dir/bundle.js"
echo "$runtime_dir/bundle.js"
