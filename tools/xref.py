#!/usr/bin/env python3
"""
xref.py — static cross-reference database for the IL2CPP binary (metadata v31).

For every method of a module (default ``Assembly-CSharp``) the tool extracts

* **metadata slot references** — string literals, types, fields and methods the
  method uses. Generated code loads them through the GOT into a global slot in
  ``.data``; before runtime initialisation the slot holds the *encoded handle*
  ``(kind << 29) | (index << 1) | 1`` (see ``il2cpp::metadata::InitializeRuntimeMetadata``).
* **direct calls** (``bl``) resolved to ``Type.method`` across *all* modules.
* **memory operands** — ``(width, offset)`` of ``ldr/str`` on object registers,
  i.e. candidate instance-field offsets.

Reverse indexes answer "who uses literal X / type Y / field Z / calls M".

Usage::

    python3 tools/xref.py method ConnectionManager TryLogin
    python3 tools/xref.py type ConnectionManager            # all methods, with refs
    python3 tools/xref.py uses --literal MainMenu
    python3 tools/xref.py uses --type ConnectionManager [--module Assembly-CSharp]
    python3 tools/xref.py uses --field ConnectionManager.offlineMode
    python3 tools/xref.py callers ConnectionManager.LoadMainMenu
    python3 tools/xref.py find "offline"                    # search type/method/field names

Only the standard library + ``capstone`` are required (analysis tool; not needed
for the build).
"""

from __future__ import annotations

import argparse
import bisect
import os
import re
import struct
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from il2cpp import Binary, Metadata, SIZEOF_FIELD, SIZEOF_METHOD, SIZEOF_TYPE  # noqa: E402

# make pickles reference "xref.MethodXref" whether run as a module or as a script
if __name__ == "__main__":  # pragma: no cover
    sys.modules["xref"] = sys.modules[__name__]

HANDLE_KINDS = {1: "type", 2: "type", 3: "class", 4: "field", 5: "str", 6: "class", 7: "field"}
TYPE_CLASS, TYPE_VALUETYPE, TYPE_GENERICINST, TYPE_SZARRAY, TYPE_VAR, TYPE_MVAR = 0x12, 0x11, 0x15, 0x1D, 0x13, 0x1E

MEM_RE = re.compile(r"^\s*(?:x\d+|w\d+),\s*\[(x\d+|sp)(?:,\s*#?(-?(?:0x[0-9a-f]+|\d+)))?(?:,\s*(\w+))?\](?:!)?")
GOT_RANGE = None  # set in Xref.__init__


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

@dataclass
class Ref:
    kind: str          # 'str' | 'type' | 'class' | 'field' | 'unknown'
    name: str          # resolved name
    raw: int           # encoded handle
    got: int           # GOT entry address
    access: str = ""   # for fields: 'r' load, 'w' store, '&' address-of


@dataclass
class MethodXref:
    module: str
    type_name: str
    method: str
    addr: int
    size: int
    refs: List[Ref] = field(default_factory=list)
    calls: List[Tuple[int, str]] = field(default_factory=list)   # (target, label)
    mem: Counter = field(default_factory=Counter)                # (width, offset) -> count

    @property
    def full(self) -> str:
        return f"{self.type_name}.{self.method}"


# ---------------------------------------------------------------------------
# field layout engine (mirrors il2cpp Class::SetupFields for v31)
# ---------------------------------------------------------------------------

PRIM_SIZE = {0x02: (1, 1), 0x03: (2, 2), 0x04: (1, 1), 0x05: (1, 1), 0x06: (2, 2), 0x07: (2, 2),
             0x08: (4, 4), 0x09: (4, 4), 0x0a: (8, 8), 0x0b: (8, 8), 0x0c: (4, 4), 0x0d: (8, 8),
             0x12: (8, 8), 0x0e: (8, 8), 0x0f: (8, 8), 0x10: (8, 8), 0x13: (8, 8), 0x14: (8, 8),
             0x15: (8, 8), 0x16: (8, 8), 0x18: (8, 8), 0x19: (8, 8), 0x1b: (8, 8), 0x1c: (8, 8),
             0x1d: (8, 8), 0x1e: (8, 8)}
T_VALUETYPE, T_CLASS, T_GENERICINST, T_SZARRAY, T_BYREF = 0x11, 0x12, 0x15, 0x1D, 0x10
OBJECT_HEADER = 0x10          # sizeof(Il2CppObject) on 64-bit
ENGINE_OBJECT_SIZE = 0x20    # UnityEngine.Object instance size in this build (m_CachedPtr + m_InstanceID) — verified in code


def _align(v: int, a: int) -> int:
    return (v + a - 1) & ~(a - 1) if a > 1 else v


