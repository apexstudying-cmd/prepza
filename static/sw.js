// Prepza service worker - v2 (interim reliability fix)
//
// v1 intercepted EVERY request, including page navigations, with no error
// handling. If that single fetch attempt hiccuped for any reason (a brief
// connection blip, a slow moment), the whole page load failed outright with
// no fallback - showing a broken/blank page. That looked exactly like being
// logged out, even though no session/cookie was ever touched.
//
// This version stops intercepting navigation requests entirely - those are
// left alone for the browser to handle exactly as it would with no service
// worker present, removing that failure point. Non-navigation requests
// (images, etc.) still get a passthrough, unchanged from v1.
//
// Proper offline support (caching Q&A documents and app pages so they work
// without a connection) is still the planned next step - this version is
// just a safety fix in the meantime, not that feature.

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  // Page navigations (loading/reloading/reopening a page) are left
  // completely alone - don't call respondWith at all, so the browser
  // handles them natively with its own retry/error behavior.
  if (event.request.mode === "navigate") {
    return;
  }

  // Everything else (images, etc.) still gets a simple passthrough.
  event.respondWith(fetch(event.request));
});
