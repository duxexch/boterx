/**
 * VEX Games Service Worker
 * Cache-first for static assets; network-first for API and game routes.
 */

const CACHE_VER  = 'vex-v2';
const STATIC_EXT = ['.css','.js','.png','.jpg','.jpeg','.gif','.svg','.woff2','.ico'];

const PRECACHE = [
  '/static/css/fx.css',
  '/static/js/fx.js',
  '/static/manifest.json',
];

// ── Install: pre-cache known static assets ──────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_VER).then(cache => cache.addAll(PRECACHE).catch(() => {}))
  );
  self.skipWaiting();
});

// ── Activate: remove old cache versions ────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_VER).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// ── Fetch: cache-first for static, network-first for everything else ────────
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Only handle same-origin GET requests
  if (event.request.method !== 'GET' || url.origin !== location.origin) return;

  const isStatic = STATIC_EXT.some(ext => url.pathname.endsWith(ext))
    || url.pathname.startsWith('/static/');
  const isApi    = url.pathname.startsWith('/api/');
  const isGame   = url.pathname.startsWith('/webapp/');

  if (isStatic) {
    // Cache-first: serve from cache, update in background
    event.respondWith(
      caches.match(event.request).then(cached => {
        const networkFetch = fetch(event.request).then(response => {
          if (response && response.status === 200) {
            const clone = response.clone();
            caches.open(CACHE_VER).then(c => c.put(event.request, clone));
          }
          return response;
        });
        return cached || networkFetch;
      })
    );
  } else if (isApi || isGame) {
    // Network-first: always try network; fall back to cache if offline
    event.respondWith(
      fetch(event.request).catch(() => caches.match(event.request))
    );
  }
  // All other routes: default browser behavior (no interception)
});
