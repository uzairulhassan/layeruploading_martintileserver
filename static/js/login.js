(function () {
  const form = document.getElementById("login-form");
  const redirectField = form.dataset.redirectField || "next";

  /** Same-app relative paths only; mirrors apps.core.login_redirect.resolve_post_login_path. */
  function resolvePostLoginPath(raw) {
    if (!raw || typeof raw !== "string") return "/";
    const path = raw.trim();
    if (!path.startsWith("/") || path.startsWith("//")) return "/";
    if (path.includes("://") || path.includes("\\")) return "/";
    const pathOnly = path.split("?", 1)[0];
    if (!pathOnly || pathOnly === "/") return "/";
    return path;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const username = document.getElementById("username").value.trim();
    const password = document.getElementById("password").value;
    const submitBtn = form.querySelector('button[type="submit"]');
    if (submitBtn) submitBtn.disabled = true;

    const destination = resolvePostLoginPath(
      new URLSearchParams(window.location.search).get(redirectField)
    );

    try {
      await Auth.login(username, password);
      Toast.flash("Signed in successfully.", "success");
      window.location.href = destination;
    } catch (err) {
      Toast.error(err.message || "Sign in failed.");
      if (submitBtn) submitBtn.disabled = false;
    }
  });
})();
