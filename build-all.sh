#!/usr/bin/env bash
#
# build-all.sh — build every variant of the offline APK in one go.
#
#   ./build-all.sh                       # uses original/*.apk
#   ./build-all.sh BASE.apk SPLIT.apk    # explicit inputs
#
# Produces five APKs that install over each other (same package, same key):
#
#   out/          A  literal redirect ConnectionScreen -> MainMenu        (menu only)
#   out-native/   B  native branch SetupFlow -> LoadMainMenu              (menu only)
#   out-battle/   C  A + StartBattle -> LoadBattle(0, null)               (arena entry)
#   out-debug/    D  C + Constants.isInDevelopment = true                 (debug GUI)
#   out-bot/      E  C + PrepareAndWaitForStart* -> InitTestMode          (bot battle)
#
# Test them in that order and keep the one that works. See docs/04-install-guide.md.

set -euo pipefail
cd "$(dirname "$0")"

CAVE="0x14c00ac=01008052e2031faa87180014"   # mov w1,#0 ; mov x2,xzr ; b LoadBattle
INIT="0x149f16c"                             # LevelController.InitTestMode

echo
echo "=== [1/5] A — literal redirect (menu only) ==="
./build.sh "$@"

echo
echo "=== [2/5] B — native branch (menu only) ==="
BRANCH="0x14c00a8=0x14c6498" NO_RENAME=1 OUT=out-native ./build.sh "$@"

echo
echo "=== [3/5] C — arena entry ==="
BRANCH="0x15a1868=0x14c00ac" WRITE="$CAVE" OUT=out-battle ./build.sh "$@"

echo
echo "=== [4/5] D — debug GUI ==="
BRANCH="0x15a1868=0x14c00ac" WRITE="$CAVE 0x170dff4=20008052" OUT=out-debug ./build.sh "$@"

echo
echo "=== [5/5] E — bot battle ==="
BRANCH="0x15a1868=0x14c00ac 0x14986f0=$INIT 0x1498744=$INIT 0x1498850=$INIT" \
WRITE="$CAVE" OUT=out-bot ./build.sh "$@"

echo
echo "All five variants built:"
for d in out out-native out-battle out-debug out-bot; do
  printf '  %-14s %s\n' "$d" "$(ls -1 "$d"/*.apk 2>/dev/null | head -n1 || echo missing)"
done
echo
echo "Next: install them one at a time and note what happens (docs/04-install-guide.md)."
