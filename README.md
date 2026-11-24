# Augment ES210 — contrôle BLE local (open / right-to-repair)

Reprendre le contrôle **en local, en Bluetooth** d'une trottinette **Augment ES210**
(module **Vicont**, firmware **ECA**) sans compte, sans serveur et sans l'appli du
fabricant : lire l'état, verrouiller/déverrouiller, réarmer le compteur des
10 allumages, piloter les modes de vitesse et **débrider**.

Outil **indépendant** d'interopérabilité. **Non affilié à Augment.**

---

## ⚠️ Avertissement / Disclaimer

> **FR —** À utiliser **uniquement sur une trottinette dont tu es propriétaire.**
> L'usage peut **annuler la garantie** Augment. Le **débridage dépasse la limite
> légale** (25 km/h en UE) : réservé à la **propriété privée**. Écrire sur la
> trottinette peut la **briquer** et modifier la vitesse peut provoquer une chute.
> **Tu assumes tout le risque.** Voir [`LICENSE`](LICENSE) (disclaimer complet).
>
> **EN —** Use **only on a scooter you own.** May **void your warranty.** Speed
> derestriction exceeds the legal road limit (25 km/h EU) → **private property
> only.** Writing can **brick** the scooter; changing speed can cause crashes.
> **You assume all risk.** Full disclaimer in [`LICENSE`](LICENSE).

---

## Testé sur

| | |
|---|---|
| Modèle | Augment **ES210** |
| Firmware | **ECA1.0.0** |
| Matériel | **Vicont-V1.3-400** |
| Fabricant module | **VC-KX** |

> ⚠️ **Une seule trottinette testée.** Autres firmwares / révisions : non vérifiés,
> à tes risques. Si tu testes une autre ES210, une PR confirmant/infirmant est
> bienvenue.

## Qu'est-ce qui est générique, qu'est-ce qui est propre à ton appareil ?

| Élément | Commun aux ES210 ? |
|---|---|
| Carte GATT (service `5833…`, carac. 6880-6886) | ✅ oui (structure firmware) |
| Compteur des 10 allumages (1ᵉʳ octet de 6884) | ✅ oui |
| Débridage (registre 6881, octet haut `0x50`, ex. `be50`) | ✅ très probablement |
| Modes de vitesse (6881, octet haut `0x4c`) | ✅ oui |
| **Jetons `unlock`/`lock` (5 octets)** | ❌ **NON — propres à chaque trottinette.** Tu dois **capturer les tiens** |

Autrement dit : le **débridage** et la **structure** sont partagés ; le
**déverrouillage** est lié à ton appareil (c'est pour ça qu'Augment le relie à ton
compte). Ce dépôt ne contient **aucun** jeton : tu mets les tiens dans `config.ini`.

## Ce que ça fait

- `status` / `config` : lire odomètre, compteur d'allumages, registre de config
- `unlock` / `lock` : (dé)verrouiller — `unlock` **remet le compteur à 10**
- `mode 0..3` : modes de vitesse (bridés)
- `set speed35` : **débrider (~35 km/h)** · `set normal25` : re-brider à 25
- `boot` : `unlock` **puis** débridage, en une commande (idéal après un verrouillage)

## Installation & usage (PC, Python)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install bleak
cp config.example.ini config.ini     # puis édite : mac, unlock, lock
python tools/augment_control.py status
python tools/augment_control.py boot
```

Fermer l'appli Augment avant (une seule connexion BLE à la fois).

## Application Android

Projet Kotlin natif (zéro dépendance) dans [`android/`](android/). Les identifiants
(MAC + jetons) se **saisissent dans l'app** (stockés en local, rien en dur).

```bash
# toolchain requis : JDK 17 + Android SDK (API 34) + Gradle 8.9
gradle -p android assembleDebug
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
# Xiaomi/HyperOS : si l'install USB est bloquée, pousse l'APK et tape-le sur le tel
adb push android/app/build/outputs/apk/debug/app-debug.apk /sdcard/Download/
```

## Capturer TES jetons `unlock` / `lock`

Ils sont propres à ta trottinette → capture-les depuis **ta** appli Augment :

1. Active **Options développeur → Journal HCI Bluetooth** sur ton Android.
2. Appli Augment ouverte et connectée à TA trottinette, fais **Déverrouiller**
   puis **Verrouiller**.
3. Récupère le log : `adb bugreport out.zip` → dézippe
   `FS/data/misc/bluetooth/logs/btsnoop_hci.log`.
4. Décode : `python tools/parse_btsnoop.py btsnoop_hci.log`
   → repère les **Write Request** sur le **handle de la carac. 6884** :
   la valeur 5 octets écrite au déverrouillage = ton `unlock`, au verrouillage = ton `lock`.
5. Mets-les dans `config.ini`.

Outils d'analyse fournis : `parse_btsnoop.py` (trames ATT), `gatt_map.py`
(handles → UUID), `analyze.py` (synthèse par caractéristique).

## Protocole (résumé)

- **Service** propriétaire `58336680-9b8b-5191-6142-22a4536ef123`.
- **6884** = commande `lock`/`unlock` (écriture 5 octets) **+** compteur en lecture
  (1ᵉʳ octet = allumages restants ; 0 → verrouillage ; `unlock` le remet à 10).
- **6881** = registre de config 16 bits (little-endian). Octet haut : `0x4c` = bridé
  (25 km/h), **`0x50` = débridé (~35)**. Modes de vitesse = bits 6-7.
- **6885** = odomètre total ×10. 6880/6882 = télémétrie. 6886 = nom.

## Licence

[MIT](LICENSE) + disclaimer. Usage entièrement à tes risques et périls.
