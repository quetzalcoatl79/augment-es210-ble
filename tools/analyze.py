"""Analyse ciblée du btsnoop : pour chaque handle, valeurs lues/notifiées/écrites,
et textes des descripteurs 0x2901. Apparie Read Request/Response.
Lecture seule. Usage : python3 -I analyze.py <btsnoop_hci.log>
"""
import struct
import sys
from collections import defaultdict, OrderedDict

# handle de valeur -> nom court (depuis gatt_map)
NAME = {
    0x0003: "fee2", 0x0028: "6880", 0x002c: "6881", 0x0030: "6882",
    0x0034: "6883", 0x0038: "6884", 0x003c: "6885", 0x0040: "6886",
}
DESC2901 = {  # handle 0x2901 -> caractéristique associée (handle valeur)
    0x0005: 0x0003, 0x002a: 0x0028, 0x002e: 0x002c, 0x0032: 0x0030,
    0x0036: 0x0034, 0x003a: 0x0038, 0x003e: 0x003c, 0x0042: 0x0040,
}


def att_frames(data):
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
            yield ts, att


def main(path):
    with open(path, "rb") as f:
        data = f.read()
    notif = defaultdict(lambda: OrderedDict())   # handle -> {val:count}
    writes = defaultdict(lambda: OrderedDict())
    reads = defaultdict(lambda: OrderedDict())
    desc_text = {}
    pending_read = None  # handle de la dernière Read Request

    for ts, att in att_frames(data):
        op = att[0]
        if op in (0x1b, 0x1d) and len(att) >= 3:        # Notification/Indication
            h = struct.unpack("<H", att[1:3])[0]
            v = att[3:].hex(' ')
            notif[h][v] = notif[h].get(v, 0) + 1
        elif op in (0x12, 0x52) and len(att) >= 3:       # Write Req/Cmd
            h = struct.unpack("<H", att[1:3])[0]
            v = att[3:].hex(' ')
            writes[h][v] = writes[h].get(v, 0) + 1
        elif op == 0x0a and len(att) >= 3:               # Read Request
            pending_read = struct.unpack("<H", att[1:3])[0]
        elif op == 0x0b and pending_read is not None:    # Read Response
            v = att[1:].hex(' ')
            reads[pending_read][v] = reads[pending_read].get(v, 0) + 1
            if pending_read in DESC2901:                 # texte 0x2901
                try:
                    desc_text[DESC2901[pending_read]] = bytes.fromhex(v.replace(' ', '')).decode('utf-8', 'replace')
                except Exception:
                    pass
            pending_read = None

    print("===== NOMS 0x2901 (User Description) des caractéristiques =====")
    for vh, txt in desc_text.items():
        print(f"  {NAME.get(vh, hex(vh))} : {txt!r}")

    print("\n===== VALEURS LUES par handle =====")
    for h in sorted(reads):
        nm = NAME.get(h, hex(h))
        for v, c in reads[h].items():
            print(f"  {nm} (0x{h:04x}) read = [{v}]  x{c}")

    print("\n===== ÉCRITURES par handle =====")
    for h in sorted(writes):
        nm = NAME.get(h, hex(h))
        for v, c in writes[h].items():
            print(f"  {nm} (0x{h:04x}) write=[{v}]  x{c}")

    print("\n===== NOTIFICATIONS : valeurs DISTINCTES par handle =====")
    for h in sorted(notif):
        nm = NAME.get(h, hex(h))
        vals = list(notif[h].items())
        print(f"  {nm} (0x{h:04x}) : {len(vals)} valeur(s) distincte(s)")
        for v, c in vals[:12]:
            print(f"       [{v}]  x{c}")
        if len(vals) > 12:
            print(f"       … (+{len(vals)-12})")


if __name__ == "__main__":
    main(sys.argv[1])
