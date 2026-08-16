/**
 * VEX Games Service Worker v3
 * Cache + Push Notifications + Notification Click
 */

const CACHE_VER  = 'vex-v5';
const STATIC_EXT = ['.css','.js','.png','.jpg','.jpeg','.gif','.svg','.woff2','.ico'];

const PRECACHE = [
  '/static/css/fx.css',
  '/static/js/fx.js',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-32.png',
  '/static/icons/favicon.png',
];

// ── Install ─────────────────────────────────────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_VER).then(cache => cache.addAll(PRECACHE).catch(() => {}))
  );
  self.skipWaiting();
});

// ── Activate ────────────────────────────────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_VER).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// ── Fetch ───────────────────────────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== location.origin) return;

  const isStatic = STATIC_EXT.some(ext => url.pathname.endsWith(ext))
    || url.pathname.startsWith('/static/');
  const isApi = url.pathname.startsWith('/api/');
  const isGame = url.pathname.startsWith('/webapp/');

  if (isStatic) {
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
    event.respondWith(
      fetch(event.request).catch(() => caches.match(event.request))
    );
  }
});

// ── Push Notifications — appears in phone notification shade ────────────────
self.addEventListener('push', event => {
  let data = { title: 'VEX Games', message: 'إشعار جديد', type: 'notification', url: '/home' };
  try {
    data = JSON.parse(event.data.text());
  } catch(e) {
    data.message = event.data.text();
  }

  // Choose icon based on notification type
  let icon = '/static/icons/icon-192.png';
  let badge = '/static/icons/icon-32.png';

  // Build notification options
  const options = {
    body: data.message || '',
    icon: icon,
    badge: badge,
    image: data.image || undefined, // Large image (for photo broadcasts)
    tag: data.type || 'vex-notification',
    renotify: true, // New notification replaces old one + alerts again
    requireInteraction: data.type === 'broadcast' || data.type === 'urgent',
    data: {
      url: data.url || '/home',
      type: data.type
    },
    vibrate: data.type === 'urgent' ? [300, 150, 300, 150, 300] : [200, 100, 200],
    actions: [
      { action: 'open', title: '📂 فتح', icon: '/static/icons/icon-32.png' },
      { action: 'dismiss', title: '✕ إغلاق' }
    ],
    // Android-specific: set priority for heads-up notification
    priority: data.type === 'urgent' ? 'high' : 'normal',
    // Silent for normal, sound for urgent/broadcast
    silent: data.type === 'normal' || data.type === 'notification'
  };

  event.waitUntil(
    self.registration.showNotification(data.title || 'VEX Games', options)
  );
});

// ── Notification click — open the website ───────────────────────────────────
self.addEventListener('notificationclick', event => {
  event.notification.close();

  if (event.action === 'dismiss') return;

  const targetUrl = event.notification.data?.url || '/home';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clientList => {
      // Try to focus an existing tab
      for (const client of clientList) {
        if (client.url.includes('vex.deals') && 'focus' in client) {
          client.navigate(targetUrl);
          return client.focus();
        }
      }
      // No existing tab — open new one
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
    })
  );
});

// ── Push subscription change (when browser refreshes endpoint) ──────────────
self.addEventListener('pushsubscriptionchange', event => {
  event.waitUntil(
    self.registration.pushManager.getSubscription().then(sub => {
      if (!sub) return;
      return fetch('/api/push/subscribe-user', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          endpoint: sub.endpoint,
          keys: sub.toJSON().keys || {}
        }),
        credentials: 'same-origin'
      }).catch(() => {});
    })
  );
});
