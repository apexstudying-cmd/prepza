// Prepza service worker - v1 (basic install support only)
//
// This is intentionally minimal for now: it just registers and passes every
// request straight through to the network, unmodified. Its only job right
// now is to satisfy the requirement that makes Chrome/Android treat Prepza
// as an installable app.
//
// Q&A offline caching logic (so purchased Q&A documents stay viewable
// without a connection after first being opened) will be added here as a
// separate, deliberate follow-up step - not bundled into this first version,
// so each piece can be tested on its own.

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  event.respondWith(fetch(event.request));
});
