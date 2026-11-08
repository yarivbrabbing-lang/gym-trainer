/* Offline support. Bump VERSION on every release so phones pick up the new files. */
const VERSION = 'gym-v1.3.0';
const ASSETS = ['./', 'index.html', 'manifest.webmanifest',
  'icon-192.png', 'icon-512.png', 'maskable-192.png', 'maskable-512.png',
  'apple-touch-icon.png', 'favicon-64.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(ASSETS)));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener('message', e => { if (e.data === 'skip') self.skipWaiting(); });
/* Same-origin GET only: serve from cache, refresh cache in the background (stale-while-revalidate). */
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== location.origin) return;
  e.respondWith(caches.open(VERSION).then(async cache => {
    const hit = await cache.match(req, { ignoreSearch: true });
    const net = fetch(req).then(res => { if (res.ok) cache.put(req, res.clone()); return res; }).catch(() => null);
    return hit || (await net) || (req.mode === 'navigate' ? cache.match('index.html') : Response.error());
  }));
});
