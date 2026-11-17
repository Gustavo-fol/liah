"""
TESTES DO NÚCLEO (o "cérebro" da Liah e a API).

Rodar: python manage.py test nucleo

A IA online NUNCA é chamada aqui: trocamos ia.gerar_resposta por um "dublê" (mock).
Assim os testes não gastam crédito, não precisam de internet e dão sempre o mesmo resultado.

O que estes testes protegem (os mais importantes do projeto):
  - risco ALTO sempre vira protocolo de crise, SEM passar pela IA
  - risco de ATENÇÃO sempre leva o CVV 188 na resposta
  - frases comuns ("morrendo de sono") NÃO disparam alarme
  - conversa salva CRIPTOGRAFADA e ninguém abre a conversa de outra pessoa
  - limite do visitante (15 por dia) e modo teste da equipe (nada salvo)
  - o dicionário em arquivo (liah-dicionario/) continua válido
"""
import json
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from contas.models import Consentimento, Usuario

from . import dicionario_arquivos
from .ia import IAIndisponivel
from .models import Conversa, Mensagem, RegraDicionario
from .processamento import processar_mensagem
from .regras import responder
from .risco import ALTO, ATENCAO, NENHUM, avaliar_risco

SENHA = "Senha-Forte-Liah-2026"

# "Dublês" da IA online
IA_FORA = mock.patch("nucleo.ia.gerar_resposta", side_effect=IAIndisponivel("sem IA nos testes"))
IA_OK = mock.patch("nucleo.ia.gerar_resposta", return_value="Resposta de teste da IA.")


def criar_usuario(email="ana@exemplo.com", consentiu=True, **extra):
    usuario = Usuario.objects.create_user(email=email, password=SENHA, situacao="ativa", **extra)
    if consentiu:
        Consentimento.objects.create(usuario=usuario, tipo=Consentimento.Tipo.DADOS_SENSIVEIS, versao="teste")
    return usuario


# ============================================================ DETECÇÃO DE RISCO

class RiscoTeste(TestCase):
    """Revise estas listas com a psicóloga: são exemplos do que NUNCA pode falhar."""

    def test_falas_de_risco_alto(self):
        for frase in ["eu quero morrer", "Vou me matar hoje", "penso em suicídio", "não quero mais viver",
                      "vou tirar minha vida"]:
            with self.subTest(frase=frase):
                self.assertEqual(avaliar_risco(frase).nivel, ALTO)

    def test_falas_de_atencao(self):
        for frase in ["ninguém sentiria minha falta", "não aguento mais", "queria dormir e não acordar",
                      "sou um peso pra todo mundo", "queria estar junto com ele"]:
            with self.subTest(frase=frase):
                self.assertEqual(avaliar_risco(frase).nivel, ATENCAO)

    def test_expressoes_comuns_nao_disparam_alarme(self):
        for frase in ["to morrendo de sono", "vou morrer de rir kkkk", "me matar de estudar pra prova",
                      "oi, tudo bem?", "meu time perdeu de novo"]:
            with self.subTest(frase=frase):
                self.assertEqual(avaliar_risco(frase).nivel, NENHUM)


class RegrasTeste(TestCase):
    def test_saudacao_sozinha_e_regra(self):
        self.assertEqual(responder("Oi, Liah").nome, "saudacao")

    def test_saudacao_com_desabafo_nao_e_regra(self):
        """'oi, meu cachorro morreu' tem que ir para a IA acolher, não ganhar um 'olá!'."""
        self.assertIsNone(responder("oi, meu cachorro morreu"))

    def test_quem_e_voce(self):
        self.assertEqual(responder("quem é você?").nome, "identidade")


# ============================================================ PROCESSAMENTO (o cérebro)

class ProcessamentoTeste(TestCase):
    def test_risco_alto_vai_para_o_protocolo_sem_ia(self):
        with IA_OK as ia:
            resposta = processar_mensagem("eu quero morrer")
        self.assertEqual(resposta.origem, "crise")
        self.assertIn("188", resposta.texto)
        ia.assert_not_called()   # a IA nem foi consultada

    def test_atencao_sempre_leva_o_cvv(self):
        with IA_OK:
            resposta = processar_mensagem("não aguento mais")
        self.assertEqual(resposta.risco, ATENCAO)
        self.assertIn("188", resposta.texto)

    def test_ia_fora_usa_a_resposta_reserva(self):
        with IA_FORA:
            resposta = processar_mensagem("hoje meu dia foi estranho")
        self.assertEqual(resposta.origem, "basica")
        self.assertTrue(resposta.texto)

    def test_ia_responde_normalmente(self):
        with IA_OK:
            resposta = processar_mensagem("hoje meu dia foi estranho")
        self.assertEqual(resposta.origem, "ia")