class Layout:
    """Computes instance/static field offsets for metadata v31.

    Instance layout of a class = parent instance size, then its own instance
    fields in declaration order, each aligned to its natural alignment.
    Validated against ConnectionManager (offlineMode @0x40, conecctingTimeOut
    @0xac, isReconnecting @0xdc) and Constants statics.
    """

    def __init__(self, x: "Xref", engine_object_size: int = ENGINE_OBJECT_SIZE):
        self.x = x
        self.m = x.m
        self.elf = x.elf
        self.engine_object_size = engine_object_size
        self._tcache: Dict[int, Tuple[int, int, str]] = {}
        self._scache: Dict[int, Tuple[int, int]] = {}
        self.field_owner = x._field_owner
        self.td_off = self.m.header.offset("typeDefinitions")
        self.fld_off = self.m.header.offset("fields")
        self.method_off = self.m.header.offset("methods")

    # -- primitives / Il2CppType ------------------------------------------
    def read_type(self, type_index: int) -> Tuple[int, int, int]:
        """Return (data, attrs, tenum) of Il2CppType[type_index]."""
        tp = self.elf.read_u64(self.x.reg.types + 8 * type_index) if self.x.reg.types else None
        if not tp or self.elf.vaddr_to_offset(tp) is None:
            return 0, 0, -1
        data, bf = struct.unpack_from("<QI", self.elf.data, self.elf.vaddr_to_offset(tp))
        return data, bf & 0xFFFF, (bf >> 16) & 0xFF

    def type_size_align(self, type_index: int) -> Tuple[int, int, str]:
        if type_index in self._tcache:
            return self._tcache[type_index]
        data, _attrs, tenum = self.read_type(type_index)
        res: Tuple[int, int, str]
        if tenum in PRIM_SIZE:
            sz, al = PRIM_SIZE[tenum]
            res = (sz, al, self.x.type_name(type_index))
        elif tenum == T_VALUETYPE and data < len(self.m.types):
            sz, al = self.struct_size(data)
            res = (sz, al, self.m.types[data].full_name)
        elif tenum == T_GENERICINST:
            gc = self.elf.read_u64(data)
            tdi = -1
            if gc and self.elf.vaddr_to_offset(gc) is not None:
                tdi = struct.unpack_from("<i", self.elf.data, self.elf.vaddr_to_offset(gc))[0]
            if 0 <= tdi < len(self.m.types) and self.is_value_type(tdi):
                sz, al = self.struct_size(tdi)   # approximation: ignores generic argument sizes
                res = (sz, al, self.m.types[tdi].full_name + "<>")
            else:
                res = (8, 8, self.x.type_name(type_index))
        else:
            res = (8, 8, self.x.type_name(type_index))
        self._tcache[type_index] = res
        return res

    def is_value_type(self, td: int) -> bool:
        bv = struct.unpack_from("<i", self.m.data, self.td_off + td * SIZEOF_TYPE + 8)[0]
        return self.read_type(bv)[2] == T_VALUETYPE

    def is_enum(self, td: int) -> bool:
        t = self.m.types[td]
        bv = struct.unpack_from("<i", self.m.data, self.td_off + td * SIZEOF_TYPE + 8)[0]
        return self.read_type(bv)[2] == 0x55 or (self.is_value_type(td) and t.full_name != "System.Enum"
                                                  and self.parent_name(td) == "System.Enum")

    def parent_name(self, td: int) -> Optional[str]:
        p = self.m.types[td].parent
        if p < 0:
            return None
        return self.x.type_name(p)

    def parent_td(self, td: int) -> Optional[int]:
        p = self.m.types[td].parent
        if p < 0:
            return None
        tds = self.x._byval.get(p)
        return tds[0] if tds else None

    def struct_size(self, td: int) -> Tuple[int, int]:
        if td in self._scache:
            return self._scache[td]
        self._scache[td] = (8, 8)  # guard against cycles
        t = self.m.types[td]
        if self.is_enum(td):
            # enums: size of the single instance field 'value__'
            for f in self.m.type_fields(t):
                data, attrs, tenum = self.read_type(f.type_index)
                if not (attrs & 0x10):
                    sz, al, _ = self.type_size_align(f.type_index)
                    self._scache[td] = (sz, al)
                    return sz, al
            self._scache[td] = (4, 4)
            return 4, 4
        off, maxa = 0, 1
        for f in self.m.type_fields(t):
            data, attrs, tenum = self.read_type(f.type_index)
            if attrs & 0x10:
                continue
            sz, al, _ = self.type_size_align(f.type_index)
            off = _align(off, al)
            off += sz
            maxa = max(maxa, al)
        res = (_align(off, maxa), maxa)
        self._scache[td] = res
        return res

    # -- class layout --------------------------------------------------------
    def instance_base(self, td: int) -> Tuple[int, str]:
        """Instance size of the parent chain (object header or UnityEngine.Object)."""
        chain = []
        cur = td
        while True:
            chain.append(cur)
            p = self.parent_td(cur)
            if p is None or p in chain or p == cur:
                break
            cur = p
        for c in chain:
            if self.m.types[c].full_name == "UnityEngine.Object":
                return self.engine_object_size, "UnityEngine.Object"
        return OBJECT_HEADER, "object"

    def instance_fields(self, td: int) -> List[Tuple[int, str, str, int, int]]:
        """[(field_index, name, type_name, offset, size)] for instance fields of type td."""
        base, _ = self.instance_base(td)
        off = base
        out = []
        t = self.m.types[td]
        for f in self.m.type_fields(t):
            data, attrs, tenum = self.read_type(f.type_index)
            if attrs & 0x10:
                continue
            sz, al, tn = self.type_size_align(f.type_index)
            off = _align(off, al)
            out.append((f.index, f.name, tn, off, sz))
            off += sz
        return out

    def static_fields(self, td: int) -> List[Tuple[int, str, str, int, int]]:
        """[(field_index, name, type_name, offset, size)] for static (non-literal) fields, declaration order."""
        off = 0
        out = []
        t = self.m.types[td]
        for f in self.m.type_fields(t):
            data, attrs, tenum = self.read_type(f.type_index)
            if not (attrs & 0x10) or (attrs & 0x40):
                continue
            sz, al, tn = self.type_size_align(f.type_index)
            off = _align(off, al)
            out.append((f.index, f.name, tn, off, sz))
            off += sz
        return out

    def instance_offset(self, td: int, field_name: str) -> Optional[int]:
        for fi, n, tn, o, sz in self.instance_fields(td):
            if n == field_name:
                return o
        # walk parents
        p = self.parent_td(td)
        if p is not None and p != td:
            return self.instance_offset(p, field_name)
        return None

    def static_offset(self, td: int, field_name: str) -> Optional[int]:
        for fi, n, tn, o, sz in self.static_fields(td):
            if n == field_name:
                return o
        return None


