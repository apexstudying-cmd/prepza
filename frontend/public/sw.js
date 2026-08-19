// Prepza service worker - v5 (React SPA shell)
//
// v4 history (navigation race/fallback, user-triggered update via
// postMessage SKIP_WAITING from sw-register.js) is unchanged - see that
// file for the update-toast flow. v5 only updates PRECACHE_URLS and the
// offline fallback path: the app is now a single-page React shell served
// at '/', so there's one shell page to precache instead of the old site's
// 7 separate static HTML pages.

const SHELL_CACHE_NAME = 'prepza-shell-v5';
const NAV_TIMEOUT_MS = 3000;

const PRECACHE_URLS = [
  '/',
  '/offline.html',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE_NAME).then((cache) => {
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
    const offline = await caches.match('/offline.html');
    if (offline) return offline;
    throw err;
  }
}

self.addEventListener('fetch', (event) => {
  if (event.request.mode === 'navigate') {
    event.respondWith(handleNavigate(event.request));
    return;
  }

  event.respondWith(
    fetch(event.request).catch(async () => {
      const cached = await caches.match(event.request, { ignoreSearch: true });
      if (cached) return cached;
      return new Response('', { status: 503, statusText: 'Network error' });
    })
  );
});
