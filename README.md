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

## 🔑 Capturer TES jetons `unlock` / `lock` (obligatoire)

Les 5 octets de verrouillage/déverrouillage sont **propres à chaque trottinette**
(c'est pourquoi Augment lie le déverrouillage à ton compte). **Ce dépôt n'en contient
aucun** : tu captures **les tiens** en observant **ta** appli Augment faire l'opération,
via le journal Bluetooth (HCI snoop) d'Android. ~10 min, aucun root.

### A. Préparer le téléphone (Android)
1. **Activer les options développeur** : *Réglages → À propos du téléphone* → tape
   **7 fois** sur « Numéro de build » (Xiaomi/HyperOS : sur « Version HyperOS/MIUI »).
2. Dans **Options pour développeurs**, active :
   - **Débogage USB**
   - **Journal HCI Bluetooth** (« Enable Bluetooth HCI snoop log ») → *Activé*.
3. **Coupe puis rallume le Bluetooth** (ça démarre un journal neuf et propre).

### B. Préparer le PC
- Installe `adb` (paquet *android-tools* / *platform-tools*).
- Branche le téléphone en USB, choisis le mode **Transfert de fichiers (MTP)**, et
  **autorise** la clé RSA quand le téléphone le demande.
- Vérifie : `adb devices` → ton téléphone doit apparaître en `device`.

### C. Capturer l'opération
1. Ouvre l'**appli Augment**, connecte-la à **ta** trottinette (allumée).
2. Fais **Déverrouiller**, attends ~2 s, puis **Verrouiller** (ces deux actions
   envoient les deux jetons qu'on veut).
3. Récupère le journal :
   ```bash
   adb bugreport capture.zip
   unzip -j capture.zip "FS/data/misc/bluetooth/logs/btsnoop_hci.log" -d .
   ```

### D. Décoder
1. Trouve le handle ATT de la caractéristique **6884** (commande) :
   ```bash
   python tools/gatt_map.py btsnoop_hci.log | grep 6884
   #  0x0038 : 6884   [read,wrNoRsp,write]      ← ici le handle = 0x0038
   ```
2. Liste les écritures et repère les **deux écritures de 5 octets sur ce handle** :
   ```bash
   python tools/parse_btsnoop.py btsnoop_hci.log | grep "Write Request"
   ```
   ```
   TX> Write Request  handle=0x0038 val=[a1 b2 c3 d4 e5]   ← déverrouillage = ton UNLOCK
   TX> Write Request  handle=0x0038 val=[f0 11 22 33 44]   ← verrouillage   = ton LOCK
   ```
   > ⚠️ Les valeurs ci-dessus sont des **exemples bidon** : les tiennes seront différentes.
3. Reporte-les **sans espaces** dans `config.ini` :
   ```ini
   unlock = a1b2c3d4e5
   lock   = f011223344
   ```

### Dépannage
- `adb devices` vide → repasse le câble en **Transfert de fichiers**, active le
  Débogage USB (Xiaomi : parfois aussi « Débogage USB (réglages de sécurité) »).
- Journal vide → « Journal HCI Bluetooth » bien *Activé* ? Refais le cycle Bluetooth
  avant de capturer.
- Beaucoup de lignes → les *Notification* sont normales (télémétrie) ; seules les
  **Write Request de 5 octets** sur le handle de 6884 t'intéressent.

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
