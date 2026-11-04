// Copy this file to the public site's assets when the collector is live.
(() => {
  "use strict";
  const endpoint = document.currentScript?.dataset.endpoint;
  if (!endpoint || location.origin !== "https://b1axk-bit.github.io" ||
      !["/stillpoint-pages/", "/stillpoint-pages/index.html"].includes(location.pathname) ||
      navigator.globalPrivacyControl || navigator.doNotTrack === "1") return;

  function countView() {
    if (document.visibilityState !== "visible" || document.prerendering) return;
    document.removeEventListener("visibilitychange", countView);
    document.removeEventListener("prerenderingchange", countView);

    let body;
    try {
      const key = "stillpoint-traffic-day-v1";
      const day = new Date(Date.now() + 8 * 3600 * 1000).toISOString().slice(0, 10);
      const saved = (localStorage.getItem(key) || "").split(":");
      const browserId = saved[0] === day && saved[1] ? saved[1] : crypto.randomUUID();
      if (browserId !== saved[1]) localStorage.setItem(key, day + ":" + browserId);
      body = JSON.stringify({event_id: crypto.randomUUID(), browser_id: browserId});
    } catch {
      // Without a stable daily ID, skip the event rather than overcount visitors.
      return;
    }
    fetch(endpoint, {
      method: "POST",
      body,
      headers: {"Content-Type": "text/plain"},
      credentials: "omit",
      referrerPolicy: "no-referrer",
      keepalive: true
    }).catch(() => {});
  }

  document.addEventListener("visibilitychange", countView);
  document.addEventListener("prerenderingchange", countView);
  countView();
})();
