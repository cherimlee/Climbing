/* 서울·경기 암장 지도 서비스 워커 (P7)
   - 지도 페이지·데이터: 네트워크 먼저, 안 되면 저장본 (항상 최신 우선)
   - three.js·글꼴 등 외부 파일: 저장본 먼저 (버전 고정 파일)
   ※ 방문 기록(localStorage)은 여기서 건드리지 않아요. */
const VER = 'cm-p8-2';
const CORE = ['./map.html', './manifest.webmanifest', './icon-192.png', './icon-512.png', './apple-touch-icon.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VER).then(c => c.addAll(CORE)).catch(() => {}).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== VER).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});

async function networkFirst(req, key) {
  const c = await caches.open(VER);
  try {
    const r = await fetch(req, { cache: 'no-store' });
    if (r && r.ok) c.put(key || req, r.clone());
    return r;
  } catch (e) {
    const hit = await c.match(key || req, { ignoreSearch: true });
    if (hit) return hit;
    throw e;
  }
}
async function cacheFirst(req) {
  const c = await caches.open(VER);
  const hit = await c.match(req);
  if (hit) return hit;
  const r = await fetch(req);
  if (r && (r.ok || r.type === 'opaque')) c.put(req, r.clone());
  return r;
}

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const u = new URL(req.url);
  if (u.origin === location.origin) {
    if (req.mode === 'navigate' && u.pathname.endsWith('/map.html')) { e.respondWith(networkFirst(req, './map.html')); return; }
    e.respondWith(networkFirst(req));
    return;
  }
  if (/cdn\.jsdelivr\.net|fonts\.googleapis\.com|fonts\.gstatic\.com|unpkg\.com|cdnjs\.cloudflare\.com/.test(u.host)) e.respondWith(cacheFirst(req));
});
