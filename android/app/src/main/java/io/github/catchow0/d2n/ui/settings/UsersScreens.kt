package io.github.catchow0.d2n.ui.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.R
import io.github.catchow0.d2n.data.AppUser
import io.github.catchow0.d2n.data.HeirRequest
import io.github.catchow0.d2n.data.NewPassword
import io.github.catchow0.d2n.data.NewUser
import io.github.catchow0.d2n.data.UserChange
import io.github.catchow0.d2n.data.UserRow
import io.github.catchow0.d2n.data.UsersAnswer
import io.github.catchow0.d2n.ui.common.D2nViewModel
import io.github.catchow0.d2n.ui.common.Notice
import io.github.catchow0.d2n.ui.common.Remote
import io.github.catchow0.d2n.ui.common.ScreenDeps
import io.github.catchow0.d2n.ui.components.ButtonKind
import io.github.catchow0.d2n.ui.components.ChoiceField
import io.github.catchow0.d2n.ui.components.Chip
import io.github.catchow0.d2n.ui.components.ChipTone
import io.github.catchow0.d2n.ui.components.ConfirmDialog
import io.github.catchow0.d2n.ui.components.D2nButton
import io.github.catchow0.d2n.ui.components.D2nTextField
import io.github.catchow0.d2n.ui.components.GlassCard
import io.github.catchow0.d2n.ui.components.IconAction
import io.github.catchow0.d2n.ui.components.LocalOnline
import io.github.catchow0.d2n.ui.components.ScreenScaffold
import io.github.catchow0.d2n.ui.components.plural
import io.github.catchow0.d2n.ui.components.remote
import io.github.catchow0.d2n.ui.theme.D2nColors
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Settings → Users (Admins): the accounts of this app. What each button may do
 * comes from the server (core/users.can), which checks it again. */
class UsersViewModel(deps: ScreenDeps) : D2nViewModel(deps) {
    private val _state = MutableStateFlow(Remote<UsersAnswer>())
    val state: StateFlow<Remote<UsersAnswer>> = _state

    private val _code = MutableStateFlow<Pair<String, String>?>(null)

    /** A recovery code just made, with the username it is for: shown once. */
    val code: StateFlow<Pair<String, String>?> = _code

    private val _formDone = MutableStateFlow(0)
    val formDone: StateFlow<Int> = _formDone

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch { _state.fill { users() } }
    }

    private fun keep(answer: UsersAnswer) {
        _state.value = Remote(answer, loading = false)
        _formDone.update { it + 1 }
    }

    fun create(username: String, password: String, role: String) =
        act("save", { createUser(NewUser(username.trim(), password, role)) }, done = { Notice("Account added: give them the temporary password") }, after = ::keep)

    /** The username and privilege, then a temporary password when one is typed. */
    fun save(user: UserRow, username: String, role: String, password: String) = act(
        "save",
        {
            if (password.isNotEmpty()) setUserPassword(user.id, NewPassword(password))
            updateUser(user.id, UserChange(username.trim().takeIf { it != user.username }, role.takeIf { it != user.role }))
        },
        done = { Notice("Account saved") },
        after = ::keep,
    )

    fun newRecoveryCode(user: UserRow) =
        act("recovery-${user.id}", { newUserRecoveryCode(user.id) }, after = { _code.value = user.username to it.code })

    fun closeCode() {
        _code.value = null
    }

    fun delete(user: UserRow, heir: String?) =
        act("delete-${user.id}", { deleteUser(user.id, HeirRequest(heir.orEmpty())) }, done = { Notice("${user.username} removed") }, after = ::keep)
}

