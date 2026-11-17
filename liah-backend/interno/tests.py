"""
TESTES DA ÁREA INTERNA.

Rodar: python manage.py test interno

O que estes testes protegem:
  - quem NÃO é da equipe recebe 404 (nem descobre que a área existe)
  - só o super admin mexe nas chaves de IA e nos planos
  - a planilha de usuários sai SEM e-mail e SEM CPF (LGPD)
  - toda ação da equipe fica registrada
"""
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from contas.models import RegistroSeguranca, Usuario

SENHA = "Senha-Forte-Liah-2026"


def criar(email, **extra):
    return Usuario.objects.create_user(email=email, password=SENHA, situacao="ativa", **extra)


class AcessoTeste(TestCase):
    def setUp(self):
        cache.clear()
        self.comum = criar("comum@exemplo.com")
        self.equipe = criar("equipe@exemplo.com", is_staff=True)
        self.admin = criar("admin@exemplo.com", is_staff=True, is_superuser=True)

    def status(self, nome_url, usuario=None, *args):
        self.client.logout()
        if usuario:
            self.client.force_login(usuario)
        return self.client.get(reverse(nome_url, args=args)).status_code

    def test_visitante_e_usuario_comum_recebem_404(self):
        for nome in ["interno:painel", "interno:relatorios", "interno:dicionario", "interno:laboratorio"]:
            with self.subTest(pagina=nome):
                self.assertEqual(self.status(nome), 404)
                self.assertEqual(self.status(nome, self.comum), 404)

    def test_equipe_entra_nas_paginas_da_equipe(self):
        for nome in ["interno:painel", "interno:relatorios", "interno:dicionario", "interno:laboratorio"]:
            with self.subTest(pagina=nome):
                self.assertEqual(self.status(nome, self.equipe), 200)

    def test_chaves_de_ia_so_para_o_super_admin(self):
        self.assertEqual(self.status("interno:ia", self.equipe), 404)
        self.assertEqual(self.status("interno:ia", self.admin), 200)

    def test_planilha_de_seguranca_so_para_o_super_admin(self):
        self.assertEqual(self.status("interno:exportar_seguranca", self.equipe), 404)
        self.assertEqual(self.status("interno:exportar_seguranca", self.admin), 200)


class PlanilhaTeste(TestCase):
    def test_planilha_de_usuarios_sem_email(self):
        criar("pessoa.secreta@exemplo.com")
        self.client.force_login(criar("equipe@exemplo.com", is_staff=True))
        resposta = self.client.get(reverse("interno:exportar_usuarios"))
        self.assertEqual(resposta.status_code, 200)
        conteudo = resposta.content.decode("utf-8-sig")
        self.assertNotIn("pessoa.secreta", conteudo)
        self.assertNotIn("@", conteudo)
        self.assertIn("Conta nº", conteudo)
        # A exportação fica registrada no histórico da equipe
        self.assertTrue(RegistroSeguranca.objects.filter(tipo=RegistroSeguranca.Tipo.ACAO_EQUIPE).exists())


class PlanoTeste(TestCase):
    def setUp(self):
        self.pessoa = criar("pessoa@exemplo.com")

    def mudar(self, quem, plano="premium"):
        self.client.force_login(quem)
        return self.client.post(reverse("interno:mudar_plano", args=[self.pessoa.pk]), {"plano": plano})

    def test_super_admin_ativa_premium_e_fica_registrado(self):
        self.mudar(criar("admin@exemplo.com", is_staff=True, is_superuser=True))
        self.pessoa.refresh_from_db()
        self.assertEqual(self.pessoa.plano, "premium")
        self.assertTrue(RegistroSeguranca.objects.filter(
            tipo=RegistroSeguranca.Tipo.ACAO_EQUIPE, detalhe__contains="Plano").exists())

    def test_equipe_comum_nao_muda_plano(self):
        resposta = self.mudar(criar("equipe@exemplo.com", is_staff=True))
        self.assertEqual(resposta.status_code, 404)
        self.pessoa.refresh_from_db()
        self.assertEqual(self.pessoa.plano, "gratuito")

    def test_plano_inexistente_e_recusado(self):
        self.mudar(criar("admin@exemplo.com", is_staff=True, is_superuser=True), plano="vip-hacker")
        self.pessoa.refresh_from_db()
        self.assertEqual(self.pessoa.plano, "gratuito")
