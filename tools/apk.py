#!/usr/bin/env python3
"""
apk.py — rebuild, align and sign an Android APK without the Android SDK.

The sandbox cannot reach Google's servers, so neither ``zipalign`` nor
``apksigner`` are available. This module implements the parts we need:

* :class:`ApkBuilder` — copy/replace/drop ZIP entries while keeping the
  original entry order and compression, with 4-byte alignment for stored
  entries and ``resources.arsc``.
* :func:`sign` — JAR (v1) + APK Signature Scheme v2 (+ v3) using a self-signed
  RSA key.
* :func:`generate_signing_key` / :func:`ensure_signing_key` — create the
  self-signed key pair.
* :func:`verify` — re-read the result with androguard.

Dependencies: the ``cryptography`` package (required) and the ``openssl`` CLI
(optional — used for the v1 PKCS#7 blob when present, with a pure
``cryptography`` fallback so Windows machines without OpenSSL work too).

Usage::

    python tools/apk.py rebuild --in base.apk --replace assets/x=y --out out.apk
    python tools/apk.py sign --in out.apk --out signed.apk --key key.pem --cert cert.pem
    python tools/apk.py verify --in signed.apk
"""

from __future__ import annotations

import argparse
import base64
import datetime
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zipfile
import zlib
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

APK_SIG_BLOCK_MAGIC = b"APK Sig Block 42"
V2_BLOCK_ID = 0x7109871A
V3_BLOCK_ID = 0xF05368C0
CHUNK_SIZE = 1024 * 1024

# Signature algorithm IDs - source.android.com/docs/security/features/apksigning/v2
#   0x0101 RSASSA-PSS   with SHA2-256, MGF1 SHA2-256, 32-byte salt
#   0x0102 RSASSA-PSS   with SHA2-512, MGF1 SHA2-512, 64-byte salt
#   0x0103 RSASSA-PKCS1-v1_5 with SHA2-256   (deterministic - what we sign with)
#   0x0104 RSASSA-PKCS1-v1_5 with SHA2-512
#   0x0201/0x0202 ECDSA, 0x0301 DSA
ALGO_RSA_PSS_SHA256 = 0x0101
ALGO_RSA_PSS_SHA512 = 0x0102
ALGO_RSA_PKCS1_SHA256 = 0x0103
ALGO_RSA_PKCS1_SHA512 = 0x0104


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _u16(v: int) -> bytes:
    return struct.pack("<H", v)


def _u32(v: int) -> bytes:
    return struct.pack("<I", v)


def _u64(v: int) -> bytes:
    return struct.pack("<Q", v)


def _len_prefixed(data: bytes) -> bytes:
    """Length prefix used *inside* the signature block: uint32 (not uint64)."""
    return _u32(len(data)) + data


def _content_digest(sections: Sequence[bytes], hash_name: str = "sha256") -> bytes:
    """Android's chunked content digest over the integrity-protected sections.

    The APK consists of three protected sections - ZIP entry contents, ZIP
    Central Directory and ZIP End of Central Directory - and *each section is
    chunked on its own* into 1 MiB pieces; the chunk counter does not carry
    over a section boundary. Chunking the concatenation instead produces a
    different digest, which Android rejects with "app not installed".

    Per chunk: H(0xa5 || u32(len(chunk)) || chunk)
    Overall:  H(0x5a || u32(chunk count) || concat(chunk digests))
    """
    digests = []
    for section in sections:
        for start in range(0, len(section), CHUNK_SIZE):
            chunk = section[start : start + CHUNK_SIZE]
            digests.append(hashlib.new(hash_name, b"\xa5" + _u32(len(chunk)) + chunk).digest())
    return hashlib.new(hash_name, b"\x5a" + _u32(len(digests)) + b"".join(digests)).digest()


# ---------------------------------------------------------------------------
# rebuild + align
# ---------------------------------------------------------------------------


