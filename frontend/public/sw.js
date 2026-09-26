// Prepza application-shell service worker.
// v16 is a deliberate cache-reset release: the previous worker could keep an
// older application shell alive on installed Android clients after uninstall /
// reinstall. Network is authoritative for navigations; cached data is only a
// fallback for genuine offline use.
const SW_VERSION = 'v17';
const SHELL_CACHE = `prepza-shell-${SW_VERSION}`;
const RUNTIME_CACHE = `prepza-runtime-${SW_VERSION}`;
const NAV_TIMEOUT_MS = 30000;
const STUDY_ASSET_CACHE = 'prepza-study-assets-v1';
const PDFJS_HOST = 'cdn.jsdelivr.net';
const PDFJS_PATH_PREFIX = '/npm/pdfjs-dist@6.3.289/build/';

const CORE_SHELL = ['/offline.html', '/manifest.json', '/icon-192.png', '/icon-512.png'];

function sameOrigin(url) { return url.origin === self.location.origin; }
function isPdfJsAsset(url) { return url.hostname === PDFJS_HOST && url.pathname.startsWith(PDFJS_PATH_PREFIX); }
function isNativeStudyPage(url) {
  return sameOrigin(url) && /^\/documents\/\\d+\/reading\/page\/\\d+$/.test(url.pathname);
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
  // Emergency cache-reset release. This is intentionally immediate so an
  // installed client cannot remain controlled by the stale worker while the
  // new production frontend is already live.
  self.skipWaiting();
  event.waitUntil(precacheShell());
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((names) => Promise.all(
      names
        .filter((name) => name.startsWith('prepza-') &&
          name !== SHELL_CACHE &&
          name !== RUNTIME_CACHE &&
          name !== STUDY_ASSET_CACHE)
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
  // Current production HTML is authoritative. We allow a generous startup
  // window because Render free services can need time to wake from sleep.
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
  const url = new URL(request.url);
  const studyPage = isNativeStudyPage(url);
  const cached = await caches.match(request, { ignoreSearch: false });
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (studyPage) return response;
    return await cacheResponse(RUNTIME_CACHE, request, response);
  } catch (_) {
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
  event.waitUntil(self.registration.showNotification(payload.title || 'Prepza', {
    body: payload.body || '',
    data: payload.data || {},
    icon: '/icon-192.png',
    badge: '/icon-192.png',
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const data = event.notification.data || {};
  event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientsList) => {
    const message = {
      type: 'OPEN_PREPZA_NOTIFICATION',
      screen: data.screen || null,
      document_id: data.document_id || null,
      related_type: data.related_type || null,
      related_id: data.related_id || null,
    };
    for (const client of clientsList) {
      if ('postMessage' in client) client.postMessage(message);
      if ('focus' in client) return client.focus();
    }
    if (self.clients.openWindow) return self.clients.openWindow('/');
  }));
});