/**
 * Security page: change password with live validation (same rules as register).
 */
(() => {
  const form = document.getElementById("password-form");
  const currentEl = document.getElementById("current_password");
  const newEl = document.getElementById("new_password");
  const confirmEl = document.getElementById("new_password_confirm");
  const saveBtn = document.getElementById("password-save-btn");

  const passwordCheck = Auth.bindPasswordCheck(newEl, confirmEl, updateSaveState);

  function updateSaveState() {
    const ready =
      Boolean(currentEl.value)
      && passwordCheck.isValid()
      && passwordCheck.matchesConfirm();
    saveBtn.disabled = !ready;
  }

  currentEl.addEventListener("input", updateSaveState);

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (saveBtn.disabled) return;

    saveBtn.disabled = true;
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
        throw new Error(Toast.fromApiBody(body, "Could not update password."));
      }
      form.reset();
      newEl.dispatchEvent(new Event("input"));
      confirmEl.dispatchEvent(new Event("input"));
      Toast.success("Password updated successfully.");
      updateSaveState();
    } catch (err) {
      Toast.error(err.message || "Could not update password.");
      updateSaveState();
    }
  });

  updateSaveState();
})();
