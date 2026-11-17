"""
DICIONÁRIO EM ARQUIVO: lê a pasta liah-dicionario/ (arquivos .toml) e grava no banco.

Por que arquivo e não o site?
  - Você escreve MUITOS contextos de uma vez, no VS Code, com busca, copiar/colar e Git.
  - O psicólogo pode revisar o próprio arquivo (ou um PDF dele).
  - O banco vira só uma "cópia de trabalho": a fonte da verdade é o arquivo.

Por que TOML?
  - Vem pronto no Python (tomllib, desde o 3.11): nada para instalar.
  - Aceita comentários (#) e textos de várias linhas (\"\"\" ... \"\"\"), e não quebra
    por causa de uma vírgula a mais, como o JSON.

Fluxo:  editar .toml  ->  python manage.py importar_dicionario  ->  a Liah já usa.
"""
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.db import transaction

from .models import Categoria, Encaminhamento, RegraDicionario

RISCOS = ("nenhum", "atencao", "alto")

# Campo do arquivo -> (obrigatório?, tipo esperado)
CAMPOS = {
    "id": (True, str),
    "titulo": (True, str),
    "situacao": (True, str),
    "nivel_risco": (True, str),
    "encaminhamento": (True, str),
    "palavras_chave": (True, list),
    "sinais_diretos": (False, list),
    "entrelinhas": (True, list),
    "falas_diretas": (False, list),
    "falas_sutis": (True, list),
    "nao_confundir": (False, list),
    "como_responder": (True, str),
    "evitar": (False, list),
    "resposta_modelo": (True, str),
    "aprovado": (False, bool),
    "revisado_por": (False, str),
    "observacoes_psicologo": (False, str),
}


@dataclass
class Leitura:
    contextos: list = field(default_factory=list)   # dicts prontos para gravar
    erros: list = field(default_factory=list)       # "arquivo: contexto: problema"
    arquivos: int = 0


def pasta():
    return Path(settings.LIAH_DICIONARIO_DIR)


def ler_pasta(caminho=None):
    """Lê e VALIDA todos os .toml. Não grava nada: só devolve o que achou e os erros."""
    caminho = Path(caminho) if caminho else pasta()
    leitura = Leitura()
    if not caminho.exists():
        leitura.erros.append(f"A pasta {caminho} não existe.")
        return leitura

    vistos = {}
    # Arquivos começando com "_" (modelo, rascunhos seus) são ignorados.
    for arquivo in sorted(caminho.glob("*.toml")):
        if arquivo.name.startswith("_"):
            continue
        leitura.arquivos += 1
        try:
            with open(arquivo, "rb") as f:          # tomllib exige abrir em modo binário
                dados = tomllib.load(f)
        except tomllib.TOMLDecodeError as erro:
            leitura.erros.append(f"{arquivo.name}: o arquivo tem um erro de escrita ({erro}).")
            continue

        categoria = dados.get("categoria")
        if categoria not in Categoria.values:
            leitura.erros.append(f"{arquivo.name}: categoria '{categoria}' não existe. "
                                 f"Use uma destas: {', '.join(Categoria.values)}.")
            continue

        for n, ctx in enumerate(dados.get("contexto", []), start=1):
            nome = ctx.get("id") or f"contexto nº {n}"
            problemas = _validar(ctx)
            if ctx.get("id") in vistos:
                problemas.append(f"o id '{ctx['id']}' já foi usado em {vistos[ctx['id']]}")
            if problemas:
                leitura.erros.extend(f"{arquivo.name}: {nome}: {p}" for p in problemas)
                continue
            vistos[ctx["id"]] = arquivo.name
            leitura.contextos.append({**ctx, "categoria": categoria, "arquivo": arquivo.name})
    return leitura


