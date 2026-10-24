#!/usr/bin/env bash
# Sync data/cache/*.csv with the `data` branch (used by the refresh-data workflow).
#   restore  copy the published CSVs into data/cache/ so history keeps growing
#   publish  write data/cache/*.csv plus manifest.json to the data branch and push
set -euo pipefail

BRANCH=data
CACHE=data/cache
WT=.publish

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

checkout_branch() {
  rm -rf "$WT"
  if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null; then
    git fetch --depth=1 origin "$BRANCH"
    git worktree add -B "$BRANCH" "$WT" "origin/$BRANCH"
  else
    git worktree add --detach "$WT"
    git -C "$WT" checkout --orphan "$BRANCH"
    git -C "$WT" rm -rfq . || true
  fi
}

case "${1:-}" in
  restore)
    checkout_branch
    mkdir -p "$CACHE"
    cp "$WT"/*.csv "$CACHE"/ 2>/dev/null || echo "No published data yet"
    ;;
  publish)
    [ -d "$WT" ] || checkout_branch
    rm -f "$WT"/*.csv
    cp "$CACHE"/*.csv "$WT"/
    (cd "$WT" && ls *.csv | python3 -c 'import json,sys,datetime; print(json.dumps({"updated": datetime.datetime.utcnow().isoformat(timespec="seconds")+"Z", "files": sorted(l.strip() for l in sys.stdin)}, indent=2))' > manifest.json)
    git -C "$WT" add -A
    if git -C "$WT" diff --cached --quiet; then
      echo "No data changes"
    else
      git -C "$WT" commit -qm "Data refresh $(date -u +%Y-%m-%d)"
      git -C "$WT" push origin "HEAD:$BRANCH"
    fi
    ;;
  *)
    echo "usage: $0 restore|publish" >&2
    exit 2
    ;;
esac
