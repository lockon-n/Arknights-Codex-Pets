#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: new_pet.sh <lowercase-pet-id>" >&2
  exit 2
fi

pet_id="$1"
if [[ ! "$pet_id" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
  echo "pet id must use lowercase letters, digits, and single hyphens" >&2
  exit 2
fi

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
pet_dir="$repo_dir/pets/$pet_id"
if [[ -e "$pet_dir" ]]; then
  echo "refusing to overwrite existing path: $pet_dir" >&2
  exit 1
fi

mkdir -p "$pet_dir/qa"
printf '{\n  "id": "%s",\n  "displayName": "",\n  "description": "",\n  "spriteVersionNumber": 2,\n  "spritesheetPath": "spritesheet.webp"\n}\n' "$pet_id" > "$pet_dir/pet.json"
printf '# Source and rights\n\n- Ark-Models source: \n- Model key: \n- Outfit category: \n- Upstream commit: \n\nArknights artwork and game content belong to their respective rights holders, including Hypergryph. This package does not grant redistribution or commercial-use rights.\n' > "$pet_dir/SOURCE.md"
printf 'created %s\n' "$pet_dir"