def _validar(ctx):
    problemas = []
    for campo, (obrigatorio, tipo) in CAMPOS.items():
        valor = ctx.get(campo)
        if valor is None:
            if obrigatorio:
                problemas.append(f"falta o campo '{campo}'")
            continue
        if not isinstance(valor, tipo):
            problemas.append(f"o campo '{campo}' deveria ser {'uma lista [ ]' if tipo is list else 'um texto' if tipo is str else 'true/false'}")
        elif tipo is list and not all(isinstance(i, str) and i.strip() for i in valor):
            problemas.append(f"a lista '{campo}' só pode ter textos não vazios")
        elif tipo is list and obrigatorio and not valor:
            problemas.append(f"a lista '{campo}' está vazia")
    desconhecidos = set(ctx) - set(CAMPOS)
    if desconhecidos:
        problemas.append(f"campos que não existem (erro de digitação?): {', '.join(sorted(desconhecidos))}")
    if ctx.get("nivel_risco") not in RISCOS:
        problemas.append(f"nivel_risco deve ser {', '.join(RISCOS)}")
    if ctx.get("encaminhamento") not in Encaminhamento.values:
        problemas.append(f"encaminhamento deve ser {', '.join(Encaminhamento.values)}")
    if ctx.get("nivel_risco") == "alto" and ctx.get("encaminhamento") != "emergencia":
        problemas.append("risco 'alto' precisa de encaminhamento 'emergencia' (segurança)")
    if ctx.get("aprovado") and not str(ctx.get("revisado_por", "")).strip():
        problemas.append("aprovado = true exige 'revisado_por' (nome do psicólogo e data)")
    if ctx.get("id") and not str(ctx["id"]).replace("-", "").replace("_", "").isalnum():
        problemas.append("o id só pode ter letras, números, - e _")
    return problemas


def _para_campos(ctx):
    """Transforma um contexto do arquivo nos campos da RegraDicionario."""
    sinais = "\n".join(
        [ctx["situacao"].strip()]
        + [f"- {s}" for s in ctx.get("sinais_diretos", [])]
        + ["Nas entrelinhas:"] + [f"- {s}" for s in ctx["entrelinhas"]]
    )
    orientacao = ctx["como_responder"].strip()
    if ctx.get("evitar"):
        orientacao += "\nEvitar: " + "; ".join(ctx["evitar"])
    aprovado = bool(ctx.get("aprovado"))
    return {
        "titulo": ctx["titulo"][:120],
        "categoria": ctx["categoria"],
        "sinais": sinais,
        "exemplos": "\n".join(ctx.get("falas_diretas", []) + ctx["falas_sutis"]),
        "nivel_risco": ctx["nivel_risco"],
        "orientacao": orientacao,
        "encaminhamento": ctx["encaminhamento"],
        "status": RegraDicionario.Status.APROVADA if aprovado else RegraDicionario.Status.RASCUNHO,
        "revisado_por_psicologo": aprovado,
        "observacoes_psicologo": "\n".join(
            x for x in (ctx.get("revisado_por", ""), ctx.get("observacoes_psicologo", "")) if x),
        "origem": RegraDicionario.Origem.ARQUIVO,
        "arquivo": ctx["arquivo"],
        "palavras_chave": "\n".join(ctx["palavras_chave"]),
        "detalhes": {
            "situacao": ctx["situacao"].strip(),
            "sinais_diretos": ctx.get("sinais_diretos", []),
            "entrelinhas": ctx["entrelinhas"],
            "falas_diretas": ctx.get("falas_diretas", []),
            "falas_sutis": ctx["falas_sutis"],
            "nao_confundir": ctx.get("nao_confundir", []),
            "como_responder": ctx["como_responder"].strip(),
            "evitar": ctx.get("evitar", []),
            "resposta_modelo": ctx["resposta_modelo"].strip(),
        },
    }


def importar(caminho=None, arquivar_ausentes=False):
    """
    Lê a pasta e grava no banco. SÓ grava se NÃO houver nenhum erro (tudo ou nada):
    assim um arquivo pela metade nunca deixa a Liah com um dicionário quebrado.
    Devolve (leitura, contagem).
    """
    leitura = ler_pasta(caminho)
    contagem = {"criadas": 0, "atualizadas": 0, "arquivadas": 0, "aprovadas": 0}
    if leitura.erros:
        return leitura, contagem

    with transaction.atomic():
        chaves = []
        for ctx in leitura.contextos:
            campos = _para_campos(ctx)
            _, criada = RegraDicionario.objects.update_or_create(chave=ctx["id"], defaults=campos)
            contagem["criadas" if criada else "atualizadas"] += 1
            contagem["aprovadas"] += campos["status"] == RegraDicionario.Status.APROVADA
            chaves.append(ctx["id"])
        if arquivar_ausentes:
            # Contexto que SAIU do arquivo: arquiva (não apaga, para não perder o histórico do laboratório).
            contagem["arquivadas"] = (
                RegraDicionario.objects.filter(origem=RegraDicionario.Origem.ARQUIVO)
                .exclude(chave__in=chaves).exclude(status=RegraDicionario.Status.ARQUIVADA)
                .update(status=RegraDicionario.Status.ARQUIVADA)
            )
    from .dicionario import limpar_indice   # a Liah passa a usar o dicionário novo na hora
    limpar_indice()
    return leitura, contagem