# pickles must reference "xref.*" whether this file runs as a module or as a script
Ref.__module__ = "xref"
MethodXref.__module__ = "xref"


def _capstone():
    try:
        from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise SystemExit("capstone is required for xref: pip install capstone") from exc
    cs = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    cs.detail = False
    return cs


# ---------------------------------------------------------------------------
# registration / modules
# ---------------------------------------------------------------------------

class Registration:
    """Il2CppMetadataRegistration, located by its two ``== typeDefinitionCount`` fields."""

    def __init__(self, elf, type_count: int):
        self.elf = elf
        self.addr: Optional[int] = None
        for s in elf.sections:
            if s.name not in (".data.rel.ro", ".data"):
                continue
            off0 = elf.vaddr_to_offset(s.addr)
            words = struct.unpack_from(f"<{s.size // 8}Q", elf.data, off0)
            for i in range(len(words) - 3):
                if words[i] == type_count and words[i + 2] == type_count:
                    va = s.addr + 8 * i
                    if elf.read_u64(va + 8) and elf.read_u64(va + 0x18):
                        self.addr = va - 0x50
                        break
            if self.addr:
                break
        if not self.addr:
            raise SystemExit("Il2CppMetadataRegistration not found")
        a = self.addr
        self.types_count = elf.read_u64(a + 0x30)
        self.types = elf.read_u64(a + 0x38)
        self.field_offsets_count = elf.read_u64(a + 0x50)
        self.field_offsets = elf.read_u64(a + 0x58)

    def field_offset(self, type_def_index: int, field_i: int) -> Optional[int]:
        """Field offset from the build-time table (may be dummy on v29+)."""
        if not self.field_offsets:
            return None
        tbl = self.elf.read_u64(self.field_offsets + 8 * type_def_index)
        if not tbl or self.elf.vaddr_to_offset(tbl + 4 * field_i) is None:
            return None
        off = self.elf.vaddr_to_offset(tbl + 4 * field_i)
        return struct.unpack_from("<I", self.elf.data, off)[0]


class Modules:
    """All Il2CppCodeGenModules (one per image) + a global address -> method map."""

    def __init__(self, binary: Binary, meta: Metadata):
        self.b = binary
        self.m = meta
        self.elf = binary.elf
        self.names: List[str] = []
        self.first_method_index: List[int] = []
        self.pointers: List[List[int]] = []
        self.addr_map: Dict[int, Tuple[str, str, str]] = {}  # addr -> (module, type, method)
        self.sorted_addrs: List[int] = []
        self._load_all()

    def _load_all(self):
        # find the codeGenModules array by looking for pointers to module structs:
        # a module struct starts with a pointer to a ".dll" name string, count, pointer.
        anchor = self.b.codegen_module("Assembly-CSharp")
        if anchor is None:
            raise SystemExit("Assembly-CSharp module not found")
        anchor_addr = anchor.address
        slot_hits = self.elf.find_ptr_relocated(anchor_addr, sections=(".data.rel.ro", ".data"))
        array_addr = None
        for slot in slot_hits:
            # walk backwards while entries look like module pointers
            start = slot
            while True:
                p = self.elf.read_u64(start - 8)
                if p and self._looks_like_module(p):
                    start -= 8
                else:
                    break
            array_addr = start
            break
        if array_addr is None:
            raise SystemExit("codeGenModules array not found")
        modules = []
        pos = array_addr
        while True:
            p = self.elf.read_u64(pos)
            if not p or not self._looks_like_module(p):
                break
            modules.append(p)
            pos += 8
        self.array_addr = array_addr
        self.module_addrs = modules
        # map modules to images by name
        img_by_name = {img.name: img for img in self.m.images}
        for mod_addr in modules:
            name_va = self.elf.read_u64(mod_addr)
            name = self.elf.read_cstr(name_va) or "?"
            count = self.elf.read_u64(mod_addr + 8)
            ptrs_va = self.elf.read_u64(mod_addr + 16)
            ptrs = [self.elf.read_u64(ptrs_va + 8 * i) for i in range(count)] if count else []
            img = img_by_name.get(name) or img_by_name.get(name.replace(".dll", ""))
            self.names.append(name)
            self.pointers.append(ptrs)
            if img is None:
                self.first_method_index.append(-1)
                continue
            first_method = self._first_method_index(img)
            self.first_method_index.append(first_method if first_method is not None else -1)
            for t in (self.m.types[img.type_start: img.type_start + img.type_count] if first_method is not None else []):
                for mm in self.m.type_methods(t):
                    k = mm.index - first_method
                    if 0 <= k < len(ptrs) and ptrs[k]:
                        self.addr_map[ptrs[k]] = (name, t.full_name, mm.name)
        self.sorted_addrs = sorted(self.addr_map)

    def _looks_like_module(self, p: int) -> bool:
        if self.elf.vaddr_to_offset(p) is None:
            return False
        name_va = self.elf.read_u64(p)
        count = self.elf.read_u64(p + 8)
        if not name_va or count is None or count > 200000:
            return False
        name = self.elf.read_cstr(name_va, 64)
        return bool(name and name.endswith(".dll"))

    def _first_method_index(self, img) -> int:
        types = self.m.types[img.type_start: img.type_start + img.type_count]
        starts = [t.method_start for t in types if t.method_count]
        return min(starts) if starts else None

    def lookup(self, addr: int) -> Optional[Tuple[str, str, str]]:
        return self.addr_map.get(addr)

    def method_size(self, addr: int) -> int:
        i = bisect.bisect_right(self.sorted_addrs, addr)
        nxt = self.sorted_addrs[i] if i < len(self.sorted_addrs) else addr + 0x400
        return min(nxt - addr, 0x10000)

    def module_index(self, name: str) -> Optional[int]:
        for i, n in enumerate(self.names):
            if n == name or n == name + ".dll" or n.replace(".dll", "") == name:
                return i
        return None


