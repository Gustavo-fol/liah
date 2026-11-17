/* ============================================================
   CHAT DA LIAH (conversa por texto)

   Não tem inteligência aqui: pega o texto, manda para a API e mostra a resposta.
   Quem pensa é o núcleo no servidor (processar_mensagem).

   Três jeitos de conversar:
     visitante -> /api/v1/visitante/mensagens/ (15 por dia, histórico só no navegador)
     logado    -> /api/v1/mensagens/ (salvo e cifrado na conta)
     teste     -> equipe sem autorização de dados emocionais: igual ao logado, mas nada é salvo

   Expõe window.LiahChat para os outros arquivos:
     LiahChat.enviar(texto)  -> manda e devolve a resposta (usado também pela voz)
     LiahChat.novaConversa()
     LiahChat.mudarRosto(expressao)
   ============================================================ */
(function () {
  "use strict";

  var app = document.getElementById("app");
  if (!app) return;

  var visitante = app.dataset.visitante === "1";
  var teste = app.dataset.teste === "1";        // equipe testando: o histórico fica só no navegador
  var historicoLocal = visitante || teste;
  var urlEnviar = app.dataset.urlEnviar;
  var urlConversas = app.dataset.urlConversas;
  var urlCadastro = app.dataset.urlCadastro;
  var urlAvaliar = app.dataset.urlAvaliar;      // ".../mensagens/0/avaliacao/": o 0 vira o id da resposta

  var conversa = document.getElementById("conversa");
  var legenda = document.getElementById("legenda");
  var form = document.getElementById("form-chat");
  var campo = document.getElementById("campo");
  var botaoEnviar = document.getElementById("botao-enviar");
  var avisoCrise = document.getElementById("aviso-crise");
  var lista = document.getElementById("lista-conversas");
  var contador = document.getElementById("contador");
  var boasVindasModelo = document.getElementById("boas-vindas").cloneNode(true);
  // role="log": a conversa é um "registro". O anúncio para leitor de tela é feito pelo anunciador abaixo,
  // por isso desligamos o aria-live da conversa inteira (senão ele leria tudo duas vezes).
  conversa.setAttribute("role", "log");
  conversa.setAttribute("aria-live", "off");

  var conversaId = null;        // logado: id da conversa no servidor
  var historicoVisitante = [];  // visitante/teste: o histórico fica SÓ aqui, no navegador
  var ocupado = false;

  // ---------------------------------------------------------- utilidades
  // O token vem do tema.js (window.LiahUtil): uma função só para o site inteiro.
  function tokenCsrf() {
    if (window.LiahUtil) return window.LiahUtil.tokenCsrf();
    var achado = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return achado ? decodeURIComponent(achado[1]) : "";
  }

  var TEMPO_MAXIMO = 40000;   // 40 s: depois disso desistimos e avisamos (a rede pode ter caído)

  // ACESSIBILIDADE: leitores de tela (NVDA, TalkBack) anunciam o que entra aqui.
  // Só colocamos a RESPOSTA da Liah (e não cada botão ou a mensagem que a própria pessoa digitou).
  var anunciador = document.createElement("div");
  anunciador.className = "visualmente-oculto";
  anunciador.setAttribute("aria-live", "polite");
  anunciador.setAttribute("role", "status");
  document.body.appendChild(anunciador);
  function anunciar(texto) {
    anunciador.textContent = "";
    // pequeno atraso: alguns leitores só anunciam se o texto "mudar" depois de vazio
    setTimeout(function () { anunciador.textContent = "Liah disse: " + texto; }, 60);
  }


  // Uma função só para falar com a API. Devolve {ok, status, dados}.
  async function api(url, opcoes) {
    opcoes = opcoes || {};
    // AbortController: cancela o pedido se passar do tempo (sem isso, o "digitando" ficaria para sempre)
    var controle = new AbortController();
    var relogio = setTimeout(function () { controle.abort(); }, TEMPO_MAXIMO);
    try {
      var resposta = await fetch(url, Object.assign({
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": tokenCsrf() },
        signal: controle.signal,
      }, opcoes));
      var dados = await resposta.json().catch(function () { return {}; });
      return { ok: resposta.ok, status: resposta.status, dados: dados };
    } finally {
      clearTimeout(relogio);
    }
  }

  // O rosto tem um "motor" próprio (rosto.js): pisca, olha, dorme... Aqui só pedimos a expressão.
  function mudarRosto(expressao, duracao) {
    if (window.LiahRosto) { window.LiahRosto.definir(expressao, duracao); return; }
    document.querySelectorAll("[data-rosto]").forEach(function (rosto) {
      rosto.dataset.expressao = expressao;
    });
  }

  function rolarParaFim() { conversa.scrollTop = conversa.scrollHeight; }

  function tirarBoasVindas() {
    var bv = document.getElementById("boas-vindas");
    if (bv) bv.remove();
  }

  // textContent (e NÃO innerHTML): se alguém digitar <script>, aparece como texto
  // e não executa. Isso evita o ataque chamado XSS.
  function adicionarBalao(autor, texto) {
    tirarBoasVindas();
    var balao = document.createElement("div");
    balao.className = "balao " + autor;
    balao.textContent = texto;
    conversa.appendChild(balao);
    rolarParaFim();
    return balao;
  }

  // ---------------------------------------------------------- resposta da Liah (rostinho + ações)
  // Ícones fixos (escritos aqui, sem nada vindo do usuário): pode usar innerHTML com segurança.
  var ICONES = {
    ouvir: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9z"/><path d="M16 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11"/></svg>',
    copiar: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h8"/></svg>',
    util: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 11v9H4v-9zM7 11l4-8a2 2 0 0 1 3 2l-1 5h6a2 2 0 0 1 2 2l-2 7a2 2 0 0 1-2 1H7"/></svg>',
    nao_util: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 13V4H4v9zM7 13l4 8a2 2 0 0 0 3-2l-1-5h6a2 2 0 0 0 2-2l-2-7a2 2 0 0 0-2-1H7"/></svg>',
  };

  function botaoAcao(tipo, rotulo) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "acao acao-" + tipo;
    b.title = rotulo;
    b.setAttribute("aria-label", rotulo);
    b.innerHTML = ICONES[tipo];
    return b;
  }

  function adicionarRespostaLiah(texto, mensagemId, avaliacao) {
    tirarBoasVindas();
    var linha = document.createElement("div");
    linha.className = "resposta-liah";

    var rosto = document.createElement("div");
    rosto.className = "rosto-bolha";
    rosto.setAttribute("aria-hidden", "true");
    rosto.innerHTML = "<span></span><span></span>";

    var coluna = document.createElement("div");
    coluna.className = "resposta-coluna";
    var balao = document.createElement("div");
    balao.className = "balao liah";
    balao.textContent = texto;          // textContent: nada do texto vira HTML (anti-XSS)

    var acoes = document.createElement("div");
    acoes.className = "acoes";

    // 🔊 Ouvir: usa a voz do navegador (voz.js). Clicar de novo para.
    if (window.speechSynthesis) {
      var ouvir = botaoAcao("ouvir", "Ouvir a resposta");
      ouvir.addEventListener("click", function () {
        if (window.LiahVoz) window.LiahVoz.ler(texto, ouvir);
      });
      acoes.appendChild(ouvir);
    }

    // 📋 Copiar
    var copiar = botaoAcao("copiar", "Copiar a resposta");
    copiar.addEventListener("click", async function () {
      try {
        await navigator.clipboard.writeText(texto);
        copiar.classList.add("feito");
        copiar.setAttribute("aria-label", "Copiado");
        setTimeout(function () { copiar.classList.remove("feito"); copiar.setAttribute("aria-label", "Copiar a resposta"); }, 1500);
      } catch (e) { /* navegador sem permissão de área de transferência */ }
    });
    acoes.appendChild(copiar);

    // 👍/👎: só quando a resposta está salva (logado). Visitante e modo teste não avaliam.
    if (mensagemId) {
      var grupo = document.createElement("span");
      grupo.className = "avaliar";
      [["util", "Isso me ajudou"], ["nao_util", "Isso não me ajudou"]].forEach(function (par) {
        var b = botaoAcao(par[0], par[1]);
        b.setAttribute("aria-pressed", avaliacao === par[0] ? "true" : "false");
        b.addEventListener("click", function () { avaliar(mensagemId, par[0], grupo); });
        grupo.appendChild(b);
      });
      acoes.appendChild(grupo);
    }

    coluna.append(balao, acoes);
    linha.append(rosto, coluna);
    conversa.appendChild(linha);
    rolarParaFim();
    return balao;
  }

  async function avaliar(mensagemId, valor, grupo) {
    var botoes = grupo.querySelectorAll("button");
    var jaMarcado = grupo.querySelector('.acao-' + valor).getAttribute("aria-pressed") === "true";
    var novo = jaMarcado ? "" : valor;           // clicar de novo desmarca
    var r = await api(urlAvaliar.replace("/0/", "/" + mensagemId + "/"), {
      method: "POST", body: JSON.stringify({ avaliacao: novo }),
    });
    if (!r.ok) return;
    botoes.forEach(function (b) {
      b.setAttribute("aria-pressed", b.classList.contains("acao-" + novo) ? "true" : "false");
    });
  }

  function mostrarDigitando() {
    tirarBoasVindas();
    var balao = document.createElement("div");
    balao.className = "balao liah";
    balao.innerHTML = '<span class="digitando" aria-label="Liah está escrevendo"><span></span><span></span><span></span></span>';
    conversa.appendChild(balao);
    rolarParaFim();
    return balao;
  }

  function atualizarLegenda(falaUsuario, falaLiah) {
    legenda.innerHTML = "";
    if (falaUsuario) {
      var p1 = document.createElement("p");
      p1.className = "fala-usuario";
      p1.textContent = "Você: " + falaUsuario;
      legenda.appendChild(p1);
    }
    if (falaLiah) {
      var p2 = document.createElement("p");
      p2.className = "fala-liah";
      p2.textContent = falaLiah;
      legenda.appendChild(p2);
    }
  }

  function mostrarAvisoCrise(risco) {
    avisoCrise.classList.toggle("oculto", !risco || risco === "nenhum");
  }

  function convidarCadastro(textoErro) {
    tirarBoasVindas();
    var balao = document.createElement("div");
    balao.className = "balao aviso";
    balao.appendChild(document.createTextNode(textoErro + " "));
    var link = document.createElement("a");
    link.href = urlCadastro;
    link.textContent = "Criar conta grátis";
    balao.appendChild(link);
    conversa.appendChild(balao);
    rolarParaFim();
  }

  function atualizarContador(restantes) {
    if (!contador || restantes === undefined) return;
    // Duas versões do mesmo texto: a curta aparece no celular, a longa no computador (CSS decide).
    var limite = app.dataset.limite;
    contador.querySelector("strong").textContent = restantes;
    contador.querySelector(".so-estreito").textContent = "/" + limite + " hoje";
    contador.querySelector(".so-largo").textContent = restantes === 1 ? " mensagem grátis hoje" : " mensagens grátis hoje";
  }

  // ---------------------------------------------------------- enviar
  async function enviar(texto) {
    texto = (texto || "").trim();
    if (!texto || ocupado) return null;
    ocupado = true;
    botaoEnviar.disabled = true;

    adicionarBalao("usuario", texto);
    atualizarLegenda(texto, "...");
    mudarRosto("pensando");
    var carregando = mostrarDigitando();

    var corpo = historicoLocal
      ? { mensagem: texto, historico: historicoVisitante }
      : { mensagem: texto, conversa_id: conversaId };

    try {
      var r = await api(urlEnviar, { method: "POST", body: JSON.stringify(corpo) });
      carregando.remove();

      if (!r.ok) {
        if (r.dados.limite) {
          convidarCadastro(r.dados.erro);
          atualizarContador(0);
        } else if (r.dados.consentimento) {
          pedirAutorizacao(r.dados.erro, r.dados.url);
        } else {
          adicionarBalao("erro", r.dados.erro || "Não consegui falar com a Liah. Verifique sua conexão.");
        }
        mudarRosto("confusa", 3000);
        atualizarLegenda(texto, r.dados.erro || "");
        return null;
      }

      var resposta = r.dados.resposta;
      adicionarRespostaLiah(resposta.texto, r.dados.mensagem_id || null);
      anunciar(resposta.texto);
      atualizarLegenda(texto, resposta.texto);
      // O rosto reage SEMPRE, com ou sem IA: usa a expressão do servidor ou lê o sentimento do texto.
      if (window.LiahRosto) window.LiahRosto.reagir(texto, resposta);
      else mudarRosto(resposta.expressao);
      if (resposta.risco !== "nenhum") mostrarAvisoCrise(resposta.risco);
      // Para a página "Sobre a Liah" acender o caminho usado. Só a ORIGEM, nunca o texto.
      try {
        sessionStorage.setItem("liah-ultima", JSON.stringify(
          { origem: resposta.origem, risco: resposta.risco, expressao: resposta.expressao }));
      } catch (e) { /* navegador sem sessionStorage: a página Sobre só não acende o caminho */ }

      if (historicoLocal) {
        historicoVisitante.push({ autor: "usuario", texto: texto }, { autor: "liah", texto: resposta.texto });
        historicoVisitante = historicoVisitante.slice(-10);
        if (visitante) atualizarContador(r.dados.restantes);
      } else {
        var nova = conversaId === null;
        conversaId = r.dados.conversa_id;
        if (nova) carregarConversas();
      }
      return resposta;
    } catch (erro) {
      carregando.remove();
      adicionarBalao("erro", erro && erro.name === "AbortError"
        ? "A Liah demorou demais para responder. Tente de novo em instantes."
        : "Sem conexão com a Liah. Tente de novo.");
      mudarRosto("confusa", 3000);
      return null;
    } finally {
      ocupado = false;
      botaoEnviar.disabled = false;
    }
  }

  // ---------------------------------------------------------- conversas (só logado)
  async function carregarConversas() {
    if (historicoLocal || !lista) return;
    var r = await api(urlConversas);
    if (!r.ok) return;
    preencherContinuar(r.dados.conversas);
    lista.innerHTML = "";
    r.dados.conversas.forEach(function (c) {
      var item = document.createElement("li");
      var abrir = document.createElement("button");
      abrir.type = "button";
      abrir.className = "item-conversa" + (c.id === conversaId ? " ativa" : "");
      abrir.textContent = c.previa || c.titulo;
      abrir.title = c.titulo;
      abrir.addEventListener("click", function () { abrirConversa(c.id); });

      var apagar = document.createElement("button");
      apagar.type = "button";
      apagar.className = "apagar-conversa";
      apagar.title = "Apagar conversa";
      apagar.setAttribute("aria-label", "Apagar " + c.titulo);
      apagar.textContent = "×";
      apagar.addEventListener("click", function () { apagarConversa(c.id); });

      item.append(abrir, apagar);
      lista.appendChild(item);
    });
  }

  async function abrirConversa(id) {
    fecharHistorico();
    var r = await api(urlConversas + id + "/");
    if (!r.ok) return;
    conversaId = id;
    conversa.innerHTML = "";
    var maiorRisco = "nenhum";
    var ultimaUsuario = "", ultimaLiah = "";
    r.dados.mensagens.forEach(function (m) {
      if (m.autor === "liah") adicionarRespostaLiah(m.texto, m.id, m.avaliacao);
      else adicionarBalao(m.autor, m.texto);
      if (m.risco !== "nenhum") maiorRisco = m.risco;
      if (m.autor === "usuario") ultimaUsuario = m.texto; else ultimaLiah = m.texto;
    });
    atualizarLegenda(ultimaUsuario, ultimaLiah);
    mostrarAvisoCrise(maiorRisco);
    mudarRosto("neutra");
    document.dispatchEvent(new CustomEvent("liah:fechar-menu"));
    carregarConversas();
  }

  async function apagarConversa(id) {
    if (!window.confirm("Apagar esta conversa para sempre?")) return;
    await api(urlConversas + id + "/", { method: "DELETE" });
    if (id === conversaId) novaConversa();
    carregarConversas();
  }

  function novaConversa() {
    conversaId = null;
    historicoVisitante = [];
    conversa.innerHTML = "";
    var bv = boasVindasModelo.cloneNode(true);
    conversa.appendChild(bv);
    ligarSugestoes(bv);
    atualizarLegenda("", "");
    mostrarAvisoCrise("nenhum");
    mudarRosto("feliz");
    carregarConversas();
    campo.focus();
  }

  // ---------------------------------------------------------- "continuar de onde parou"
  function preencherContinuar(conversas) {
    var caixa = conversa.querySelector("[data-continuar]");
    if (!caixa) return;
    var ul = caixa.querySelector("ul");
    ul.innerHTML = "";
    conversas.slice(0, 3).forEach(function (c) {
      var li = document.createElement("li");
      var b = document.createElement("button");
      b.type = "button";
      b.className = "continuar-item";
      var t = document.createElement("strong");
      t.textContent = c.previa || "Conversa";
      var d = document.createElement("span");
      d.textContent = c.titulo.replace("Conversa de ", "") + " · " + c.mensagens + " mensagens";
      b.append(t, d);
      b.addEventListener("click", function () { abrirConversa(c.id); });
      li.appendChild(b);
      ul.appendChild(li);
    });
    caixa.hidden = conversas.length === 0;
  }

  // ---------------------------------------------------------- painel de histórico
  var painelHist = document.getElementById("historico");
  var listaHist = document.getElementById("historico-lista");
  var infoHist = document.getElementById("historico-info");
  var campoHist = document.getElementById("historico-campo");

  function formatarData(iso) {
    var d = new Date(iso);
    return d.toLocaleDateString("pt-BR") + " " + d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  }

  async function mostrarHistorico(busca) {
    if (!painelHist) return;
    painelHist.hidden = false;
    infoHist.textContent = "Carregando...";
    var url = urlConversas + (busca ? "?busca=" + encodeURIComponent(busca) : "");
    var r = await api(url);
    listaHist.innerHTML = "";
    if (!r.ok) { infoHist.textContent = r.dados.erro || "Não consegui carregar o histórico."; return; }
    var cs = r.dados.conversas;
    infoHist.textContent = busca
      ? cs.length + " conversa(s) com “" + busca + "”."
      : (cs.length ? cs.length + " conversa(s) guardada(s)." : "Você ainda não tem conversas guardadas. Fale com a Liah e elas aparecem aqui.");
    cs.forEach(function (c) {
      var li = document.createElement("li");
      li.className = "historico-item";
      var abrir = document.createElement("button");
      abrir.type = "button";
      abrir.className = "historico-abrir";
      var t = document.createElement("strong");
      t.textContent = c.previa || "(sem texto)";
      var meta = document.createElement("span");
      meta.textContent = formatarData(c.atualizada_em) + " · " + c.mensagens + " mensagens";
      abrir.append(t, meta);
      abrir.addEventListener("click", function () { fecharHistorico(); abrirConversa(c.id); });
      var apagar = document.createElement("button");
      apagar.type = "button";
      apagar.className = "botao neutro pequeno";
      apagar.textContent = "Apagar";
      apagar.setAttribute("aria-label", "Apagar a conversa de " + formatarData(c.atualizada_em));
      apagar.addEventListener("click", async function () {
        await apagarConversa(c.id);
        mostrarHistorico(campoHist.value.trim());
      });
      li.append(abrir, apagar);
      listaHist.appendChild(li);
    });
  }
  function fecharHistorico() { if (painelHist) painelHist.hidden = true; }

  if (painelHist) {
    document.getElementById("abrir-historico").addEventListener("click", function () {
      document.dispatchEvent(new CustomEvent("liah:fechar-menu"));
      mostrarHistorico("");
      campoHist.focus();
    });
    document.getElementById("fechar-historico").addEventListener("click", fecharHistorico);
    document.getElementById("historico-busca").addEventListener("submit", function (e) {
      e.preventDefault();
      mostrarHistorico(campoHist.value.trim());
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") fecharHistorico(); });
  }

  // ---------------------------------------------------------- falta de autorização (LGPD)
  function pedirAutorizacao(textoErro, url) {
    var div = document.createElement("div");
    div.className = "balao erro";
    div.append(document.createTextNode(textoErro + " "));
    var link = document.createElement("a");
    link.href = url;
    link.textContent = "Ver minhas autorizações";
    div.appendChild(link);
    conversa.appendChild(div);
    rolarParaFim();
  }

  function ligarSugestoes(raiz) {
    raiz.querySelectorAll(".sugestao").forEach(function (botao) {
      botao.addEventListener("click", function () { enviar(botao.textContent); });
    });
  }

  // ---------------------------------------------------------- caixa de texto
  function ajustarAltura() {
    campo.style.height = "auto";
    campo.style.height = Math.min(campo.scrollHeight, 160) + "px";
  }

  form.addEventListener("submit", function (evento) {
    evento.preventDefault(); // não recarrega a página: é isso que faz o app ser uma SPA
    if (ocupado) return;     // ainda esperando a resposta anterior: NÃO apaga o que a pessoa digitou
    var texto = campo.value;
    campo.value = "";
    ajustarAltura();
    enviar(texto);
  });
  campo.addEventListener("input", ajustarAltura);
  // Celular/tablet (tela de toque): Enter PULA LINHA, quem envia é o botão (igual ao WhatsApp).
  var telaDeToque = window.matchMedia && window.matchMedia("(pointer: coarse)").matches;
  campo.addEventListener("keydown", function (e) {
    // isComposing: a pessoa ainda está montando a palavra (acentos, teclado japonês...): não envia
    if (e.isComposing || e.keyCode === 229) return;
    if (e.key === "Enter" && !e.shiftKey && !telaDeToque) {  // Enter envia; Shift+Enter pula linha
      e.preventDefault();
      form.requestSubmit();
    }
  });

  ligarSugestoes(document);
  carregarConversas();

  window.LiahChat = { enviar: enviar, novaConversa: novaConversa, mudarRosto: mudarRosto };
})();
