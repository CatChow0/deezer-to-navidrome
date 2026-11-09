package io.github.catchow0.d2n.data

import android.content.Context
import java.security.KeyStore
import com.google.crypto.tink.Aead
import com.google.crypto.tink.KeyTemplates
import com.google.crypto.tink.RegistryConfiguration
import com.google.crypto.tink.aead.AeadConfig
import com.google.crypto.tink.integration.android.AndroidKeysetManager
import java.util.Base64

/** Seals a secret for storage, and opens it again. */
interface SecretBox {
    fun seal(plain: String): String
    fun open(sealed: String): String

    /** Forgets the key, so the next seal makes a new one. */
    fun reset()
}

/**
 * AES-256-GCM, with a keyset itself wrapped by a key of the Android Keystore
 * that never leaves the phone: the sealed token is useless anywhere else.
 */
class TinkSecretBox(context: Context) : SecretBox {
    private val app = context.applicationContext
    private var aead: Aead? = null

    @Synchronized
    private fun aead(): Aead = aead ?: run {
        AeadConfig.register()
        AndroidKeysetManager.Builder()
            .withSharedPref(app, KEYSET, PREFS)
            .withKeyTemplate(KeyTemplates.get("AES256_GCM"))
            .withMasterKeyUri("android-keystore://$MASTER_KEY")
            .build()
            .keysetHandle
            .getPrimitive(RegistryConfiguration.get(), Aead::class.java)
            .also { aead = it }
    }

    override fun seal(plain: String): String =
        Base64.getEncoder().encodeToString(aead().encrypt(plain.toByteArray(Charsets.UTF_8), CONTEXT))

    override fun open(sealed: String): String =
        String(aead().decrypt(Base64.getDecoder().decode(sealed), CONTEXT), Charsets.UTF_8)

    /** A keyset copied from another phone cannot be opened here: forget it
     * and its Keystore key; the next seal makes new ones. */
    @Synchronized
    override fun reset() {
        aead = null
        app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().clear().commit()
        runCatching { KeyStore.getInstance("AndroidKeyStore").apply { load(null) }.deleteEntry(MASTER_KEY) }
    }

    private companion object {
        val CONTEXT = "d2n-session".toByteArray(Charsets.UTF_8)
        const val KEYSET = "d2n_keyset"
        const val PREFS = "d2n_keyset_prefs"
        const val MASTER_KEY = "d2n_master_key"
    }
}
