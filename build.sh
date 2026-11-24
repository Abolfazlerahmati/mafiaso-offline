#!/usr/bin/env bash
#
# build.sh — one-command build of the offline APK (Linux / macOS / WSL / Git Bash).
# Windows users can double-click build.cmd instead.
#
#   ./build.sh                       # uses original/*.apk, output in out/
#   ./build.sh BASE.apk SPLIT.apk    # explicit inputs
#   ./build.sh --pair                # emit base+split instead of a single APK
#   BRANCH="0x14c00a8=0x14c6498" NO_RENAME=1 OUT=out-native ./build.sh
#                                    # native-code variant: keep the login scene
#                                    # but branch ConnectionManager.SetupFlow
#                                    # straight to LoadMainMenu
#   RENAME="A=B" ./build.sh        # a different literal redirect (default:
#                                    # ConnectionScreen=MainMenu)
#
# Requirements: python3 (3.9+) and internet access to PyPI on the first run
# (installs the single dependency, `cryptography`). The `openssl` CLI is
# optional — it is used for the v1 signature when present.

set -euo pipefail

cd "$(dirname "$0")"

VENV="${VENV:-.tools/venv}"
PY="$VENV/bin/python"
OUT="${OUT:-out}"
MODE="--single"

if [[ "${1:-}" == "--pair" ]]; then MODE=""; shift; fi

if [[ $# -ge 2 ]]; then
  BASE="$1"; SPLIT="$2"
else
  BASE="$(ls original/*base*.apk 2>/dev/null | head -n1 || true)"
  SPLIT="$(ls original/*split*arm64*.apk 2>/dev/null | head -n1 || true)"
fi

if [[ -z "${BASE:-}" || ! -f "$BASE" ]]; then
  echo "!! base APK not found. Put the two Cafe Bazaar 3.4.2 files in original/:" >&2
  echo "   pesarkhande-3.4.2-base.apk" >&2
  echo "   pesarkhande-3.4.2-split_config.arm64_v8a.apk" >&2
  echo "   (expected SHA-256 hashes are listed in docs/04-install-guide.md)" >&2
  exit 1
fi
if [[ -z "${SPLIT:-}" || ! -f "$SPLIT" ]]; then
  echo "!! split APK not found (it carries libil2cpp.so and the other native libs)." >&2
  exit 1
fi

if [[ ! -x "$PY" ]]; then
  PYTHON="${PYTHON:-}"
  if [[ -z "$PYTHON" ]]; then
    if command -v python3 >/dev/null 2>&1; then PYTHON=python3
    elif command -v python >/dev/null 2>&1; then PYTHON=python
    else echo "!! python3 not found (https://www.python.org/downloads/)" >&2; exit 1; fi
  fi
  echo "[deps] creating virtualenv in $VENV"
  "$PYTHON" -m venv "$VENV"
  "$PY" -m pip install -q --upgrade pip
  "$PY" -m pip install -q cryptography
fi

"$PY" -c "import cryptography" 2>/dev/null || "$PY" -m pip install -q cryptography
echo "[deps] ok ($("$PY" -c 'import cryptography;print("cryptography", cryptography.__version__)'))"
mkdir -p "$OUT"

# literal redirect (data-only patch). NO_RENAME=1 disables it, RENAME=... replaces it.
RENAME="${RENAME-ConnectionScreen=MainMenu}"
RENAME_ARGS=""
if [[ -z "${NO_RENAME:-}" ]]; then
  for spec in ${RENAME:-}; do RENAME_ARGS="$RENAME_ARGS --rename $spec"; done
fi

# optional native-code patches, e.g. BRANCH="0x14c00a8=0x14c6498"
BRANCH_ARGS=""
for spec in ${BRANCH:-}; do BRANCH_ARGS="$BRANCH_ARGS --branch $spec"; done

"$PY" tools/patch.py build \
  --base "$BASE" \
  --split "$SPLIT" \
  $MODE \
  $RENAME_ARGS \
  $BRANCH_ARGS \
  --key keys/release.key.pem \
  --cert keys/release.cert.pem \
  --out "$OUT"

echo
if [[ -n "$MODE" ]]; then
  echo "Build finished -> $OUT/pesarkhande-offline-arm64.apk"
  echo "Install:  adb install $OUT/pesarkhande-offline-arm64.apk"
else
  echo "Build finished -> $OUT/pesarkhande-offline-{base,split_config.arm64_v8a}.apk"
  echo "Install:  adb install-multiple $OUT/pesarkhande-offline-base.apk $OUT/pesarkhande-offline-split_config.arm64_v8a.apk"
fi
echo "Guide:    docs/04-install-guide.md"
