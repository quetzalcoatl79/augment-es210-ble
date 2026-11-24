"""Pilotage BLE local d'une trottinette Augment ES210 (module Vicont / firmware ECA),
sans l'appli du fabricant. Rejoue des commandes BLE constantes et un registre de config.

⚠️  Voir le DISCLAIMER (LICENSE / README). À n'utiliser QUE sur ta propre trottinette.
    Les jetons unlock/lock sont PROPRES À TON APPAREIL : tu dois les capturer toi-même
    (README « Capturer tes jetons »). Rien n'est écrit « à l'aveugle » : seules des
    valeurs connues (les tiennes, ou validées sur ES210) sont envoyées.

Config : copie config.example.ini -> config.ini et remplis mac/unlock/lock.

Usage :
    python augment_control.py status            # lire l'état (ne modifie rien)
    python augment_control.py config            # lire + décoder le registre 6881
    python augment_control.py unlock|lock
    python augment_control.py mode 0|1|2|3       # modes de vitesse (bridés)
    python augment_control.py set speed35|normal25|<nom>
    python augment_control.py boot               # unlock + débridage, en un coup
    python augment_control.py list
"""
import asyncio
import configparser
import os
import sys

from bleak import BleakClient, BleakScanner

HERE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.environ.get("AUGMENT_CONFIG",
                          os.path.join(os.path.dirname(HERE), "config.ini"))

SERVICE_PREFIX = "0000{}-0000-1000-8000-00805f9b34fb"
CH_CMD = SERVICE_PREFIX.format("6884")  # lock/unlock + compteur
CH_CFG = SERVICE_PREFIX.format("6881")  # registre de config
B = (bytes, bytearray)

# Modes de vitesse (bridés) — structure commune aux ES210, octet haut 0x4c.
MODE_VAL = {0: "1e4c", 1: "5e4c", 2: "9e4c", 3: "de4c"}


def load_config():
    if not os.path.exists(CFG_PATH):
        raise SystemExit(f"Config absente : {CFG_PATH}\n"
                         "Copie config.example.ini -> config.ini et remplis mac/unlock/lock.")
    cp = configparser.ConfigParser()
    cp.read(CFG_PATH)
    s = cp["scooter"]
    mac = s.get("mac", "").strip()
    unlock = s.get("unlock", "").strip().replace(" ", "")
    lock = s.get("lock", "").strip().replace(" ", "")
    if not mac or mac.upper().startswith("AA:BB"):
        raise SystemExit("Renseigne 'mac' dans config.ini.")
    cfg_safe = {
        "speed35": s.get("speed35", "be50").strip().replace(" ", ""),
        "normal25": s.get("normal25", "de4c").strip().replace(" ", ""),
    }
    return mac, unlock, lock, cfg_safe


def decode_cfg(v) -> str:
    x = int.from_bytes(bytes(v[:2]), "little")
    mode = (x >> 6) & 0x3
    hi = (x >> 8) & 0xFF
    tag = {0x50: "DÉBRIDÉ(0x50)", 0x4c: "bridé(0x4c=25)",
           0x0c: "bridé(0x0c=25)"}.get(hi, f"?octet-haut=0x{hi:02x}?")
    return f"0x{x:04x} (= {bytes(v[:2]).hex(' ')})  {tag}  mode={mode}"


async def connect(mac):
    print("Recherche de la trottinette…", flush=True)
    dev = await BleakScanner.find_device_by_address(mac, timeout=30)
    if dev is None:
        raise SystemExit("Introuvable. Appli Augment fermée ? Scooter allumé ? "
                         "(une seule connexion BLE à la fois)")
    return dev


async def rd(c, uuid):
    try:
        return await c.read_gatt_char(uuid)
    except Exception as e:  # noqa: BLE001
        return f"err:{e}"


async def write_cfg(c, hexval):
    before = await rd(c, CH_CFG)
    print(f"Avant : {decode_cfg(before) if isinstance(before,B) else before}")
    await c.write_gatt_char(CH_CFG, bytes.fromhex(hexval), response=True)
    print(f"Écrit sur 6881 : {hexval}")
    await asyncio.sleep(0.6)
    after = await rd(c, CH_CFG)
    print(f"Après : {decode_cfg(after) if isinstance(after,B) else after}")


async def show_status(c):
    odo = await rd(c, SERVICE_PREFIX.format("6885"))
    km = int.from_bytes(odo, "little") / 10 if isinstance(odo, B) else odo
    cmd = await rd(c, CH_CMD)
    cfg = await rd(c, CH_CFG)
    print(f"Odomètre (6885)      : {km} km")
    print(f"6884 (commande/état) : {bytes(cmd).hex(' ') if isinstance(cmd,B) else cmd}"
          + (f"   → {cmd[0]} allumages restants" if isinstance(cmd, B) and cmd else ""))
    print(f"6881 (config)        : {decode_cfg(cfg) if isinstance(cfg,B) else cfg}")


async def main(argv):
    action = argv[0] if argv else "status"
    mac, unlock, lock, cfg_safe = load_config()

    if action == "list":
        print("Modes :", MODE_VAL)
        print("Config nommée :", cfg_safe)
        return

    need_token = action in ("unlock", "lock", "boot")
    if need_token and (not unlock or not lock):
        raise SystemExit("Renseigne 'unlock' et 'lock' dans config.ini "
                         "(jetons propres à TA trottinette, voir README).")

    dev = await connect(mac)
    async with BleakClient(dev) as c:
        print("Connecté.", flush=True)
        if action == "status":
            await show_status(c)
        elif action == "config":
            cfg = await rd(c, CH_CFG)
            print(f"6881 : {decode_cfg(cfg) if isinstance(cfg,B) else cfg}")
        elif action == "unlock":
            await c.write_gatt_char(CH_CMD, bytes.fromhex(unlock), response=True)
            print(f"unlock envoyé : {unlock}")
        elif action == "lock":
            await c.write_gatt_char(CH_CMD, bytes.fromhex(lock), response=True)
            print(f"lock envoyé : {lock}")
        elif action == "mode":
            if len(argv) < 2 or argv[1] not in ("0", "1", "2", "3"):
                raise SystemExit("Usage : mode 0|1|2|3")
            await write_cfg(c, MODE_VAL[int(argv[1])])
        elif action == "set":
            name = argv[1] if len(argv) > 1 else ""
            if name not in cfg_safe:
                raise SystemExit(f"Nom inconnu. Dispo : {', '.join(cfg_safe)}")
            await write_cfg(c, cfg_safe[name])
        elif action == "boot":
            print("1) unlock (réarme le compteur)…")
            await c.write_gatt_char(CH_CMD, bytes.fromhex(unlock), response=True)
            await asyncio.sleep(0.5)
            print("2) débridage…")
            await write_cfg(c, cfg_safe["speed35"])
        else:
            raise SystemExit(f"Action inconnue : {action}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
