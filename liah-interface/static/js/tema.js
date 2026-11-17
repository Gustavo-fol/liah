/* ============================================================
   TEMA CLARO / ESCURO
   O CSS troca TODAS as cores sozinho quando o <html> recebe data-tema="escuro".
   Este arquivo só decide qual tema usar e salva a escolha:
     - no navegador (localStorage), para visitantes;
     - na conta (API /preferencias/), para valer em qualquer aparelho.
   Qualquer botão com o atributo data-alternar-tema funciona como "trocar tema".
   ============================================================ */
(function () {
  "use strict";
  var raiz = document.documentElement;
  var midiaEscura = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

  function aplicar(escolhido) {
    var escuro = escolhido === "escuro" || (escolhido === "sistema" && midiaEscura && midiaEscura.matches);
    raiz.dataset.tema = escuro ? "escuro" : "claro";
    raiz.dataset.temaEscolhido = escolhido;
    document.dispatchEvent(new CustomEvent("liah:tema", { detail: raiz.dataset.tema }));
  }

  function tokenCsrf() {
    var achado = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return achado ? decodeURIComponent(achado[1]) : "";
  }
  // Utilidades COMPARTILHADAS: os outros arquivos (chat.js, voz.js) usam esta mesma função.
  window.LiahUtil = { tokenCsrf: tokenCsrf };

  function definir(escolhido) {
    aplicar(escolhido);
    try { localStorage.setItem("liah-tema", escolhido); } catch (e) { /* navegador sem storage */ }

    var corpo = document.body;
    if (corpo && corpo.dataset.logado && corpo.dataset.urlPreferencias) {
      fetch(corpo.dataset.urlPreferencias, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": tokenCsrf() },
        body: JSON.stringify({ tema: escolhido }),
      }).catch(function () { /* sem internet: fica salvo só no navegador */ });
    }
  }

  function alternar() {
    definir(raiz.dataset.tema === "escuro" ? "claro" : "escuro");
  }

  // Se a pessoa escolheu "igual ao aparelho", acompanha quando o aparelho mudar.
  if (midiaEscura && midiaEscura.addEventListener) {
    midiaEscura.addEventListener("change", function () {
      if (raiz.dataset.temaEscolhido === "sistema") aplicar("sistema");
    });
  }

  document.addEventListener("click", function (evento) {
    if (evento.target.closest("[data-alternar-tema]")) alternar();
  });

  window.LiahTema = { definir: definir, alternar: alternar };
})();
