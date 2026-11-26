import json
import struct
from pathlib import Path


def enc_bl(pc: int, target: int) -> bytes:
    imm26 = ((target - pc) // 4) & 0x3FFFFFF
    return struct.pack("<I", 0x94000000 | imm26)


def enc_b(pc: int, target: int) -> bytes:
    imm26 = ((target - pc) // 4) & 0x3FFFFFF
    return struct.pack("<I", 0x14000000 | imm26)


def enc_adrp(pc: int, target: int, reg: int = 0) -> bytes:
    pc_page = pc & ~0xFFF
    tgt_page = target & ~0xFFF
    imm = (tgt_page - pc_page) >> 12
    immlo = imm & 0x3
    immhi = (imm >> 2) & 0x7FFFF
    return struct.pack("<I", 0x90000000 | (immlo << 29) | (immhi << 5) | reg)


def enc_add_imm(rd: int, rn: int, imm12: int) -> bytes:
    return struct.pack("<I", 0x91000000 | ((imm12 & 0xFFF) << 10) | (rn << 5) | rd)


def main() -> None:
    src = Path("work/libil2cpp.so")
    dst = Path("work/libil2cpp_patched.so")
    data = bytearray(src.read_bytes())

    heroes = [
        "Changiz", "Shahin", "Shaboon", "Taghi", "Kambiz", "Shapoor", "Davood", "Sasan",
        "Doctor", "Ghobad", "Heshmat", "Esi", "Dozd", "Parastar", "NanJoon", "Ghabrkan",
        "Sharare", "Mechanic", "Robert", "Mahpeykar", "Zombie", "Jasem", "Boxer", "Afsoon",
        "Comiser", "Samurai", "Zinat", "Sahara", "PinHead", "Gambler", "Bijan", "Swat",
        "ChenLi", "Pirate", "Gypsy", "Balsamic", "BabaJan", "AmmeKaty", "Yavar", "Kite",
    ]

    profile = {
        "id": "offline-player",
        "name": "Offline",
        "coin": 9999999,
        "gem": 999999,
        "trophy": 5000,
        "level": 10,
        "xp": 0,
        "heros": [{"name": h, "level": 1, "cards": 9999} for h in heroes],
        "deck": heroes[:4],
        "unlockedSkins": [],
    }
    ret_addrs = [
        0x16728C4, 0x167641C, 0x167633C,
        0x159C400, 0x15A3C68, 0x159FBF0, 0x15C33D0,
        0x184B6AC, 0x183A304,
        0x17C17BC, 0x17C2470, 0x17C252C, 0x17C16AC, 0x17C2678,
        0x1506204, 0x150629C,
        0x1514680, 0x151A948,
        0x16D0FF8,
        0x163D770, 0x163C71C,
        0x171CCB8, 0x17175FC, 0x171B910, 0x171BCF0,
        0x15EAD68,
    ]
    for a in ret_addrs:
        data[a : a + 4] = bytes.fromhex("c0035fd6")

    data[0x165ED34 : 0x165ED3C] = bytes.fromhex("20008052c0035fd6")

    dst.write_bytes(data)
    print(f"Wrote {dst} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
