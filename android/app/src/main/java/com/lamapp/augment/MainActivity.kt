package com.lamapp.augment

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.content.Context
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.os.Bundle
import android.text.InputType
import android.text.method.ScrollingMovementMethod
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.app.Activity
import java.text.SimpleDateFormat
import java.util.ArrayDeque
import java.util.Date
import java.util.Locale
import java.util.UUID

/**
 * Pilotage BLE local d'une trottinette Augment ES210 (module Vicont / firmware ECA),
 * sans l'appli du fabricant.
 *
 * ⚠️ Voir le DISCLAIMER (LICENSE / README). À n'utiliser QUE sur ta propre trottinette.
 *
 * AUCUN identifiant n'est codé en dur : la MAC et les jetons unlock/lock (propres à
 * TA trottinette, à capturer depuis ton appli — cf. README) se saisissent dans l'app
 * et sont stockés localement (SharedPreferences).
 */
@SuppressLint("MissingPermission")
class MainActivity : Activity() {

    companion object {
        private val SERVICE = UUID.fromString("58336680-9b8b-5191-6142-22a4536ef123")
        private val CH_CMD = UUID.fromString("00006884-0000-1000-8000-00805f9b34fb")
        private val CH_CFG = UUID.fromString("00006881-0000-1000-8000-00805f9b34fb")
        private val CH_ODO = UUID.fromString("00006885-0000-1000-8000-00805f9b34fb")

        // Valeurs du registre 6881, communes aux ES210 (modifiables en config avancée).
        private const val DEF_SPEED35 = "be50"  // débridage ~35
        private const val DEF_NORMAL25 = "de4c"  // mode 3 bridé 25

        private const val REQ_PERMS = 1
        private const val PREFS = "augment"
    }

    private lateinit var adapter: BluetoothAdapter
    private var gatt: BluetoothGatt? = null
    private lateinit var logView: TextView
    private lateinit var macField: EditText
    private lateinit var unlockField: EditText
    private lateinit var lockField: EditText
    private val actionButtons = mutableListOf<Button>()

    private val ops = ArrayDeque<() -> Unit>()
    private var busy = false
    private var pendingAction: (() -> Unit)? = null

