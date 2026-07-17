// Palmeiras Agenda — Service Worker
const CACHE_NAME = 'palmeiras-v1.1.37';
const HTML_FALLBACK = '/index.html';

// App shell resources to pre-cache on install
const APP_SHELL = [
  HTML_FALLBACK,
  '/static/css/styles.css?v=61',
  '/static/js/config.js?v=23',
  '/static/js/app.js?v=61',
  '/static/favicon.png',
  '/static/brand/palmeiras-agenda-mark.svg?v=5',
  '/static/brand/palmeiras-agenda-mark-small.svg',
  '/static/brand/palmeiras-agenda-icon-192-v5.png',
  '/static/brand/palmeiras-agenda-icon-512-v5.png',
  '/static/brand/palmeiras-agenda-maskable-512-v5.png',
  '/static/brand/palmeiras-agenda-favicon-16-v5.png',
  '/static/brand/palmeiras-agenda-favicon-32-v5.png',
  '/static/brand/palmeiras-agenda-favicon-v5.png',
  '/manifest.webmanifest?v=7'
];

// API endpoints — network-only, with cache fallback only when offline
const API_ROUTES = '/api/';

function cacheAppShell(cache) {
  return Promise.all(
    APP_SHELL.map((url) =>
      cache.add(url).catch(() => {
        // Optional brand/favicon assets should not prevent the PWA from installing.
      })
    )
  );
}

function cacheResponse(request, response) {
  if (!response || !response.ok) return response;
  const clone = response.clone();
  caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
  return response;
}

async function networkFirst(request, fallbackRequest = request) {
  try {
    const response = await fetch(request);
    return cacheResponse(fallbackRequest, response);
  } catch (error) {
    const cached = await caches.match(fallbackRequest);
    if (cached) return cached;
    throw error;
  }
}

async function staleWhileRevalidate(request) {
  const cached = await caches.match(request);
  const fetchPromise = fetch(request)
    .then((response) => cacheResponse(request, response))
    .catch(() => cached);
  return cached || fetchPromise;
}

// Install: pre-cache app shell
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cacheAppShell(cache);
    })
  );
  self.skipWaiting();
});

// Activate: clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      const oldKeys = keys.filter((k) => k !== CACHE_NAME);
      await Promise.all(oldKeys.map((k) => caches.delete(k)));
      await self.clients.claim();

      // If this worker replaced an older shell cache, reload open app tabs once
      // so users are not stranded on retired markup from the previous worker.
      if (oldKeys.length) {
        const windows = await self.clients.matchAll({ type: 'window' });
        await Promise.all(
          windows
            .filter((client) => client.url && client.url.startsWith(self.location.origin))
            .map((client) => client.navigate(client.url).catch(() => {}))
        );
      }
    })()
  );
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

// Fetch: stale-while-revalidate for app shell, fresh network for API
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Only handle same-origin GET requests
  if (request.method !== 'GET' || url.origin !== self.location.origin) {
    return;
  }

  // API routes: always go to the network so scores/results do not stick after
  // collector updates; cached API data is only an offline fallback.
  if (url.pathname.startsWith(API_ROUTES)) {
    event.respondWith(
      fetch(request, { cache: 'no-store' })
        .catch(() => caches.match(request).then((cached) => cached || Response.error()))
    );
    return;
  }

  // HTML navigations must not be served stale ahead of the network.
  if (request.mode === 'navigate' || (request.headers.get('accept') || '').includes('text/html')) {
    event.respondWith(networkFirst(request, HTML_FALLBACK));
    return;
  }

  // App shell: stale-while-revalidate
  event.respondWith(staleWhileRevalidate(request));
});
