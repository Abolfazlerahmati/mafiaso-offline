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
    json_bytes = json.dumps(profile, separators=(",", ":")).encode("utf-8") + b"\x00"
    json_off = 0x2A59400
    data[json_off : json_off + len(json_bytes)] = json_bytes

    pc = 0x14C00A8
    pc_va = pc + 0x4000
    json_va = json_off + 0x8000
    code = bytearray()
    # stp x29, x30, [sp, #-32]! ; mov x29, sp ; str x19, [sp, #16] ; mov x19, x0
    code += bytes.fromhex("fd7bbea9fd030091f30b00f9f30300aa")
    code += enc_adrp(pc_va + len(code), json_va, 0)
    code += enc_add_imm(0, 0, json_va & 0xFFF)
    code += enc_bl(pc + len(code), 0x11F7038)
    code += enc_bl(pc + len(code), 0x174E0A4)
    code += bytes.fromhex("e10300aa000080d2")
    code += enc_bl(pc + len(code), 0x165B46C)
    # mov x0, x19 ; ldr x19, [sp, #16] ; ldp x29, x30, [sp], #32
    code += bytes.fromhex("e00313aaf30b40f9fd7bc2a8")
    code += enc_b(pc + len(code), 0x14C6498)
    data[pc : pc + len(code)] = code

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
