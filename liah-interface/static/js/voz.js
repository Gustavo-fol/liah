/* ============================================================
   VOZ DA LIAH

   1) OUVIR: o reconhecimento de voz do próprio navegador (Web Speech API)
      transforma a fala em texto. Funciona no Chrome e no Edge.
      Atenção (privacidade): o navegador manda o áudio para o servidor dele
      (Google/Microsoft) para reconhecer. Isso precisa estar na Política de Privacidade.
   2) MEDIR o volume do microfone (Web Audio API) para animar a orbe e o rosto.
   3) FALAR: a síntese de voz do navegador (speechSynthesis) lê a resposta.

   4) PLANO B (robô / Raspberry Pi): o Chromium do Raspberry não tem o reconhecimento
      do Google (dá erro "network"). Aí a Liah GRAVA o áudio (MediaRecorder) e manda para
      o SERVIDOR dela (/api/v1/voz/transcrever/), que usa a OpenAI. A resposta também pode
      ser falada pelo servidor (/api/v1/voz/falar/) quando o aparelho não tem voz em português.

   Só funciona em HTTPS ou em localhost (regra dos navegadores para microfone).
   ============================================================ */
(function () {
  "use strict";

  var app = document.getElementById("app");
  var palco = document.getElementById("palco");
  var botaoMic = document.getElementById("botao-mic");
  var estado = document.getElementById("estado-voz");
  var canvas = document.getElementById("orbe");
  if (!app || !botaoMic || !canvas) return;

  var Reconhecimento = window.SpeechRecognition || window.webkitSpeechRecognition;
  var raiz = document.documentElement;
  var urlTranscrever = app.dataset.urlVozTranscrever;
  var urlFalar = app.dataset.urlVozFalar;
  var podeGravar = !!(window.MediaRecorder && navigator.mediaDevices && urlTranscrever);
  // Começa pelo navegador; se ele falhar por falta de serviço, passa a usar o servidor.
  var usarServidor = !Reconhecimento && podeGravar;
  var gravador = null, pedacos = [];
  var audioServidor = null;

  var reconhecedor = null;
  var ouvindo = false;
  var fluxoMic = null, contextoAudio = null, analisador = null, dadosFreq = null;
  var nivel = 0;            // 0 a 1: "volume" atual (suavizado)
  var falando = false;
  var cores = {};

  // ---------------------------------------------------------- estado / textos
  function mostrarEstado(texto) { estado.textContent = texto; }

  function modoVoz() { return (palco.dataset.modo || "").indexOf("voz") === 0; }   // o display usa "voz-robo"

  if (!Reconhecimento && !podeGravar) {
    app.classList.add("sem-voz");
    mostrarEstado("Seu navegador não reconhece voz. Use o Chrome ou o Edge, ou digite abaixo.");
  }

  // ---------------------------------------------------------- microfone (volume)
  async function ligarMedidor() {
    try {
      fluxoMic = await navigator.mediaDevices.getUserMedia({ audio: true });
      contextoAudio = new (window.AudioContext || window.webkitAudioContext)();
      var fonte = contextoAudio.createMediaStreamSource(fluxoMic);
      analisador = contextoAudio.createAnalyser();
      analisador.fftSize = 256;                       // 128 "faixas" de frequência
      dadosFreq = new Uint8Array(analisador.frequencyBinCount);
      fonte.connect(analisador);
    } catch (erro) {
      analisador = null; // sem permissão: a orbe anima de forma "sintética"
    }
  }

  function desligarMedidor() {
    if (fluxoMic) fluxoMic.getTracks().forEach(function (t) { t.stop(); });
    if (contextoAudio) contextoAudio.close();
    fluxoMic = contextoAudio = analisador = null;
  }

  // ---------------------------------------------------------- ouvir
  function tokenCsrf() { return window.LiahUtil ? window.LiahUtil.tokenCsrf() : ""; }

  async function responderA(texto) {
    mostrarEstado("Liah está pensando...");
    var resposta = await window.LiahChat.enviar(texto);
    if (resposta) falar(resposta.texto);
    else mostrarEstado("Toque no microfone para falar");
  }

  // ---------------------------------------------------------- ouvir pelo SERVIDOR (plano B)
  async function gravarParaServidor() {
    pararDeFalar();
    await ligarMedidor();
    if (!fluxoMic) { mostrarEstado("Permita o uso do microfone no navegador para falar com a Liah."); return; }
    pedacos = [];
    gravador = new MediaRecorder(fluxoMic);
    gravador.ondataavailable = function (e) { if (e.data && e.data.size) pedacos.push(e.data); };
    gravador.onstop = async function () {
      ouvindo = false;
      botaoMic.setAttribute("aria-pressed", "false");
      var tipo = (gravador.mimeType || "audio/webm").split(";")[0];
      desligarMedidor();
      if (!pedacos.length) return;
      mostrarEstado("Entendendo o que você disse...");
      var dados = new FormData();
      dados.append("audio", new Blob(pedacos, { type: tipo }), "fala." + (tipo.indexOf("ogg") >= 0 ? "ogg" : "webm"));
      try {
        var r = await fetch(urlTranscrever, {
          method: "POST", body: dados, credentials: "same-origin", headers: { "X-CSRFToken": tokenCsrf() },
        });
        var json = await r.json().catch(function () { return {}; });
        if (r.status === 503 && Reconhecimento) {
          // O servidor ainda não tem a voz configurada: volta para o reconhecimento do navegador.
          usarServidor = false;
          mostrarEstado("Toque no microfone e fale de novo.");
          return;
        }
        if (!r.ok || !json.texto) { mostrarEstado(json.erro || "Não entendi. Tente de novo."); return; }
        mostrarEstado(json.texto);
        responderA(json.texto);
      } catch (e) {
        mostrarEstado("Sem conexão com a Liah. Tente de novo.");
      }
    };
    gravador.start();
    ouvindo = true;
    botaoMic.setAttribute("aria-pressed", "true");
    window.LiahChat.mudarRosto("atenta");
    mostrarEstado("Ouvindo... toque de novo para enviar.");
    // segurança: para sozinho depois de 30 s
    setTimeout(function () { if (gravador && gravador.state === "recording") gravador.stop(); }, 30000);
  }

  async function comecarAOuvir() {
    if (usarServidor) return gravarParaServidor();
    if (!Reconhecimento) return;
    pararDeFalar();

    reconhecedor = new Reconhecimento();
    reconhecedor.lang = "pt-BR";
    reconhecedor.interimResults = true;   // mostra o texto enquanto a pessoa fala
    reconhecedor.continuous = false;      // para sozinho quando a pessoa fica em silêncio

    var textoFinal = "";

    reconhecedor.onresult = function (evento) {
      var parcial = "";
      for (var i = evento.resultIndex; i < evento.results.length; i++) {
        var trecho = evento.results[i][0].transcript;
        if (evento.results[i].isFinal) textoFinal += trecho; else parcial += trecho;
      }
      mostrarEstado((textoFinal + parcial) || "Ouvindo...");
    };

    reconhecedor.onerror = function (evento) {
      var mensagens = {
        "not-allowed": "Permita o uso do microfone no navegador para falar com a Liah.",
        "no-speech": "Não ouvi nada. Toque no microfone e tente de novo.",
        "network": "Sem internet para reconhecer a voz.",
      };
      // Sem o serviço de voz do navegador (Raspberry Pi, Chromium sem chaves do Google):
      // a partir de agora usa o servidor da Liah.
      // Só troca se o navegador NÃO tiver o serviço (Raspberry Pi). Uma queda de internet
      // passageira no Chrome normal não deve mudar o modo para sempre.
      if (evento.error === "service-not-allowed" && podeGravar) {
        usarServidor = true;
        mostrarEstado("Vou usar o servidor da Liah para ouvir. Toque no microfone de novo.");
        return;
      }
      mostrarEstado(mensagens[evento.error] || "Não consegui ouvir. Tente de novo.");
    };

    reconhecedor.onend = async function () {
      ouvindo = false;
      botaoMic.setAttribute("aria-pressed", "false");
      desligarMedidor();
      if (!textoFinal.trim()) return;
      responderA(textoFinal);
    };

    await ligarMedidor();
    reconhecedor.start();
    ouvindo = true;
    botaoMic.setAttribute("aria-pressed", "true");
    window.LiahChat.mudarRosto("atenta");
    mostrarEstado("Ouvindo...");
  }

  function pararDeOuvir() {
    if (gravador && gravador.state === "recording") { gravador.stop(); return; }
    if (reconhecedor && ouvindo) reconhecedor.stop();
  }

  // ---------------------------------------------------------- falar
  function escolherVoz() {
    var vozes = window.speechSynthesis ? window.speechSynthesis.getVoices() : [];
    var ptBR = vozes.filter(function (v) { return /pt[-_]BR/i.test(v.lang); });
    // Preferência por vozes femininas conhecidas; senão, qualquer voz pt-BR.
    return ptBR.find(function (v) { return /francisca|maria|luciana|google/i.test(v.name); }) || ptBR[0] || null;
  }

  // Fala pelo SERVIDOR (voz da OpenAI): quando o aparelho não tem voz em português.
  async function falarPeloServidor(texto) {
    try {
      var r = await fetch(urlFalar, {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": tokenCsrf() },
        body: JSON.stringify({ texto: texto }),
      });
      if (!r.ok) { mostrarEstado("A voz da Liah não está disponível agora. A resposta está na tela."); return; }
      var url = URL.createObjectURL(await r.blob());
      audioServidor = new Audio(url);
      audioServidor.onplay = function () { falando = true; mostrarEstado("Liah está falando..."); };
      audioServidor.onended = audioServidor.onerror = function () {
        falando = false; URL.revokeObjectURL(url); mostrarEstado("Toque no microfone para falar");
      };
      audioServidor.play();
    } catch (e) {
      mostrarEstado("Toque no microfone para falar");
    }
  }

  function falar(texto) {
    if (!modoVoz()) { mostrarEstado("Toque no microfone para falar"); return; }
    // A voz do NAVEGADOR vem sempre primeiro (é grátis e não depende da internet).
    // A do servidor só entra se o aparelho não tiver síntese de voz nenhuma (ex.: alguns Raspberry Pi).
    if (!window.speechSynthesis && urlFalar) { falarPeloServidor(texto); return; }
    if (!window.speechSynthesis) { mostrarEstado("Toque no microfone para falar"); return; }
    pararDeFalar();
    var fala = new SpeechSynthesisUtterance(texto.replace(/[•*#]/g, ""));
    fala.lang = "pt-BR";
    fala.rate = 1.0;
    var voz = escolherVoz();
    if (voz) fala.voice = voz;
    fala.onstart = function () { falando = true; mostrarEstado("Liah está falando..."); };
    fala.onend = fala.onerror = function () { falando = false; mostrarEstado("Toque no microfone para falar"); };
    window.speechSynthesis.speak(fala);
  }

  function pararDeFalar() {
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    if (audioServidor) { audioServidor.pause(); audioServidor = null; }
    falando = false;
  }

  botaoMic.addEventListener("click", function () {
    if (ouvindo) pararDeOuvir(); else comecarAOuvir();
  });

  // ---------------------------------------------------------- orbe (desenho)
  var ctx = canvas.getContext("2d");

  function lerCores() {
    var estilo = getComputedStyle(raiz);
    cores.azul = estilo.getPropertyValue("--azul").trim() || "#1f56a8";
    cores.ciano = estilo.getPropertyValue("--ciano").trim() || "#3aa7e8";
    cores.escuro = raiz.dataset.tema === "escuro";
  }
  lerCores();
  document.addEventListener("liah:tema", lerCores);

  function ajustarTamanho() {
    // Desenha na resolução real da tela (fica nítido em celular/retina).
    var dpr = window.devicePixelRatio || 1;
    var lado = canvas.clientWidth || 300;
    canvas.width = lado * dpr;
    canvas.height = lado * dpr;
  }
  window.addEventListener("resize", ajustarTamanho);

  function calcularNivel(t) {
    var alvo;
    if (analisador && ouvindo) {
      analisador.getByteFrequencyData(dadosFreq);
      var soma = 0;
      for (var i = 0; i < dadosFreq.length; i++) soma += dadosFreq[i];
      alvo = Math.min(1, (soma / dadosFreq.length) / 90);
    } else if (falando) {
      // A síntese de voz não entrega o áudio: simulamos uma "fala" com ondas.
      alvo = 0.35 + 0.3 * Math.abs(Math.sin(t * 9)) * Math.abs(Math.sin(t * 2.3));
    } else {
      alvo = 0.04 + 0.03 * Math.sin(t * 1.5); // "respirando" em repouso
    }
    nivel += (alvo - nivel) * 0.18;          // suaviza para não tremer
    // No PALCO (e não na página toda): o navegador só recalcula o rosto, não o site inteiro.
    palco.style.setProperty("--nivel", nivel.toFixed(3));
  }

  function desenhar(t) {
    var w = canvas.width, h = canvas.height, cx = w / 2, cy = h / 2;
    ctx.clearRect(0, 0, w, h);
    var base = w * 0.2 * (1 + nivel * 0.35);

    // Brilho de fundo
    var brilho = ctx.createRadialGradient(cx, cy, base * 0.3, cx, cy, base * 2.1);
    brilho.addColorStop(0, cores.ciano + "55");
    brilho.addColorStop(1, cores.ciano + "00");
    ctx.fillStyle = brilho;
    ctx.fillRect(0, 0, w, h);

    // "Riscos" que saem da orbe conforme o som
    var raios = 72;
    ctx.lineCap = "round";
    ctx.lineWidth = Math.max(1.5, w * 0.006);
    for (var i = 0; i < raios; i++) {
      var ang = (i / raios) * Math.PI * 2 + t * 0.15;
      var freq = dadosFreq && ouvindo ? dadosFreq[i % dadosFreq.length] / 255 : 0;
      var onda = 0.5 + 0.5 * Math.sin(i * 0.9 + t * 3);
      var comp = base * (0.08 + nivel * 0.5 * onda + freq * 0.45);
      var r1 = base * 1.12;
      ctx.strokeStyle = cores.ciano + (cores.escuro ? "cc" : "aa");
      ctx.beginPath();
      ctx.moveTo(cx + Math.cos(ang) * r1, cy + Math.sin(ang) * r1);
      ctx.lineTo(cx + Math.cos(ang) * (r1 + comp), cy + Math.sin(ang) * (r1 + comp));
      ctx.stroke();
    }

    // A orbe: um círculo "vivo", com a borda ondulando
    var orbe = ctx.createRadialGradient(cx - base * 0.3, cy - base * 0.35, base * 0.1, cx, cy, base * 1.1);
    orbe.addColorStop(0, "#bfe9ff");
    orbe.addColorStop(0.45, cores.ciano);
    orbe.addColorStop(1, cores.azul);
    ctx.fillStyle = orbe;
    ctx.beginPath();
    for (var a = 0; a <= Math.PI * 2 + 0.01; a += Math.PI / 60) {
      var r = base * (1 + 0.03 * Math.sin(a * 5 + t * 2) + nivel * 0.08 * Math.sin(a * 8 - t * 3));
      var x = cx + Math.cos(a) * r, y = cy + Math.sin(a) * r;
      if (a === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.fill();
  }

  // A animação só RODA quando há rosto/orbe na tela (modos voz, robô, display) e a aba está visível.
  // No chat de texto ela fica parada: economiza bateria no celular e CPU no Raspberry Pi.
  var MODOS_ANIMADOS = ["voz", "robo", "voz-robo"];
  var animando = false;
  function deveAnimar() {
    return !document.hidden && (MODOS_ANIMADOS.indexOf(palco.dataset.modo) >= 0 || app.classList.contains("modo-display"));
  }

  function quadro(agora) {
    if (!deveAnimar()) { animando = false; return; }   // para o laço; volta quando o modo/aba mudar
    var t = agora / 1000;
    calcularNivel(t);
    if (palco.dataset.modo === "voz") {
      if (canvas.width === 0 || canvas.clientWidth * (window.devicePixelRatio || 1) !== canvas.width) ajustarTamanho();
      desenhar(t);
    }
    requestAnimationFrame(quadro);
  }
  function talvezAnimar() {
    if (!animando && deveAnimar()) { animando = true; requestAnimationFrame(quadro); }
  }
  // Religa quando a aba volta a ficar visível ou quando o modo do palco muda.
  document.addEventListener("visibilitychange", talvezAnimar);
  new MutationObserver(talvezAnimar).observe(palco, { attributes: true, attributeFilter: ["data-modo"] });
  new MutationObserver(talvezAnimar).observe(app, { attributes: true, attributeFilter: ["class"] });
  talvezAnimar();

  // Algumas vozes só carregam depois de um tempo
  if (window.speechSynthesis) window.speechSynthesis.onvoiceschanged = function () {};

  // Botão "ouvir" de cada resposta (funciona em QUALQUER modo, inclusive no chat de texto).
  var botaoLendo = null;
  function ler(texto, botao) {
    if (!window.speechSynthesis) return;
    var mesmoBotao = botaoLendo === botao && window.speechSynthesis.speaking;
    window.speechSynthesis.cancel();
    if (botaoLendo) botaoLendo.classList.remove("lendo");
    botaoLendo = null;
    if (mesmoBotao) return;                       // 2º clique no mesmo botão = parar
    var fala = new SpeechSynthesisUtterance(texto.replace(/[•*#]/g, ""));
    fala.lang = "pt-BR";
    var voz = escolherVoz();
    if (voz) fala.voice = voz;
    fala.onend = fala.onerror = function () { if (botao) botao.classList.remove("lendo"); botaoLendo = null; };
    if (botao) { botao.classList.add("lendo"); botaoLendo = botao; }
    window.speechSynthesis.speak(fala);
  }

  window.LiahVoz = {
    ler: ler,
    ouvirOuParar: function () { if (ouvindo) pararDeOuvir(); else comecarAOuvir(); },
    parar: function () { pararDeOuvir(); pararDeFalar(); desligarMedidor(); },
  };
})();
