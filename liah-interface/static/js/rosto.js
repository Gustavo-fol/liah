/* ============================================================
   ROSTO DA LIAH (o "motor de expressões")

   É uma prévia do display de LED do robô físico. Funciona SOZINHO, no navegador:
   não depende da IA nem da internet. A IA (quando ligada) só sugere a expressão
   da resposta. Sem IA, o próprio rosto lê o texto e escolhe uma expressão.

   O que ele faz:
     - pisca de vez em quando (às vezes duas vezes seguidas, como gente);
     - olha em volta quando está parado e SEGUE o mouse;
     - fica ATENTO e olha para baixo enquanto a pessoa digita;
     - fica PENSANDO enquanto espera a resposta;
     - "FALA" (boca mexendo) enquanto a resposta aparece;
     - escolhe uma expressão pelo sentimento do texto (feliz, acolhedora, curiosa...);
     - DORME depois de 1 minuto sem ninguém mexer, e acorda assustada quando alguém volta.

   Expressões: neutra, feliz, atenta, acolhedora, preocupada, pensando,
               surpresa, curiosa, confusa, dormindo
   (no robô físico, as mesmas palavras vão escolher a animação do display)

   Uso pelos outros arquivos:
     LiahRosto.definir("feliz", 3000)   -> muda a expressão (e volta ao normal depois de 3 s)
     LiahRosto.reagir(textoDaPessoa, resposta) -> escolhe a expressão e "fala"
   ============================================================ */
