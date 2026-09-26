/**
 * Shared signup / onetime form handler.
 * Expects #register-form with data-endpoint and data-fail-message.
 */
(() => {
  const form = document.getElementById("register-form");
  if (!form) return;

  const endpoint = form.dataset.endpoint;
  const failMessage = form.dataset.failMessage || "Registration failed.";
  const errorBox = document.getElementById("register-error");
  const submitBtn = document.getElementById("register-submit");
  const usernameInput = document.getElementById("username");
  const statusEl = document.getElementById("username-status");
  const passwordInput = document.getElementById("password");
  const confirmInput = document.getElementById("password_confirm");

  let usernameCheck = null;
  let passwordCheck = null;

  function refreshSubmit() {
    if (!usernameCheck || !passwordCheck) {
      submitBtn.disabled = true;
      return;
    }
    const ready =
      usernameCheck.isAvailable()
      && passwordCheck.isValid()
      && passwordCheck.matchesConfirm();
    submitBtn.disabled = !ready;
  }

  usernameCheck = Auth.bindUsernameCheck(usernameInput, statusEl, refreshSubmit);
  passwordCheck = Auth.bindPasswordCheck(passwordInput, confirmInput, refreshSubmit);
  refreshSubmit();

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorBox.classList.add("hidden");

    const username = usernameInput.value.trim();
    const email = document.getElementById("email").value.trim();
    const password = passwordInput.value;
    const passwordConfirm = confirmInput.value;

    if (!usernameCheck.isAvailable()) {
      errorBox.textContent = "Please choose an available username.";
      errorBox.classList.remove("hidden");
      return;
    }
    if (!passwordCheck.isValid()) {
      errorBox.textContent = "Password does not meet the requirements.";
      errorBox.classList.remove("hidden");
      return;
    }
    if (!passwordCheck.matchesConfirm()) {
      errorBox.textContent = "Passwords do not match.";
      errorBox.classList.remove("hidden");
      return;
    }

    submitBtn.disabled = true;
    try {
      await Auth.register(endpoint, {
        username,
        email,
        password,
        password_confirm: passwordConfirm,
      });
      window.location.href = "/";
    } catch (err) {
      errorBox.textContent = err.message || failMessage;
      errorBox.classList.remove("hidden");
      refreshSubmit();
    }
  });
})();