class ApkBuilder:
    """Copy an APK, replacing or dropping entries, and align stored data."""

    def __init__(self, src: str):
        self.src = src
        self.replacements: Dict[str, bytes] = {}
        self.drops: set = set()
        self.additions: Dict[str, bytes] = {}
        self._zin = zipfile.ZipFile(src)

    def replace(self, name: str, data: bytes) -> "ApkBuilder":
        self.replacements[name] = data
        return self

    def add(self, name: str, data: bytes) -> "ApkBuilder":
        self.additions[name] = data
        return self

    def drop(self, name: str) -> "ApkBuilder":
        self.drops.add(name)
        return self

    def build(self, out_path: str) -> None:
        zin = self._zin
        entries: List[Tuple[str, int, bytes]] = []  # name, method, payload
        for info in zin.infolist():
            if info.filename in self.drops:
                continue
            if info.filename.startswith("META-INF/"):
                continue  # signatures are regenerated
            method = zipfile.ZIP_DEFLATED if info.compress_type == zipfile.ZIP_DEFLATED else zipfile.ZIP_STORED
            if info.filename in self.replacements:
                payload = self.replacements[info.filename]
            else:
                payload = zin.read(info.filename)
            entries.append((info.filename, method, payload))
        for name, payload in self.additions.items():
            entries.append((name, zipfile.ZIP_DEFLATED, payload))

        with open(out_path, "wb") as fh:
            offsets: Dict[str, int] = {}
            crcs: Dict[str, Tuple[int, int, int]] = {}
            for name, method, payload in entries:
                # Android requires resources.arsc to be stored uncompressed.
                if name == "resources.arsc":
                    method = zipfile.ZIP_STORED
                if method == zipfile.ZIP_DEFLATED:
                    # ZIP uses raw DEFLATE (no zlib header/trailer)
                    co = zlib.compressobj(6, zlib.DEFLATED, -15)
                    data = co.compress(payload) + co.flush()
                else:
                    data = payload
                crc = zlib.crc32(payload) & 0xFFFFFFFF
                offset = fh.tell()
                name_bytes = name.encode("utf-8")
                # pad the local header so that the data starts 4-byte aligned
                rem = (offset + 30 + len(name_bytes)) % 4
                extra = b""
                if rem:
                    pad = 4 - rem
                    if pad < 4:
                        pad += 4
                    extra = struct.pack("<HH", 0xD935, pad) + b"\0" * pad
                flags = 0x0800  # UTF-8 names
                header = (
                    b"PK\x03\x04"
                    + _u16(20)  # version needed
                    + _u16(flags)
                    + _u16(method)
                    + _u16(0)  # time
                    + _u16(0x21)  # date (1980-01-01)
                    + _u32(crc)
                    + _u32(len(data))
                    + _u32(len(payload))
                    + _u16(len(name_bytes))
                    + _u16(len(extra))
                    + name_bytes
                    + extra
                )
                fh.write(header)
                fh.write(data)
                offsets[name] = offset
                crcs[name] = (crc, len(data), len(payload))

            cd_start = fh.tell()
            for name, method, payload in entries:
                crc, csize, usize = crcs[name]
                name_bytes = name.encode("utf-8")
                extra_cd = b""
                fh.write(
                    b"PK\x01\x02"
                    + _u16(20)  # version made by
                    + _u16(20)  # version needed
                    + _u16(0x0800)
                    + _u16(method)
                    + _u16(0)
                    + _u16(0x21)
                    + _u32(crc)
                    + _u32(csize)
                    + _u32(usize)
                    + _u16(len(name_bytes))
                    + _u16(len(extra_cd))
                    + _u16(0)  # comment length
                    + _u16(0)  # disk number
                    + _u16(0)  # internal attrs
                    + _u32(0)  # external attrs
                    + _u32(offsets[name])
                    + name_bytes
                    + extra_cd
                )
            cd_size = fh.tell() - cd_start
            fh.write(
                b"PK\x05\x06"
                + _u16(0)
                + _u16(0)
                + _u16(len(entries))
                + _u16(len(entries))
                + _u32(cd_size)
                + _u32(cd_start)
                + _u16(0)
            )
        self._zin.close()


# ---------------------------------------------------------------------------
# signing
# ---------------------------------------------------------------------------


def _run(cmd: Sequence[str]) -> bytes:
    return subprocess.run(cmd, check=True, capture_output=True).stdout


def _jar_manifest(entries: Sequence[Tuple[str, bytes]]) -> bytes:
    lines = ["Manifest-Version: 1.0", "Created-By: mafiaso-offline tools/apk.py", ""]
    for name, payload in entries:
        digest = base64.b64encode(hashlib.sha256(payload).digest()).decode()
        lines.append(f"Name: {name}")
        lines.append(f"SHA-256-Digest: {digest}")
        lines.append("")
    return ("\r\n".join(lines) + "\r\n").encode()


