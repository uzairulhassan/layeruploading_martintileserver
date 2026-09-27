document.getElementById("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();

  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value;
  const submitBtn = event.target.querySelector('button[type="submit"]');
  if (submitBtn) submitBtn.disabled = true;

  try {
    await Auth.login(username, password);
    Toast.flash("Signed in successfully.", "success");
    window.location.href = "/";
  } catch (err) {
    Toast.error(err.message || "Sign in failed.");
    if (submitBtn) submitBtn.disabled = false;
  }
});
