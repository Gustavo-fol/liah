"""
Transforma o DICIONÁRIO APROVADO em texto para a IA principal ler.

Só entram regras com status "aprovada" e contextos marcados como "aprovado":
é aqui que a revisão do psicólogo vira comportamento real da Liah.

COMO A LIAH ESCOLHE O QUE LER (recuperação, a mesma ideia do "RAG"):
  Com centenas de contextos, mandar TODOS para a IA em cada mensagem seria caro, lento
  e confuso. Então, para cada mensagem, damos uma NOTA a cada contexto aprovado:
    - palavra-chave do contexto aparece na fala (ou nas últimas falas)  -> +3 cada
      (palavra sozinha vale também nas variações: "sumir" pega "sumisse", "sumindo")
    - palavras das falas de exemplo aparecem na fala                    -> +1 cada (máx. 3)
    - a fala tem sinal de risco, o contexto é de risco e já teve acerto -> +2
  Os contextos com maior nota (até MAX_SELECIONADOS) vão para a IA COMPLETOS:
  entrelinhas, o que não confundir, como responder, o que evitar e a RESPOSTA-MODELO,
  que funciona como exemplo de "é assim que se responde" (few-shot).
"""
from django.core.cache import cache

from .models import ContextoReferencia, RegraDicionario
from .texto import normalizar

MAX_REGRAS = 60              # limite da análise do laboratório
MAX_SELECIONADOS = 5         # contextos completos por mensagem na conversa
MAX_CARACTERES_CONTEXTO = 1500
PALAVRAS_VAZIAS = set("""a o e de da do das dos que eu me meu minha voce com para por um uma em no na nos nas
nao sim mas mais muito ja ta to tou isso esse essa ele ela se so ai la cara tipo""".split())


def regras_aprovadas():
    return RegraDicionario.objects.filter(status=RegraDicionario.Status.APROVADA)[:MAX_REGRAS]


def _indice():
    """
    Pré-processa as regras aprovadas UMA vez e guarda no cache por 5 minutos
    (importar o dicionário limpa o cache: veja limpar_indice()).
    """
    indice = cache.get("liah:dicionario:indice")
    if indice is None:
        indice = []
        for r in RegraDicionario.objects.filter(status=RegraDicionario.Status.APROVADA):
            chaves = [normalizar(p) for p in r.lista_palavras_chave()]
            palavras = set()
            for fala in r.lista_exemplos():
                palavras |= {p for p in normalizar(fala).split() if len(p) > 3 and p not in PALAVRAS_VAZIAS}
            indice.append({"pk": r.pk, "chaves": [c for c in chaves if c], "palavras": palavras,
                           "risco": r.nivel_risco})
        cache.set("liah:dicionario:indice", indice, 300)
    return indice


def _radical(palavra):
    """Raiz simples para pegar variações: 'sumir' -> 'sumi', 'chorando' -> 'chora'."""
    return palavra[:max(4, len(palavra) - 3)]


def _bate(chave, texto, palavras):
    """A palavra-chave aparece no texto? Frases: exatas. Palavra sozinha (5+ letras): também pelo radical."""
    if f" {chave} " in texto:
        return True
    if " " not in chave and len(chave) >= 5:
        raiz = _radical(chave)
        return any(p.startswith(raiz) for p in palavras)
    return False


def limpar_indice():
    cache.delete("liah:dicionario:indice")


def selecionar(mensagem, historico=None, nivel_risco="nenhum", limite=MAX_SELECIONADOS):
    """Devolve as regras aprovadas mais ligadas ao que a pessoa está falando agora."""
    ultimas = [h["texto"] for h in (historico or [])[-4:] if h.get("autor") == "usuario"]
    atual = f" {normalizar(mensagem)} "
    contexto = f" {normalizar(' '.join(ultimas))} "
    palavras_atual = set(atual.split())
    palavras_contexto = set(contexto.split())

    notas = []
    for item in _indice():
        nota = 0
        for chave in item["chaves"]:
            if _bate(chave, atual, palavras_atual):
                nota += 3
            elif _bate(chave, contexto, palavras_contexto):
                nota += 1           # a pessoa falou disso há pouco: ainda é relevante
        nota += min(len(item["palavras"] & palavras_atual), 3)
        if nota and nivel_risco != "nenhum" and item["risco"] != "nenhum":
            nota += 2               # só reforça quem já tem ligação com a fala
        if nota >= 2:
            notas.append((nota, item["pk"]))

    notas.sort(reverse=True)
    pks = [pk for _, pk in notas[:limite]]
    por_pk = RegraDicionario.objects.in_bulk(pks)
    return [por_pk[pk] for pk in pks if pk in por_pk]


def texto_regras(regras, com_orientacao=True):
    linhas = []
    for r in regras:
        d = r.detalhes or {}
        linhas.append(f"[REGRA {r.pk}] {r.titulo} ({r.get_categoria_display()})")
        linhas.append(f"  Sinais: {r.sinais}")
        if d.get("nao_confundir"):
            linhas.append("  NÃO confundir com: " + " | ".join(d["nao_confundir"][:4]))
        exemplos = r.lista_exemplos()
        if exemplos:
            linhas.append("  Exemplos: " + " | ".join(exemplos[:5]))
        linhas.append(f"  Risco: {r.nivel_risco} | Encaminhamento: {r.encaminhamento}")
        if com_orientacao:
            linhas.append(f"  Como responder: {r.orientacao}")
            if d.get("resposta_modelo"):
                linhas.append(f"  Exemplo de boa resposta (adapte, não copie): {d['resposta_modelo']}")
    return "\n".join(linhas)


def texto_contextos():
    partes = []
    for c in ContextoReferencia.objects.filter(aprovado=True)[:10]:
        partes.append(f"### {c.titulo}\n{c.conteudo[:MAX_CARACTERES_CONTEXTO]}")
    return "\n\n".join(partes)


def texto_dicionario_completo(mensagem="", historico=None, nivel_risco="nenhum"):
    """O bloco que entra no prompt da conversa com o usuário (só os contextos que importam agora)."""
    selecionadas = selecionar(mensagem, historico, nivel_risco) if mensagem else list(regras_aprovadas()[:MAX_SELECIONADOS])
    regras = texto_regras(selecionadas)
    contextos = texto_contextos()
    if not regras and not contextos:
        return ""
    partes = ["DICIONÁRIO DA LIAH (revisado por psicólogo). Estes são os contextos que PARECEM ligados à "
              "fala atual. Confira se a fala realmente se encaixa (veja o 'NÃO confundir com') antes de usar. "
              "Use para perceber o que a pessoa diz nas entrelinhas e para escolher como responder e quando "
              "encaminhar. Nunca diga à pessoa que ela 'se encaixa numa regra':"]
    if regras:
        partes.append(regras)
    if contextos:
        partes.append("CONTEXTOS DE REFERÊNCIA DO PSICÓLOGO:\n" + contextos)
    return "\n\n".join(partes)
