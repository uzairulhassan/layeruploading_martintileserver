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

  function bindPasswordToggles() {
    document.querySelectorAll("[data-password-toggle]").forEach((btn) => {
      const field = btn.closest(".password-field");
      const input = field?.querySelector("input");
      if (!input) return;
      const showIcon = btn.querySelector(".password-toggle-show");
      const hideIcon = btn.querySelector(".password-toggle-hide");

      btn.addEventListener("click", () => {
        const showing = input.type === "text";
        input.type = showing ? "password" : "text";
        btn.setAttribute("aria-label", showing ? "Show password" : "Hide password");
        btn.setAttribute("title", showing ? "Show password" : "Hide password");
        showIcon?.classList.toggle("hidden", !showing);
        hideIcon?.classList.toggle("hidden", showing);
      });
    });
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
      form.querySelectorAll(".password-field input").forEach((input) => {
        input.type = "password";
      });
      form.querySelectorAll("[data-password-toggle]").forEach((btn) => {
        btn.setAttribute("aria-label", "Show password");
        btn.setAttribute("title", "Show password");
        btn.querySelector(".password-toggle-show")?.classList.remove("hidden");
        btn.querySelector(".password-toggle-hide")?.classList.add("hidden");
      });
      newEl.dispatchEvent(new Event("input"));
      confirmEl.dispatchEvent(new Event("input"));
      Toast.success("Password updated successfully.");
      updateSaveState();
    } catch (err) {
      Toast.error(err.message || "Could not update password.");
      updateSaveState();
    }
  });

  bindPasswordToggles();
  updateSaveState();
})();
