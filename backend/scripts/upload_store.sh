#!/bin/sh
# Uploads the local point-in-time store to the API's Railway volume and swaps it in
# (S15.1), until ingestion runs on a schedule (S15.5). doc/hosting.md has the details.
#
# Needs the Railway CLI signed in as the owner, with an SSH key registered
# (`railway ssh keys add`), since volume transfers go over SSH, and this repository
# linked once, from its root:
#   railway link --project quant-time-machine --environment production --service api
# Then run it from anywhere:
#   backend/scripts/upload_store.sh
#
# DATA_DIR picks the store to upload (default backend/data), and API_URL the deployment
# to smoke-test afterward (default production).
set -eu

backend=$(cd "$(dirname "$0")/.." && pwd)
store=${DATA_DIR:-$backend/data}/store
url=${API_URL:-https://quant-time-machine-api.up.railway.app}
volume=api-data
cd "$backend/.."  # where the Railway link lives

version=$(ls "$store/_versions" 2>/dev/null | sed -n 's/\.json$//p' | sort | tail -n 1)
if [ -z "$version" ]; then
  echo "No data version in $store/_versions: ingest first." >&2
  exit 1
fi

files() { railway volume files --volume "$volume" "$@"; }
exists() { # exists NAME: whether /NAME is at the top of the volume
  files list / --json 2>/dev/null | python3 -c '
import json, sys
names = {f["path"] for f in json.load(sys.stdin)["files"]}
sys.exit(0 if "/" + sys.argv[1] in names else 1)' "$1"
}

# A clean copy, without the Finder's files. _versions/ comes along, so the API reports
# the same data version as this machine.
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
rsync -a --exclude .DS_Store --exclude '._*' "$store/" "$stage/store/"

echo "Uploading data version $version ($(du -sh "$stage/store" | cut -f1)) to /data/store.new"
files upload "$stage/store" /store.new --overwrite

# The swap. The old store becomes /store.previous; to roll back, swap the names back.
# Between the two renames, for a second or two, requests find no store.
if exists store.previous; then files delete /store.previous --yes; fi
if exists store; then files rename /store /store.previous; fi
files rename /store.new /store

echo "Checking $url"
uv run "$backend/scripts/smoke_test.py" "$url" --data-version "$version"
