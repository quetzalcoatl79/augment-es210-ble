"""Décodeur btsnoop -> trames ATT (écritures et notifications) de la trottinette.

Lecture seule d'un fichier btsnoop_hci.log. N'écrit rien en Bluetooth.
Affiche, dans l'ordre chronologique, les Write Request/Command et les
Handle Value Notification/Indication, avec handle ATT + payload hex + ASCII.
Usage : python parse_btsnoop.py <btsnoop_hci.log> [mac_cible]
"""
import struct
import sys
from datetime import datetime, timedelta, timezone

EPOCH = datetime(2000, 1, 1, tzinfo=timezone.utc)  # btsnoop : us depuis 2000-01-01 (filetime/1e... non, cf code)

ATT_OPS = {
    0x12: "Write Request",
    0x52: "Write Command",
    0x1b: "Notification",
    0x1d: "Indication",
    0x13: "Write Response",
    0x0a: "Read Request",
    0x0b: "Read Response",
    0x16: "Prepare Write Req",
    0x18: "Execute Write Req",
}


def ascii_of(b: bytes) -> str:
    return "".join(chr(x) if 32 <= x < 127 else "." for x in b)


def ts_str(us: int) -> str:
    # btsnoop timestamp = microsecondes depuis 0000-01-01 ; on ne garde que l'heure
    try:
        base = datetime(1, 1, 1, tzinfo=timezone.utc)
        dt = base + timedelta(microseconds=us)
        return dt.strftime("%H:%M:%S.%f")[:-3]
    except Exception:
        return str(us)


def main(path: str) -> None:
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"btsnoop\x00":
        print("Pas un fichier btsnoop (magic absent) :", data[:8])
        return
    version, datalink = struct.unpack(">II", data[8:16])
    print(f"# btsnoop v{version} datalink={datalink}  ({len(data)} octets)")
    off = 16
    n_att = 0
    # état L2CAP minimal : on suit le CID ATT = 0x0004
    while off + 24 <= len(data):
        orig_len, incl_len, flags, drops, ts = struct.unpack(">IIIIq", data[off:off + 24])
        off += 24
        pkt = data[off:off + incl_len]
        off += incl_len
        if not pkt:
            continue
        ind = pkt[0]  # H4 packet indicator
        direction = "TX>" if (flags & 0x01) == 0 else "<RX"  # flags bit0 : 0=sent,1=received (selon impl)
        if ind != 0x02:  # on ne veut que l'ACL data
            continue
        acl = pkt[1:]
        if len(acl) < 4:
            continue
        handle_flags, acl_len = struct.unpack("<HH", acl[:4])
        l2 = acl[4:4 + acl_len]
        if len(l2) < 4:
            continue
        l2_len, cid = struct.unpack("<HH", l2[:4])
        if cid != 0x0004:  # CID ATT
            continue
        att = l2[4:4 + l2_len]
        if not att:
            continue
        op = att[0]
        if op not in ATT_OPS:
            continue
        name = ATT_OPS[op]
        rest = att[1:]
        line = f"{ts_str(ts)} {direction} {name:16}"
        if op in (0x12, 0x52, 0x1b, 0x1d) and len(rest) >= 2:
            hnd = struct.unpack("<H", rest[:2])[0]
            val = rest[2:]
            line += f" handle=0x{hnd:04x} val=[{val.hex(' ')}] '{ascii_of(val)}'"
        else:
            line += f" data=[{rest.hex(' ')}]"
        print(line)
        n_att += 1
    print(f"# {n_att} trames ATT pertinentes")


if __name__ == "__main__":
    main(sys.argv[1])
