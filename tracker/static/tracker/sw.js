const CACHE = 'msp-tracker-v1';
const URLS = ['/', '/tech/', '/static/tracker/css/mobile.css'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(URLS)));
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  e.respondWith(
    caches.match(e.request).then(r => r || fetch(e.request).then(resp => {
      const copy = resp.clone();
      caches.open(CACHE).then(c => c.put(e.request, copy));
      return resp;
    }))
  );
});

self.addEventListener('sync', e => {
  if (e.tag === 'sync-visits') {
    e.waitUntil(syncPendingVisits());
  }
});

async function syncPendingVisits() {
  const db = await openDB();
  const tx = db.transaction('visits', 'readwrite');
  const store = tx.objectStore('visits');
  const all = await store.getAll();
  for (const visit of all) {
    if (visit.synced) continue;
    try {
      const resp = await fetch('/api/tech/log-visit/', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken')},
        body: JSON.stringify(visit)
      });
      if (resp.ok) {
        visit.synced = true;
        store.put(visit);
      }
    } catch (err) { console.warn('Sync failed, will retry', err); }
  }
}

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open('msp-tracker', 1);
    req.onupgradeneeded = e => {
      e.target.result.createObjectStore('visits', {keyPath: 'id', autoIncrement: true});
    };
    req.onsuccess = e => resolve(e.target.result);
    req.onerror = reject;
  });
}

function getCookie(name) {
  const v = `; ${document.cookie}`;
  const parts = v.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(';').shift();
}