(function () {
  "use strict";

  var reduzirMovimento = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function rostos() { return document.querySelectorAll("[data-rosto]"); }
  function aleatorio(min, max) { return min + Math.random() * (max - min); }

  var expressaoAtual = "neutra";
  var relogioVolta = null;      // volta para "neutra" depois de um tempo
  var relogioFala = null;
  var ultimoMovimentoMouse = 0;
  var ultimaAtividade = Date.now();
  var dormindo = false;

  // ---------------------------------------------------------- expressão
  function aplicar(expressao) {
    expressaoAtual = expressao;
    rostos().forEach(function (r) { r.dataset.expressao = expressao; });
  }

  function definir(expressao, duracao) {
    clearTimeout(relogioVolta);
    if (dormindo && expressao !== "dormindo") acordar(true);
    aplicar(expressao || "neutra");
    if (duracao) relogioVolta = setTimeout(function () { aplicar("neutra"); }, duracao);
  }

  // ---------------------------------------------------------- piscar
  function piscarUmaVez() {
    rostos().forEach(function (r) { r.classList.add("piscando"); });
    setTimeout(function () {
      rostos().forEach(function (r) { r.classList.remove("piscando"); });
    }, 130);
  }

  function cicloDePiscar() {
    if (!dormindo && expressaoAtual !== "pensando") {
      piscarUmaVez();
      if (Math.random() < 0.2) setTimeout(piscarUmaVez, 260);   // piscada dupla de vez em quando
    }
    setTimeout(cicloDePiscar, aleatorio(2200, 5500));
  }

  // ---------------------------------------------------------- olhar
  // --olhar-x / --olhar-y vão de -1 a 1 (o CSS transforma em movimento dos olhos)
  function olhar(x, y) {
    rostos().forEach(function (r) {
      r.style.setProperty("--olhar-x", x.toFixed(2));
      r.style.setProperty("--olhar-y", y.toFixed(2));
    });
  }

  function cicloDeOlhar() {
    var parada = Date.now() - ultimoMovimentoMouse > 2500;
    if (parada && !dormindo && (expressaoAtual === "neutra" || expressaoAtual === "feliz")) {
      // 60% das vezes olha para o centro (para a pessoa); no resto, dá uma "olhadinha" em volta
      if (Math.random() < 0.6) olhar(0, 0);
      else olhar(aleatorio(-0.9, 0.9), aleatorio(-0.6, 0.5));
    }
    setTimeout(cicloDeOlhar, aleatorio(1800, 4200));
  }

  // Segue o mouse: calcula a direção do cursor em relação ao centro do rosto grande.
  var quadroPendente = false;
  document.addEventListener("mousemove", function (e) {
    atividade();
    ultimoMovimentoMouse = Date.now();
    if (quadroPendente || expressaoAtual === "pensando") return;
    quadroPendente = true;
    requestAnimationFrame(function () {
      quadroPendente = false;
      var grande = document.querySelector(".rosto-grande");
      var caixa = grande && grande.offsetParent ? grande.getBoundingClientRect() : null;
      if (!caixa || !caixa.width) return;
      var dx = (e.clientX - (caixa.left + caixa.width / 2)) / (window.innerWidth / 2);
      var dy = (e.clientY - (caixa.top + caixa.height / 2)) / (window.innerHeight / 2);
      olhar(Math.max(-1, Math.min(1, dx * 1.4)), Math.max(-1, Math.min(1, dy * 1.4)));
    });
  });

  // ---------------------------------------------------------- dormir / acordar
  var TEMPO_PARA_DORMIR = 60000;   // 1 minuto sem ninguém mexer

  function atividade() {
    ultimaAtividade = Date.now();
    if (dormindo) acordar(false);
  }

  function acordar(silencioso) {
    dormindo = false;
    rostos().forEach(function (r) { r.classList.remove("dormindo"); });
    if (!silencioso) {
      aplicar("surpresa");             // "opa, alguém chegou!"
      olhar(0, 0);
      clearTimeout(relogioVolta);
      relogioVolta = setTimeout(function () { aplicar("feliz"); }, 700);
      setTimeout(function () { if (expressaoAtual === "feliz") aplicar("neutra"); }, 2600);
    }
  }

  function talvezDormir() {
    var semFalar = !relogioFala;
    if (!dormindo && semFalar && expressaoAtual !== "pensando" && Date.now() - ultimaAtividade > TEMPO_PARA_DORMIR) {
      dormindo = true;
      clearTimeout(relogioVolta);
      aplicar("dormindo");
      olhar(0, 0.4);
      rostos().forEach(function (r) { r.classList.add("dormindo"); });
    }
  }
  setInterval(talvezDormir, 5000);
  ["keydown", "touchstart", "click", "scroll"].forEach(function (evento) {
    document.addEventListener(evento, atividade, { passive: true });
  });

  // ---------------------------------------------------------- digitando
  var relogioDigitando = null;
  document.addEventListener("input", function (e) {
    if (!e.target || e.target.id !== "campo") return;
    atividade();
    if (expressaoAtual === "pensando") return;
    aplicar("atenta");
    olhar(0, 0.8);                      // olha para a caixa de texto
    clearTimeout(relogioDigitando);
    relogioDigitando = setTimeout(function () {
      if (expressaoAtual === "atenta") { aplicar("neutra"); olhar(0, 0); }
    }, 2500);
  });

  // ---------------------------------------------------------- sentimento do texto (sem IA)
  // Bem simples, só para o rosto: procura palavras no texto da PESSOA.
  // (A segurança de verdade, a detecção de risco, é feita no servidor.)
  var SENTIMENTOS = [
    ["acolhedora", /trist|sozinh|chor|saudade|perdi|morreu|faleceu|mal hoje|nao estou bem|não estou bem|desanim|cansad|ansios|medo|nervos|preocupad|panico|pânico|desabaf/],
    ["feliz", /obrigad|valeu|feliz|alegr|legal|otimo|ótimo|adorei|amei|incrivel|incrível|haha|kkk|rs\b|bom dia|boa tarde|boa noite|\boi\b|\bola\b|olá|tchau/],
    ["surpresa", /nossa|uau|serio\?|sério\?|caramba|eita|que isso/],
    ["curiosa", /\?$|como voce|como você|o que voce|o que você|quem e voce|quem é você|por que|porque/],
  ];

  function sentimento(texto) {
    var t = (texto || "").toLowerCase().trim();
    for (var i = 0; i < SENTIMENTOS.length; i++) {
      if (SENTIMENTOS[i][1].test(t)) return SENTIMENTOS[i][0];
    }
    return "atenta";
  }

  // ---------------------------------------------------------- falar
  function falar(texto) {
    clearTimeout(relogioFala);
    var duracao = Math.max(1200, Math.min(6000, (texto || "").length * 45));
    if (reduzirMovimento) duracao = 600;
    rostos().forEach(function (r) { r.classList.add("falando"); });
    relogioFala = setTimeout(function () {
      relogioFala = null;
      rostos().forEach(function (r) { r.classList.remove("falando"); });
    }, duracao);
    return duracao;
  }

  /**
   * Reação à resposta: a expressão vem da IA/servidor quando for marcante
   * (preocupada, acolhedora, feliz...). Se vier só "atenta"/"neutra", o próprio rosto
   * escolhe pelo sentimento do que a pessoa escreveu.
   */
  function reagir(textoPessoa, resposta) {
    atividade();
    var doServidor = resposta && resposta.expressao;
    var marcante = doServidor && ["atenta", "neutra", "pensando"].indexOf(doServidor) < 0;
    var expressao = marcante ? doServidor : sentimento(textoPessoa);
    clearTimeout(relogioVolta);
    aplicar(expressao);
    olhar(0, 0);
    var duracao = falar(resposta && resposta.texto);
    // Risco: mantém a expressão por mais tempo (não "sorri" logo depois de um assunto sério)
    var segura = expressao === "preocupada" ? 20000 : 6000;
    relogioVolta = setTimeout(function () { aplicar("neutra"); }, duracao + segura);
  }

  // ---------------------------------------------------------- início
  aplicar("neutra");
  if (!reduzirMovimento) {
    setTimeout(cicloDePiscar, 1200);
    setTimeout(cicloDeOlhar, 2500);
  }

  window.LiahRosto = { definir: definir, reagir: reagir, piscar: piscarUmaVez, olhar: olhar, sentimento: sentimento };
})();
