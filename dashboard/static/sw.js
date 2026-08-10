// VEX Service Worker — PWA + Push Notifications
const CACHE_NAME = 'vex-v1';
const STATIC_ASSETS = [
  '/',
  '/static/css/game-base.css',
  '/static/js/game-base.js',
  '/static/js/app.js',
  '/static/css/style.css',
  '/webapp/games',
];

// Install: cache static assets
self.addEventListener('install', function(e) {
  e.waitUntil(
    caches.open(CACHE_NAME).then(function(cache) {
      return cache.addAll(STATIC_ASSETS).catch(function() {});
    })
  );
  self.skipWaiting();
});

// Activate: clean old caches
self.addEventListener('activate', function(e) {
  e.waitUntil(
    caches.keys().then(function(names) {
      return Promise.all(
        names.filter(function(n) { return n !== CACHE_NAME; })
             .map(function(n) { return caches.delete(n); })
      );
    })
  );
  self.clients.claim();
});

// Fetch: cache-first for static, network-first for API
self.addEventListener('fetch', function(e) {
  var url = e.request.url;
  if (url.includes('/api/')) {
    // Network-first for API
    e.respondWith(
      fetch(e.request).catch(function() {
        return caches.match(e.request);
      })
    );
  } else {
    // Cache-first for static
    e.respondWith(
      caches.match(e.request).then(function(cached) {
        return cached || fetch(e.request).then(function(resp) {
          if (resp.ok) {
            var clone = resp.clone();
            caches.open(CACHE_NAME).then(function(cache) {
              cache.put(e.request, clone);
            });
          }
          return resp;
        }).catch(function() {
          return caches.match('/');
        });
      })
    );
  }
});

// Push notifications from admin
self.addEventListener('push', function(e) {
  var data = {};
  try { data = e.data ? e.data.json() : {}; } catch(err) {}
  var title = data.title || 'VEX';
  var options = {
    body: data.body || data.message || '',
    icon: data.icon || '/static/icons/icon-192.png',
    badge: '/static/icons/icon-192.png',
    tag: data.tag || 'vex-notif',
    data: data.url ? { url: data.url } : {},
    vibrate: [200, 100, 200],
    requireInteraction: data.persistent || false,
  };
  e.waitUntil(self.registration.showNotification(title, options));
});

// Click on push notification → open URL
self.addEventListener('notificationclick', function(e) {
  e.notification.close();
  var url = (e.notification.data && e.notification.data.url) || '/';
  e.waitUntil(
    clients.matchAll({ type: 'window' }).then(function(clientList) {
      for (var i = 0; i < clientList.length; i++) {
        if (clientList[i].url.includes(url) && 'focus' in clientList[i]) {
          return clientList[i].focus();
        }
      }
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});