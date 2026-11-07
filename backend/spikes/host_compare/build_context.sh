#!/bin/sh
# Assembles the benchmark image's build context from backend/ into DIR (a new temporary
# directory if none is given) and prints its path. Then, from DIR:
#   Railway:   railway up --ci
#   Cloud Run: gcloud run deploy SERVICE --source .
# Run it from anywhere; it reads the store from $DATA_DIR/store (default backend/data).
set -eu
backend=$(cd "$(dirname "$0")/../.." && pwd)
out=${1:-$(mktemp -d)}
data=${DATA_DIR:-$backend/data}

mkdir -p "$out/spikes"
cp "$backend/pyproject.toml" "$backend/uv.lock" "$backend/.python-version" "$out/"
rsync -a --delete --exclude __pycache__ --exclude .DS_Store "$backend/app" "$out/"
cp "$backend/spikes/hosting.py" "$out/spikes/"
cp "$backend/spikes/host_compare/bench_app.py" "$backend/spikes/host_compare/Dockerfile" "$out/"
rsync -a --delete --exclude .DS_Store "$data/store/" "$out/store/"
echo "$out"
