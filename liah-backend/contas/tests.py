"""
TESTES DO APP CONTAS.

Rodar (dentro de liah-backend):   python manage.py test
Só este app:                      python manage.py test contas

Como funciona: o Django cria um BANCO DE TESTE vazio (não mexe no seu db.sqlite3),
roda cada teste e apaga tudo no final. Cada método que começa com "test_" é um teste.
self.assertEqual(a, b) = "isto TEM que ser igual"; se não for, o teste falha e mostra onde.

O que estes testes protegem:
  - CPF: validação, criptografia e a "impressão digital" (HMAC)
  - regras de idade do cadastro (12 / 18 anos)
  - login: só conta ATIVA entra, e o bloqueio depois de 5 senhas erradas
  - exclusão de conta e a proteção contra IDOR (mexer na conta de outra pessoa)
"""
from datetime import date, timedelta

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Consentimento, RegistroSeguranca, Usuario, calcular_idade
from .seguranca import cifrar, decifrar, gerar_hmac, mascarar_cpf, validar_cpf

SENHA = "Senha-Forte-Liah-2026"

# Nos testes, e-mail NUNCA sai de verdade: vai para uma "caixa" na memória (mail.outbox).
EMAIL_DE_TESTE = {
    "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
    "MAILERS": {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}},
}


def gerar_cpf(base):
    """Monta um CPF VÁLIDO a partir de 9 dígitos (calcula os 2 verificadores)."""
    digitos = [int(d) for d in str(base).zfill(9)[:9]]
    for tamanho in (9, 10):
        soma = sum(digitos[i] * (tamanho + 1 - i) for i in range(tamanho))
        digitos.append((soma * 10) % 11 % 10)
    return "".join(map(str, digitos))


def nascimento_com_idade(anos):
    """Data de nascimento de alguém que tem exatamente `anos` anos hoje (aniversário já passou)."""
    # 1º de janeiro: em qualquer dia do ano o aniversário já passou.
    return date(timezone.localdate().year - anos, 1, 1)


def criar_usuario(email="ana@exemplo.com", cpf_base=123456789, idade=30, situacao="ativa", **extra):
    usuario = Usuario.objects.create_user(
        email=email, password=SENHA, first_name="Ana",
        data_nascimento=nascimento_com_idade(idade), situacao=situacao, email_confirmado=True, **extra,
    )
    usuario.definir_cpf(gerar_cpf(cpf_base))
    usuario.save()
    return usuario


class BaseTeste(TestCase):
    def setUp(self):
        # O limitador de tentativas usa o cache: limpamos para um teste não afetar o outro.
        cache.clear()


# ============================================================ CPF E CRIPTOGRAFIA

class CPFTeste(TestCase):
    def test_cpf_valido_com_e_sem_pontuacao(self):
        cpf = gerar_cpf(529982247)
        self.assertEqual(validar_cpf(cpf), cpf)
        formatado = f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
        self.assertEqual(validar_cpf(formatado), cpf)

    def test_cpf_invalido(self):
        for errado in ["111.111.111-11", "123", "12345678900", "", "abcdefghijk"]:
            with self.subTest(cpf=errado), self.assertRaises(ValidationError):
                validar_cpf(errado)

    def test_mascara_mostra_so_os_dois_ultimos(self):
        self.assertEqual(mascarar_cpf("52998224725"), "***.***.***-25")

    def test_cifrar_e_decifrar(self):
        cifrado = cifrar("52998224725")
        self.assertNotIn("52998224725", cifrado)          # no banco não aparece o número
        self.assertEqual(decifrar(cifrado), "52998224725")
        self.assertNotEqual(cifrar("52998224725"), cifrado)  # cada vez sai diferente

    def test_hmac_sempre_igual_para_o_mesmo_cpf(self):
        self.assertEqual(gerar_hmac("52998224725"), gerar_hmac("52998224725"))
        self.assertNotEqual(gerar_hmac("52998224725"), gerar_hmac("52998224726"))


