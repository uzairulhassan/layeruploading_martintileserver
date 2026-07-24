document.getElementById("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const errorBox = document.getElementById("login-error");
  errorBox.classList.add("hidden");

  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value;

  try {
    await Auth.login(username, password);
    window.location.href = "/";
  } catch (err) {
    errorBox.textContent = err.message || "Sign in failed.";
    errorBox.classList.remove("hidden");
  }
});
