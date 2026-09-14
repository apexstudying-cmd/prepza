// Prepza application-shell service worker.
// Keep the shell network-first so a bad cached HTML document can never pin a
// production release. Runtime asset caching remains opt-in and versioned.
const SW_VERSION = 'v12';
const SHELL_CACHE = `prepza-shell-${SW_VERSION}`;
const RUNTIME_CACHE = `prepza-runtime-${SW_VERSION}`;
const NAV_TIMEOUT_MS = 1800;
const STUDY_ASSET_CACHE = 'prepza-study-assets-v1';
const PDFJS_HOST = 'cdn.jsdelivr.net';
const PDFJS_PATH_PREFIX = '/npm/pdfjs-dist@6.3.289/build/';

const CORE_SHELL = ['/offline.html', '/manifest.json', '/icon-192.png', '/icon-512.png'];

function sameOrigin(url) { return url.origin === self.location.origin; }
function isPdfJsAsset(url) { return url.hostname === PDFJS_HOST && url.pathname.startsWith(PDFJS_PATH_PREFIX); }
function isNativeStudyPage(url) {
  return sameOrigin(url) && /^\/documents\/\d+\/reading\/page\/\d+$/.test(url.pathname);
}

function isCacheableAsset(request) {
  if (request.method !== 'GET') return false;
  const url = new URL(request.url);
  if (url.pathname === '/sw.js' || url.pathname === '/sw-register.js') return false;
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/socket.io/')) return false;
  if (isPdfJsAsset(url)) return /\.(?:js|mjs|map)$/i.test(url.pathname);
  if (isNativeStudyPage(url)) return true;
  if (!sameOrigin(url)) return false;
  return url.pathname.startsWith('/assets/') ||
    /\.(?:css|js|mjs|png|jpg|jpeg|webp|gif|svg|ico|woff2?|ttf|otf)$/i.test(url.pathname);
}

async function cacheResponse(cacheName, request, response) {
  if (!response || (!response.ok && response.type !== 'opaque')) return response;
  try { const cache = await caches.open(cacheName); await cache.put(request, response.clone()); } catch (_) {}
  return response;
}

async function precacheShell() {
  const cache = await caches.open(SHELL_CACHE);
  await Promise.all(CORE_SHELL.map(async (url) => {
    try { const response = await fetch(url, { cache: 'no-store' }); if (response.ok) await cache.put(url, response); } catch (_) {}
  }));
}

self.addEventListener('install', (event) => {
  event.waitUntil(precacheShell().then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((names) => Promise.all(
      names
        .filter((name) => name.startsWith('prepza-') &&
          name !== SHELL_CACHE &&
          name !== RUNTIME_CACHE)
        .map((name) => caches.delete(name)),
    )).then(() => self.clients.claim()),
  );
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
  if (event.data && event.data.type === 'CLEAR_STUDY_ASSETS') {
    event.waitUntil(caches.delete(STUDY_ASSET_CACHE));
  }
});

function timeout(ms) { return new Promise((_, reject) => setTimeout(() => reject(new Error('nav-timeout')), ms)); }

async function handleNavigation(request) {
  // Never serve a cached app shell before giving the network a chance. This is
  // the critical recovery path after a frontend rollback or failed release.
  const network = fetch(request, { cache: 'no-store' }).then(async (response) => {
    if (response && response.ok && response.headers.get('content-type')?.includes('text/html')) {
      try {
        const cache = await caches.open(SHELL_CACHE);
        await cache.put('/', response.clone());
      } catch (_) {}
    }
    return response;
  });

  try {
    const response = await Promise.race([network, timeout(NAV_TIMEOUT_MS)]);
    if (response && response.ok) return response;
    throw new Error('navigation-failed');
  } catch (_) {
    const shell = await caches.match('/', { ignoreSearch: true });
    if (shell) return shell;
    const offline = await caches.match('/offline.html');
    if (offline) return offline;
    return new Response('Offline', { status: 503, statusText: 'Offline' });
  }
}

async function handleAsset(request) {
  const cacheName = isNativeStudyPage(new URL(request.url)) ? STUDY_ASSET_CACHE : RUNTIME_CACHE;
  const cached = await caches.match(request, { ignoreSearch: false });
  if (cached) return cached;
  try { return await cacheResponse(cacheName, request, await fetch(request)); }
  catch (_) {
    const fallback = await caches.match(request, { ignoreSearch: false });
    return fallback || new Response('', { status: 503, statusText: 'Network error' });
  }
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.mode === 'navigate') { event.respondWith(handleNavigation(request)); return; }
  if (isCacheableAsset(request)) { event.respondWith(handleAsset(request)); return; }
});

self.addEventListener('push', (event) => {
  let payload = { title: 'Prepza', body: '' };
  try { if (event.data) payload = event.data.json(); }
  catch (_) { payload.body = event.data ? event.data.text() : ''; }
  event.waitUntil(self.registration.showNotification(payload.title || 'Prepza', { body: payload.body || '' }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientsList) => {
    for (const client of clientsList) { if ('focus' in client) return client.focus(); }
    if (self.clients.openWindow) return self.clients.openWindow('/');
  }));
});