def _jar_sf(manifest: bytes) -> bytes:
    """CERT.SF: one digest per manifest section."""
    sections = []
    for block in manifest.split(b"\r\n\r\n"):
        block = block.strip(b"\r\n")
        if not block:
            continue
        sections.append(block)
    # X-Android-APK-Signed tells Android's v1 verifier that this APK is also
    # signed with the v2 scheme, so stripping the v2 block is detected.
    lines = [
        "Signature-Version: 1.0",
        "Created-By: mafiaso-offline tools/apk.py",
        "X-Android-APK-Signed: 2",
        "",
    ]
    for block in sections:
        if not block.startswith(b"Name: "):
            continue  # the manifest main section has no per-file digest
        digest = base64.b64encode(hashlib.sha256(block + b"\r\n").digest()).decode()
        # first line of the section holds "Name: ..."
        name_line = block.split(b"\r\n")[0].decode()
        lines.append(name_line)
        lines.append(f"SHA-256-Digest: {digest}")
        lines.append("")
    return ("\r\n".join(lines) + "\r\n").encode()


def openssl_available() -> bool:
    """Whether the ``openssl`` CLI should be used for the v1 PKCS#7 blob.

    It is optional: :func:`_pkcs7_sign_cryptography` produces the same structure
    without it. Set ``MAFIASO_NO_OPENSSL=1`` to force the fallback (used by the
    test-suite to exercise the Windows-without-OpenSSL path).
    """
    if os.environ.get("MAFIASO_NO_OPENSSL"):
        return False
    return shutil.which("openssl") is not None


def _pkcs7_sign(data: bytes, key_pem: str, cert_pem: str) -> bytes:
    """Return a DER PKCS#7 ``SignedData`` over ``data`` (``META-INF/*.RSA``)."""
    if openssl_available():
        return _pkcs7_sign_openssl(data, key_pem, cert_pem)
    return _pkcs7_sign_cryptography(data, key_pem, cert_pem)


def _pkcs7_sign_openssl(data: bytes, key_pem: str, cert_pem: str) -> bytes:
    with tempfile.TemporaryDirectory() as td:
        sf = os.path.join(td, "CERT.SF")
        out = os.path.join(td, "CERT.RSA")
        with open(sf, "wb") as fh:
            fh.write(data)
        _run(
            [
                "openssl", "smime", "-sign", "-binary", "-noattr",
                "-outform", "DER", "-in", sf,
                "-signer", cert_pem, "-inkey", key_pem, "-out", out,
            ]
        )
        with open(out, "rb") as fh:
            return fh.read()


