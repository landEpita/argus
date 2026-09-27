/* Argus service worker: shows alerts pushed by the server, even when Argus is closed. */
self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { title: "Argus alert", body: event.data ? event.data.text() : "" };
  }
  const glyph = data.severity === "critical" ? "■ " : data.severity === "warning" ? "▲ " : "";
  event.waitUntil(
    self.registration.showNotification(`${glyph}${data.title || "Argus alert"}`, {
      body: data.body || "",
      tag: data.tag,
      icon: "/icon.svg",
      data: { url: data.url || "/" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data?.url || "/", self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      const open = windows.find((w) => w.url.startsWith(self.location.origin));
      if (open) {
        open.navigate(url);
        return open.focus();
      }
      return self.clients.openWindow(url);
    }),
  );
});
