"""
python manage.py importar_dicionario              -> valida e importa liah-dicionario/*.toml
python manage.py importar_dicionario --verificar  -> só confere os arquivos, não grava nada
python manage.py importar_dicionario --arquivar-ausentes
        -> contextos que você APAGOU do arquivo viram "arquivados" no banco
"""
from django.core.management.base import BaseCommand, CommandError

from nucleo import dicionario_arquivos


class Command(BaseCommand):
    help = "Importa o dicionário de contextos dos arquivos .toml da pasta liah-dicionario/."

    def add_arguments(self, parser):
        parser.add_argument("--verificar", action="store_true", help="Só valida, não grava.")
        parser.add_argument("--arquivar-ausentes", action="store_true",
                            help="Arquiva no banco os contextos que não estão mais nos arquivos.")
        parser.add_argument("--pasta", help="Outra pasta (padrão: LIAH/liah-dicionario).")

    def handle(self, *args, **opcoes):
        if opcoes["verificar"]:
            leitura = dicionario_arquivos.ler_pasta(opcoes["pasta"])
            contagem = None
        else:
            leitura, contagem = dicionario_arquivos.importar(opcoes["pasta"], opcoes["arquivar_ausentes"])

        self.stdout.write(f"Arquivos lidos: {leitura.arquivos} | contextos válidos: {len(leitura.contextos)}")
        if leitura.erros:
            for erro in leitura.erros:
                self.stderr.write(self.style.ERROR(f"  ✗ {erro}"))
            raise CommandError(f"{len(leitura.erros)} problema(s). Nada foi gravado: corrija e rode de novo.")

        if contagem is None:
            self.stdout.write(self.style.SUCCESS("Tudo certo nos arquivos. (Nada foi gravado: era só verificação.)"))
            return
        self.stdout.write(self.style.SUCCESS(
            f"Importado! {contagem['criadas']} novo(s), {contagem['atualizadas']} atualizado(s), "
            f"{contagem['arquivadas']} arquivado(s). Aprovados pelo psicólogo (a Liah já usa): {contagem['aprovadas']}."))
        pendentes = len(leitura.contextos) - contagem["aprovadas"]
        if pendentes:
            self.stdout.write(self.style.WARNING(
                f"{pendentes} contexto(s) ainda com aprovado = false: ficam como RASCUNHO e a Liah NÃO usa "
                "na conversa até o psicólogo aprovar (o laboratório já pode testá-los)."))
