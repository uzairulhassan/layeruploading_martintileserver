/**
 * My Account page: avatar upload/remove + username/email with 30-day cooldown.
 * Identity fields start read-only; Edit unlocks them when the cooldown allows.
 */
(() => {
  const avatarEl = document.getElementById("account-avatar");
  const avatarInput = document.getElementById("avatar-input");
  const avatarRemoveBtn = document.getElementById("avatar-remove-btn");
  const form = document.getElementById("account-form");
  const usernameInput = document.getElementById("account-username");
  const emailInput = document.getElementById("account-email");
  const usernameStatus = document.getElementById("account-username-status");
  const emailStatus = document.getElementById("account-email-status");
  const usernameCooldown = document.getElementById("username-cooldown");
  const emailCooldown = document.getElementById("email-cooldown");
  const saveBtn = document.getElementById("account-save-btn");
  const typeBadge = document.getElementById("account-type-badge");
  const createdEl = document.getElementById("account-created");
  const editUsernameBtn = document.getElementById("edit-username-btn");
  const cancelUsernameBtn = document.getElementById("cancel-username-btn");
  const editEmailBtn = document.getElementById("edit-email-btn");
  const cancelEmailBtn = document.getElementById("cancel-email-btn");

  let profile = null;
  let editingUsername = false;
  let editingEmail = false;

  const usernameCheck = Auth.bindUsernameCheck(
    usernameInput,
    usernameStatus,
    updateSaveState,
    {
      currentUsername: usernameInput.value,
      availableMessage: "Available",
      takenMessage: "Not available",
      currentMessage: "Available",
    },
  );

  function clearHint(el) {
    if (!el) return;
    el.textContent = "";
    el.className = "field-hint";
  }

  function formatDate(iso) {
    if (!iso) return "—";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "—";
    return date.toLocaleDateString(undefined, {
      year: "numeric",
      month: "long",
      day: "numeric",
    });
  }

  function formatCooldown(iso) {
    if (!iso) return "";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "";
    return `Next change available ${date.toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    })}.`;
  }

  function initialsFromUsername(username) {
    return String(username || "?").trim().slice(0, 2).toUpperCase() || "?";
  }

  function renderAvatar(user) {
    if (!avatarEl) return;
    if (user.avatar_url) {
      avatarEl.innerHTML = `<img src="${Auth.escapeHtml(user.avatar_url)}" alt="">`;
    } else {
      avatarEl.innerHTML = `<span class="avatar-initials">${Auth.escapeHtml(initialsFromUsername(user.username))}</span>`;
    }
    avatarRemoveBtn?.classList.toggle("hidden", !user.avatar_url);
    Auth.syncHeaderAvatar(user);
  }

  function syncIdentityControls() {
    if (!profile) return;

    const canUser = Boolean(profile.can_change_username);
    const canEmail = Boolean(profile.can_change_email);

    usernameInput.readOnly = !editingUsername;
    emailInput.readOnly = !editingEmail;

    editUsernameBtn.classList.toggle("hidden", editingUsername || !canUser);
    cancelUsernameBtn.classList.toggle("hidden", !editingUsername);
    editEmailBtn.classList.toggle("hidden", editingEmail || !canEmail);
    cancelEmailBtn.classList.toggle("hidden", !editingEmail);

    if (!canUser) {
      usernameCooldown.hidden = false;
      usernameCooldown.textContent = formatCooldown(profile.next_username_change_at);
      if (!editingUsername) clearHint(usernameStatus);
    } else {
      usernameCooldown.hidden = true;
      usernameCooldown.textContent = "";
    }

    if (!canEmail) {
      emailCooldown.hidden = false;
      emailCooldown.textContent = formatCooldown(profile.next_email_change_at);
      if (!editingEmail) clearHint(emailStatus);
    } else {
      emailCooldown.hidden = true;
      emailCooldown.textContent = "";
    }

    if (!editingUsername) clearHint(usernameStatus);
    if (!editingEmail) clearHint(emailStatus);
  }

  function applyProfile(user) {
    profile = user;
    editingUsername = false;
    editingEmail = false;
    usernameInput.value = user.username || "";
    emailInput.value = user.email || "";
    usernameCheck.setCurrentUsername(user.username);
    renderAvatar(user);
    syncIdentityControls();

    if (typeBadge) {
      const isAdmin = user.account_type === "Admin" || user.is_staff;
      typeBadge.textContent = isAdmin ? "Admin" : "User";
      typeBadge.className = `account-badge ${isAdmin ? "is-admin" : "is-user"}`;
    }
    if (createdEl) createdEl.textContent = formatDate(user.date_joined);

    const nameEl = document.querySelector(".profile-meta-name");
    if (nameEl) nameEl.textContent = user.username;
    const emailEl = document.querySelector(".profile-meta-email");
    if (emailEl) {
      if (user.email) {
        emailEl.textContent = user.email;
        emailEl.hidden = false;
      } else {
        emailEl.hidden = true;
      }
    }

    updateSaveState();
  }

  function usernameOk() {
    if (!profile) return false;
    if (!editingUsername) return true;
    const value = usernameInput.value.trim();
    if (!value) return false;
    if (value.toLowerCase() === profile.username.toLowerCase()) return true;
    return Boolean(usernameCheck.isAvailable());
  }

  function emailOk() {
    if (!profile) return false;
    if (!editingEmail) return true;
    const value = emailInput.value.trim();
    return Boolean(value) && value.includes("@");
  }

  function hasChanges() {
    if (!profile) return false;
    const usernameChanged =
      editingUsername
      && usernameInput.value.trim().toLowerCase() !== profile.username.toLowerCase();
    const emailChanged =
      editingEmail
      && emailInput.value.trim().toLowerCase() !== (profile.email || "").toLowerCase();
    return usernameChanged || emailChanged;
  }

  function updateSaveState() {
    const ready = hasChanges() && usernameOk() && emailOk();
    saveBtn.disabled = !ready;
  }

  function startEditUsername() {
    if (!profile?.can_change_username) return;
    editingUsername = true;
    syncIdentityControls();
    usernameInput.focus();
    usernameInput.select();
    usernameInput.dispatchEvent(new Event("input"));
    updateSaveState();
  }

  function cancelEditUsername() {
    editingUsername = false;
    usernameInput.value = profile?.username || "";
    clearHint(usernameStatus);
    syncIdentityControls();
    updateSaveState();
  }

  function startEditEmail() {
    if (!profile?.can_change_email) return;
    editingEmail = true;
    syncIdentityControls();
    emailInput.focus();
    emailInput.select();
    updateSaveState();
  }

  function cancelEditEmail() {
    editingEmail = false;
    emailInput.value = profile?.email || "";
    clearHint(emailStatus);
    syncIdentityControls();
    updateSaveState();
  }

  async function loadProfile() {
    const response = await Auth.apiFetch("/api/auth/me/");
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      Toast.error(Toast.fromApiBody(body, "Could not load profile."));
      return;
    }
    applyProfile(body);
  }

  avatarInput?.addEventListener("change", async () => {
    const file = avatarInput.files?.[0];
    if (!file) return;
    const allowedTypes = ["image/jpeg", "image/png"];
    const name = (file.name || "").toLowerCase();
    const hasAllowedExt = name.endsWith(".jpg") || name.endsWith(".jpeg") || name.endsWith(".png");
    if ((file.type && !allowedTypes.includes(file.type)) || (!file.type && !hasAllowedExt)) {
      Toast.error("Use a JPG or PNG image.");
      avatarInput.value = "";
      return;
    }
    const data = new FormData();
    data.append("avatar", file);
    try {
      const response = await Auth.apiFetch("/api/auth/me/avatar/", {
        method: "POST",
        body: data,
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(Toast.fromApiBody(body, "Upload failed."));
      }
      applyProfile(body);
      Toast.success("Profile photo updated.");
    } catch (err) {
      Toast.error(err.message || "Upload failed.");
    } finally {
      avatarInput.value = "";
    }
  });

  avatarRemoveBtn?.addEventListener("click", async () => {
    try {
      const response = await Auth.apiFetch("/api/auth/me/avatar/", { method: "DELETE" });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(Toast.fromApiBody(body, "Could not remove photo."));
      }
      applyProfile(body);
      Toast.success("Profile photo removed.");
    } catch (err) {
      Toast.error(err.message || "Could not remove photo.");
    }
  });

  editUsernameBtn?.addEventListener("click", startEditUsername);
  cancelUsernameBtn?.addEventListener("click", cancelEditUsername);
  editEmailBtn?.addEventListener("click", startEditEmail);
  cancelEmailBtn?.addEventListener("click", cancelEditEmail);

  emailInput.addEventListener("input", () => {
    if (!editingEmail) return;
    clearHint(emailStatus);
    updateSaveState();
  });

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (saveBtn.disabled || !profile) return;

    const payload = {};
    const nextUsername = usernameInput.value.trim();
    const nextEmail = emailInput.value.trim();
    if (editingUsername && nextUsername.toLowerCase() !== profile.username.toLowerCase()) {
      payload.username = nextUsername;
    }
    if (editingEmail && nextEmail.toLowerCase() !== (profile.email || "").toLowerCase()) {
      payload.email = nextEmail;
    }
    if (!Object.keys(payload).length) return;

    saveBtn.disabled = true;
    try {
      const response = await Auth.apiFetch("/api/auth/me/", {
        method: "PATCH",
        body: payload,
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(Toast.fromApiBody(body, "Could not save changes."));
      }
      applyProfile(body);
      Toast.success("Account updated.");
    } catch (err) {
      Toast.error(err.message || "Could not save changes.");
      updateSaveState();
    }
  });

  document.addEventListener("DOMContentLoaded", () => {
    loadProfile().catch(() => {
      Toast.error("Could not load profile.");
    });
  });
})();
