#!/usr/bin/env bash
# Round 22: package the run directories that release_manifest_v2.json registers into ONE archive, so the content behind the manifest's
# hashes can travel with it. The manifest binds each run by repository-relative path + a file-by-file digest; the run directories live in
# outputs/runs/ (~190 MB together), which is why they are not copied into docs/.
#   usage: bash package_runs.sh <output.tar.gz>        (read-only on outputs/)
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "$REPO_ROOT"
OUT="${1:?usage: package_runs.sh <output.tar.gz>}"
MANIFEST="docs/audit_artifacts/round_source_linking_t0_t2/round22_t1_closeout_20261007/release_manifest_v2.json"
RUNS=$(python3 -c "import json; print(' '.join('outputs/runs/' + r for r in json.load(open('$MANIFEST'))['runs']))")
# shellcheck disable=SC2086
tar -czf "$OUT" $RUNS "$MANIFEST"
echo "wrote $OUT ($(du -h "$OUT" | cut -f1)); verify after unpacking with: python docs/audit_artifacts/round_source_linking_t0_t2/round22_t1_closeout_20261007/verify_release_manifest_v2.py"
