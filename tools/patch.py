#!/usr/bin/env python3
"""
patch.py — apply reversible patches to the Mafioso APK set and re-sign it.

Currently implemented (all data-only, no native code is modified):

* ``rename`` — change a C# string literal inside ``global-metadata.dat``.
  Unity loads scenes by name (``SceneManager.LoadScene("ConnectionScreen")``),
  so renaming a literal redirects the boot flow without touching IL2CPP code.
* ``--single`` — merge the base APK with the arm64 native libraries of the
  config split and flip ``android:isSplitRequired`` to ``false`` in the binary
  manifest, producing one standalone APK that installs with plain ``adb install``.
* ``--branch SITE=TARGET`` — write an AArch64 ``b`` instruction at a virtual
  address inside ``libil2cpp.so``. This is a *code* patch: it redirects an
  existing method to another one without touching metadata. The original four
  bytes are recorded in ``assets/pesarkhande-offline/patches.json`` so the
  change stays auditable and reversible.

Example — skip the login screen and boot straight into the main menu, as one
standalone APK::

    python tools/patch.py build\
        --base original/pesarkhande-3.4.2-base.apk\
        --split original/pesarkhande-3.4.2-split_config.arm64_v8a.apk\
        --single\
        --rename ConnectionScreen=MainMenu\
        --out out/

Without ``--single`` the result is a base+split pair signed with the same
self-signed key (``adb install-multiple`` or SAI).

Requirements: Python 3.9+, the ``cryptography`` package and — optionally —
the ``openssl`` CLI (a pure-``cryptography`` fallback exists). Every step is
logged and reversible: the original files are never modified. The signing key
is generated in ``keys/`` on first use; keep it so later builds install over
earlier ones.
"""

from __future__ import annotations

import argparse
import os
import struct
import sys
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from apk import ApkBuilder, ensure_signing_key, sign, verify, verify_v2_crypto  # noqa: E402
from il2cpp import DEFAULT_METADATA, parse_header  # noqa: E402
from axml import set_bool_attribute  # noqa: E402

METADATA_ENTRY = "assets/bin/Data/Managed/Metadata/global-metadata.dat"
LIBIL2CPP = "lib/arm64-v8a/libil2cpp.so"
MANIFEST_ENTRY = "assets/pesarkhande-offline/patches.json"


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
# native code patching (AArch64)
# ---------------------------------------------------------------------------


def _elf_loads(data: bytes) -> List[Tuple[int, int, int]]:
    """PT_LOAD segments of an ELF64 image as ``(vaddr, filesz, file offset)``."""
    if data[:4] != b"\x7fELF" or data[4] != 2:
        raise SystemExit("not a 64-bit ELF image")
    (e_phoff,) = struct.unpack_from("<Q", data, 0x20)
    e_phentsize, e_phnum = struct.unpack_from("<HH", data, 0x36)
    loads: List[Tuple[int, int, int]] = []
    for i in range(e_phnum):
        p_type, _flags, p_offset, p_vaddr, _paddr, p_filesz, _memsz = struct.unpack_from(
            "<IIQQQQQ", data, e_phoff + i * e_phentsize
        )
        if p_type == 1:  # PT_LOAD
            loads.append((p_vaddr, p_filesz, p_offset))
    return loads


def vaddr_to_offset(data: bytes, vaddr: int) -> int:
    """File offset of a virtual address inside an ELF64 image."""
    for vaddr0, filesz, offset in _elf_loads(data):
        if vaddr0 <= vaddr < vaddr0 + filesz:
            return offset + (vaddr - vaddr0)
    raise SystemExit(f"virtual address {vaddr:#x} is not inside any PT_LOAD segment")


def encode_branch(site: int, target: int, link: bool = False) -> bytes:
    """Encode an AArch64 ``b``/``bl`` (reach: +/-128 MiB, 4-byte aligned)."""
    delta = target - site
    if delta % 4:
        raise SystemExit(f"branch {site:#x} -> {target:#x} is not 4-byte aligned")
    imm = delta >> 2
    if not (-(1 << 25) <= imm < (1 << 25)):
        raise SystemExit(f"branch {site:#x} -> {target:#x} exceeds the +/-128 MiB reach")
    word = (0x94000000 if link else 0x14000000) | (imm & 0x3FFFFFF)
    return struct.pack("<I", word)


def decode_branch(word: int, site: int) -> Tuple[bool, int]:
    """Inverse of :func:`encode_branch` — returns ``(is_bl, target)``."""
    imm = word & 0x3FFFFFF
    if imm & (1 << 25):
        imm -= 1 << 26
    return (bool(word >> 31), site + (imm << 2))


