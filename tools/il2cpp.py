#!/usr/bin/env python3
"""
il2cpp.py — IL2CPP metadata + binary toolkit for the Mafioso offline project.

Reads Unity's ``global-metadata.dat`` (v31 / Unity 6) and ``libil2cpp.so`` and
maps managed types/methods/fields to native addresses, so that patch points can
be located without a .NET decompiler.

Typical usage::

    python tools/il2cpp.py info
    python tools/il2cpp.py class ConnectionScreen
    python tools/il2cpp.py method SimulateBotAction
    python tools/il2cpp.py literal "DEBUG MODE"
    python tools/il2cpp.py disasm 0x123456 --count 40

Only standard-library + capstone are required.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import re
import struct
import sys
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "work")
DEFAULT_METADATA = os.path.join(WORK, "global-metadata.dat")
DEFAULT_BINARY = os.path.join(WORK, "libil2cpp.so")

METADATA_MAGIC = 0xFAB11BAF


# ---------------------------------------------------------------------------
# metadata header
# ---------------------------------------------------------------------------

# (offset, size) pairs in declaration order for metadata v31.
# Entries that only exist in older versions are marked None and skipped.
HEADER_PAIRS: Sequence[Optional[Tuple[str, str]]] = (
    ("stringLiteralOffset", "stringLiteralSize"),
    ("stringLiteralDataOffset", "stringLiteralDataSize"),
    ("stringOffset", "stringSize"),
    ("eventsOffset", "eventsSize"),
    ("propertiesOffset", "propertiesSize"),
    ("methodsOffset", "methodsSize"),
    ("parameterDefaultValuesOffset", "parameterDefaultValuesSize"),
    ("fieldDefaultValuesOffset", "fieldDefaultValuesSize"),
    ("fieldAndParameterDefaultValueDataOffset", "fieldAndParameterDefaultValueDataSize"),
    ("fieldMarshaledSizesOffset", "fieldMarshaledSizesSize"),
    ("parametersOffset", "parametersSize"),
    ("fieldsOffset", "fieldsSize"),
    ("genericParametersOffset", "genericParametersSize"),
    ("genericParameterConstraintsOffset", "genericParameterConstraintsSize"),
    ("genericContainersOffset", "genericContainersSize"),
    ("nestedTypesOffset", "nestedTypesSize"),
    ("interfacesOffset", "interfacesSize"),
    ("vtableMethodsOffset", "vtableMethodsSize"),
    ("interfaceOffsetsOffset", "interfaceOffsetsSize"),
    ("typeDefinitionsOffset", "typeDefinitionsSize"),
    None,  # rgctxEntries (<= 24.1)
    ("imagesOffset", "imagesSize"),
    ("assembliesOffset", "assembliesSize"),
    None,  # metadataUsageLists (19..24.5)
    None,  # metadataUsagePairs (19..24.5)
    ("fieldRefsOffset", "fieldRefsSize"),
    ("referencedAssembliesOffset", "referencedAssembliesSize"),
    None,  # attributesInfo (21..27.2)
    None,  # attributeTypes (21..27.2)
    ("attributeDataOffset", "attributeDataSize"),
    ("attributeDataRangeOffset", "attributeDataRangeSize"),
    ("unresolvedVirtualCallParameterTypesOffset", "unresolvedVirtualCallParameterTypesSize"),
    ("unresolvedVirtualCallParameterRangesOffset", "unresolvedVirtualCallParameterRangesSize"),
    ("windowsRuntimeTypeNamesOffset", "windowsRuntimeTypeNamesSize"),
    ("windowsRuntimeStringsOffset", "windowsRuntimeStringsSize"),
    ("exportedTypeDefinitionsOffset", "exportedTypeDefinitionsSize"),
)

# struct sizes for v31 (bytes)
SIZEOF_TYPE = 88
SIZEOF_METHOD = 36
SIZEOF_FIELD = 12
SIZEOF_STRING_LITERAL = 8
SIZEOF_IMAGE = 40


@dataclasses.dataclass
class MetaHeader:
    sanity: int
    version: int
    fields: Dict[str, int]

    def offset(self, name: str) -> int:
        return self.fields[name + "Offset"]

    def size(self, name: str) -> int:
        return self.fields[name + "Size"]


def parse_header(data: bytes) -> MetaHeader:
    if len(data) < 8:
        raise ValueError("metadata too small")
    sanity, version = struct.unpack_from("<II", data, 0)
    fields: Dict[str, int] = {}
    off = 8
    for pair in HEADER_PAIRS:
        if pair is None:
            continue
        if off + 8 > len(data):
            break
        o, s = struct.unpack_from("<II", data, off)
        fields[pair[0]] = o
        fields[pair[1]] = s
        off += 8
    return MetaHeader(sanity, version, fields)


# ---------------------------------------------------------------------------
# data model
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class TypeInfo:
    index: int
    name: str
    namespace: str
    flags: int
    field_start: int
    field_count: int
    method_start: int
    method_count: int
    token: int
    parent: int

    @property
    def full_name(self) -> str:
        return f"{self.namespace}.{self.name}" if self.namespace else self.name


@dataclasses.dataclass
class MethodInfo:
    index: int
    name: str
    declaring_type: int
    parameter_count: int
    token: int
    flags: int

    @property
    def rid(self) -> int:
        return self.token & 0xFFFFFF


@dataclasses.dataclass
class FieldInfo:
    index: int
    name: str
    type_index: int
    token: int


@dataclasses.dataclass
class ImageInfo:
    index: int
    name: str
    type_start: int
    type_count: int


class Metadata:
    """Parses global-metadata.dat (v31)."""

    def __init__(self, path: str = DEFAULT_METADATA):
        self.path = path
        with open(path, "rb") as fh:
            self.data = fh.read()
        self.header = parse_header(self.data)
        if self.header.sanity != METADATA_MAGIC:
            raise ValueError(
                f"unexpected metadata magic {self.header.sanity:#x} "
                f"(expected {METADATA_MAGIC:#x}) — compressed metadata is not supported"
            )
        self.version = self.header.version
        self._strings_off = self.header.offset("string")
        self._strings_size = self.header.size("string")
        self.types = self._read_types()
        self.methods = self._read_methods()
        self.fields = self._read_fields()
        self.images = self._read_images()
        self.literals = self._read_literals()

    # -- strings ---------------------------------------------------------
    def string_at(self, index: int) -> str:
        if index < 0 or index >= self._strings_size:
            return f"<bad string index {index}>"
        start = self._strings_off + index
        end = self.data.find(b"\0", start)
        if end < 0:
            end = self._strings_off + self._strings_size
        return self.data[start:end].decode("utf-8", "replace")

    # -- tables ----------------------------------------------------------
    def _read_types(self) -> List[TypeInfo]:
        off = self.header.offset("typeDefinitions")
        size = self.header.size("typeDefinitions")
        if size % SIZEOF_TYPE:
            raise ValueError(f"typeDefinitions size {size} not a multiple of {SIZEOF_TYPE}")
        out: List[TypeInfo] = []
        for i in range(size // SIZEOF_TYPE):
            base = off + i * SIZEOF_TYPE
            (
                name_index,
                ns_index,
                byval_type,
                declaring,
                parent,
                element_type,
                generic_container,
                flags,
                field_start,
                method_start,
                event_start,
                property_start,
                nested_start,
                interfaces_start,
                vtable_start,
                iface_offsets_start,
                method_count,
                property_count,
                field_count,
                event_count,
                nested_count,
                vtable_count,
                interfaces_count,
                iface_offsets_count,
                bitfield,
                token,
            ) = struct.unpack_from("<7iI8i8H2I", self.data, base)
            out.append(
                TypeInfo(
                    index=i,
                    name=self.string_at(name_index),
                    namespace=self.string_at(ns_index),
                    flags=flags,
                    field_start=field_start,
                    field_count=field_count,
                    method_start=method_start,
                    method_count=method_count,
                    token=token,
                    parent=parent,
                )
            )
        return out

    def _read_methods(self) -> List[MethodInfo]:
        off = self.header.offset("methods")
        size = self.header.size("methods")
        if size % SIZEOF_METHOD:
            raise ValueError(f"methods size {size} not a multiple of {SIZEOF_METHOD}")
        out: List[MethodInfo] = []
        for i in range(size // SIZEOF_METHOD):
            base = off + i * SIZEOF_METHOD
            (
                name_index,
                declaring,
                return_type,
                return_param_token,
                parameter_start,
                generic_container,
                token,
                flags,
                iflags,
                slot,
                parameter_count,
            ) = struct.unpack_from("<I5iI4H", self.data, base)
            out.append(
                MethodInfo(
                    index=i,
                    name=self.string_at(name_index),
                    declaring_type=declaring,
                    parameter_count=parameter_count,
                    token=token,
                    flags=flags,
                )
            )
        return out

    def _read_fields(self) -> List[FieldInfo]:
        off = self.header.offset("fields")
        size = self.header.size("fields")
        if size % SIZEOF_FIELD:
            raise ValueError(f"fields size {size} not a multiple of {SIZEOF_FIELD}")
        out: List[FieldInfo] = []
        for i in range(size // SIZEOF_FIELD):
            name_index, type_index, token = struct.unpack_from("<IiI", self.data, off + i * SIZEOF_FIELD)
            out.append(FieldInfo(i, self.string_at(name_index), type_index, token))
        return out

    def _read_images(self) -> List[ImageInfo]:
        off = self.header.offset("images")
        size = self.header.size("images")
        if size % SIZEOF_IMAGE:
            raise ValueError(f"images size {size} not a multiple of {SIZEOF_IMAGE}")
        out: List[ImageInfo] = []
        for i in range(size // SIZEOF_IMAGE):
            (
                name_index,
                assembly_index,
                type_start,
                type_count,
                exported_start,
                exported_count,
                entry_point,
                token,
                attr_start,
                attr_count,
            ) = struct.unpack_from("<Ii i I i I i I i I".replace(" ", ""), self.data, off + i * SIZEOF_IMAGE)
            out.append(ImageInfo(i, self.string_at(name_index), type_start, type_count))
        return out

    def _read_literals(self) -> List[str]:
        off = self.header.offset("stringLiteral")
        size = self.header.size("stringLiteral")
        data_off = self.header.offset("stringLiteralData")
        data_size = self.header.size("stringLiteralData")
        if size % SIZEOF_STRING_LITERAL:
            raise ValueError(f"stringLiteral size {size} not a multiple of {SIZEOF_STRING_LITERAL}")
        out: List[str] = []
        for i in range(size // SIZEOF_STRING_LITERAL):
            length, data_index = struct.unpack_from("<Ii", self.data, off + i * SIZEOF_STRING_LITERAL)
            if data_index < 0 or data_index + length > data_size:
                out.append("")
                continue
            raw = self.data[data_off + data_index : data_off + data_index + length]
            out.append(raw.decode("utf-8", "replace"))
        return out

    # -- helpers ---------------------------------------------------------
    def find_type(self, name: str) -> List[TypeInfo]:
        name = name.lower()
        return [t for t in self.types if t.name.lower() == name or t.full_name.lower() == name]

    def search_types(self, needle: str) -> List[TypeInfo]:
        needle = needle.lower()
        return [t for t in self.types if needle in t.full_name.lower()]

    def type_fields(self, t: TypeInfo) -> List[FieldInfo]:
        return self.fields[t.field_start : t.field_start + t.field_count]

    def type_methods(self, t: TypeInfo) -> List[MethodInfo]:
        return self.methods[t.method_start : t.method_start + t.method_count]

    def method_type(self, m: MethodInfo) -> Optional[TypeInfo]:
        if 0 <= m.declaring_type < len(self.types):
            return self.types[m.declaring_type]
        return None


# ---------------------------------------------------------------------------
# ELF / libil2cpp.so
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class Section:
    name: str
    addr: int
    offset: int
    size: int
    flags: int


class Elf:
    """Minimal ELF64 little-endian reader (sections + PT_LOAD mapping)."""

    def __init__(self, path: str):
        self.path = path
        with open(path, "rb") as fh:
            self.data = fh.read()
        if self.data[:4] != b"\x7fELF":
            raise ValueError("not an ELF file")
        self._parse()

    def _parse(self) -> None:
        d = self.data
        (e_shoff,) = struct.unpack_from("<Q", d, 0x28)
        (e_shentsize, e_shnum, e_shstrndx) = struct.unpack_from("<HHH", d, 0x3A)
        self.sections: List[Section] = []
        for i in range(e_shnum):
            base = e_shoff + i * e_shentsize
            name_off, sh_type, flags, addr, offset, size = struct.unpack_from("<IIQQQQ", d, base)
            self.sections.append(Section("", addr, offset, size, flags))
        # section names live in the section-header string table
        if e_shstrndx >= len(self.sections):
            raise ValueError("bad e_shstrndx")
        strtab = self.sections[e_shstrndx]
        for i, sec in enumerate(self.sections):
            base = e_shoff + i * e_shentsize
            (name_off,) = struct.unpack_from("<I", d, base)
            start = strtab.offset + name_off
            end = d.find(b"\0", start)
            sec.name = d[start:end].decode("ascii", "replace") if end >= 0 else ""

        # RELATIVE relocations: in a shared object most pointers are stored as 0
        # and patched at load time, so reads must honour the addend.
        self.rel: Dict[int, int] = {}
        for sec in self.sections:
            if sec.name == ".rela.dyn":
                for i in range(sec.size // 24):
                    r_offset, r_info, r_addend = struct.unpack_from("<QQq", d, sec.offset + i * 24)
                    if r_info & 0xFFFFFFFF == 0x403:  # R_AARCH64_RELATIVE
                        self.rel[r_offset] = r_addend

        # program headers for vaddr -> file offset
        e_phoff = struct.unpack_from("<Q", d, 0x20)[0]
        e_phentsize, e_phnum = struct.unpack_from("<HH", d, 0x36)
        self.loads: List[Tuple[int, int, int, int]] = []  # vaddr, filesz, offset, memsz
        for i in range(e_phnum):
            base = e_phoff + i * e_phentsize
            p_type, p_flags, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz = struct.unpack_from(
                "<IIQQQQQ", d, base
            )
            if p_type == 1:  # PT_LOAD
                self.loads.append((p_vaddr, p_filesz, p_offset, p_memsz))

    # -- address translation --------------------------------------------
    def vaddr_to_offset(self, vaddr: int) -> Optional[int]:
        for v, filesz, off, memsz in self.loads:
            if v <= vaddr < v + filesz:
                return off + (vaddr - v)
        return None

    def offset_to_vaddr(self, off: int) -> Optional[int]:
        for v, filesz, o, memsz in self.loads:
            if o <= off < o + filesz:
                return v + (off - o)
        return None

    # -- readers ---------------------------------------------------------
    def read_u64(self, vaddr: int) -> Optional[int]:
        """Read a pointer-sized value, honouring RELATIVE relocations."""
        if vaddr in self.rel:
            return self.rel[vaddr]
        off = self.vaddr_to_offset(vaddr)
        if off is None or off + 8 > len(self.data):
            return None
        return struct.unpack_from("<Q", self.data, off)[0]

    def find_ptr_relocated(self, value: int, sections: Sequence[str] = (".data.rel.ro", ".data")) -> List[int]:
        """VAs (8-byte aligned) whose *effective* value equals ``value``.

        Raw byte search misses relocated pointers, so this walks the requested
        sections and compares :meth:`read_u64` results.
        """
        hits: List[int] = []
        for sec in self.sections:
            if sec.name not in sections:
                continue
            start = sec.addr & ~7
            end = sec.addr + sec.size
            for va in range(start, end - 7, 8):
                if self.read_u64(va) == value:
                    hits.append(va)
        return hits

    def read_cstr(self, vaddr: int, limit: int = 512) -> Optional[str]:
        off = self.vaddr_to_offset(vaddr)
        if off is None:
            return None
        end = self.data.find(b"\0", off, off + limit)
        if end < 0:
            return None
        return self.data[off:end].decode("utf-8", "replace")

    def find_cstr(self, text: str) -> Optional[int]:
        """VA of the first NUL-terminated occurrence of ``text``."""
        needle = text.encode() + b"\0"
        pos = self.data.find(needle)
        if pos < 0:
            return None
        return self.offset_to_vaddr(pos)

    def find_ptr(self, value: int) -> List[int]:
        """VAs of all 8-byte words equal to ``value`` inside allocated sections."""
        needle = struct.pack("<Q", value)
        hits: List[int] = []
        start = 0
        while True:
            pos = self.data.find(needle, start)
            if pos < 0:
                break
            va = self.offset_to_vaddr(pos)
            if va is not None:
                hits.append(va)
            start = pos + 1
        return hits


@dataclasses.dataclass
class CodeGenModule:
    name: str
    address: int
    method_pointer_count: int
    method_pointers: int  # VA of the array
    module: "Elf"


class Binary:
    """libil2cpp.so + CodeGenModule lookup."""

    def __init__(self, path: str = DEFAULT_BINARY):
        self.path = path
        self.elf = Elf(path)
        self._modules: Dict[str, CodeGenModule] = {}

    # -- codegen modules -------------------------------------------------
    def codegen_module(self, module_name: str) -> Optional[CodeGenModule]:
        """Locate ``Il2CppCodeGenModule`` for ``module_name`` (e.g. 'Assembly-CSharp').

        The struct starts with a pointer to the module name string, so we look for
        that string, then for a pointer to it in the data sections.
        """
        key = module_name
        if key in self._modules:
            return self._modules[key]
        name_va = self.elf.find_cstr(module_name)
        if name_va is None:
            # try with .dll suffix
            name_va = self.elf.find_cstr(module_name + ".dll")
        if name_va is None:
            return None
        for ptr_va in self.elf.find_ptr_relocated(name_va):
            count = self.elf.read_u64(ptr_va + 8)
            array_va = self.elf.read_u64(ptr_va + 16)
            if count is None or array_va is None:
                continue
            if not (0 < count < 200000):
                continue
            if self.elf.vaddr_to_offset(array_va) is None:
                continue
            mod = CodeGenModule(module_name, ptr_va, count, array_va, self.elf)
            self._modules[key] = mod
            return mod
        return None

    def method_pointers(self, module_name: str) -> Optional[List[int]]:
        mod = self.codegen_module(module_name)
        if mod is None:
            return None
        out: List[int] = []
        for i in range(mod.method_pointer_count):
            va = mod.module.read_u64(mod.method_pointers + 8 * i)
            if va is None:
                return None
            out.append(va)
        return out

    # -- text range ------------------------------------------------------
    def text_range(self) -> Tuple[int, int]:
        """Lowest/highest address of executable sections (Unity puts IL2CPP code in `il2cpp`)."""
        ranges = [
            (sec.addr, sec.addr + sec.size)
            for sec in self.elf.sections
            if sec.name in (".text", "il2cpp") and sec.size
        ]
        if not ranges:
            return 0, 0
        return min(r[0] for r in ranges), max(r[1] for r in ranges)

    def is_executable(self, va: int) -> bool:
        lo, hi = self.text_range()
        return lo <= va < hi


# ---------------------------------------------------------------------------
# disassembly
# ---------------------------------------------------------------------------


def disassemble(binary: Binary, va: int, count: int = 30) -> List[str]:
    try:
        from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("capstone is required: pip install capstone") from exc
    off = binary.elf.vaddr_to_offset(va)
    if off is None:
        raise SystemExit(f"address {va:#x} is not mapped")
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    md.detail = False
    code = binary.elf.data[off : off + count * 4]
    lines: List[str] = []
    for ins in md.disasm(code, va):
        lines.append(f"{ins.address:#012x}  {ins.mnemonic:<8s} {ins.op_str}")
    return lines


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _load(meta_path: str, bin_path: Optional[str]) -> Tuple[Metadata, Optional[Binary]]:
    meta = Metadata(meta_path)
    binary = None
    if bin_path and os.path.exists(bin_path):
        binary = Binary(bin_path)
    return meta, binary


def _resolve_address(binary: Optional[Binary], meta: Metadata, m: MethodInfo) -> Optional[int]:
    if binary is None:
        return None
    t = meta.method_type(m)
    if t is None:
        return None
    image = None
    for img in meta.images:
        if img.type_start <= t.index < img.type_start + img.type_count:
            image = img
            break
    if image is None:
        return None
    ptrs = binary.method_pointers(image.name)
    if not ptrs:
        return None
    idx = m.rid - 1
    if 0 <= idx < len(ptrs):
        return ptrs[idx]
    return None


def cmd_info(meta: Metadata, binary: Optional[Binary]) -> None:
    print(f"metadata : {meta.path}")
    print(f"version  : {meta.version}")
    print(f"size     : {len(meta.data):,} bytes")
    print(f"types    : {len(meta.types):,}")
    print(f"methods  : {len(meta.methods):,}")
    print(f"fields   : {len(meta.fields):,}")
    print(f"images   : {len(meta.images):,}")
    print(f"literals : {len(meta.literals):,}")
    print("\nheader (offset/size):")
    for pair in HEADER_PAIRS:
        if pair is None:
            continue
        try:
            o = meta.header.fields[pair[0]]
            s = meta.header.fields[pair[1]]
        except KeyError:
            continue
        print(f"  {pair[0]:<48s} {o:#012x} {s:#012x}")
    if binary:
        lo, hi = binary.text_range()
        print(f"\nbinary   : {binary.path}")
        print(f".text    : {lo:#x}..{hi:#x} ({hi - lo:,} bytes)")
        for img in meta.images:
            mod = binary.codegen_module(img.name)
            if mod:
                print(f"  module {img.name:<28s} @{mod.address:#x} methods={mod.method_pointer_count}")


def cmd_classes(meta: Metadata, args: argparse.Namespace) -> None:
    pats = args.pattern
    rows = meta.types
    if pats:
        rows = [t for t in rows if any(p.lower() in t.full_name.lower() for p in pats)]
    for t in rows[: args.limit]:
        print(f"{t.index:6d}  {t.full_name}  (methods={t.method_count}, fields={t.field_count})")
    print(f"-- {len(rows)} types")


def _print_type(meta: Metadata, binary: Optional[Binary], t: TypeInfo, verbose: bool) -> None:
    print(f"\n=== {t.full_name}  (type #{t.index}, token {t.token:#x}) ===")
    print(f"flags={t.flags:#x} parent={t.parent} methods={t.method_count} fields={t.field_count}")
    print("-- fields --")
    for f in meta.type_fields(t):
        print(f"  {f.index:6d}  {f.name}")
    print("-- methods --")
    for m in meta.type_methods(t):
        addr = _resolve_address(binary, meta, m)
        a = f"{addr:#x}" if addr else "-"
        print(f"  {m.index:6d}  {m.name:<48s} token={m.token:#010x} params={m.parameter_count} addr={a}")


def cmd_class(meta: Metadata, binary: Optional[Binary], args: argparse.Namespace) -> None:
    for name in args.names:
        found = meta.find_type(name) or meta.search_types(name)
        if not found:
            print(f"!! type not found: {name}")
            continue
        for t in found[: args.limit]:
            _print_type(meta, binary, t, args.verbose)


def cmd_method(meta: Metadata, binary: Optional[Binary], args: argparse.Namespace) -> None:
    needle = args.pattern.lower()
    hits = []
    for t in meta.types:
        for m in meta.type_methods(t):
            if needle in m.name.lower():
                addr = _resolve_address(binary, meta, m)
                hits.append((t.full_name, m, addr))
    for tn, m, addr in hits[: args.limit]:
        a = f"{addr:#x}" if addr else "-"
        print(f"{tn:<40s} {m.name:<44s} token={m.token:#010x} addr={a}")
    print(f"-- {len(hits)} methods")


def cmd_literal(meta: Metadata, args: argparse.Namespace) -> None:
    pat = re.compile(args.pattern, re.I)
    n = 0
    for i, text in enumerate(meta.literals):
        if pat.search(text):
            preview = text.replace("\n", "\\n")
            print(f"{i:6d}  {preview[: args.width]}")
            n += 1
            if n >= args.limit:
                break
    print(f"-- {n} literals shown")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metadata", default=DEFAULT_METADATA)
    ap.add_argument("--binary", default=DEFAULT_BINARY)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("info")

    p = sub.add_parser("classes")
    p.add_argument("pattern", nargs="*")
    p.add_argument("--limit", type=int, default=80)

    p = sub.add_parser("class")
    p.add_argument("names", nargs="+")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("-v", "--verbose", action="store_true")

    p = sub.add_parser("method")
    p.add_argument("pattern")
    p.add_argument("--limit", type=int, default=60)

    p = sub.add_parser("literal")
    p.add_argument("pattern")
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("--width", type=int, default=160)

    p = sub.add_parser("disasm")
    p.add_argument("address")
    p.add_argument("--count", type=int, default=30)

    args = ap.parse_args(argv)
    meta, binary = _load(args.metadata, args.binary if os.path.exists(args.binary) else None)

    if args.cmd == "info":
        cmd_info(meta, binary)
    elif args.cmd == "classes":
        cmd_classes(meta, args)
    elif args.cmd == "class":
        cmd_class(meta, binary, args)
    elif args.cmd == "method":
        cmd_method(meta, binary, args)
    elif args.cmd == "literal":
        cmd_literal(meta, args)
    elif args.cmd == "disasm":
        va = int(args.address, 0)
        for line in disassemble(binary, va, args.count):
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
