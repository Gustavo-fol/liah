"""
python manage.py exportar_treino
python manage.py exportar_treino --incluir-rascunhos   (só para TESTES, nunca para produção)

Gera arquivos de TREINO de verdade (fine-tuning) a partir do dicionário APROVADO:

  liah-dicionario/exportacoes/openai-conversa.jsonl
      Cada fala (direta e sutil) vira um exemplo:  sistema + fala da pessoa -> resposta-modelo.
      É o formato que a OpenAI aceita em platform.openai.com > Fine-tuning.
      Depois do treino, a OpenAI te dá um nome de modelo (ft:...): cole em Área interna > IA.

  liah-dicionario/exportacoes/openai-analise.jsonl
      fala -> JSON com o contexto, o risco e o encaminhamento (ensina a CLASSIFICAR).

  liah-dicionario/exportacoes/gemini-conversa.jsonl
      O mesmo da conversa, no formato do Gemini (Vertex AI / Google AI Studio).

Os dados são FICTÍCIOS (escritos no dicionário), nenhuma conversa real de usuário entra aqui.
"""
import json

from django.core.management.base import BaseCommand

from nucleo import dicionario_arquivos
from nucleo.models import RegraDicionario
from nucleo.prompts import PROMPT_SISTEMA

PROMPT_ANALISE_TREINO = ("Você é o módulo de análise da Liah. Diga qual contexto do dicionário a fala encaixa, "
                         "o nível de risco e o encaminhamento, em JSON.")


class Command(BaseCommand):
    help = "Exporta o dicionário aprovado em JSONL para fine-tuning (OpenAI e Gemini)."

    def add_arguments(self, parser):
        parser.add_argument("--incluir-rascunhos", action="store_true",
                            help="Inclui contextos ainda NÃO aprovados (só para testes).")

    def handle(self, *args, **opcoes):
        regras = RegraDicionario.objects.filter(origem=RegraDicionario.Origem.ARQUIVO).exclude(status="arquivada")
        if not opcoes["incluir_rascunhos"]:
            regras = regras.filter(status=RegraDicionario.Status.APROVADA)

        saida = dicionario_arquivos.pasta() / "exportacoes"
        saida.mkdir(parents=True, exist_ok=True)
        conversa, analise, gemini = [], [], []

        for r in regras:
            d = r.detalhes or {}
            modelo = d.get("resposta_modelo", "").strip()
            for fala in d.get("falas_diretas", []) + d.get("falas_sutis", []):
                if modelo:
                    conversa.append({"messages": [
                        {"role": "system", "content": PROMPT_SISTEMA},
                        {"role": "user", "content": fala},
                        {"role": "assistant", "content": modelo},
                    ]})
                    gemini.append({
                        "systemInstruction": {"role": "system", "parts": [{"text": PROMPT_SISTEMA}]},
                        "contents": [
                            {"role": "user", "parts": [{"text": fala}]},
                            {"role": "model", "parts": [{"text": modelo}]},
                        ],
                    })
                analise.append({"messages": [
                    {"role": "system", "content": PROMPT_ANALISE_TREINO},
                    {"role": "user", "content": fala},
                    {"role": "assistant", "content": json.dumps({
                        "contexto": r.chave, "categoria": r.categoria,
                        "nivel_risco": r.nivel_risco, "encaminhamento": r.encaminhamento,
                    }, ensure_ascii=False)},
                ]})
            # Falsos positivos: ensinam a NÃO alarmar à toa.
            for fala in d.get("nao_confundir", []):
                analise.append({"messages": [
                    {"role": "system", "content": PROMPT_ANALISE_TREINO},
                    {"role": "user", "content": fala},
                    {"role": "assistant", "content": json.dumps({
                        "contexto": None, "categoria": None, "nivel_risco": "nenhum", "encaminhamento": "nenhum",
                    }, ensure_ascii=False)},
                ]})

        for nome, linhas in (("openai-conversa", conversa), ("openai-analise", analise), ("gemini-conversa", gemini)):
            with open(saida / f"{nome}.jsonl", "w", encoding="utf-8") as f:
                for linha in linhas:
                    f.write(json.dumps(linha, ensure_ascii=False) + "\n")
            self.stdout.write(f"  {nome}.jsonl: {len(linhas)} exemplo(s)")

        if not conversa:
            self.stdout.write(self.style.WARNING(
                "Nenhum contexto APROVADO ainda. Aprove no arquivo (aprovado = true + revisado_por) e importe, "
                "ou use --incluir-rascunhos só para testar o formato."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Pronto em {saida}"))
        if len(conversa) < 10:
            self.stdout.write("Dica: a OpenAI exige pelo menos 10 exemplos; o ideal são 50 a 100 ou mais.")
