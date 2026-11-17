/* SERVICE WORKER DA LIAH (gerado pelo Django em /sw.js)
   Só faz uma coisa: quando a pessoa abre o app SEM internet, mostra a página "offline"
   em vez do dinossauro do Chrome. Conversas NUNCA são guardadas aqui. */
"use strict";

var CACHE = "liah-offline-v1";
var OFFLINE = "{{ url_offline|escapejs }}";
var ARQUIVOS = [OFFLINE{% for a in arquivos %}, "{{ a|escapejs }}"{% endfor %}];

self.addEventListener("install", function (evento) {
  evento.waitUntil(caches.open(CACHE).then(function (c) { return c.addAll(ARQUIVOS); }));
  self.skipWaiting();
});

self.addEventListener("activate", function (evento) {
  // apaga caches de versões antigas
  evento.waitUntil(caches.keys().then(function (nomes) {
    return Promise.all(nomes.filter(function (n) { return n !== CACHE; }).map(function (n) { return caches.delete(n); }));
  }));
  self.clients.claim();
});

self.addEventListener("fetch", function (evento) {
  // Só NAVEGAÇÃO (abrir uma página). A API e o resto vão direto para a rede, sem cache.
  if (evento.request.mode !== "navigate") return;
  evento.respondWith(fetch(evento.request).catch(function () { return caches.match(OFFLINE); }));
});
