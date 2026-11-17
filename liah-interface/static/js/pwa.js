/* Registra o service worker (deixa a Liah "instalável" e mostra uma página amigável sem internet). */
"use strict";
if ("serviceWorker" in navigator && window.isSecureContext) {
  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/sw.js").catch(function () { /* sem SW: o site funciona igual */ });
  });
}