def _pkcs7_sign_cryptography(data: bytes, key_pem: str, cert_pem: str) -> bytes:
    """Same as :func:`_pkcs7_sign_openssl` (``-noattr``, content embedded) but
    using only the ``cryptography`` package."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.serialization import pkcs7

    key = _load_key(key_pem)
    with open(cert_pem, "rb") as fh:
        cert = x509.load_pem_x509_certificate(fh.read())
    return (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(data)
        .add_signer(cert, key, hashes.SHA256())
        .sign(
            serialization.Encoding.DER,
            [
                pkcs7.PKCS7Options.Binary,
                # NoAttributes == direct signature over the content, no
                # authenticated attributes and no S/MIME capabilities
                # (equivalent to ``openssl smime -sign -noattr``).
                pkcs7.PKCS7Options.NoAttributes,
            ],
        )
    )


def _load_key(key_pem: str):
    from cryptography.hazmat.primitives import serialization
    with open(key_pem, "rb") as fh:
        return serialization.load_pem_private_key(fh.read(), password=None)


def generate_signing_key(key_path: str, cert_path: str, days: int = 3650) -> None:
    """Create a self-signed RSA-2048 key (PKCS#8 PEM) and certificate.

    Android only needs a consistent signer for updates — the identity is
    arbitrary, so a personal key is generated on the builder's machine and
    never shipped. Keep it: every future build must be signed with the same
    key to install over the previous one.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    os.makedirs(os.path.dirname(os.path.abspath(key_path)), exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name(
        [
            x509.NameAttribute(x509.NameOID.ORGANIZATION_NAME, "Personal Build"),
            x509.NameAttribute(x509.NameOID.COMMON_NAME, "mafiaso-offline"),
        ]
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=days))
        .sign(key, hashes.SHA256())
    )
    with open(key_path, "wb") as fh:
        fh.write(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
    with open(cert_path, "wb") as fh:
        fh.write(cert.public_bytes(serialization.Encoding.PEM))
    try:
        os.chmod(key_path, 0o600)
    except OSError:  # e.g. Windows — the ACL is inherited from the folder
        pass


def ensure_signing_key(key_path: str, cert_path: str, days: int = 3650) -> bool:
    """Generate the key pair if missing. Returns True when it was created."""
    if os.path.exists(key_path) and os.path.exists(cert_path):
        return False
    generate_signing_key(key_path, cert_path, days)
    return True


def _sequence_field(entry: bytes) -> bytes:
    """Wrap one entry in the double length prefix Android expects.

    Both the digests and the signatures field are
    ``len-prefixed(len-prefixed(u32 algorithm id + len-prefixed payload))``:
    one prefix for the field, one for the sequence of entries. Emitting only
    the inner one produces an APK that apksig/Android refuse with a generic
    "app not installed" (androguard rejects it too).
    """
    return _len_prefixed(_len_prefixed(entry))


_ALGO_HASH = {
    ALGO_RSA_PSS_SHA256: "sha256",
    ALGO_RSA_PSS_SHA512: "sha512",
    ALGO_RSA_PKCS1_SHA256: "sha256",
    ALGO_RSA_PKCS1_SHA512: "sha512",
}


def _verify_signature(pubkey, algo: int, signature: bytes, data: bytes) -> None:
    """Raise InvalidSignature (or ValueError) if the signature does not verify."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    if algo in (ALGO_RSA_PSS_SHA256, ALGO_RSA_PSS_SHA512):
        h = hashes.SHA256() if algo == ALGO_RSA_PSS_SHA256 else hashes.SHA512()
        salt = 32 if algo == ALGO_RSA_PSS_SHA256 else 64
        pubkey.verify(signature, data, padding.PSS(mgf=padding.MGF1(h), salt_length=salt), h)
    elif algo in (ALGO_RSA_PKCS1_SHA256, ALGO_RSA_PKCS1_SHA512):
        h = hashes.SHA256() if algo == ALGO_RSA_PKCS1_SHA256 else hashes.SHA512()
        pubkey.verify(signature, data, padding.PKCS1v15(), h)
    else:
        raise ValueError(f"unsupported signature algorithm {algo:#x}")


def _signer_block(signed_data: bytes, signature: bytes, public_key: bytes) -> bytes:
    return _len_prefixed(_len_prefixed(signed_data) + _len_prefixed(signature) + _len_prefixed(public_key))


def sign(
    apk_in: str,
    apk_out: str,
    key_pem: str,
    cert_pem: str,
    v1: bool = True,
    v2: bool = True,
    v3: bool = False,
    min_sdk: int = 23,
    max_sdk: int = 2147483647,
) -> None:
    """Sign ``apk_in`` and write ``apk_out``.

    v1 (JAR) keeps Android 6 working, v2 is required for targetSdk >= 30.
    v3 is off by default because the shipped game is signed v1+v2 only and a
    malformed v3 signer makes Android refuse the whole APK.
    """
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.x509 import load_pem_x509_certificate

    key = _load_key(key_pem)
    with open(cert_pem, "rb") as fh:
        cert_der = load_pem_x509_certificate(fh.read()).public_bytes(serialization.Encoding.DER)
    public_key_der = key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )

    with zipfile.ZipFile(apk_in) as z:
        entries = [(i.filename, z.read(i.filename)) for i in z.infolist()]

    # ---- v1 ------------------------------------------------------------
    if v1:
        manifest = _jar_manifest(entries)
        sf = _jar_sf(manifest)
        rsa = _pkcs7_sign(sf, key_pem, cert_pem)
        entries.extend(
            [
                ("META-INF/MANIFEST.MF", manifest),
                ("META-INF/CERT.SF", sf),
                ("META-INF/CERT.RSA", rsa),
            ]
        )
        # rebuild with the META-INF entries
        tmpdir = tempfile.mkdtemp()
        tmp = os.path.join(tmpdir, "v1.apk")
        builder = ApkBuilder(apk_in)
        for name, payload in entries[-3:]:
            builder.add(name, payload)
        builder.build(tmp)
        apk_in = tmp

    # ---- content digest --------------------------------------------------
    with open(apk_in, "rb") as fh:
        data = fh.read()
    eocd_pos = data.rfind(b"PK\x05\x06")
    if eocd_pos < 0:
        raise SystemExit("not a zip: EOCD not found")
    cd_size, cd_start = struct.unpack_from("<II", data, eocd_pos + 12)
    if cd_start + cd_size != eocd_pos:
        raise SystemExit("zip layout not supported (data descriptor / trailing bytes)")
    eocd = bytearray(data[eocd_pos:])
    struct.pack_into("<I", eocd, 16, cd_start)  # CD offset as if no signing block
    digest = _content_digest([data[:cd_start], data[cd_start:eocd_pos], bytes(eocd)])

    # ---- v2 / v3 signed data --------------------------------------------
    digests_field = _sequence_field(_u32(ALGO_RSA_PKCS1_SHA256) + _len_prefixed(digest))
    certs_field = _len_prefixed(_len_prefixed(cert_der))
    # v2 signed data: digests | certificates | additional attributes
    signed_data_v2 = digests_field + certs_field + _len_prefixed(b"")
    # v3 signed data: digests | certificates | minSDK | maxSDK | additional attributes
    signed_data_v3 = (
        digests_field + certs_field + _u32(min_sdk) + _u32(max_sdk) + _len_prefixed(b"")
    )
    sig_v2 = key.sign(signed_data_v2, padding.PKCS1v15(), hashes.SHA256())
    sig_v3 = key.sign(signed_data_v3, padding.PKCS1v15(), hashes.SHA256())
    # _signer_block() adds the field prefix itself, so only the sequence prefix here
    sig_field_v2 = _len_prefixed(_u32(ALGO_RSA_PKCS1_SHA256) + _len_prefixed(sig_v2))
    sig_field_v3 = _len_prefixed(_u32(ALGO_RSA_PKCS1_SHA256) + _len_prefixed(sig_v3))

    blocks: List[Tuple[int, bytes]] = []
    if v2:
        # v2 signer = signed data | signatures | public key
        blocks.append((V2_BLOCK_ID, _len_prefixed(_signer_block(signed_data_v2, sig_field_v2, public_key_der))))
    if v3:
        # v3 signer = signed data | minSDK | maxSDK | signatures | public key
        # (source.android.com/.../apksigning/v3 — minSDK/maxSDK sit *between*
        #  the signed data and the signatures, and are duplicated inside it)
        signer_v3 = _len_prefixed(
            _len_prefixed(signed_data_v3)
            + _u32(min_sdk)
            + _u32(max_sdk)
            + _len_prefixed(sig_field_v3)
            + _len_prefixed(public_key_der)
        )
        blocks.append((V3_BLOCK_ID, _len_prefixed(signer_v3)))

    # ---- assemble the signing block --------------------------------------
    pairs = b"".join(_u64(len(_u32(i) + v)) + _u32(i) + v for i, v in blocks)
    block_body = pairs + _u64(len(pairs) + 8 + len(APK_SIG_BLOCK_MAGIC)) + APK_SIG_BLOCK_MAGIC
    block = _u64(len(block_body)) + block_body

    with open(apk_out, "wb") as fh:
        fh.write(data[:cd_start])
        fh.write(block)
        fh.write(data[cd_start:eocd_pos])
        new_eocd = bytearray(data[eocd_pos:])
        struct.pack_into("<I", new_eocd, 16, cd_start + len(block))
        fh.write(new_eocd)


# ---------------------------------------------------------------------------
# verification
# ---------------------------------------------------------------------------
def verify_v2_crypto(apk_path: str) -> Tuple[bool, str]:
    """Recompute the content digest and verify the v2 signature.

    This is the real acceptance test: androguard only reports whether a block
    is present, Android verifies the cryptography.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.exceptions import InvalidSignature

    data = open(apk_path, "rb").read()
    eocd_pos = data.rfind(b"PK\x05\x06")
    cd_start = struct.unpack_from("<I", data, eocd_pos + 16)[0]
    # layout: [u64 size][pairs...][u64 size][16-byte magic][central directory]
    block_len = struct.unpack_from("<Q", data, cd_start - 24)[0]
    block_start = cd_start - 8 - block_len
    if data[cd_start - 16 : cd_start] != APK_SIG_BLOCK_MAGIC:
        return False, "signing block magic not found"
    block = data[block_start + 8 : cd_start - 24]

    # walk the uint64-length-prefixed ID/value pairs
    pos = 0
    v2_value = None
    while pos + 12 <= len(block):
        pair_len = struct.unpack_from("<Q", block, pos)[0]
        pair_id = struct.unpack_from("<I", block, pos + 8)[0]
        value = block[pos + 12 : pos + 8 + pair_len]
        if pair_id == V2_BLOCK_ID:
            v2_value = value
            break
        pos += 8 + pair_len
    if v2_value is None:
        return False, "no v2 block"

    def rd(buf: bytes, off: int) -> Tuple[bytes, int]:
        (n,) = struct.unpack_from("<I", buf, off)
        return buf[off + 4 : off + 4 + n], off + 4 + n

    signers, _ = rd(v2_value, 0)
    signer, _ = rd(signers, 0)
    signed_data, off = rd(signer, 0)
    signatures_field, off = rd(signer, off)
    public_key_der, off = rd(signer, off)
    if off != len(signer):
        return False, "trailing bytes in v2 signer"
    signatures, _ = rd(signatures_field, 0)

    # digests inside signed data: field -> sequence -> (algo, len-prefixed digest)
    digests_field, sd_off = rd(signed_data, 0)
    digests_seq, _ = rd(digests_field, 0)
    algo = struct.unpack_from("<I", digests_seq, 0)[0]
    expected_digest, _ = rd(digests_seq, 4)
    hash_name = _ALGO_HASH.get(algo)
    if hash_name is None:
        return False, f"unsupported signature algorithm {algo:#x}"

    # digest of the unsigned APK - three sections, each chunked on its own
    eocd = bytearray(data[eocd_pos:])
    struct.pack_into("<I", eocd, 16, block_start)
    digest = _content_digest(
        [data[:block_start], data[cd_start:eocd_pos], bytes(eocd)], hash_name
    )
    if expected_digest != digest:
        return False, f"content digest mismatch (algo {algo:#x})"

    certs_blob, sd_off = rd(signed_data, sd_off)
    cert_der, _ = rd(certs_blob, 0)
    cert = x509.load_der_x509_certificate(cert_der)
    pubkey = serialization.load_der_public_key(public_key_der)
    if pubkey.public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    ) != cert.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    ):
        return False, "public key does not match certificate"

    sig_algo = struct.unpack_from("<I", signatures, 0)[0]
    if sig_algo != algo:
        return False, f"signature algo {sig_algo:#x} does not match digest algo {algo:#x}"
    signature, _ = rd(signatures, 4)
    try:
        _verify_signature(pubkey, sig_algo, signature, signed_data)
    except InvalidSignature:
        return False, f"RSA signature invalid (algo {sig_algo:#x})"
    return True, f"v2 OK (algo {sig_algo:#x}, subject={cert.subject.rfc4514_string()})"




