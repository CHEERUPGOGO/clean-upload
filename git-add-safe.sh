#!/bin/bash
# git-add-safe.sh: git add modified files, skipping files > SIZE_LIMIT (default 10MB)
# Usage: ./git-add-safe.sh [path...]  (default: modified/untracked files only)

SIZE_LIMIT_MB=${GIT_ADD_SIZE_LIMIT_MB:-10}
SIZE_LIMIT=$((SIZE_LIMIT_MB * 1024 * 1024))

if [ $# -eq 0 ]; then
    # Get only modified and untracked files (much faster than scanning everything)
    FILES=$(git ls-files -m -o --exclude-standard 2>/dev/null)
else
    FILES="$*"
fi

[ -z "$FILES" ] && echo "No files to add." && exit 0

# Find large files to skip (only among our candidate files)
LARGE_FILES=$(echo "$FILES" | tr '\n' '\0' | xargs -0 find 2>/dev/null | xargs -I{} stat -c'%s %n' {} 2>/dev/null | awk -v lim="$SIZE_LIMIT" '$1 > lim {print $2}')

# Build skip set
declare -A SKIP
for f in $LARGE_FILES; do
    SKIP["$f"]=1
done

added=0
skipped=0

while IFS= read -r f; do
    [ -z "$f" ] && continue
    [ -d "$f" ] && continue
    if [ -n "${SKIP[$f]}" ]; then
        size=$(stat -c%s "$f" 2>/dev/null || echo "?")
        mb=$((size / 1024 / 1024))
        echo "SKIP (${mb}MB > ${SIZE_LIMIT_MB}MB): $f"
        skipped=$((skipped + 1))
    else
        git add "$f" 2>/dev/null
        added=$((added + 1))
    fi
done <<< "$FILES"

echo ""
echo "Done: $added added, $skipped skipped (>${SIZE_LIMIT_MB}MB)"