def patch_native(
    so: bytes,
    branches: Sequence[str],
    expects: Optional[Dict[int, bytes]] = None,
    verbose: bool = True,
) -> Tuple[bytes, List[dict]]:
    """Apply ``SITE=TARGET`` branches to an ELF image; returns (image, records)."""
    out = bytearray(so)
    records: List[dict] = []
    for spec in branches:
        site_s, _, target_s = spec.partition("=")
        site, target = int(site_s, 0), int(target_s, 0)
        off = vaddr_to_offset(out, site)
        old = bytes(out[off : off + 4])
        want = (expects or {}).get(site)
        if want is not None and old != want:
            raise SystemExit(
                f"{site:#x}: expected {want.hex()} but found {old.hex()} — "
                "the library does not match the analysed build"
            )
        new = encode_branch(site, target)
        out[off : off + 4] = new
        is_bl, back = decode_branch(struct.unpack("<I", new)[0], site)
        if back != target or is_bl:
            raise SystemExit(f"{site:#x}: branch did not encode back to {target:#x}")
        records.append(
            {
                "site": f"{site:#x}",
                "target": f"{target:#x}",
                "before": old.hex(),
                "after": new.hex(),
                "instruction": "b" + ("l" if is_bl else ""),
            }
        )
        if verbose:
            print(f"  {site:#x}: {old.hex()} -> {new.hex()}  (b {target:#x})")
    return bytes(out), records


def patch_raw(so: bytes, writes: Sequence[str], verbose: bool = True) -> Tuple[bytes, List[dict]]:
    """Write raw bytes at virtual addresses: ``SITE=HEX`` (hex, even length)."""
    out = bytearray(so)
    records: List[dict] = []
    for spec in writes:
        site_s, _, hex_s = spec.partition("=")
        site, payload = int(site_s, 0), bytes.fromhex(hex_s.strip())
        if not payload:
            raise SystemExit(f"{site_s}: empty payload")
        off = vaddr_to_offset(out, site)
        old = bytes(out[off : off + len(payload)])
        out[off : off + len(payload)] = payload
        records.append(
            {
                "site": f"{site:#x}",
                "before": old.hex(),
                "after": payload.hex(),
                "instruction": "raw",
            }
        )
        if verbose:
            print(f"  {site:#x}: {old.hex()} -> {payload.hex()}  ({len(payload)} bytes)")
    return bytes(out), records


def build_manifest(renames: Sequence[str], native: Sequence[dict]) -> bytes:
    """Small JSON audit trail embedded in the APK next to the patched data."""
    import datetime
    import json

    doc = {
        "app": "com.paeezanstudio.pesarkhande",
        "version": "3.4.2",
        "variant": "offline-personal",
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "literals": [
            {"from": old, "to": new} for old, _, new in (r.partition("=") for r in renames)
        ],
        "native": native,
        "reversible": "each entry records the original bytes; undo = restore them",
    }
    return (json.dumps(doc, indent=2) + "\n").encode()


# ---------------------------------------------------------------------------
# build pipeline
# ---------------------------------------------------------------------------


def ensure_key(key_path: str, cert_path: str) -> None:
    """Create the personal signing key on first use (kept in ``keys/``)."""
    if ensure_signing_key(key_path, cert_path):
        print(f"generated signing key: {key_path}")


