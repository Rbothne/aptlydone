#!/usr/bin/env bash
# Generated data lives on the "data" branch as a single commit that every run replaces, so the repository
# does not grow with each update.
#
#   data-branch.sh load   put the branch's files into data/ and site/data/   (exit 3: the branch does not exist yet)
#   data-branch.sh save   replace the branch with the current files; on the 1st of a month also keep a dated copy
#
# DATA_REMOTE names the remote to use (default: origin).
set -euo pipefail
remote="${DATA_REMOTE:-origin}"

case "${1:-}" in
  load)
    mkdir -p data site/data
    if ! git fetch -q --depth=1 "$remote" data 2>/dev/null; then
      echo "no data branch yet"
      exit 3
    fi
    git show FETCH_HEAD:buildings.json > data/buildings.json
    if git cat-file -e FETCH_HEAD:state.json 2>/dev/null; then
      git show FETCH_HEAD:state.json > data/state.json
    fi
    if git cat-file -e FETCH_HEAD:site-data 2>/dev/null; then
      git archive FETCH_HEAD site-data | tar -x --strip-components=1 -C site/data
    fi
    ;;

  save)
    out="$(mktemp -d)"
    mkdir -p "$out/site-data"
    cp data/buildings.json "$out/"
    if [ -f data/state.json ]; then cp data/state.json "$out/"; fi
    if ls site/data/*.json >/dev/null 2>&1; then cp site/data/*.json "$out/site-data/"; fi

    # Build the commit with plumbing commands and a throwaway index, so the checked-out files are left alone.
    export GIT_INDEX_FILE="$out.index"
    git --work-tree="$out" add -A -f .
    tree="$(git write-tree)"
    unset GIT_INDEX_FILE
    commit="$(GIT_AUTHOR_NAME='github-actions[bot]' GIT_COMMITTER_NAME='github-actions[bot]' \
              GIT_AUTHOR_EMAIL='41898282+github-actions[bot]@users.noreply.github.com' \
              GIT_COMMITTER_EMAIL='41898282+github-actions[bot]@users.noreply.github.com' \
              git commit-tree "$tree" -m "Buildings, price history and page data, $(date -u +%Y-%m-%dT%H:%MZ)")"
    git push -q --force "$remote" "$commit:refs/heads/data"
    if [ "$(date -u +%d)" = "01" ]; then
      git push -q --force "$remote" "$commit:refs/heads/data-$(date -u +%Y-%m)"
    fi
    rm -rf "$out" "$out.index"
    echo "saved data branch at $commit"
    ;;

  *)
    echo "usage: data-branch.sh load|save" >&2
    exit 2
    ;;
esac