# ============================================================ API (usuário logado)

class APITeste(TestCase):
    def setUp(self):
        cache.clear()

    def enviar(self, corpo, url_nome="nucleo:api_enviar"):
        return self.client.post(reverse(url_nome), json.dumps(corpo), content_type="application/json")

    def test_status_publico(self):
        resposta = self.client.get(reverse("nucleo:api_status"))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["nome"], "Liah")

    def test_sem_login_recebe_401(self):
        self.assertEqual(self.enviar({"mensagem": "oi"}).status_code, 401)

    def test_sem_autorizacao_de_dados_recebe_403(self):
        self.client.force_login(criar_usuario(consentiu=False))
        resposta = self.enviar({"mensagem": "oi"})
        self.assertEqual(resposta.status_code, 403)
        self.assertTrue(resposta.json()["consentimento"])

    def test_mensagem_vazia_ou_grande_demais(self):
        self.client.force_login(criar_usuario())
        self.assertEqual(self.enviar({"mensagem": "   "}).status_code, 400)
        self.assertEqual(self.enviar({"mensagem": "a" * 2001}).status_code, 400)

    def test_conversa_salva_e_criptografada(self):
        usuario = criar_usuario()
        self.client.force_login(usuario)
        with IA_FORA:
            resposta = self.enviar({"mensagem": "meu segredo de teste"})
        self.assertEqual(resposta.status_code, 201)
        conversa = Conversa.objects.get(pk=resposta.json()["conversa_id"])
        self.assertEqual(conversa.usuario, usuario)
        pergunta = conversa.mensagens.get(autor=Mensagem.Autor.USUARIO)
        self.assertEqual(pergunta.texto, "meu segredo de teste")        # lendo pelo sistema: ok
        self.assertNotIn("segredo", pergunta.texto_cifrado)              # no banco: ilegível

    def test_ninguem_abre_a_conversa_de_outra_pessoa(self):
        """IDOR: o id da conversa vem do navegador; não pode abrir/apagar a de outro."""
        dono = criar_usuario()
        conversa = Conversa.objects.create(usuario=dono)
        self.client.force_login(criar_usuario(email="intruso@exemplo.com"))
        url = reverse("nucleo:api_conversa", args=[conversa.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)
        self.assertEqual(self.enviar({"mensagem": "oi", "conversa_id": conversa.pk}).status_code, 404)
        self.assertTrue(Conversa.objects.filter(pk=conversa.pk).exists())

    def test_lista_e_busca_so_nas_minhas_conversas(self):
        usuario = criar_usuario()
        self.client.force_login(usuario)
        with IA_FORA:
            self.enviar({"mensagem": "falei do meu cachorro"})
            self.enviar({"mensagem": "falei da escola"})
        todas = self.client.get(reverse("nucleo:api_conversas")).json()["conversas"]
        self.assertEqual(len(todas), 2)
        achadas = self.client.get(reverse("nucleo:api_conversas"), {"busca": "cachorro"}).json()["conversas"]
        self.assertEqual(len(achadas), 1)
        self.assertIn("cachorro", achadas[0]["previa"])

    def test_apagar_minha_conversa(self):
        usuario = criar_usuario()
        conversa = Conversa.objects.create(usuario=usuario)
        self.client.force_login(usuario)
        self.assertEqual(self.client.delete(reverse("nucleo:api_conversa", args=[conversa.pk])).status_code, 200)
        self.assertFalse(Conversa.objects.filter(pk=conversa.pk).exists())

    def test_limite_de_20_por_minuto(self):
        self.client.force_login(criar_usuario())
        with IA_FORA:
            codigos = [self.enviar({"mensagem": f"mensagem {i}"}).status_code for i in range(21)]
        self.assertEqual(codigos[-1], 429)

    def test_equipe_sem_autorizacao_testa_sem_salvar_nada(self):
        equipe = criar_usuario(email="equipe@exemplo.com", consentiu=False, is_staff=True)
        self.client.force_login(equipe)
        with IA_FORA:
            resposta = self.enviar({"mensagem": "teste da equipe"})
        self.assertEqual(resposta.status_code, 201)
        self.assertTrue(resposta.json()["teste"])
        self.assertFalse(Conversa.objects.filter(usuario=equipe).exists())

    def test_avaliar_resposta_da_liah(self):
        usuario = criar_usuario()
        self.client.force_login(usuario)
        with IA_FORA:
            dados = self.enviar({"mensagem": "hoje foi difícil"}).json()
        url = reverse("nucleo:api_avaliar", args=[dados["mensagem_id"]])
        self.assertEqual(self.client.post(url, json.dumps({"avaliacao": "util"}), content_type="application/json").status_code, 200)
        self.assertEqual(Mensagem.objects.get(pk=dados["mensagem_id"]).avaliacao, "util")
        self.assertEqual(self.client.post(url, json.dumps({"avaliacao": "5 estrelas"}), content_type="application/json").status_code, 400)

    def test_ninguem_avalia_resposta_de_outra_pessoa(self):
        dono = criar_usuario()
        self.client.force_login(dono)
        with IA_FORA:
            dados = self.enviar({"mensagem": "oi tudo bem com você hoje"}).json()
        self.client.force_login(criar_usuario(email="intruso@exemplo.com"))
        url = reverse("nucleo:api_avaliar", args=[dados["mensagem_id"]])
        resposta = self.client.post(url, json.dumps({"avaliacao": "nao_util"}), content_type="application/json")
        self.assertEqual(resposta.status_code, 404)
        self.assertEqual(Mensagem.objects.get(pk=dados["mensagem_id"]).avaliacao, "")

    def test_preferencia_de_tema(self):
        usuario = criar_usuario()
        self.client.force_login(usuario)
        self.assertEqual(self.enviar({"tema": "invalido"}, "nucleo:api_preferencias").status_code, 400)
        self.assertEqual(self.enviar({"tema": "escuro"}, "nucleo:api_preferencias").status_code, 200)
        usuario.refresh_from_db()
        self.assertEqual(usuario.tema, "escuro")


# ============================================================ VISITANTE

class VisitanteTeste(TestCase):
    def setUp(self):
        cache.clear()

    def enviar(self, texto="oi"):
        return self.client.post(reverse("nucleo:api_visitante"), json.dumps({"mensagem": texto}),
                                content_type="application/json")

    def test_visitante_conversa_sem_salvar(self):
        with IA_FORA:
            resposta = self.enviar("quem é você?")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["restantes"], 14)
        self.assertEqual(Conversa.objects.count(), 0)   # nada vai para o banco

    def test_limite_de_15_por_dia(self):
        with IA_FORA:
            for _ in range(15):
                self.assertEqual(self.enviar().status_code, 200)
            resposta = self.enviar()
        self.assertEqual(resposta.status_code, 429)
        self.assertTrue(resposta.json()["limite"])

    def test_visitante_em_crise_recebe_o_protocolo(self):
        resposta = self.enviar("eu quero morrer")
        self.assertEqual(resposta.json()["resposta"]["origem"], "crise")
        self.assertIn("188", resposta.json()["resposta"]["texto"])