# ---------------------------------------------------------------------------
# the database
# ---------------------------------------------------------------------------

class Xref:
    def __init__(self, meta_path: Optional[str] = None, bin_path: Optional[str] = None):
        self.m = Metadata(meta_path) if meta_path else Metadata()
        self.b = Binary(bin_path) if bin_path else Binary()
        self.elf = self.b.elf
        self.reg = Registration(self.elf, len(self.m.types))
        self.mods = Modules(self.b, self.m)
        self.cs = _capstone()
        self._byval: Dict[int, List[int]] = defaultdict(list)
        td_off = self.m.header.offset("typeDefinitions")
        for i in range(len(self.m.types)):
            bv = struct.unpack_from("<i", self.m.data, td_off + i * SIZEOF_TYPE + 8)[0]
            self._byval[bv].append(i)
        self._field_owner: Dict[int, int] = {}
        for t in self.m.types:
            for k in range(t.field_count):
                self._field_owner[t.field_start + k] = t.index
        self._fr_off = self.m.header.offset("fieldRefs")
        self._fr_count = self.m.header.size("fieldRefs") // 8
        self.methods: Dict[str, MethodXref] = {}
        self.by_type: Dict[str, List[MethodXref]] = defaultdict(list)
        self.rev_literal: Dict[str, List[MethodXref]] = defaultdict(list)
        self.rev_type: Dict[str, List[MethodXref]] = defaultdict(list)
        self.rev_field: Dict[str, List[MethodXref]] = defaultdict(list)
        self.rev_call: Dict[str, List[MethodXref]] = defaultdict(list)

    # -- type resolution -------------------------------------------------
    def type_name(self, type_index: int) -> str:
        tds = self._byval.get(type_index)
        if tds:
            return self.m.types[tds[0]].full_name
        tp = self.elf.read_u64(self.reg.types + 8 * type_index) if self.reg.types else None
        if not tp:
            return f"type#{type_index}"
        off = self.elf.vaddr_to_offset(tp)
        if off is None:
            return f"type#{type_index}"
        data, bitfield = struct.unpack_from("<QI", self.elf.data, off)
        tenum = (bitfield >> 16) & 0xFF
        if tenum in (TYPE_CLASS, TYPE_VALUETYPE) or (2 <= tenum <= 0x0E and data < len(self.m.types)):
            return self.m.types[data].full_name if data < len(self.m.types) else f"type#{type_index}"
        if tenum == TYPE_GENERICINST:
            gc = self.elf.read_u64(data)
            if gc:
                goff = self.elf.vaddr_to_offset(gc)
                if goff is not None:
                    tdi = struct.unpack_from("<i", self.elf.data, goff)[0]
                    if 0 <= tdi < len(self.m.types):
                        return self.m.types[tdi].full_name + "<>"
        if tenum == TYPE_SZARRAY:
            return self.type_name_from_ptr(self.elf.read_u64(data)) + "[]"
        if tenum == TYPE_VAR:
            return f"!{data}"
        if tenum == TYPE_MVAR:
            return f"!!{data}"
        return f"type#{type_index}({tenum:#x})"

    def type_name_from_ptr(self, tp: int) -> str:
        if not tp or self.elf.vaddr_to_offset(tp) is None:
            return "?"
        off = self.elf.vaddr_to_offset(tp)
        data, bitfield = struct.unpack_from("<QI", self.elf.data, off)
        tenum = (bitfield >> 16) & 0xFF
        if tenum in (TYPE_CLASS, TYPE_VALUETYPE):
            return self.m.types[data].full_name
        if tenum == TYPE_GENERICINST:
            gc = self.elf.read_u64(data)
            goff = self.elf.vaddr_to_offset(gc) if gc else None
            if goff is not None:
                tdi = struct.unpack_from("<i", self.elf.data, goff)[0]
                return self.m.types[tdi].full_name + "<>"
        if tenum == TYPE_SZARRAY:
            return self.type_name_from_ptr(self.elf.read_u64(data)) + "[]"
        return f"type({tenum:#x})"

    def decode_handle(self, val: int) -> Tuple[str, str]:
        if not (val & 1):
            return "unknown", f"ptr#{val:#x}"
        kind = (val >> 29) & 7
        idx = (val >> 1) & 0x0FFFFFFF
        if kind == 5:
            return "str", self.m.literals[idx] if idx < len(self.m.literals) else f"str#{idx}"
        if kind in (1, 2, 3, 6):
            return HANDLE_KINDS[kind], self.type_name(idx)
        if kind in (4, 7):
            if idx < self._fr_count:
                tdi, fdi = struct.unpack_from("<ii", self.m.data, self._fr_off + 8 * idx)
                owner = self._field_owner.get(fdi)
                tname = self.m.types[owner].full_name if owner is not None else self.type_name(tdi)
                fname = self.m.fields[fdi].name if fdi < len(self.m.fields) else f"field#{fdi}"
                return "field", f"{tname}.{fname}"
            return "field", f"fieldRef#{idx}"
        return "unknown", f"handle#{val:#x}"

    # -- scanning ----------------------------------------------------------
    def scan(self, module: str = "Assembly-CSharp", limit_types: Optional[Iterable[str]] = None) -> List[MethodXref]:
        k = self.mods.module_index(module)
        if k is None:
            raise SystemExit(f"module not found: {module} (have {len(self.mods.names)} modules)")
        name = self.mods.names[k]
        img = next((i for i in self.m.images if i.name == name or i.name == name.replace('.dll', '')), None)
        if img is None:
            raise SystemExit(f"image not found for {name}")
        wanted = set(limit_types) if limit_types else None
        out: List[MethodXref] = []
        for t in self.m.types[img.type_start: img.type_start + img.type_count]:
            if wanted is not None and t.full_name not in wanted:
                continue
            for mm in self.m.type_methods(t):
                x = self._scan_method(name, t.full_name, mm.name, self.mods.first_method_index[k], self.mods.pointers[k], mm.index)
                if x:
                    out.append(x)
        return out

    def _method_info(self, method_index: int):
        off = self.m.header.offset("methods") + method_index * SIZEOF_METHOD
        vals = struct.unpack_from("<I5iI4H", self.m.data, off)
        return {"flags": vals[6], "iflags": vals[7]}

    def _scan_method(self, module: str, type_name: str, method: str, first: int, ptrs: Sequence[int], method_index: int) -> Optional[MethodXref]:
        key = f"{type_name}.{method}"
        if key in self.methods:
            return self.methods[key]
        k = method_index - first
        if not (0 <= k < len(ptrs)) or not ptrs[k]:
            return None
        addr = ptrs[k]
        size = self.mods.method_size(addr)
        x = MethodXref(module, type_name, method, addr, size)
        off = self.elf.vaddr_to_offset(addr)
        if off is None:
            return None
        code = self.elf.data[off: off + size]
        is_static = bool(self._method_info(method_index)["flags"] & 0x10)
        w = Walker(self, x, is_static)
        w.run(code, addr)
        self._index(x)
        return x

    def field_at_instance(self, type_name: str, offset: int) -> Optional[str]:
        """Name of the instance field of ``type_name`` (or a parent) covering ``offset``."""
        L = self.layout()
        td = self._td_of(type_name)
        while td is not None:
            base = L.instance_base(td)[0]
            for fi, n, tn, o, sz in L.instance_fields(td):
                if o <= offset < o + max(sz, 1):
                    return f"{self.m.types[td].full_name}.{n}"
            if offset < base:
                return None
            td = L.parent_td(td)
            if td is not None and td == self._td_of(type_name):
                return None
        return None

    def field_at_static(self, class_name: str, offset: int) -> Optional[str]:
        L = self.layout()
        td = self._td_of(class_name)
        if td is None:
            return None
        for fi, n, tn, o, sz in L.static_fields(td):
            if o <= offset < o + max(sz, 1):
                return f"{class_name}.{n}"
        return None

    def _td_of(self, name: str) -> Optional[int]:
        if not hasattr(self, "_td_cache"):
            self._td_cache: Dict[str, Optional[int]] = {}
        if name not in self._td_cache:
            hit = self.m.find_type(name)
            self._td_cache[name] = hit[0].index if hit else None
        return self._td_cache[name]

    def layout(self) -> "Layout":
        if not hasattr(self, "_layout"):
            self._layout = Layout(self)
        return self._layout

    def is_static_method(self, type_name: str, method: str) -> bool:
        hit = self.m.find_type(type_name)
        if not hit:
            return False
        for mm in self.m.type_methods(hit[0]):
            if mm.name == method:
                return bool(self._method_info(mm.index)["flags"] & 0x10)
        return False

    def label(self, addr: int) -> str:
        hit = self.mods.lookup(addr)
        if hit:
            return f"{hit[1]}.{hit[2]}"
        if addr in RUNTIME_HINTS:
            return RUNTIME_HINTS[addr]
        return f"sub_{addr:x}"

    def _index(self, x: MethodXref):
        self.methods[x.full] = x
        self.by_type[x.type_name].append(x)
        for r in x.refs:
            if r.kind == "str":
                self.rev_literal[r.name].append(x)
            elif r.kind in ("type", "class"):
                self.rev_type[r.name].append(x)
            elif r.kind == "field":
                self.rev_field[r.name].append(x)
        for _, lab in x.calls:
            self.rev_call[lab].append(x)

    def build(self, module: str = "Assembly-CSharp", progress: bool = False, cache: bool = True) -> List[MethodXref]:
        import pickle
        cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "work", f"xref-{module.replace('.', '_')}.pkl")
        if cache and os.path.exists(cache_path) and os.path.getmtime(cache_path) > os.path.getmtime(self.b.path):
            with open(cache_path, "rb") as fh:
                saved = pickle.load(fh)
            self.methods = saved["methods"]
            self.by_type = saved["by_type"]
            self.rev_literal = saved["rev_literal"]
            self.rev_type = saved["rev_type"]
            self.rev_field = saved["rev_field"]
            self.rev_call = saved["rev_call"]
            return list(self.methods.values())
        k = self.mods.module_index(module)
        name = self.mods.names[k]
        img = next(i for i in self.m.images if i.name == name or i.name == name.replace(".dll", ""))
        out = []
        for n, t in enumerate(self.m.types[img.type_start: img.type_start + img.type_count]):
            for mm in self.m.type_methods(t):
                x = self._scan_method(name, t.full_name, mm.name, self.mods.first_method_index[k], self.mods.pointers[k], mm.index)
                if x:
                    out.append(x)
            if progress and n % 200 == 0:
                print(f"  ... {n} types", file=sys.stderr)
        if cache:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "wb") as fh:
                pickle.dump({"methods": self.methods, "by_type": self.by_type, "rev_literal": self.rev_literal,
                             "rev_type": self.rev_type, "rev_field": self.rev_field, "rev_call": self.rev_call}, fh)
        return out


