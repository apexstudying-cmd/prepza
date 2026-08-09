// Prepza service worker - v3 (offline page navigation)
//
// v2 stopped intercepting navigation requests entirely after v1's blanket
// interception (with no fallback) caused broken/blank pages on any brief
// network hiccup - indistinguishable from being logged out.
//
// v3 reintroduces navigation handling, but deliberately never blocks on a
// single fetch attempt with no fallback:
//   1. Race the network fetch against a short timeout. Whichever settles
//      first is used.
//   2. If the network wins, use it, and also refresh the cached copy of
//      that page in the background for next time (the network fetch keeps
//      running even after the race settles, so a slow-but-eventually-
//      successful response still updates the cache).
//   3. If the timeout wins, or the network fetch fails outright, fall back
//      to the cached copy of that page (ignoring any query string, since
//      unit.html?id=X and viewer.html?id=X share one cached shell).
//   4. If nothing is cached either, fall back to a small offline.html page
//      instead of leaving the request unresolved.
//   5. Only if even offline.html isn't cached does this re-throw, letting
//      the browser show its own native offline error - matching v2's
//      "never fail silently and never fail to resolve" principle.
//
// Non-navigation requests (images, API calls, etc.) are untouched - simple
// passthrough, same as v2. The separate "prepza-qna-offline-*" cache used
// by viewer.html's Save Offline feature is never read or deleted here -
// activate() only ever cleans up caches prefixed "prepza-shell-".

const SHELL_CACHE_NAME = 'prepza-shell-v3';
const NAV_TIMEOUT_MS = 3000;

const PRECACHE_URLS = [
  '/static/dashboard.html',
  '/static/my-library.html',
  '/static/payment-history.html',
  '/static/unit.html',
  '/static/settings.html',
  '/static/viewer.html',
  '/static/offline.html',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE_NAME).then((cache) => {
      // Best-effort: one URL failing (e.g. a page renamed later) shouldn't
      // block the rest from being cached.
      return Promise.all(
        PRECACHE_URLS.map((url) =>
          fetch(url)
            .then((res) => {
              if (res.ok) return cache.put(url, res);
            })
            .catch(() => {})
        )
      );
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(
        names
          .filter((name) => name.indexOf('prepza-shell-') === 0 && name !== SHELL_CACHE_NAME)
          .map((name) => caches.delete(name))
      )
    ).then(() => self.clients.claim())
  );
});

function timeout(ms) {
  return new Promise((_, reject) => setTimeout(() => reject(new Error('nav-timeout')), ms));
}

async function handleNavigate(request) {
  const networkPromise = fetch(request).then((res) => {
    if (res && res.ok) {
      caches.open(SHELL_CACHE_NAME).then((cache) => cache.put(request, res.clone())).catch(() => {});
    }
    return res;
  });

  try {
    return await Promise.race([networkPromise, timeout(NAV_TIMEOUT_MS)]);
  } catch (err) {
    const cached = await caches.match(request, { ignoreSearch: true });
    if (cached) return cached;
    const offline = await caches.match('/static/offline.html');
    if (offline) return offline;
    throw err;
  }
}

self.addEventListener('fetch', (event) => {
  if (event.request.mode === 'navigate') {
    event.respondWith(handleNavigate(event.request));
    return;
  }

  // Everything else (images, etc.) still gets a simple passthrough.
  event.respondWith(fetch(event.request));
});