# ============================================================ PÁGINAS

class PaginasTeste(TestCase):
    def test_chat_aberto_para_visitante(self):
        self.assertEqual(self.client.get(reverse("nucleo:chat")).status_code, 200)

    def test_sobre(self):
        resposta = self.client.get(reverse("nucleo:sobre"))
        self.assertContains(resposta, "Como a Liah decide o que responder")


# ============================================================ DICIONÁRIO EM ARQUIVO

class DicionarioTeste(TestCase):
    def test_arquivos_do_dicionario_sem_erros(self):
        """
        Lê a pasta liah-dicionario/ DE VERDADE. Se você errar algo num .toml,
        este teste falha e mostra o arquivo e o contexto com problema.
        """
        leitura = dicionario_arquivos.ler_pasta()
        self.assertEqual(leitura.erros, [], "\n".join(leitura.erros))
        self.assertGreater(len(leitura.contextos), 0)

    def test_importar_cria_rascunhos_e_reimportar_nao_duplica(self):
        _, contagem = dicionario_arquivos.importar()
        total = RegraDicionario.objects.filter(origem="arquivo").count()
        self.assertEqual(contagem["criadas"], total)
        _, contagem2 = dicionario_arquivos.importar()
        self.assertEqual(contagem2["criadas"], 0)                       # atualiza, não duplica
        self.assertEqual(RegraDicionario.objects.filter(origem="arquivo").count(), total)

    def test_contexto_nao_aprovado_nao_entra_na_conversa(self):
        from .dicionario import limpar_indice, selecionar
        dicionario_arquivos.importar()
        limpar_indice()
        aprovadas_no_arquivo = RegraDicionario.objects.filter(origem="arquivo", status="aprovada").exists()
        selecionadas = selecionar("meu cachorro morreu ontem")
        if not aprovadas_no_arquivo:
            self.assertEqual(selecionadas, [])   # rascunho NUNCA vai para o usuário
        for regra in selecionadas:
            self.assertEqual(regra.status, "aprovada")