def build(
    base_apk: str,
    split_apk: Optional[str],
    out_dir: str,
    renames: Sequence[str],
    key: str,
    cert: str,
    extra_replace: Sequence[str] = (),
    branches: Sequence[str] = (),
    lib_name: str = LIBIL2CPP,
    writes: Sequence[str] = (),
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

    native_records: List[dict] = []
    lib_payloads: Dict[str, bytes] = {}
    if branches:
        if not split_apk:
            raise SystemExit("--branch needs --split (it carries libil2cpp.so)")
        print(f"[1.5/4] patching native code in {lib_name}")
        with zipfile.ZipFile(split_apk) as z:
            so = z.read(lib_name)
        lib_payloads[lib_name], native_records = patch_native(so, branches)
        if writes:
            lib_payloads[lib_name], extra = patch_raw(lib_payloads[lib_name], writes)
            native_records += extra

    manifest = build_manifest(renames, native_records)

    print("[2/4] rebuilding base APK")
    tmp_base = os.path.join(out_dir, "base-unsigned.apk")
    builder = ApkBuilder(base_apk).replace(METADATA_ENTRY, bytes(meta))
    for spec in extra_replace:
        name, path = spec.split("=", 1)
        builder.replace(name, open(path, "rb").read())
    builder.add(MANIFEST_ENTRY, manifest)
    builder.build(tmp_base)

    print("[3/4] signing base")
    base_out = os.path.join(out_dir, "pesarkhande-offline-base.apk")
    sign(tmp_base, base_out, key, cert)
    os.remove(tmp_base)

    outs = [base_out]
    if split_apk:
        print("[4/4] rebuilding + signing split")
        tmp_split = os.path.join(out_dir, "split-unsigned.apk")
        split_builder = ApkBuilder(split_apk)
        for name, payload in lib_payloads.items():
            split_builder.replace(name, payload)
        split_builder.build(tmp_split)
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


def build_single(
    base_apk: str,
    split_apk: str,
    out_dir: str,
    renames: Sequence[str],
    key: str,
    cert: str,
    extra_replace: Sequence[str] = (),
    branches: Sequence[str] = (),
    lib_name: str = LIBIL2CPP,
    writes: Sequence[str] = (),
) -> str:
    """Merge base + native libs from the split into one standalone APK.

    ``android:isSplitRequired`` is flipped to false in the binary manifest so
    Android accepts a single-file install (no SAI / install-multiple needed).
    """
    import zipfile

    os.makedirs(out_dir, exist_ok=True)
    ensure_key(key, cert)

    with zipfile.ZipFile(base_apk) as z:
        meta = bytearray(z.read(METADATA_ENTRY))
        manifest = z.read("AndroidManifest.xml")
    with zipfile.ZipFile(split_apk) as z:
        libs = {i.filename: z.read(i.filename) for i in z.infolist() if i.filename.startswith("lib/")}
    if not libs:
        raise SystemExit("the split APK contains no lib/ entries")


    print("[1/4] patching metadata literals")
    for spec in renames:
        old, new = spec.split("=", 1)
        meta, hits = patch_literal(meta, old, new)
        if hits == 0:
            raise SystemExit(f"literal not found: {old!r}")
        print(f"  {hits} occurrence(s)")

    native_records: List[dict] = []
    if branches:
        if lib_name not in libs:
            raise SystemExit(f"{lib_name} not found in the split APK")
        print(f"[1.5/4] patching native code in {lib_name}")
        libs[lib_name], native_records = patch_native(libs[lib_name], branches)
    if writes:
        if lib_name not in libs:
            raise SystemExit(f"{lib_name} not found in the split APK")
        print(f"[1.6/4] writing raw bytes into {lib_name}")
        libs[lib_name], extra = patch_raw(libs[lib_name], writes)
        native_records += extra

    print("[2/4] patching manifest (isSplitRequired -> false)")
    manifest, hits = set_bool_attribute(manifest, "application", "isSplitRequired", False)
    if hits != 1:
        raise SystemExit(f"unexpected isSplitRequired hit count: {hits}")

    print(f"[3/4] rebuilding APK with {len(libs)} native libraries")
    tmp = os.path.join(out_dir, "single-unsigned.apk")
    builder = (
        ApkBuilder(base_apk)
        .replace(METADATA_ENTRY, bytes(meta))
        .replace("AndroidManifest.xml", manifest)
    )
    for spec in extra_replace:
        name, path = spec.split("=", 1)
        builder.replace(name, open(path, "rb").read())
    for name, payload in libs.items():
        builder.add(name, payload)
    builder.add(MANIFEST_ENTRY, build_manifest(renames, native_records))
    builder.build(tmp)

    print("[4/4] signing")
    out_path = os.path.join(out_dir, "pesarkhande-offline-arm64.apk")
    sign(tmp, out_path, key, cert)
    os.remove(tmp)

    ok, msg = verify_v2_crypto(out_path)
    print(f"\nverify: v2 {'OK' if ok else 'FAILED'} — {msg}")
    if not ok:
        raise SystemExit(1)
    return out_path


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
    p.add_argument(
        "--branch",
        action="append",
        default=[],
        metavar="SITE=TARGET",
        help="write an AArch64 'b' at virtual address SITE going to TARGET (hex)",
    )
    p.add_argument("--lib", default=LIBIL2CPP, help="library that --branch applies to")
    p.add_argument(
        "--write",
        action="append",
        default=[],
        metavar="SITE=HEX",
        help="write raw hex bytes at a virtual address (code cave / stub)",
    )
    p.add_argument("--single", action="store_true", help="merge base+split into one standalone APK")
    p.add_argument("--replace", action="append", default=[], metavar="NAME=PATH")
    p.add_argument("--key", default="keys/release.key.pem")
    p.add_argument("--cert", default="keys/release.cert.pem")

    p = sub.add_parser("inspect", help="show which literals match a pattern")
    p.add_argument("--metadata", default=DEFAULT_METADATA)
    p.add_argument("pattern")

    args = ap.parse_args(argv)

    if args.cmd == "build":
        if args.single:
            if not args.split:
                raise SystemExit("--single requires --split")
            out = build_single(
                args.base, args.split, args.out, args.rename, args.key, args.cert,
                args.replace, args.branch, args.lib, args.write,
            )
            print("\ninstall with:")
            print(f"  adb install {out}")
        else:
            outs = build(
                args.base, args.split, args.out, args.rename, args.key, args.cert,
                args.replace, args.branch, args.lib, args.write,
            )
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
