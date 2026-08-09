// Prepza service worker - v4 (explicit update flow)
//
// v2 stopped intercepting navigation requests entirely after v1's blanket
// interception (with no fallback) caused broken/blank pages on any brief
// network hiccup - indistinguishable from being logged out.
//
// v3 reintroduced navigation handling with a race + fallback chain (see
// handleNavigate below) and precached the app shell pages so navigation
// still resolves offline.
//
// v4 changes how *updates* to this file itself are rolled out. Previously
// install() called self.skipWaiting() unconditionally, so a new SW version
// took over as soon as it finished installing - silently, mid-session, with
// no user control. That's the same "surprise" failure mode as v1 in spirit:
// content changing under someone without warning. v4 instead lets a new
// worker install and sit in the "waiting" state. It only activates when the
// page explicitly asks it to (via postMessage({type: 'SKIP_WAITING'})),
// which sw-register.js sends after the user clicks an "Update" button in a
// toast. This keeps updates user-triggered and predictable.
//
// Navigation handling (race/fallback/offline.html) and cache-cleanup scope
// (only ever touching "prepza-shell-*", never "prepza-qna-offline-*") are
// unchanged from v3.

const SHELL_CACHE_NAME = 'prepza-shell-v4';
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
    })
    // Deliberately no self.skipWaiting() here - see v4 note above. This
    // worker now waits until the page explicitly tells it to take over.
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

// Lets sw-register.js hand control to a waiting worker on demand, once the
// user clicks "Update" in the toast, instead of this worker deciding on its
// own to activate.
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
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

  // Everything else (images, etc.) still gets a simple passthrough,
  // but falls back to a cached copy (if any) or a plain 503 instead
  // of leaving an unhandled rejection when the network hiccups.
  event.respondWith(
    fetch(event.request).catch(async () => {
      const cached = await caches.match(event.request, { ignoreSearch: true });
      if (cached) return cached;
      return new Response('', { status: 503, statusText: 'Network error' });
    })
  );
});
