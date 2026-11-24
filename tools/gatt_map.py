"""Reconstruit la table GATT (handle -> UUID) depuis un btsnoop, en décodant
la découverte de services : Read By Type Response (0x09, déclarations de
caractéristiques) et Find Information Response (0x05, descripteurs).
Lecture seule. Usage : python3 -I gatt_map.py <btsnoop_hci.log>
"""
import struct
import sys


def uuid_str(b: bytes) -> str:
    if len(b) == 2:
        return f"{struct.unpack('<H', b)[0]:04x}"
    if len(b) == 16:
        u = b[::-1].hex()
        return f"{u[0:8]}-{u[8:12]}-{u[12:16]}-{u[16:20]}-{u[20:]}"
    return b.hex()


def att_frames(data: bytes):
    off = 16
    while off + 24 <= len(data):
        orig_len, incl_len, flags, drops, ts = struct.unpack(">IIIIq", data[off:off + 24])
        off += 24
        pkt = data[off:off + incl_len]
        off += incl_len
        if not pkt or pkt[0] != 0x02:
            continue
        acl = pkt[1:]
        if len(acl) < 4:
            continue
        _, acl_len = struct.unpack("<HH", acl[:4])
        l2 = acl[4:4 + acl_len]
        if len(l2) < 4:
            continue
        l2_len, cid = struct.unpack("<HH", l2[:4])
        if cid != 0x0004:
            continue
        att = l2[4:4 + l2_len]
        if att:
            yield att


def main(path: str) -> None:
    with open(path, "rb") as f:
        data = f.read()
    char_val = {}   # value_handle -> (uuid, props)
    char_decl = {}  # decl_handle -> value_handle
    desc = {}       # handle -> uuid (descripteurs)
    for att in att_frames(data):
        op = att[0]
        if op == 0x09:  # Read By Type Response : liste de (handle, valeur)
            each = att[1]
            body = att[2:]
            if each not in (7, 21):  # pas une déclaration de caractéristique
                continue
            for i in range(0, len(body) - each + 1, each):
                rec = body[i:i + each]
                decl_h = struct.unpack("<H", rec[:2])[0]
                # déclaration de caractéristique : props(1) + value_handle(2) + uuid
                props = rec[2]
                val_h = struct.unpack("<H", rec[3:5])[0]
                u = uuid_str(rec[5:])
                char_val[val_h] = (u, props)
                char_decl[decl_h] = val_h
        elif op == 0x05:  # Find Information Response : (handle, uuid)
            fmt = att[1]
            body = att[2:]
            step = 4 if fmt == 1 else 18
            for i in range(0, len(body) - step + 1, step):
                h = struct.unpack("<H", body[i:i + 2])[0]
                u = uuid_str(body[i + 2:i + step])
                desc[h] = u

    def prop_str(p):
        f = []
        if p & 0x02: f.append("read")
        if p & 0x04: f.append("wrNoRsp")
        if p & 0x08: f.append("write")
        if p & 0x10: f.append("notify")
        if p & 0x20: f.append("indicate")
        return ",".join(f)

    print("# CARACTÉRISTIQUES (value_handle : uuid [props])")
    for h in sorted(char_val):
        u, p = char_val[h]
        print(f"  0x{h:04x} : {u}   [{prop_str(p)}]")
    print("# DESCRIPTEURS (handle : uuid)")
    for h in sorted(desc):
        print(f"  0x{h:04x} : {desc[h]}")


if __name__ == "__main__":
    main(sys.argv[1])
