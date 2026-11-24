#!/usr/bin/env python3
"""
patch.py — apply reversible patches to the Mafioso APK set and re-sign it.

Currently implemented (all data-only, no native code is modified):

* ``rename`` — change a C# string literal inside ``global-metadata.dat``.
  Unity loads scenes by name (``SceneManager.LoadScene("ConnectionScreen")``),
  so renaming a literal redirects the boot flow without touching IL2CPP code.

Example — skip the login screen and boot straight into the main menu::

    python tools/patch.py build \\
        --base original/pesarkhande-3.4.2-base.apk \\
        --split original/pesarkhande-3.4.2-split_config.arm64_v8a.apk \\
        --rename ConnectionScreen=MainMenu \\
        --out out/

The result is a base+split pair signed with the same self-signed key, ready for
``adb install-multiple`` (or SAI). Every step is logged and reversible: the
original files are never modified.
"""

from __future__ import annotations

import argparse
import os
import struct
import subprocess
import sys
import tempfile
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from apk import ApkBuilder, sign, verify, verify_v2_crypto  # noqa: E402
from il2cpp import DEFAULT_METADATA, parse_header  # noqa: E402

METADATA_ENTRY = "assets/bin/Data/Managed/Metadata/global-metadata.dat"


# ---------------------------------------------------------------------------
# metadata literal patching
# ---------------------------------------------------------------------------


def patch_literal(data: bytearray, old: str, new: str, verbose: bool = True) -> Tuple[bytearray, int]:
    """Replace every occurrence of the exact string literal ``old`` with ``new``.

    The literal table stores ``(length, dataIndex)`` pairs; the bytes live in a
    separate blob. A shorter replacement is written in place and the length is
    lowered, which leaves the old tail unused but harmless.
    """
    header = parse_header(bytes(data))
    table_off = header.offset("stringLiteral")
    table_size = header.size("stringLiteral")
    data_off = header.offset("stringLiteralData")
    data_size = header.size("stringLiteralData")
    old_bytes = old.encode("utf-8")
    new_bytes = new.encode("utf-8")

    hits = 0
    for i in range(table_size // 8):
        length, index = struct.unpack_from("<Ii", data, table_off + i * 8)
        if length != len(old_bytes):
            continue
        if index < 0 or index + length > data_size:
            continue
        if bytes(data[data_off + index : data_off + index + length]) != old_bytes:
            continue
        if len(new_bytes) > length:
            raise SystemExit(f"replacement for {old!r} is longer than the original")
        data[data_off + index : data_off + index + length] = new_bytes + b"\0" * (length - len(new_bytes))
        struct.pack_into("<I", data, table_off + i * 8, len(new_bytes))
        hits += 1
        if verbose:
            print(f"  literal #{i}: {old!r} -> {new!r}")
    return data, hits


# ---------------------------------------------------------------------------
# build pipeline
# ---------------------------------------------------------------------------


def ensure_key(key_path: str, cert_path: str) -> None:
    if os.path.exists(key_path) and os.path.exists(cert_path):
        return
    os.makedirs(os.path.dirname(os.path.abspath(key_path)), exist_ok=True)
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", key_path, "-out", cert_path,
            "-days", "3650", "-nodes", "-subj", "/CN=mafiaso-offline/O=Personal Build",
        ],
        check=True,
        capture_output=True,
    )
    os.chmod(key_path, 0o600)
    print(f"generated signing key: {key_path}")


def build(
    base_apk: str,
    split_apk: Optional[str],
    out_dir: str,
    renames: Sequence[str],
    key: str,
    cert: str,
    extra_replace: Sequence[str] = (),
) -> List[str]:
    os.makedirs(out_dir, exist_ok=True)
    ensure_key(key, cert)

    import zipfile

    with zipfile.ZipFile(base_apk) as z:
        meta = bytearray(z.read(METADATA_ENTRY))

    print("[1/4] patching metadata literals")
    for spec in renames:
        old, new = spec.split("=", 1)
        meta, hits = patch_literal(meta, old, new)
        if hits == 0:
            raise SystemExit(f"literal not found: {old!r}")
        print(f"  {hits} occurrence(s)")

    print("[2/4] rebuilding base APK")
    tmp_base = os.path.join(out_dir, "base-unsigned.apk")
    builder = ApkBuilder(base_apk).replace(METADATA_ENTRY, bytes(meta))
    for spec in extra_replace:
        name, path = spec.split("=", 1)
        builder.replace(name, open(path, "rb").read())
    builder.build(tmp_base)

    print("[3/4] signing base")
    base_out = os.path.join(out_dir, "pesarkhande-offline-base.apk")
    sign(tmp_base, base_out, key, cert)
    os.remove(tmp_base)

    outs = [base_out]
    if split_apk:
        print("[4/4] rebuilding + signing split")
        tmp_split = os.path.join(out_dir, "split-unsigned.apk")
        ApkBuilder(split_apk).build(tmp_split)
        split_out = os.path.join(out_dir, "pesarkhande-offline-split_config.arm64_v8a.apk")
        sign(tmp_split, split_out, key, cert)
        os.remove(tmp_split)
        outs.append(split_out)

    print("\nverifying:")
    for path in outs:
        ok, msg = verify_v2_crypto(path)
        print(f"  {os.path.basename(path)}: v2 {'OK' if ok else 'FAILED'} — {msg}")
        if not ok:
            raise SystemExit(1)
    return outs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("build", help="patch metadata, rebuild and sign the APK set")
    p.add_argument("--base", required=True)
    p.add_argument("--split", default=None)
    p.add_argument("--out", default="out")
    p.add_argument("--rename", action="append", default=[], metavar="OLD=NEW")
    p.add_argument("--replace", action="append", default=[], metavar="NAME=PATH")
    p.add_argument("--key", default="keys/release.key.pem")
    p.add_argument("--cert", default="keys/release.cert.pem")

    p = sub.add_parser("inspect", help="show which literals match a pattern")
    p.add_argument("--metadata", default=DEFAULT_METADATA)
    p.add_argument("pattern")

    args = ap.parse_args(argv)

    if args.cmd == "build":
        outs = build(args.base, args.split, args.out, args.rename, args.key, args.cert, args.replace)
        print("\ninstall with:")
        print("  adb install-multiple " + " ".join(outs))
    elif args.cmd == "inspect":
        import re

        data = open(args.metadata, "rb").read()
        header = parse_header(data)
        table_off, table_size = header.offset("stringLiteral"), header.size("stringLiteral")
        data_off, data_size = header.offset("stringLiteralData"), header.size("stringLiteralData")
        pat = re.compile(args.pattern, re.I)
        for i in range(table_size // 8):
            length, index = struct.unpack_from("<Ii", data, table_off + i * 8)
            if length <= 0 or index < 0 or index + length > data_size:
                continue
            text = data[data_off + index : data_off + index + length].decode("utf-8", "replace")
            if pat.search(text):
                print(f"{i:6d}  {text!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
