// Prepza service worker - v6
// v6 forces activation of the newest shell so users do not stay on a stale
// React bundle after a deployment containing navigation/UI fixes.

const SHELL_CACHE_NAME = 'prepza-shell-v6';
const NAV_TIMEOUT_MS = 3000;

const PRECACHE_URLS = ['/', '/offline.html'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE_NAME).then((cache) =>
      Promise.all(
        PRECACHE_URLS.map((url) =>
          fetch(url)
            .then((res) => {
              if (res.ok) return cache.put(url, res);
            })
            .catch(() => {})
        )
      )
    ).then(() => self.skipWaiting())
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
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
});

function timeout(ms) {
  return new Promise((_, reject) => setTimeout(() => reject(new Error('nav-timeout')), ms));
}

async function handleNavigate(request) {
  const networkPromise = fetch(request)
    .then((res) => {
      if (res && res.ok) {
        caches.open(SHELL_CACHE_NAME).then((cache) => cache.put(request, res.clone())).catch(() => {});
      }
      return res;
    })
    .catch(() => undefined);

  try {
    const res = await Promise.race([networkPromise, timeout(NAV_TIMEOUT_MS)]);
    if (res) return res;
    throw new Error('network-failed');
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

self.addEventListener('push', (event) => {
  let payload = { title: 'Prepza', body: '' };
  try {
    if (event.data) payload = event.data.json();
  } catch (err) {
    payload.body = event.data ? event.data.text() : '';
  }
  event.waitUntil(self.registration.showNotification(payload.title || 'Prepza', { body: payload.body || '' }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientsList) => {
      for (const client of clientsList) {
        if ('focus' in client) return client.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow('/');
    })
  );
});
