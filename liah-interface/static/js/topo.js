/*
  Menu do topo das páginas públicas (Sobre, Entrar, Cadastro, Conta...).
  No celular os links ficam atrás do botão ☰; no computador aparecem direto (o CSS decide).
  aria-expanded avisa leitores de tela se o menu está aberto.
*/
(function () {
  "use strict";
  var botao = document.getElementById("botao-menu-topo");
  var menu = document.getElementById("menu-topo");
  if (!botao || !menu) return;

  function alternar(abrir) {
    menu.classList.toggle("aberto", abrir);
    botao.setAttribute("aria-expanded", abrir ? "true" : "false");
    botao.setAttribute("aria-label", abrir ? "Fechar o menu" : "Abrir o menu");
  }
  botao.addEventListener("click", function () { alternar(!menu.classList.contains("aberto")); });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && menu.classList.contains("aberto")) { alternar(false); botao.focus(); }
  });
  // Clicou fora do topo: fecha
  document.addEventListener("click", function (e) {
    if (menu.classList.contains("aberto") && !e.target.closest(".topo")) alternar(false);
  });
})();