class UsuarioModeloTeste(TestCase):
    def test_cpf_guardado_cifrado_e_legivel(self):
        usuario = criar_usuario()
        self.assertEqual(usuario.ler_cpf(), gerar_cpf(123456789))
        self.assertNotIn(gerar_cpf(123456789), usuario.cpf_cifrado)

    def test_idade_antes_do_aniversario(self):
        hoje = timezone.localdate()
        amanha = hoje + timedelta(days=1)
        nascimento = date(amanha.year - 20, amanha.month, amanha.day)   # faz 20 anos AMANHÃ
        self.assertEqual(calcular_idade(nascimento), 19)  # ainda não fez 20

    def test_adolescente_precisa_de_autorizacao(self):
        adolescente = criar_usuario(idade=15)
        self.assertTrue(adolescente.precisa_autorizacao_responsavel())
        adulto = criar_usuario(email="b@exemplo.com", cpf_base=987654321, idade=30)
        self.assertFalse(adulto.precisa_autorizacao_responsavel())

    def test_so_adulto_ativo_com_cpf_pode_ser_responsavel(self):
        self.assertTrue(criar_usuario(idade=30).pode_ser_responsavel())
        self.assertFalse(criar_usuario(email="c@exemplo.com", cpf_base=111222333, idade=16).pode_ser_responsavel())
        self.assertFalse(criar_usuario(email="d@exemplo.com", cpf_base=444555666, situacao="pendente_email").pode_ser_responsavel())

    def test_email_salvo_em_minusculo(self):
        usuario = Usuario.objects.create_user(email="Maria@Exemplo.COM", password=SENHA)
        self.assertEqual(usuario.email, "maria@exemplo.com")


# ============================================================ CADASTRO

@override_settings(**EMAIL_DE_TESTE)
class CadastroTeste(BaseTeste):
    def dados(self, idade, **extra):
        nascimento = nascimento_com_idade(idade)
        dados = {
            "first_name": "Bia", "last_name": "Teste", "email": "Bia@Exemplo.com",
            "data_nascimento": nascimento.isoformat(),
            "cpf": gerar_cpf(529982247),
            "password1": SENHA, "password2": SENHA,
            "aceite_termos": "on", "aceite_dados_sensiveis": "on",
        }
        dados.update(extra)
        return dados

    def test_adulto_se_cadastra_e_fica_aguardando_email(self):
        resposta = self.client.post(reverse("contas:cadastro_proprio"), self.dados(25))
        self.assertRedirects(resposta, reverse("contas:cadastro_enviado"))
        usuario = Usuario.objects.get(email="bia@exemplo.com")      # salvo em minúsculo
        self.assertEqual(usuario.situacao, Usuario.Situacao.PENDENTE_EMAIL)
        self.assertTrue(usuario.tem_consentimento(Consentimento.Tipo.TERMOS))
        self.assertTrue(usuario.tem_consentimento(Consentimento.Tipo.DADOS_SENSIVEIS))
        self.assertFalse(usuario.tem_consentimento(Consentimento.Tipo.TREINO_IA))  # opcional, não marcado

    def test_menor_de_12_nao_cria_conta_sozinho(self):
        resposta = self.client.post(reverse("contas:cadastro_proprio"), self.dados(10))
        self.assertEqual(resposta.status_code, 200)       # voltou para o formulário com erro
        self.assertFalse(Usuario.objects.filter(email="bia@exemplo.com").exists())

    def test_adolescente_sem_dados_do_responsavel_nao_passa(self):
        resposta = self.client.post(reverse("contas:cadastro_proprio"), self.dados(15))
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Usuario.objects.filter(email="bia@exemplo.com").exists())

    def test_cpf_repetido_nao_passa(self):
        criar_usuario(email="outra@exemplo.com", cpf_base=529982247)
        resposta = self.client.post(reverse("contas:cadastro_proprio"), self.dados(25))
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Usuario.objects.filter(email="bia@exemplo.com").exists())

    def test_sem_aceitar_dados_sensiveis_nao_passa(self):
        dados = self.dados(25)
        del dados["aceite_dados_sensiveis"]
        self.client.post(reverse("contas:cadastro_proprio"), dados)
        self.assertFalse(Usuario.objects.filter(email="bia@exemplo.com").exists())


# ============================================================ LOGIN

