#!/usr/bin/env bash
#
# get-apks.sh — put the two original 3.4.2 APKs into original/
#
#   ./get-apks.sh
#
# Tries, in order:
#   1. files already in original/
#   2. the git tag "apk-parts"  (git fetch + git archive)
#   3. the same tag as a tarball from codeload.github.com (no git needed)
# and, whichever route won, reassembles them:
#
#   part-00 + part-01 -> set.tar -> base.apk + split_0.apk
#
# (GitHub refuses single files over 100 MB, so the APKs are stored as two parts
#  that must be concatenated before the tar can be opened.)

set -euo pipefail
cd "$(dirname "$0")"

EXPECT_BASE="94a9beca7ae0025062bb1f5ed76541e8a7d1df41054cc491b1b9f5325d67643b"
EXPECT_SPLIT="e47f734399c489d92b65270a141603e80eb956fac1a086d6ec1efb2ee4b29370"
TAG=apk-parts
TMP=".apk-parts"

sha_of() { sha256sum "$1" 2>/dev/null | cut -d' ' -f1 || shasum -a 256 "$1" | cut -d' ' -f1; }

echo "== 1/4 looking for existing files in original/ =="
mkdir -p original
if [[ -f original/base.apk && -f original/split_0.apk ]]; then
  echo "   found:"; ls -l original/base.apk original/split_0.apk | sed 's/^/   /'
  echo "== 4/4 verifying hashes =="
  HB=$(sha_of original/base.apk); HS=$(sha_of original/split_0.apk)
  if [[ "$HB" == "$EXPECT_BASE" && "$HS" == "$EXPECT_SPLIT" ]]; then
    echo "   OK — both files match 3.4.2"; exit 0
  fi
  echo "   !! hash mismatch (not 3.4.2?) — delete original/*.apk and re-run"; exit 1
fi

echo "== 2/4 fetching tag '$TAG' =="
rm -rf "$TMP"; mkdir -p "$TMP"
if [[ -d .git ]] && git fetch origin "refs/tags/$TAG:refs/tags/$TAG" --force 2>/dev/null; then
  echo "   route: git fetch + git archive"
  git archive --format=tar "refs/tags/$TAG" | tar -x -C "$TMP"
else
  echo "   route: tarball from codeload.github.com (no git needed)"
  curl -L --fail --progress-bar \
    -o "$TMP/parts.tgz" \
    "https://codeload.github.com/Abolfazlerahmati/mafiaso-offline/tar.gz/refs/tags/$TAG"
  tar -xzf "$TMP/parts.tgz" -C "$TMP" --strip-components=1
fi

echo "== 3/4 reassembling =="
if [[ -f "$TMP/base.apk" ]]; then
  echo "   the tag already contains base.apk / split_0.apk"
  cp "$TMP/base.apk" "$TMP/split_0.apk" original/
elif [[ -f "$TMP/set.tar" ]]; then
  echo "   extracting set.tar"
  tar -xf "$TMP/set.tar" -C "$TMP"
  cp "$TMP/base.apk" "$TMP/split_0.apk" original/
elif [[ -f "$TMP/part-00" && -f "$TMP/part-01" ]]; then
  echo "   concatenating part-00 + part-01 -> set.tar"
  cat "$TMP/part-00" "$TMP/part-01" > "$TMP/set.tar"
  tar -xf "$TMP/set.tar" -C "$TMP"
  cp "$TMP/base.apk" "$TMP/split_0.apk" original/
else
  echo "   !! no base.apk / set.tar / part-00 in $TMP"; ls -l "$TMP"; exit 1
fi
rm -rf "$TMP"

echo "== 4/4 verifying hashes =="
HB=$(sha_of original/base.apk); HS=$(sha_of original/split_0.apk)
ls -l original/base.apk original/split_0.apk | sed 's/^/   /'
if [[ "$HB" == "$EXPECT_BASE" && "$HS" == "$EXPECT_SPLIT" ]]; then
  echo "   OK — both files match 3.4.2"
else
  echo "   !! unexpected hashes:"; echo "   base : $HB"; echo "   split: $HS"; exit 1
fi
echo
echo "Next: ./build-all.sh"