    private fun prefs(): SharedPreferences = getSharedPreferences(PREFS, Context.MODE_PRIVATE)
    private fun cfg(key: String, def: String = ""): String = prefs().getString(key, def) ?: def

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val bm = getSystemService(BLUETOOTH_SERVICE) as BluetoothManager
        adapter = bm.adapter

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(40, 40, 40, 40)
        }

        root.addView(TextView(this).apply {
            text = "🛴 Augment ES210 — contrôle BLE"
            textSize = 20f
            setTypeface(typeface, Typeface.BOLD)
            setPadding(0, 0, 0, 8)
        })
        root.addView(TextView(this).apply {
            text = "Propriétaire uniquement · usage à tes risques (voir README)."
            textSize = 11f
            setTextColor(Color.GRAY)
            setPadding(0, 0, 0, 20)
        })

        // --- Config (saisie des identifiants propres à TA trottinette) ---
        macField = labeledField(root, "Adresse MAC (AA:BB:CC:DD:EE:FF)", cfg("mac"),
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS)
        unlockField = labeledField(root, "Jeton unlock (5 octets hexa, ex. a1b2c3d4e5)", cfg("unlock"),
            InputType.TYPE_CLASS_TEXT)
        lockField = labeledField(root, "Jeton lock (hexa)", cfg("lock"),
            InputType.TYPE_CLASS_TEXT)
        root.addView(Button(this).apply {
            text = "💾 Enregistrer la config"
            setOnClickListener { saveConfig() }
        })

        // --- Actions ---
        addAction(root, "🔌 Connecter") { connect() }
        addAction(root, "ℹ️ État (status)") { doStatus() }
        addAction(root, "🔓 Déverrouiller") { writeHex(CH_CMD, cfg("unlock"), "unlock") }
        addAction(root, "🔒 Verrouiller") { writeHex(CH_CMD, cfg("lock"), "lock") }
        addAction(root, "🏎️ Débrider 35 km/h") { writeHex(CH_CFG, cfg("speed35", DEF_SPEED35), "débrider 35") }
        addAction(root, "🐢 Rebrider 25 km/h") { writeHex(CH_CFG, cfg("normal25", DEF_NORMAL25), "rebrider 25") }
        addAction(root, "⚡ BOOT (unlock + 35)") { doBoot() }
        addAction(root, "✖️ Déconnecter") { disconnect() }

        logView = TextView(this).apply {
            setPadding(0, 24, 0, 0)
            typeface = Typeface.MONOSPACE
            textSize = 12f
            setTextColor(Color.DKGRAY)
            movementMethod = ScrollingMovementMethod()
            setTextIsSelectable(true)
        }
        root.addView(logView)

        setContentView(ScrollView(this).apply {
            addView(root, ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        })
        setActionsEnabled(false)
        log("Renseigne MAC + jetons, « Enregistrer », ferme l'appli Augment, puis « Connecter ».")
    }

    private fun labeledField(parent: LinearLayout, label: String, value: String, inputType: Int): EditText {
        parent.addView(TextView(this).apply {
            text = label; textSize = 11f; setTextColor(Color.GRAY); setPadding(0, 12, 0, 0)
        })
        val e = EditText(this).apply {
            setText(value); this.inputType = inputType; textSize = 14f
        }
        parent.addView(e)
        return e
    }

    private fun addAction(parent: LinearLayout, label: String, onClick: () -> Unit) {
        val b = Button(this).apply { text = label; setOnClickListener { onClick() } }
        actionButtons.add(b)
        parent.addView(b)
    }

    private fun setActionsEnabled(connected: Boolean) {
        runOnUiThread {
            actionButtons.forEach { it.isEnabled = it.text.contains("Connecter") || connected }
        }
    }

    private fun saveConfig() {
        prefs().edit()
            .putString("mac", macField.text.toString().trim().uppercase())
            .putString("unlock", normHex(unlockField.text.toString()))
            .putString("lock", normHex(lockField.text.toString()))
            .apply()
        log("Config enregistrée.")
    }

    // ---------- Connexion ----------

    private fun connect() {
        val missing = arrayOf(
            android.Manifest.permission.BLUETOOTH_CONNECT,
            android.Manifest.permission.BLUETOOTH_SCAN,
        ).filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
        if (missing.isNotEmpty()) {
            pendingAction = { connect() }
            requestPermissions(missing.toTypedArray(), REQ_PERMS)
            return
        }
        val mac = cfg("mac")
        if (!isValidMac(mac)) { log("⚠️ Renseigne une MAC valide puis Enregistre."); return }
        if (!adapter.isEnabled) { log("⚠️ Bluetooth désactivé."); return }
        disconnect()
        log("Connexion à $mac …")
        val dev: BluetoothDevice = adapter.getRemoteDevice(mac)
        gatt = dev.connectGatt(this, false, gattCallback, BluetoothDevice.TRANSPORT_LE)
    }

    private fun disconnect() {
        gatt?.let { it.disconnect(); it.close() }
        gatt = null
        synchronized(ops) { ops.clear(); busy = false }
        setActionsEnabled(false)
    }

    override fun onRequestPermissionsResult(
        requestCode: Int, permissions: Array<out String>, grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQ_PERMS) {
            if (grantResults.isNotEmpty() && grantResults.all { it == PackageManager.PERMISSION_GRANTED })
                pendingAction?.invoke()
            else log("⚠️ Permissions Bluetooth refusées.")
            pendingAction = null
        }
    }

    private val gattCallback = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(g: BluetoothGatt, status: Int, newState: Int) {
            if (newState == BluetoothProfile.STATE_CONNECTED) {
                log("Connecté. Découverte des services…"); g.discoverServices()
            } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                log("Déconnecté (status=$status)."); setActionsEnabled(false)
            }
        }

        override fun onServicesDiscovered(g: BluetoothGatt, status: Int) {
            if (status == BluetoothGatt.GATT_SUCCESS && g.getService(SERVICE) != null) {
                log("✅ Service trouvé — prêt."); setActionsEnabled(true); doStatus()
            } else log("❌ Service introuvable (status=$status).")
        }

        override fun onCharacteristicWrite(g: BluetoothGatt, ch: BluetoothGattCharacteristic, status: Int) {
            log("  write ${shortUuid(ch.uuid)} status=$status ${if (status == 0) "OK" else "ÉCHEC"}")
            opDone()
        }

        override fun onCharacteristicRead(
            g: BluetoothGatt, ch: BluetoothGattCharacteristic, value: ByteArray, status: Int
        ) {
            if (status == BluetoothGatt.GATT_SUCCESS) handleRead(ch.uuid, value)
            else log("  read ${shortUuid(ch.uuid)} ÉCHEC status=$status")
            opDone()
        }
    }

    // ---------- Opérations (sérialisées) ----------

    private fun enqueue(op: () -> Unit) { synchronized(ops) { ops.add(op) }; drain() }

    private fun drain() {
        val next: (() -> Unit)?
        synchronized(ops) {
            if (busy) return
            next = ops.pollFirst()
            if (next == null) return
            busy = true
        }
        next?.invoke()
    }

    private fun opDone() { synchronized(ops) { busy = false }; drain() }

    private fun characteristic(uuid: UUID) = gatt?.getService(SERVICE)?.getCharacteristic(uuid)

    private fun writeHex(uuid: UUID, hex: String, label: String) {
        val bytes = hexToBytes(hex)
        if (bytes == null) { log("$label : valeur hexa manquante/invalide (config ?)"); return }
        enqueue {
            val ch = characteristic(uuid)
            if (ch == null || gatt == null) { log("$label : non connecté"); opDone(); return@enqueue }
            log("$label → ${bytes.toHex()}")
            gatt!!.writeCharacteristic(ch, bytes, BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT)
        }
    }

    private fun readCmd(uuid: UUID) = enqueue {
        val ch = characteristic(uuid)
        if (ch == null || gatt == null) { opDone(); return@enqueue }
        if (!gatt!!.readCharacteristic(ch)) opDone()
    }

    private fun doStatus() { log("— état —"); readCmd(CH_ODO); readCmd(CH_CMD); readCmd(CH_CFG) }

    private fun doBoot() {
        log("— BOOT : unlock puis débridage —")
        writeHex(CH_CMD, cfg("unlock"), "unlock")
        writeHex(CH_CFG, cfg("speed35", DEF_SPEED35), "débrider 35")
        readCmd(CH_CMD); readCmd(CH_CFG)
    }

    private fun handleRead(uuid: UUID, v: ByteArray) {
        when (uuid) {
            CH_ODO -> if (v.size >= 4) {
                val km = ((v[0].toLong() and 0xff) or ((v[1].toLong() and 0xff) shl 8) or
                    ((v[2].toLong() and 0xff) shl 16) or ((v[3].toLong() and 0xff) shl 24)) / 10.0
                log("  odomètre : $km km")
            }
            CH_CMD -> if (v.isNotEmpty())
                log("  compteur : ${v[0].toInt() and 0xff} allumages restants  (${v.toHex()})")
            CH_CFG -> if (v.size >= 2) {
                val x = (v[0].toInt() and 0xff) or ((v[1].toInt() and 0xff) shl 8)
                val tag = when ((x shr 8) and 0xff) {
                    0x50 -> "DÉBRIDÉ (~35)"; 0x4c, 0x0c -> "bridé (25)"
                    else -> "? octet-haut=0x%02x".format((x shr 8) and 0xff)
                }
                log("  config : ${v.toHex()}  →  $tag  (mode ${(x shr 6) and 3})")
            }
        }
    }

    // ---------- utilitaires ----------

    private fun shortUuid(u: UUID) = u.toString().substring(4, 8)
    private fun ByteArray.toHex() = joinToString(" ") { "%02x".format(it) }
    private fun normHex(s: String) = s.trim().lowercase().replace(" ", "").replace(":", "")
    private fun isValidMac(m: String) = Regex("^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$").matches(m)

    private fun hexToBytes(s: String): ByteArray? {
        val h = normHex(s)
        if (h.isEmpty() || h.length % 2 != 0) return null
        return try {
            ByteArray(h.length / 2) { h.substring(it * 2, it * 2 + 2).toInt(16).toByte() }
        } catch (e: Exception) { null }
    }

    private val tsFmt = SimpleDateFormat("HH:mm:ss", Locale.FRANCE)
    private fun log(msg: String) = runOnUiThread { logView.append("${tsFmt.format(Date())}  $msg\n") }

    override fun onDestroy() { super.onDestroy(); disconnect() }
}
