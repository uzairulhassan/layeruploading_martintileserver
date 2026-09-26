/**
 * Security page: change password with live validation (same rules as register).
 */
(() => {
  const form = document.getElementById("password-form");
  const currentEl = document.getElementById("current_password");
  const newEl = document.getElementById("new_password");
  const confirmEl = document.getElementById("new_password_confirm");
  const statusEl = document.getElementById("password-form-status");
  const saveBtn = document.getElementById("password-save-btn");

  function setHint(text, state) {
    statusEl.textContent = text || "";
    statusEl.className = "field-hint" + (state ? ` is-${state}` : "");
  }

  const passwordCheck = Auth.bindPasswordCheck(newEl, confirmEl, updateSaveState);

  function updateSaveState() {
    const ready =
      Boolean(currentEl.value)
      && passwordCheck.isValid()
      && passwordCheck.matchesConfirm();
    saveBtn.disabled = !ready;
  }

  currentEl.addEventListener("input", () => {
    setHint("", "");
    updateSaveState();
  });

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (saveBtn.disabled) return;

    saveBtn.disabled = true;
    setHint("Updating password…", "pending");
    try {
      const response = await Auth.apiFetch("/api/auth/me/password/", {
        method: "POST",
        body: {
          current_password: currentEl.value,
          new_password: newEl.value,
          new_password_confirm: confirmEl.value,
        },
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        const message =
          body.current_password
            ? (Array.isArray(body.current_password) ? body.current_password[0] : body.current_password)
            : body.new_password
              ? (Array.isArray(body.new_password) ? body.new_password[0] : body.new_password)
              : body.new_password_confirm
                ? (Array.isArray(body.new_password_confirm) ? body.new_password_confirm[0] : body.new_password_confirm)
                : (body.detail || "Could not update password.");
        throw new Error(message);
      }
      form.reset();
      newEl.dispatchEvent(new Event("input"));
      confirmEl.dispatchEvent(new Event("input"));
      setHint("Password updated successfully.", "ok");
      updateSaveState();
    } catch (err) {
      setHint(err.message || "Could not update password.", "error");
      updateSaveState();
    }
  });

  updateSaveState();
})();
