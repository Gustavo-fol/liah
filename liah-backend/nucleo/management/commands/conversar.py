"""
python manage.py conversar

O SEU chatbot de dúvidas original, agora usando o cérebro da Liah.
Mesmo loop (input -> processar_mensagem -> print), mesmo "x" para sair,
mesmo histórico e mesma análise de dúvidas repetidas no final.
Não salva nada no banco: é para testar o núcleo rapidinho pelo terminal.
"""
from django.core.management.base import BaseCommand

from nucleo.processamento import processar_mensagem
from nucleo.servicos import duvidas_repetidas


class Command(BaseCommand):
    help = "Conversa com a Liah pelo terminal (modo teste, não salva nada)."

    def handle(self, *args, **opcoes):
        print("Seja bem-vindo(a)! Você está conversando com a Liah.")
        print("Para sair, digite 'x'")
        print("-" * 40)

        historico = []
        duvidas = []

        while True:
            try:
                mensagem = input("Você: ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if mensagem.lower() == "x":
                break

            if mensagem == "":
                print("Liah: Digite uma mensagem válida.")
                continue

            # O histórico vai no formato que o núcleo entende.
            historico_formatado = []
            for usuario, liah in historico:
                historico_formatado.append({"autor": "usuario", "texto": usuario})
                historico_formatado.append({"autor": "liah", "texto": liah})

            resposta = processar_mensagem(mensagem, historico_formatado)
            print("Liah:", resposta.texto)
            # Linha de "bastidores": ajuda a entender e testar o núcleo.
            print(self.style.WARNING(
                f"      [origem: {resposta.origem} | risco: {resposta.risco} | expressão: {resposta.expressao}]"
            ))

            historico.append((mensagem, resposta.texto))
            duvidas.append(mensagem)

        print("-" * 40)
        print("Histórico da conversa:")
        for usuario, liah in historico:
            print("Você:", usuario)
            print("Liah:", liah)
            print("-" * 20)

        repetidas = duvidas_repetidas(duvidas)
        print("Dúvidas repetidas:", repetidas if repetidas else "Nenhuma")
        print("Saindo...")
