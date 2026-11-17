/* ============================================================
   CASCA DO APP: barra lateral + troca de modos (SPA)

   - Cada botão com data-modo troca o layout SEM recarregar a página.
   - O modo escolhido fica no endereço (?modo=voz) e no navegador:
     dá F5, ou abre o link, e volta no mesmo modo.
   - A lateral recolhe (computador) ou desliza por cima (celular).
   ============================================================ */
(function () {
  "use strict";

  var app = document.getElementById("app");
  if (!app) return;
  var palco = document.getElementById("palco");
  var titulo = document.getElementById("titulo-modo");
  var botoesModo = document.querySelectorAll("[data-modo]");

  var MODOS = {
    "chat": "Chat",
    "robo": "Chat com robô",
    "voz": "Voz",
    "voz-robo": "Voz com robô",
    "display": "Display do robô",
  };

  function lerStorage(chave) { try { return localStorage.getItem(chave); } catch (e) { return null; } }
  function gravarStorage(chave, valor) { try { localStorage.setItem(chave, valor); } catch (e) { /* ok */ } }

  // ---------------------------------------------------------- modos
  function definirModo(modo, animar) {
    if (!MODOS[modo]) modo = "chat";

    function aplicar() {
      // DISPLAY DO ROBÔ = o layout "voz com robô" em tela cheia, sem menu nem botões.
      // É o modo que o Raspberry Pi abre: /chat/?modo=display
      app.classList.toggle("modo-display", modo === "display");
      palco.dataset.modo = modo === "display" ? "voz-robo" : modo;
      titulo.textContent = MODOS[modo];
      botoesModo.forEach(function (b) {
        var ativo = b.dataset.modo === modo;
        b.classList.toggle("ativo", ativo);
        b.setAttribute("aria-pressed", ativo ? "true" : "false");
      });
    }

    // View Transitions: o navegador anima a troca de layout sozinho (onde existir).
    if (animar && document.startViewTransition) document.startViewTransition(aplicar);
    else aplicar();

    // O display não fica "lembrado": quem abrir o site depois não cai numa tela sem menu.
    if (modo !== "display") gravarStorage("liah-modo", modo);
    var url = new URL(window.location.href);
    url.searchParams.set("modo", modo);
    history.replaceState(null, "", url);   // muda o endereço sem recarregar

    if (modo.indexOf("voz") !== 0 && window.LiahVoz) window.LiahVoz.parar();
    fecharMenu();
  }

  botoesModo.forEach(function (botao) {
    botao.addEventListener("click", function () { definirModo(botao.dataset.modo, true); });
  });

  // ---------------------------------------------------------- lateral
  function abrirMenu() { app.classList.add("menu-aberto"); }
  function fecharMenu() { app.classList.remove("menu-aberto"); }

  document.getElementById("abrir-menu").addEventListener("click", abrirMenu);
  document.getElementById("cortina").addEventListener("click", fecharMenu);
  document.addEventListener("liah:fechar-menu", fecharMenu);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") fecharMenu(); });

  document.getElementById("recolher").addEventListener("click", function () {
    var recolhida = app.classList.toggle("recolhida");
    gravarStorage("liah-lateral", recolhida ? "recolhida" : "aberta");
  });
  if (lerStorage("liah-lateral") === "recolhida") app.classList.add("recolhida");

  document.getElementById("nova-conversa").addEventListener("click", function () {
    if (window.LiahChat) window.LiahChat.novaConversa();
    fecharMenu();
  });

  // ---------------------------------------------------------- display do robô
  // Tocar em qualquer lugar da tela liga/desliga o microfone (no robô não tem teclado).
  // O 1º toque também pede TELA CHEIA (o navegador só deixa depois de um toque).
  palco.addEventListener("click", function (e) {
    if (!app.classList.contains("modo-display") || e.target.closest("button, a")) return;
    if (!document.fullscreenElement && document.documentElement.requestFullscreen) {
      document.documentElement.requestFullscreen().catch(function () { /* sem permissão: segue normal */ });
    }
    if (window.LiahVoz) window.LiahVoz.ouvirOuParar();
  });
  var sairDisplay = document.getElementById("sair-display");
  if (sairDisplay) sairDisplay.addEventListener("click", function () {
    if (document.fullscreenElement) document.exitFullscreen();
    definirModo("voz-robo", true);
  });

  // ---------------------------------------------------------- início
  var doEndereco = new URLSearchParams(window.location.search).get("modo");
  // Quem abre a Liah pela 1ª vez já vê o ROSTO ("Chat com robô"): é a prévia do robô físico.
  definirModo(doEndereco || lerStorage("liah-modo") || "robo", false);
})();