class LoginTeste(BaseTeste):
    def entrar(self, email, senha):
        return self.client.post(reverse("contas:entrar"), {"username": email, "password": senha})

    def test_conta_ativa_entra(self):
        criar_usuario()
        resposta = self.entrar("ANA@exemplo.com", SENHA)   # maiúscula também funciona
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    def test_conta_sem_email_confirmado_nao_entra(self):
        criar_usuario(situacao="pendente_email")
        self.entrar("ana@exemplo.com", SENHA)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_bloqueia_depois_de_5_senhas_erradas(self):
        criar_usuario()
        for _ in range(5):
            self.entrar("ana@exemplo.com", "senha-errada")
        # Agora nem a senha CERTA funciona até passar o tempo de bloqueio.
        self.entrar("ana@exemplo.com", SENHA)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertTrue(RegistroSeguranca.objects.filter(tipo=RegistroSeguranca.Tipo.LOGIN_BLOQUEADO).exists())

    def test_paginas_da_conta_exigem_login(self):
        resposta = self.client.get(reverse("contas:painel"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("contas:entrar"), resposta["Location"])


# ============================================================ EXCLUSÃO E IDOR

@override_settings(**EMAIL_DE_TESTE)
class ExclusaoTeste(BaseTeste):
    def test_usuario_exclui_a_propria_conta(self):
        usuario = criar_usuario()
        self.client.force_login(usuario)
        resposta = self.client.post(reverse("contas:excluir_conta"), {"senha": SENHA, "confirmacao": "excluir"})
        self.assertRedirects(resposta, reverse("contas:conta_excluida"))
        self.assertFalse(Usuario.objects.filter(pk=usuario.pk).exists())

    def test_senha_errada_nao_exclui(self):
        usuario = criar_usuario()
        self.client.force_login(usuario)
        self.client.post(reverse("contas:excluir_conta"), {"senha": "errada", "confirmacao": "EXCLUIR"})
        self.assertTrue(Usuario.objects.filter(pk=usuario.pk).exists())

    def test_crianca_nao_exclui_a_propria_conta(self):
        responsavel = criar_usuario()
        crianca = criar_usuario(email="kid@exemplo.com", cpf_base=222333444, idade=9, responsavel=responsavel)
        self.client.force_login(crianca)
        self.client.post(reverse("contas:excluir_conta"), {"senha": SENHA, "confirmacao": "EXCLUIR"})
        self.assertTrue(Usuario.objects.filter(pk=crianca.pk).exists())

    def test_ninguem_exclui_a_crianca_de_outra_pessoa(self):
        """IDOR: trocar o número na URL não pode dar acesso à conta de outra família."""
        dono = criar_usuario()
        crianca = criar_usuario(email="kid@exemplo.com", cpf_base=222333444, idade=9, responsavel=dono)
        intruso = criar_usuario(email="intruso@exemplo.com", cpf_base=555666777)
        self.client.force_login(intruso)
        resposta = self.client.post(reverse("contas:excluir_dependente", args=[crianca.pk]),
                                    {"senha": SENHA, "confirmacao": "EXCLUIR"})
        self.assertEqual(resposta.status_code, 404)
        self.assertTrue(Usuario.objects.filter(pk=crianca.pk).exists())

    def test_responsavel_exclui_a_propria_crianca(self):
        dono = criar_usuario()
        crianca = criar_usuario(email="kid@exemplo.com", cpf_base=222333444, idade=9, responsavel=dono)
        self.client.force_login(dono)
        self.client.post(reverse("contas:excluir_dependente", args=[crianca.pk]),
                         {"senha": SENHA, "confirmacao": "EXCLUIR"})
        self.assertFalse(Usuario.objects.filter(pk=crianca.pk).exists())


# ============================================================ PÁGINAS DE ERRO

@override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"])
class PaginasDeErroTeste(TestCase):
    def test_404_com_a_cara_da_liah(self):
        resposta = self.client.get("/endereco-que-nao-existe/")
        self.assertEqual(resposta.status_code, 404)
        self.assertContains(resposta, "Não encontrei essa página", status_code=404)
        self.assertContains(resposta, "188", status_code=404)
