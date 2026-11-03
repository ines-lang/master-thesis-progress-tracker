#!/bin/bash
# Build the GitHub version of the repo on branch github-full, without checking it out:
# the files of local master (LaTeX, as on ShareLaTeX) plus code/, minus the files in code/.github_exclude.
# master never contains code/, so ShareLaTeX never receives it.
#
# Usage (from anywhere):
#   bash code/sync_github.sh "<one-line message explaining the changes>"
#   git push github github-full:master
set -e
MSG="$1"
[ -n "$MSG" ] || { echo 'usage: bash code/sync_github.sh "<one-line message>"'; exit 1; }
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
BRANCH=github-full

# temporary index = master's tree + every non-excluded file under code/
export GIT_INDEX_FILE="$(git rev-parse --git-dir)/index-github"
rm -f "$GIT_INDEX_FILE"
git read-tree master
git ls-files --others -z --exclude-from=code/.github_exclude -- code | xargs -0 -r git update-index --add --
TREE=$(git write-tree)
rm -f "$GIT_INDEX_FILE"
unset GIT_INDEX_FILE

PARENT=$(git rev-parse --verify -q "$BRANCH") || { echo "branch $BRANCH missing"; exit 1; }
if [ "$(git rev-parse "$BRANCH^{tree}")" = "$TREE" ]; then
    echo "nothing changed since $BRANCH"; exit 0
fi
COMMIT=$(git commit-tree "$TREE" -p "$PARENT" -m "$MSG")
git update-ref "refs/heads/$BRANCH" "$COMMIT" "$PARENT"
git diff --stat "$PARENT" "$COMMIT" | tail -1
echo "$BRANCH -> $(git log -1 --format='%h %s' "$COMMIT")"
