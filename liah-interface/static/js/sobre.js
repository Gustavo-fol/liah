/*
  Página "Sobre a Liah".
  1) Etapas clicáveis: mostra a explicação de cada etapa do caminho.
  2) Acende o caminho que a ÚLTIMA mensagem desta visita percorreu.
     O chat.js guarda no sessionStorage só a ORIGEM da resposta (ex.: "regra"), nunca o texto:
     o sessionStorage some quando a aba fecha e fica só neste navegador.
*/
(function () {
  "use strict";
  var caminho = document.getElementById("caminho");
  if (!caminho) return;
  var etapas = caminho.querySelectorAll(".etapa");
  var textos = document.querySelectorAll("#explicacao [data-texto]");

  function mostrar(chave) {
    etapas.forEach(function (b) { b.setAttribute("aria-selected", b.dataset.etapa === chave ? "true" : "false"); });
    textos.forEach(function (p) { p.hidden = p.dataset.texto !== chave; });
  }
  etapas.forEach(function (b, i) {
    b.addEventListener("click", function () { mostrar(b.dataset.etapa); });
    // setas do teclado andam entre as etapas (padrão de "abas" acessíveis)
    b.addEventListener("keydown", function (e) {
      var alvo = e.key === "ArrowRight" ? etapas[i + 1] : e.key === "ArrowLeft" ? etapas[i - 1] : null;
      if (alvo) { alvo.focus(); mostrar(alvo.dataset.etapa); }
    });
  });

  var nomes = { crise: "protocolo de crise", regra: "regras fixas", ia: "IA online", basica: "reserva (IA fora do ar)" };
  var ultima = null;
  try { ultima = JSON.parse(sessionStorage.getItem("liah-ultima") || "null"); } catch (e) { ultima = null; }
  if (!ultima || !ultima.origem) return;

  var caminhos = JSON.parse(caminho.dataset.caminhos || "{}");
  (caminhos[ultima.origem] || []).forEach(function (chave, i) {
    var b = document.getElementById("etapa-" + chave);
    if (b) setTimeout(function () { b.classList.add("usada"); }, 150 * i);  // acende em sequência
  });
  var span = document.querySelector("#ultima span");
  span.textContent = "resolvida por " + (nomes[ultima.origem] || ultima.origem) +
    ", rosto “" + (ultima.expressao || "neutra") + "”" +
    (ultima.risco && ultima.risco !== "nenhum" ? ", com sinal de " + ultima.risco + "." : ".");
})();
