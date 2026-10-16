// Bump this whenever the caching strategy below changes so the old cache is
// dropped on activate.
const CACHE_NAME = 'yamtrack-v2';

// Only static assets are pre-cached. Never pre-cache '/' (or any HTML page):
// the shell changes on every deploy and a stale cached page hides new
// templates and scripts.
const STATIC_ASSETS = [
  '/static/css/main.css',
  '/static/favicon/android-chrome-192x192.png',
  '/static/favicon/android-chrome-512x512.png',
  '/static/fonts/roboto-flex.woff2'
];

// Install event - cache the static assets and take over as soon as possible.
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

// Fetch event:
//   navigations -> network first (fall back to cache only when offline)
//   static assets -> cache first, then network
//   everything else (HTMX, API, POSTs, images) -> left to the browser
self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          }
          return response;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  if (request.method === 'GET' && url.origin === self.location.origin && url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(request).then((cached) => {
        if (cached) {
          return cached;
        }
        return fetch(request).then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          }
          return response;
        });
      })
    );
  }

  // Anything else is handled by the browser's default network behaviour.
});

// Activate event - drop old caches and start controlling open pages.
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((cacheNames) => Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      ))
      .then(() => self.clients.claim())
  );
});