# ---------------------------------------------------------------------------
# instruction walker: resolves metadata slots, calls and field accesses
# ---------------------------------------------------------------------------

CALLER_SAVED = {f"x{i}" for i in range(18)}
LOADS = ("ldr", "ldur", "ldrb", "ldrh", "ldrsw", "ldrsb", "ldrsh")
STORES = ("str", "stur", "strb", "strh")


class Walker:
    """One pass over a method body.

    Tracks what registers hold (``this`` pointer, class pointer, ``static_fields``
    block, metadata slot) so that memory operands can be turned into
    ``Type.field`` references instead of bare offsets.
    """

    def __init__(self, x: "Xref", mx: MethodXref, is_static: bool, collect_notes: bool = False):
        self.x, self.mx, self.is_static = x, mx, is_static
        self.regs_page: Dict[str, int] = {}
        self.role: Dict[str, tuple] = {} if is_static else {"x0": ("this", mx.type_name)}
        self.seen_refs = set()
        self.notes: Dict[int, str] = {}  # insn address -> annotation (for disasm)
        self.collect_notes = collect_notes

    def note(self, addr: int, text: str) -> None:
        if self.collect_notes:
            self.notes[addr] = text

    def _field_ref(self, full: str, got: int, raw: int, access: str = "") -> None:
        key = ("field", full)
        for r in self.mx.refs:
            if r.kind == "field" and r.name == full:
                if access and access not in r.access:
                    r.access += access
                return
        self.seen_refs.add(key)
        self.mx.refs.append(Ref("field", full, raw, got, access))

    def _slot_ref(self, kind: str, name: str, got: int, raw: int) -> None:
        key = (kind, name, got)
        if key not in self.seen_refs:
            self.seen_refs.add(key)
            self.mx.refs.append(Ref(kind, name, raw, got))

    def run(self, code: bytes, addr: int, max_insns: Optional[int] = None) -> None:
        from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM  # type: ignore
        cs = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
        for n, insn in enumerate(cs.disasm(code, addr)):
            if max_insns is not None and n >= max_insns:
                break
            self.step(insn)

    def step(self, insn) -> None:  # noqa: C901 - a small instruction interpreter
        mn, ops, addr = insn.mnemonic, insn.op_str, insn.address
        parts = [p.strip() for p in ops.split(",")]
        dst = parts[0] if parts else ""
        width = 4 if dst.startswith("w") or dst.startswith("s") else 8
        note = ""

        if mn == "adrp":
            self.regs_page[dst] = int(parts[1].lstrip("#"), 0)
            self.role.pop(dst, None)
        elif mn == "bl":
            tgt = int(ops.lstrip("#"), 0)
            lab = self.x.label(tgt)
            self.mx.calls.append((tgt, lab))
            note = "; " + lab
            for r in CALLER_SAVED:
                self.regs_page.pop(r, None)
                self.role.pop(r, None)
        elif mn in ("b", "br", "ret", "cbz", "cbnz", "tbz", "tbnz", "cmp", "ccmp", "tst", "nop", "dmb", "prfm"):
            pass
        elif mn == "mov" and len(parts) == 2 and parts[1] in self.role:
            self.role[dst] = self.role[parts[1]]
            self.regs_page.pop(dst, None)
        elif mn == "add" and len(parts) == 3 and parts[1] in self.role and parts[2].startswith("#"):
            imm = int(parts[2].lstrip("#"), 0)
            role = self.role[parts[1]]
            if role[0] == "static":
                self.role[dst] = ("staticoff", role[1], imm)
                note = f"; &{self.x.field_at_static(role[1], imm) or role[1] + '+' + hex(imm)}"
            elif role[0] == "staticoff":
                self.role[dst] = ("staticoff", role[1], role[2] + imm)
            self.regs_page.pop(dst, None)
        elif (mn in LOADS or mn in STORES) and "[" in ops:
            mm = MEM_RE.match(ops)
            if not mm:
                return
            base, imm, index = mm.group(1), mm.group(2), mm.group(3)
            imm_v = int(imm, 0) if imm else 0
            role = self.role.get(base)
            if base in self.regs_page and not index:
                ga = self.regs_page[base] + imm_v
                slot = self.x.elf.read_u64(ga) if self.x.elf.vaddr_to_offset(ga) is not None else None
                if slot and self.x.elf.vaddr_to_offset(slot) is not None:
                    kind, nm = self.x.decode_handle(self.x.elf.read_u64(slot))
                    if mn == "ldr" and width == 8:
                        self.role[dst] = ("slot", kind, nm)
                    self.regs_page.pop(dst, None)
                    self._slot_ref(kind, nm, ga, self.x.elf.read_u64(slot))
                    note = f"; &{nm!r}" if kind == "str" else f"; &{nm}"
                return
            if role is None or index:
                if base != "sp" and not index and 0 <= imm_v < 0x4000 and mn in LOADS + STORES:
                    self.mx.mem[(width if mn in ("ldr", "ldur", "str", "stur") else 1, imm_v)] += 1
                if mn in LOADS:
                    self.role.pop(dst, None)
                    self.regs_page.pop(dst, None)
                return
            kind = role[0]
            if kind == "slot" and imm_v == 0 and mn == "ldr" and width == 8:
                self.role[dst] = ("val", role[2])
                note = f"; load {role[2]!r}" if role[1] == "str" else f"; load {role[2]}"
                self.regs_page.pop(dst, None)
            elif kind == "val" and imm_v == 0xB8 and mn == "ldr" and width == 8:
                self.role[dst] = ("static", role[1])
                note = f"; {role[1]}.static_fields"
                self.regs_page.pop(dst, None)
            elif kind in ("static", "staticoff", "this"):
                cls = role[1]
                off = imm_v if kind != "staticoff" else role[2] + imm_v
                full = self.x.field_at_static(cls, off) if kind != "this" else self.x.field_at_instance(cls, off)
                if full:
                    self._field_ref(full, 0, off, "w" if mn in STORES else "r")
                    note = f"; {'&' if mn == 'add' else ''}{full}"
                elif kind == "this" and mn in LOADS + STORES:
                    self.mx.mem[(width if mn in ("ldr", "ldur", "str", "stur") else 1, off)] += 1
                if mn == "add":
                    self.role[dst] = ("staticoff", cls, off) if kind != "this" else ("thisoff", cls, off)
                if mn in LOADS:
                    self.role.pop(dst, None)
                    self.regs_page.pop(dst, None)
            elif kind == "thisoff":
                full = self.x.field_at_instance(role[1], role[2] + imm_v)
                if full:
                    self._field_ref(full, 0, role[2] + imm_v, "&" if mn == "add" else ("w" if mn in STORES else "r"))
                    note = f"; &{full}"
                if mn in LOADS:
                    self.role.pop(dst, None)
                    self.regs_page.pop(dst, None)
            else:
                if mn in LOADS:
                    self.role.pop(dst, None)
                    self.regs_page.pop(dst, None)
        else:
            # any other instruction: invalidate registers it (probably) writes
            if mn not in ("stp",) and dst and (dst.startswith("x") or dst.startswith("w")):
                if not any(dst == p for p in parts[1:]):
                    self.role.pop("x" + dst[1:] if dst.startswith("w") else dst, None)
                    self.role.pop(dst, None)
                    self.regs_page.pop(dst, None)
                    self.regs_page.pop("x" + dst[1:] if dst.startswith("w") else dst, None)
        if note:
            self.note(addr, note)


