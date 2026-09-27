/**
 * Shared signup / onetime form handler.
 * Expects #register-form with data-endpoint and data-fail-message.
 */
(() => {
  const form = document.getElementById("register-form");
  if (!form) return;

  const endpoint = form.dataset.endpoint;
  const failMessage = form.dataset.failMessage || "Registration failed.";
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

    const username = usernameInput.value.trim();
    const email = document.getElementById("email").value.trim();
    const password = passwordInput.value;
    const passwordConfirm = confirmInput.value;

    if (!usernameCheck.isAvailable()) {
      Toast.error("Please choose an available username.");
      return;
    }
    if (!passwordCheck.isValid()) {
      Toast.error("Password does not meet the requirements.");
      return;
    }
    if (!passwordCheck.matchesConfirm()) {
      Toast.error("Passwords do not match.");
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
      Toast.flash("Account created. Please sign in.", "success");
      window.location.href = "/login/";
    } catch (err) {
      Toast.error(err.message || failMessage);
      refreshSubmit();
    }
  });
})();
