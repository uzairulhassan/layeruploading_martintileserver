/**
 * Reliable auth background video: force muted autoplay and fade in once a frame is ready.
 */
(() => {
  const video = document.getElementById("auth-bg-video");
  if (!video) return;

  let revealed = false;
  let playAttempts = 0;

  function reveal() {
    if (revealed || video.classList.contains("is-failed")) return;
    revealed = true;
    video.classList.add("is-ready");
  }

  function armMutedInline() {
    video.muted = true;
    video.defaultMuted = true;
    video.playsInline = true;
    video.setAttribute("muted", "");
    video.setAttribute("playsinline", "");
  }

  async function ensurePlaying() {
    armMutedInline();
    if (!video.paused) {
      if (video.readyState >= 2) reveal();
      return;
    }
    playAttempts += 1;
    try {
      await video.play();
      if (video.readyState >= 2) reveal();
    } catch (err) {
      if (playAttempts < 6) setTimeout(ensurePlaying, 400 * playAttempts);
    }
  }

  function onReady() {
    if (video.readyState >= 2) reveal();
    ensurePlaying();
  }

  video.addEventListener("loadeddata", onReady);
  video.addEventListener("canplay", onReady);
  video.addEventListener("playing", reveal);
  video.addEventListener("error", () => video.classList.add("is-failed"));
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) ensurePlaying();
  });
  window.addEventListener("pageshow", ensurePlaying);
  document.addEventListener("pointerdown", ensurePlaying, { once: true, passive: true });

  armMutedInline();
  try {
    video.load();
  } catch (err) {
    // ignore
  }
  if (video.readyState >= 2) onReady();
  else ensurePlaying();

  setTimeout(() => {
    if (video.readyState >= 2) {
      reveal();
      ensurePlaying();
    }
  }, 1200);
})();
