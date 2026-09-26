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
  const usernameCheck = Auth.bindUsernameCheck(usernameInput, statusEl, submitBtn);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorBox.classList.add("hidden");

    const username = usernameInput.value.trim();
    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;
    const passwordConfirm = document.getElementById("password_confirm").value;

    if (!usernameCheck.isAvailable()) {
      errorBox.textContent = "Please choose an available username.";
      errorBox.classList.remove("hidden");
      return;
    }
    if (password !== passwordConfirm) {
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
      submitBtn.disabled = !usernameCheck.isAvailable();
    }
  });
})();
