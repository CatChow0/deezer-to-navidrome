package io.github.catchow0.d2n.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// The accounts of the app (docs/api/openapi.yaml: /me, /auth/first-password,
// /auth/forgot, /users): Super-Admin, Admins and Standard accounts.

@Serializable
data class AppUser(
    val id: String = "",
    val username: String = "",
    val role: String = STANDARD,
    @SerialName("must_change") val mustChange: Boolean = false,
    @SerialName("from_env") val fromEnv: Boolean = false,
) {
    val roleLabel: String get() = ROLE_LABELS[role] ?: role

    companion object {
        const val SUPERADMIN = "superadmin"
        const val ADMIN = "admin"
        const val STANDARD = "standard"
        val ROLE_LABELS = mapOf(SUPERADMIN to "Super-Admin", ADMIN to "Admin", STANDARD to "Standard")
    }
}

@Serializable
data class NewPassword(val password: String, val device: String? = null)

@Serializable
data class ForgotRequest(val username: String, val code: String, val password: String)

/** /auth/forgot: the account's next recovery code, shown once. */
@Serializable
data class ForgotAnswer(@SerialName("recovery_code") val recoveryCode: String = "")

/** /auth/forgot/superadmin: the file written in the server's data folder. */
@Serializable
data class SuperAdminCode(val file: String = "", val minutes: Int = 15)

/** A new recovery code, for yourself or for an account an Admin manages. */
@Serializable
data class CodeAnswer(val code: String = "")

/** What the asker may do to this account (core/users.can on the server). */
@Serializable
data class UserRights(
    val edit: Boolean = false,
    val delete: Boolean = false,
    val promote: Boolean = false,
    val demote: Boolean = false,
)

@Serializable
data class UserRow(
    val id: String,
    val username: String = "",
    val role: String = AppUser.STANDARD,
    @SerialName("must_change") val mustChange: Boolean = false,
    @SerialName("from_env") val fromEnv: Boolean = false,
    @SerialName("navidrome_accounts") val navidromeAccounts: Int = 0,
    @SerialName("deezer_accounts") val deezerAccounts: Int = 0,
    val can: UserRights = UserRights(),
) {
    val roleLabel: String get() = AppUser.ROLE_LABELS[role] ?: role
}

@Serializable
data class UsersAnswer(val users: List<UserRow> = emptyList(), val me: String = "")

@Serializable
data class UserName(val id: String, val username: String = "")

@Serializable
data class UserNamesAnswer(val users: List<UserName> = emptyList())

@Serializable
data class NewUser(val username: String, val password: String, val role: String)

@Serializable
data class UserChange(val username: String? = null, val role: String? = null)

/** Deleting an account: its Navidrome and Deezer accounts go to `heir`, or are removed with it when empty. */
@Serializable
data class HeirRequest(val heir: String = "")

@Serializable
data class UsersRequest(val users: List<String>)

@Serializable
data class ProfilesRequest(val profiles: List<String>)

@Serializable
data class CatboardAnswer(@SerialName("catboard_profiles") val catboardProfiles: List<String> = emptyList())

@Serializable
data class ProfilesCleared(val cleared: Int = 0, val what: String = "")
