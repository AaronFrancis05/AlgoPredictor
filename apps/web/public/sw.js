// AlgoPredict service worker: shows notifications and opens their link when tapped.
// It has no fetch handler and caches nothing, so it never changes what pages load.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const raw = event.notification.data && event.notification.data.link;
  const path = typeof raw === "string" && raw.startsWith("/") && !raw.startsWith("//") ? raw : "/dashboard";
  const url = new URL(path, self.location.origin).href;
  event.waitUntil((async () => {
    const tabs = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    const tab = tabs.find((c) => new URL(c.url).origin === self.location.origin);
    if (tab) {
      await tab.focus();
      if ("navigate" in tab) {
        try {
          await tab.navigate(url);
          return;
        } catch {
          // an uncontrolled tab cannot be navigated from here: open a new one
        }
      } else {
        return;
      }
    }
    await self.clients.openWindow(url);
  })());
});