def verify_signing_block(apk_path: str) -> Tuple[bool, str]:
    """Parse the APK Signing Block structurally and verify every signer.

    ``verify_v2_crypto`` only checks that the content digest and the v2 RSA
    signature are right; it does not check that the *layout* of the signers is
    what Android expects. A malformed signer (e.g. a v3 block with minSdk in
    the wrong place) makes Android reject the whole APK with a generic
    "app not installed" - hence this check.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.exceptions import InvalidSignature

    data = open(apk_path, "rb").read()
    eocd_pos = data.rfind(b"PK\x05\x06")
    cd_start = struct.unpack_from("<I", data, eocd_pos + 16)[0]
    block_len = struct.unpack_from("<Q", data, cd_start - 24)[0]
    block_start = cd_start - 8 - block_len
    if data[cd_start - 16 : cd_start] != APK_SIG_BLOCK_MAGIC:
        return False, "signing block magic not found"
    if block_start < 0:
        return False, "signing block length out of range"

    def rd(buf: bytes, off: int) -> Tuple[bytes, int]:
        (n,) = struct.unpack_from("<I", buf, off)
        if off + 4 + n > len(buf):
            raise ValueError(f"length prefix {n} overruns {len(buf)} at {off}")
        return buf[off + 4 : off + 4 + n], off + 4 + n

    found: List[str] = []
    pos = block_start + 8
    limit = cd_start - 24
    while pos + 12 <= limit:
        pair_len = struct.unpack_from("<Q", data, pos)[0]
        if pair_len < 4 or pos + 8 + pair_len > limit:
            return False, f"corrupt id-value pair at {pos:#x}"
        pair_id = struct.unpack_from("<I", data, pos + 8)[0]
        value = data[pos + 12 : pos + 8 + pair_len]
        if pair_id not in (V2_BLOCK_ID, V3_BLOCK_ID):
            # e.g. 0x42726577 - the verity padding block; not a signer
            pos += 8 + pair_len
            continue
        try:
            signers, _ = rd(value, 0)
            signer, _ = rd(signers, 0)
            signed_data, off = rd(signer, 0)
            if pair_id == V3_BLOCK_ID:
                min_sdk, max_sdk = struct.unpack_from("<II", signer, off)
                off += 8
            signatures_field, off = rd(signer, off)
            public_key_der, off = rd(signer, off)
            if off != len(signer):
                raise ValueError("trailing bytes in signer")
            signatures, _ = rd(signatures_field, 0)
            # signed data: digests | certificates [| minSDK | maxSDK] | attributes
            sd_off = 0
            _digests, sd_off = rd(signed_data, sd_off)
            certs, sd_off = rd(signed_data, sd_off)
            if pair_id == V3_BLOCK_ID:
                sd_min, sd_max = struct.unpack_from("<II", signed_data, sd_off)
                sd_off += 8
                if (sd_min, sd_max) != (min_sdk, max_sdk):
                    raise ValueError("signed data SDK range does not match the signer")
            _attrs, sd_off = rd(signed_data, sd_off)
            # apksig's verifier ignores anything after the attributes field
            if sd_off != len(signed_data):
                found.append(f"{len(signed_data) - sd_off} trailing byte(s) in signed data")
            if not certs:
                raise ValueError("no certificate in signed data")
            if pair_id == V3_BLOCK_ID:
                found.append(f"v3(minSdk={min_sdk}, maxSdk={max_sdk})")
            else:
                found.append("v2")
            # verify the signature over the signed data
            sig_algo = struct.unpack_from("<I", signatures, 0)[0]
            signature, _ = rd(signatures, 4)
            pubkey = serialization.load_der_public_key(public_key_der)
            try:
                _verify_signature(pubkey, sig_algo, signature, signed_data)
            except InvalidSignature:
                return False, f"invalid signature in block {pair_id:#x}"
        except Exception as exc:
            return False, f"malformed block {pair_id:#x}: {type(exc).__name__}: {exc}"
        pos += 8 + pair_len

    if not found:
        return False, "no v2/v3 signer found"
    return True, "signers OK: " + ", ".join(found)


def _parse_jar_manifest(raw: bytes) -> Dict[str, Dict[str, str]]:
    """Return ``{entry name: {attribute: value}}`` from a JAR manifest.

    Handles the 72-byte line wrapping of the JAR spec, where a continuation
    line starts with a single space.
    """
    text = raw.decode("utf-8", "replace").replace("\r\n", "\n")
    unfolded: List[str] = []
    for line in text.split("\n"):
        if line.startswith(" ") and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)

    sections: List[List[str]] = [[]]
    for line in unfolded:
        if not line.strip():
            if sections[-1]:
                sections.append([])
            continue
        sections[-1].append(line)

    out: Dict[str, Dict[str, str]] = {}
    for section in sections:
        if not section:
            continue
        attrs: Dict[str, str] = {}
        for line in section:
            if ":" in line:
                key, _, value = line.partition(":")
                attrs[key.strip()] = value.strip()
        name = attrs.get("Name")
        if name:
            out[name] = attrs
    return out


def verify_v1(apk_path: str) -> Tuple[bool, str]:
    """Check the JAR (v1) signature: MANIFEST.MF digests and the PKCS#7 blob.

    Android falls back to v1 on old platforms and checks it on new ones for
    rollback protection, so a broken v1 signature is a real install failure.
    """
    import base64 as _b64
    import re as _re
    import shutil as _shutil
    import subprocess as _sp
    import tempfile as _tf

    with zipfile.ZipFile(apk_path) as z:
        names = z.namelist()
        mf = next((n for n in names if n.upper() == "META-INF/MANIFEST.MF"), None)
        sf = next((n for n in names if n.upper().endswith(".SF")), None)
        rsa = next((n for n in names if n.upper().endswith((".RSA", ".DSA", ".EC"))), None)
        if not (mf and sf and rsa):
            return False, "v1 files missing"
        manifest = z.read(mf)
        sf_bytes = z.read(sf)
        rsa_bytes = z.read(rsa)
        payloads = {n: z.read(n) for n in names}

    # --- MANIFEST.MF: every entry digest must match the stored file -----------
    checked = 0
    for name, attrs in _parse_jar_manifest(manifest).items():
        if "SHA-256-Digest" not in attrs:
            return False, f"no SHA-256 digest for {name}"
        want = _b64.b64decode(attrs["SHA-256-Digest"])
        if name not in payloads:
            return False, f"{name} listed in the manifest but missing from the APK"
        if hashlib.sha256(payloads[name]).digest() != want:
            return False, f"digest mismatch for {name}"
        checked += 1

    # --- CERT.SF / CERT.RSA --------------------------------------------------
    if _shutil.which("openssl") is None:
        return True, f"v1 digests OK ({checked} entries); PKCS#7 not checked (no openssl)"
    with _tf.TemporaryDirectory() as td:
        sf_path = os.path.join(td, "CERT.SF")
        rsa_path = os.path.join(td, "CERT.RSA")
        with open(sf_path, "wb") as fh:
            fh.write(sf_bytes)
        with open(rsa_path, "wb") as fh:
            fh.write(rsa_bytes)
        proc = _sp.run(
            ["openssl", "smime", "-verify", "-noverify", "-inform", "DER",
             "-in", rsa_path, "-content", sf_path],
            capture_output=True,
        )
    if proc.returncode != 0:
        return False, "PKCS#7 signature does not verify: " + proc.stderr.decode("utf-8", "replace").strip()
    return True, f"v1 OK ({checked} entries, PKCS#7 verified)"


def verify(apk_path: str) -> int:
    ok, msg = verify_v1(apk_path)
    print(f"v1 check         : {ok} — {msg}")
    ok, msg = verify_v2_crypto(apk_path)
    print(f"v2 crypto check  : {ok} — {msg}")
    ok, msg = verify_signing_block(apk_path)
    print(f"signing block    : {ok} — {msg}")
    # Independent cross-check with androguard's own parser. It is stricter than
    # the crypto check above: it parses the whole signer, so a wrong field
    # layout (which Android also rejects) shows up here. Optional dependency.
    try:
        from loguru import logger

        logger.remove()
        from androguard.core.apk import APK

        a = APK(apk_path)
        print(f"package          : {a.get_package()}")
        print(f"versionName      : {a.get_androidversion_name()}")
        print(f"versionCode      : {a.get_androidversion_code()}")
        print(f"signed v1/v2/v3  : {a.is_signed_v1()} / {a.is_signed_v2()} / {a.is_signed_v3()}")
        try:
            certs = a.get_certificates_der_v2() or []
            print(f"androguard v2    : OK ({len(certs)} certificate(s))")
        except Exception as exc:
            print(f"androguard v2    : FAILED — {type(exc).__name__}: {exc}")
            return 1
    except ImportError:
        print("androguard       : not installed, skipped (pip install androguard)")
        return 0
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes

    der_list = []
    for c in a.get_certificates():  # asn1crypto Certificate in androguard >= 4, DER bytes before
        der_list.append(c.dump() if hasattr(c, "dump") else bytes(c))
    for der in der_list:
        cert = x509.load_der_x509_certificate(der)
        print(f"certificate(v1)  : {cert.subject.rfc4514_string()}")
        print(f"sha256           : {cert.fingerprint(hashes.SHA256()).hex()}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("rebuild")
    p.add_argument("--in", dest="src", required=True)
    p.add_argument("--out", dest="out", required=True)
    p.add_argument("--replace", action="append", default=[], metavar="NAME=PATH")
    p.add_argument("--add", action="append", default=[], metavar="NAME=PATH")
    p.add_argument("--drop", action="append", default=[])

    p = sub.add_parser("sign")
    p.add_argument("--in", dest="src", required=True)
    p.add_argument("--out", dest="out", required=True)
    p.add_argument("--key", required=True)
    p.add_argument("--cert", required=True)
    p.add_argument("--no-v1", action="store_true")
    p.add_argument("--no-v2", action="store_true")
    p.add_argument("--v3", action="store_true", help="also add a v3 signer (off by default, like the original APK)")

    p = sub.add_parser("verify")
    p.add_argument("--in", dest="src", required=True)

    args = ap.parse_args(argv)

    if args.cmd == "rebuild":
        b = ApkBuilder(args.src)
        for spec in args.replace:
            name, path = spec.split("=", 1)
            b.replace(name, open(path, "rb").read())
        for spec in args.add:
            name, path = spec.split("=", 1)
            b.add(name, open(path, "rb").read())
        for name in args.drop:
            b.drop(name)
        b.build(args.out)
        print(f"wrote {args.out}")
    elif args.cmd == "sign":
        sign(args.src, args.out, args.key, args.cert, v1=not args.no_v1, v2=not args.no_v2, v3=args.v3)
        print(f"wrote {args.out}")
    elif args.cmd == "verify":
        return verify(args.src)
    return 0


if __name__ == "__main__":
    sys.exit(main())