def annotated_disasm(x: "Xref", mx: MethodXref, max_insns: int = 400) -> List[str]:
    """Disassemble with slot names, call targets and field names inline."""
    from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM  # type: ignore
    cs = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    off = x.elf.vaddr_to_offset(mx.addr)
    code = x.elf.data[off: off + mx.size]
    mx.refs.clear()
    mx.calls.clear()
    mx.mem.clear()
    is_static = x.is_static_method(mx.type_name, mx.method)
    w = Walker(x, mx, is_static, collect_notes=True)
    out: List[str] = []
    for n, insn in enumerate(cs.disasm(code, mx.addr)):
        if n >= max_insns:
            out.append("  ... (truncated)")
            break
        w.step(insn)
        out.append(f"  {insn.address:#011x}  {insn.mnemonic:<8s} {insn.op_str:<44s} {w.notes.get(insn.address, '')}")
    return out


RUNTIME_HINTS = {
    0x11F36A8: "il2cpp_codegen_initialize_runtime_metadata",
    0x11F3824: "il2cpp_runtime_class_init",
    0x270FF70: "SceneManager.LoadScene?",
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _find_type(x: Xref, name: str) -> List:
    return x.m.find_type(name) or x.m.search_types(name)


def _print_method(x: Xref, mx: MethodXref, offsets: bool = True) -> None:
    print(f"\n== {mx.full} @ {mx.addr:#x} ({mx.size} bytes)")
    if mx.refs:
        kinds = defaultdict(list)
        for r in mx.refs:
            kinds[r.kind].append(r.name)
        for k, v in kinds.items():
            print(f"  {k:5s}: " + ", ".join(repr(s) if k == "str" else s for s in dict.fromkeys(v)))
    calls = [lab for _, lab in mx.calls]
    ext = [c for c in calls if not c.startswith("il2cpp_codegen")]
    if ext:
        print("  calls: " + ", ".join(dict.fromkeys(ext)))
    if offsets and mx.mem:
        items = sorted(mx.mem.items(), key=lambda kv: (kv[0][1], kv[0][0]))
        print("  mem  : " + ", ".join(f"{w}B@{o:#x}" if w != 1 else f"b@{o:#x}" for (w, o), c in items if 0x10 <= o < 0x800))


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("method", help="show refs/calls/offsets of one method")
    p.add_argument("type"); p.add_argument("method")
    p = sub.add_parser("type", help="all methods of a type")
    p.add_argument("type"); p.add_argument("--no-mem", action="store_true")
    p = sub.add_parser("uses", help="who references an item")
    p.add_argument("--literal"); p.add_argument("--type"); p.add_argument("--field"); p.add_argument("--call")
    p.add_argument("--writes", action="store_true", help="only methods that store to the field")
    p.add_argument("--module", default=None, help="restrict to one module (default: all scanned)")
    p = sub.add_parser("callers", help="who calls Type.method")
    p.add_argument("target")
    p = sub.add_parser("layout", help="computed field offsets of a type")
    p.add_argument("type"); p.add_argument("--static", action="store_true")
    p = sub.add_parser("disasm", help="annotated disassembly of one method")
    p.add_argument("type"); p.add_argument("method"); p.add_argument("--max", type=int, default=400)
    p = sub.add_parser("find", help="search type/method/field names")
    p.add_argument("needle")
    p.add_argument("--module", default=None)
    args = ap.parse_args(argv)

    x = Xref()
    if args.cmd == "find":
        for t in x.m.search_types(args.needle):
            print(f"type   #{t.index:<6d} {t.full_name}  ({t.method_count} methods)")
        for t in x.m.types:
            for mm in x.m.type_methods(t):
                if args.needle.lower() in mm.name.lower():
                    print(f"method {t.full_name}.{mm.name}")
            for f in x.m.type_fields(t):
                if args.needle.lower() in f.name.lower():
                    print(f"field  {t.full_name}.{f.name}")
        return 0
    if args.cmd in ("method", "type"):
        types = _find_type(x, args.type)
        if not types:
            raise SystemExit("type not found")
        for t in types:
            if args.cmd == "method":
                for mm in x.m.type_methods(t):
                    if mm.name == args.method:
                        mx = x._scan_method("Assembly-CSharp", t.full_name, mm.name, x.mods.first_method_index[x.mods.module_index("Assembly-CSharp")], x.mods.pointers[x.mods.module_index("Assembly-CSharp")], mm.index)
                        if mx:
                            _print_method(x, mx, not args.no_mem if hasattr(args, "no_mem") else True)
            else:
                for mx in x.scan(module="Assembly-CSharp", limit_types={t.full_name}):
                    _print_method(x, mx, not args.no_mem)
        return 0
    if args.cmd == "layout":
        L = Layout(x)
        for t in _find_type(x, args.type):
            rows = L.static_fields(t.index) if args.static else L.instance_fields(t.index)
            base = 0 if args.static else L.instance_base(t.index)[0]
            print(f"== {t.full_name} (#{t.index}) {'static' if args.static else 'instance'} base={base:#x}")
            for fi, n, tn, o, sz in rows:
                print(f"  +{o:#06x}  {n:36s} {tn}  (size {sz})")
        return 0
    if args.cmd == "disasm":
        types = _find_type(x, args.type)
        if not types:
            raise SystemExit("type not found")
        k = x.mods.module_index("Assembly-CSharp")
        for t in types:
            for mm in x.m.type_methods(t):
                if mm.name == args.method:
                    mx = x._scan_method("Assembly-CSharp", t.full_name, mm.name, x.mods.first_method_index[k], x.mods.pointers[k], mm.index)
                    for line in annotated_disasm(x, mx, args.max):
                        print(line)
        return 0
    # uses / callers need the whole module scanned
    module = getattr(args, "module", None) or "Assembly-CSharp"
    x.build(module, progress=True)
    if args.cmd == "uses":
        if args.literal:
            hits = x.rev_literal.get(args.literal, [])
        elif args.type:
            hits = x.rev_type.get(args.type, [])
        elif args.field:
            hits = x.rev_field.get(args.field, [])
        elif args.call:
            hits = x.rev_call.get(args.call, [])
        else:
            raise SystemExit("give one of --literal/--type/--field/--call")
        if args.writes:
            hits = [h for h in hits if any(r.kind == "field" and r.name == args.field and "w" in r.access for r in h.refs)]
        print(f"{len(hits)} method(s):")
        for h in hits:
            acc = "".join(sorted({a for r in h.refs if r.kind == "field" and r.name == args.field for a in r.access})) if args.field else ""
            print(f"  {h.full} @ {h.addr:#x}" + (f"  [{acc}]" if acc else ""))
    elif args.cmd == "callers":
        hits = x.rev_call.get(args.target, [])
        print(f"{len(hits)} caller(s):")
        for h in hits:
            print(f"  {h.full} @ {h.addr:#x}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