private val ROLE_CHOICES = listOf(AppUser.STANDARD to "Standard", AppUser.ADMIN to "Admin")

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun UsersScreen(vm: UsersViewModel, onBack: () -> Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val code by vm.code.collectAsStateWithLifecycle()
    val formDone by vm.formDone.collectAsStateWithLifecycle()
    val online = LocalOnline.current
    var adding by remember { mutableStateOf(false) }
    var editing by remember { mutableStateOf<UserRow?>(null) }
    var removing by remember { mutableStateOf<UserRow?>(null) }
    LaunchedEffect(formDone) {
        adding = false
        editing = null
        removing = null
    }
    ScreenScaffold(
        title = "Users",
        onBack = onBack,
        actions = { IconAction(R.drawable.ic_add, "Add an account", { adding = true }, enabled = online) },
        refreshing = state.refreshing,
        onRefresh = vm::refresh,
    ) {
        item(key = "lead") {
            Text(
                "Who signs in here. An Admin manages the Standard accounts, and only the Super-Admin the Admins. The Super-Admin, made at the first start, cannot be removed.",
                style = MaterialTheme.typography.bodySmall,
                color = D2nColors.Muted,
            )
        }
        remote(state, onRetry = vm::refresh, skeletons = 3, skeletonHeight = 96.dp) { answer ->
            items(answer.users, key = { it.id }) { user ->
                GlassCard(Modifier.fillMaxWidth()) {
                    Text(user.username + if (user.id == answer.me) " (you)" else "", style = MaterialTheme.typography.titleMedium)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Chip(user.roleLabel, tone = if (user.role == AppUser.STANDARD) ChipTone.Idle else ChipTone.Info)
                        if (user.mustChange) Chip("Must choose a password", tone = ChipTone.Partial)
                    }
                    Text(
                        "${plural(user.navidromeAccounts, "Navidrome account")} · ${plural(user.deezerAccounts, "Deezer account")}",
                        style = MaterialTheme.typography.bodySmall,
                        color = D2nColors.Muted,
                    )
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        D2nButton("Edit", { editing = user }, kind = ButtonKind.Ghost, small = true, enabled = online && user.can.edit)
                        if (user.id != answer.me && user.can.edit) {
                            D2nButton("Recovery code", { vm.newRecoveryCode(user) }, kind = ButtonKind.Ghost, small = true, enabled = online && "recovery-${user.id}" !in busy)
                        }
                        D2nButton("Delete", { removing = user }, kind = ButtonKind.Danger, small = true, enabled = online && user.can.delete)
                    }
                }
            }
        }
    }
    val users = state.value?.users.orEmpty()
    if (adding || editing != null) {
        UserForm(editing, state.value?.me.orEmpty(), "save" in busy, onDismiss = {
            adding = false
            editing = null
        }) { username, role, password ->
            editing?.let { vm.save(it, username, role, password) } ?: vm.create(username, password, role)
        }
    }
    removing?.let { user -> DeleteUserSheet(user, users.filter { it.id != user.id }, "delete-${user.id}" in busy, { removing = null }) { heir -> vm.delete(user, heir) } }
    code?.let { (username, value) ->
        ConfirmDialog(
            "Recovery code for $username",
            "$value\n\nGive it to them: with it, they choose a new password on the sign-in screen. Their old code stops working. It is shown only now.",
            "Done",
            vm::closeCode,
            vm::closeCode,
            danger = false,
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun Sheet(onDismiss: () -> Unit, content: @Composable () -> Unit) {
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = D2nColors.Ink2,
        contentColor = D2nColors.Text,
    ) {
        Column(
            Modifier.fillMaxWidth().navigationBarsPadding().imePadding().padding(horizontal = 24.dp).padding(bottom = 16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) { content() }
    }
}

/** A new account (temporary password), or one to edit: username, privilege as
 * the asker may give it, and a temporary password for someone else. */
@Composable
private fun UserForm(user: UserRow?, me: String, busy: Boolean, onDismiss: () -> Unit, onSave: (String, String, String) -> Unit) {
    var username by remember { mutableStateOf(user?.username.orEmpty()) }
    var role by remember { mutableStateOf(user?.role ?: AppUser.STANDARD) }
    var password by remember { mutableStateOf("") }
    val canRole = user == null || (user.role != AppUser.SUPERADMIN && (user.can.promote || user.can.demote))
    val canPassword = user == null || (user.id != me && !user.fromEnv)
    Sheet(onDismiss) {
        Text(if (user != null) "Edit ${user.username}" else "New account", Modifier.semantics { heading() }, style = MaterialTheme.typography.titleMedium)
        D2nTextField(username, { username = it }, "Username", enabled = user?.fromEnv != true)
        if (canRole) ChoiceField("Privilege", ROLE_CHOICES, role, { role = it })
        if (canPassword) {
            D2nTextField(
                password, { password = it }, "Temporary password", password = true,
                placeholder = if (user != null) "Leave empty to keep it" else null,
                supporting = if (user == null) "Give it to them: they choose their own at the first sign-in." else "They choose their own at the next sign-in; their devices are signed out.",
            )
        }
        val ready = username.isNotBlank() && (if (user == null) password.length >= 8 else password.isEmpty() || password.length >= 8)
        D2nButton(if (busy) "Saving…" else if (user != null) "Save" else "Add the account", { onSave(username, role, password) }, Modifier.fillMaxWidth(), enabled = !busy && ready)
    }
}

/** Deleting an account: its Navidrome and Deezer accounts go to another one, or with it. */
@Composable
private fun DeleteUserSheet(user: UserRow, heirs: List<UserRow>, busy: Boolean, onDismiss: () -> Unit, onDelete: (String?) -> Unit) {
    var heir by remember { mutableStateOf<String?>(heirs.firstOrNull()?.id) }
    var sure by remember { mutableStateOf(false) }
    Sheet(onDismiss) {
        Text("Remove ${user.username}?", Modifier.semantics { heading() }, style = MaterialTheme.typography.titleMedium)
        Text(
            "Their ${plural(user.navidromeAccounts, "Navidrome account")} and ${plural(user.deezerAccounts, "Deezer account")}, and their devices are signed out. This cannot be undone.",
            style = MaterialTheme.typography.bodySmall,
            color = D2nColors.Muted,
        )
        ChoiceField(
            "Their accounts",
            heirs.map<UserRow, Pair<String?, String>> { it.id to "Give them to ${it.username}" } + (null to "Remove them, with their playlists"),
            heir,
            { heir = it },
        )
        if (sure) {
            D2nButton(if (busy) "Removing…" else "Remove ${user.username} for good", { onDelete(heir) }, Modifier.fillMaxWidth(), kind = ButtonKind.Danger, enabled = !busy)
        } else {
            D2nButton("Remove ${user.username}", { sure = true }, Modifier.fillMaxWidth(), kind = ButtonKind.Danger)
        }
    }
}
