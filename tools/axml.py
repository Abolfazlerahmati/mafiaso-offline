#!/usr/bin/env python3
"""
axml.py — minimal binary AndroidManifest.xml (AXML) editor.

Only what this project needs: flip a boolean attribute of a named tag, e.g.
``android:isSplitRequired`` on ``<application>``, so that a base APK merged
with its native libs installs as a single standalone APK.

The parser walks the chunk list and resolves string-pool indices itself, so it
does not depend on androguard's writing support (which does not exist).
"""

from __future__ import annotations

import struct
from typing import Callable, Dict, List, Optional, Tuple

RES_STRING_POOL_TYPE = 0x0001
RES_XML_START_ELEMENT_TYPE = 0x0102
TYPE_INT_BOOLEAN = 0x12


def _string_pool_reader(data: bytes, chunk_start: int) -> Callable[[int], str]:
    ctype, hsize, csize = struct.unpack_from("<HHI", data, chunk_start)
    if ctype != RES_STRING_POOL_TYPE:
        raise ValueError(f"not a string pool at {chunk_start:#x}")
    string_count, style_count, flags, strings_start, _styles_start = struct.unpack_from(
        "<5I", data, chunk_start + 8
    )
    offsets = struct.unpack_from(f"<{string_count}I", data, chunk_start + 28)
    utf8 = bool(flags & 0x100)

    def get(index: int) -> str:
        if index == 0xFFFFFFFF:
            return ""
        off = chunk_start + strings_start + offsets[index]
        if utf8:
            n = data[off]
            off += 1
            if n & 0x80:
                n = ((n & 0x7F) << 8) | data[off]
                off += 1
            m = data[off]
            off += 1
            if m & 0x80:
                m = ((m & 0x7F) << 8) | data[off]
                off += 1
            return data[off : off + m].decode("utf-8", "replace")
        n = struct.unpack_from("<H", data, off)[0]
        off += 2
        if n & 0x8000:
            n = ((n & 0x7FFF) << 16) | struct.unpack_from("<H", data, off)[0]
            off += 2
        return data[off : off + 2 * n].decode("utf-16-le", "replace")

    return get


def iter_chunks(data: bytes):
    """Yield (offset, type, header_size, size) for every chunk in the file."""
    pos = 8  # skip the top-level ResChunk_header of the XML tree
    while pos + 8 <= len(data):
        ctype, hsize, csize = struct.unpack_from("<HHI", data, pos)
        if csize < 8:
            break
        yield pos, ctype, hsize, csize
        pos += csize


def find_string_pool(data: bytes) -> int:
    for pos, ctype, hsize, csize in iter_chunks(data):
        if ctype == RES_STRING_POOL_TYPE:
            return pos
    raise ValueError("string pool not found")


def _iter_start_tags(data: bytes, get_string: Callable[[int], str]):
    for pos, ctype, hsize, csize in iter_chunks(data):
        if ctype != RES_XML_START_ELEMENT_TYPE:
            continue
        ext = pos + hsize
        _ns, name = struct.unpack_from("<II", data, ext)
        attribute_start, attribute_size, attribute_count = struct.unpack_from("<HHH", data, ext + 8)
        attr_base = ext + attribute_start
        yield pos, get_string(name), attr_base, attribute_size, attribute_count


def set_bool_attribute(data: bytes, tag: str, attr: str, value: bool) -> Tuple[bytes, int]:
    """Return a copy of ``data`` with ``tag/attr`` set to ``value`` and the hit count."""
    buf = bytearray(data)
    get_string = _string_pool_reader(data, find_string_pool(data))
    hits = 0
    for _pos, name, attr_base, attribute_size, attribute_count in _iter_start_tags(data, get_string):
        if name != tag:
            continue
        for i in range(attribute_count):
            a = attr_base + i * attribute_size
            _ans, aname, _araw = struct.unpack_from("<III", data, a)
            if get_string(aname) != attr:
                continue
            struct.pack_into("<HBBI", buf, a + 12, 8, 0, TYPE_INT_BOOLEAN, 1 if value else 0)
            hits += 1
    return bytes(buf), hits


def get_bool_attribute(data: bytes, tag: str, attr: str) -> Optional[bool]:
    get_string = _string_pool_reader(data, find_string_pool(data))
    for _pos, name, attr_base, attribute_size, attribute_count in _iter_start_tags(data, get_string):
        if name != tag:
            continue
        for i in range(attribute_count):
            a = attr_base + i * attribute_size
            _ans, aname, _araw = struct.unpack_from("<III", data, a)
            if get_string(aname) == attr:
                _vsize, _res0, dtype, vdata = struct.unpack_from("<HBBI", data, a + 12)
                return bool(vdata) if dtype == TYPE_INT_BOOLEAN else None
    return None
