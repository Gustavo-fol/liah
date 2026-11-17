/* Confirmações antes de apagar (área interna e Minha conta).
   Antes era onclick="return confirm(...)" no HTML, mas a CSP (segurança) bloqueia JavaScript
   escrito dentro do HTML. Agora basta pôr data-confirmar="pergunta" num <form> ou <button>. */
"use strict";

document.addEventListener("submit", function (evento) {
  var form = evento.target;
  // o botão que enviou o formulário (ex.: "Apagar") pode ter a sua própria pergunta
  var botao = evento.submitter;
  var pergunta = (botao && botao.dataset.confirmar) || form.dataset.confirmar;
  if (pergunta && !window.confirm(pergunta)) {
    evento.preventDefault();
  }
});
