"""
SEGURANÇA DOS DADOS PESSOAIS (CPF e tokens).

Três ferramentas diferentes, cada uma com um papel:

1) validar_cpf  -> confere se o número É UM CPF possível (dígitos verificadores).
2) gerar_hmac   -> "impressão digital" do CPF com chave secreta. NÃO dá pra voltar
                   ao número. Serve para descobrir se o CPF já foi usado em outra conta.
3) cifrar/decifrar -> "cofre" com chave (Fernet). Dá pra ler o número de volta,
                   mas SÓ quem tem a chave LIAH_FERNET_KEY do .env.

As duas chaves ficam no .env. Se você PERDER as chaves:
  - os CPFs cifrados viram lixo ilegível (não tem como recuperar);
  - a checagem de duplicado para de funcionar.
Por isso: guarde uma cópia das chaves num lugar seguro (gerenciador de senhas).
"""
import hashlib
import hmac
import re

from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings
from django.core.exceptions import ValidationError


# ---------------------------------------------------------------- CPF

def limpar_cpf(cpf):
    """Tira pontos, traço e espaços: '123.456.789-09' -> '12345678909'."""
    # re.sub(padrão, troca, texto): \D significa "qualquer coisa que NÃO é dígito".
    return re.sub(r"\D", "", cpf or "")


def validar_cpf(cpf):
    """
    Devolve o CPF só com números se for válido. Se não for, levanta ValidationError
    (é assim que o Django mostra a mensagem de erro embaixo do campo).
    """
    digitos = limpar_cpf(cpf)

    # 11 dígitos, e não pode ser tudo igual (111.111.111-11 passa na conta, mas é falso).
    if len(digitos) != 11 or digitos == digitos[0] * 11:
        raise ValidationError("CPF inválido.")

    # Os 2 últimos dígitos são calculados a partir dos anteriores:
    #  - 1º verificador: os 9 primeiros dígitos multiplicados por 10, 9, 8 ... 2
    #  - 2º verificador: os 10 primeiros multiplicados por 11, 10, 9 ... 2
    # Soma tudo, multiplica por 10, pega o resto da divisão por 11 (se der 10, vira 0).
    for tamanho in (9, 10):
        soma = sum(int(digitos[i]) * (tamanho + 1 - i) for i in range(tamanho))
        verificador = (soma * 10) % 11 % 10
        if verificador != int(digitos[tamanho]):
            raise ValidationError("CPF inválido.")

    return digitos


def mascarar_cpf(digitos):
    """Para mostrar na tela sem expor o número: ***.***.***-09"""
    return f"***.***.***-{digitos[-2:]}" if digitos else "—"


# ---------------------------------------------------------------- HMAC

def gerar_hmac(texto):
    """
    hmac.new(chave, mensagem, algoritmo) mistura o texto com a CHAVE SECRETA e
    passa pelo SHA-256. Resultado: 64 caracteres hexadecimais, sempre iguais para
    o mesmo CPF + mesma chave. Sem a chave, um atacante não consegue testar
    os ~1 bilhão de CPFs possíveis para descobrir qual é qual.
    """
    chave = settings.LIAH_HMAC_KEY.encode()       # .encode(): texto -> bytes
    return hmac.new(chave, texto.encode(), hashlib.sha256).hexdigest()


def hash_token(token):
    """
    Hash simples (sem chave) para os tokens dos links de e-mail.
    Guardamos só o hash no banco: se o banco vazar, os links continuam inúteis.
    Aqui SHA-256 puro basta porque o token é aleatório e enorme (impossível de chutar).
    """
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------- Criptografia

def _fernet():
    """
    MultiFernet = um "chaveiro": CIFRA sempre com a 1ª chave (a atual) e consegue DECIFRAR
    com qualquer uma da lista (a atual + as antigas de LIAH_FERNET_KEYS_ANTIGAS).
    É isso que permite TROCAR a chave sem perder nada (veja o comando rotacionar_chave).
    """
    chaves = [settings.LIAH_FERNET_KEY, *getattr(settings, "LIAH_FERNET_KEYS_ANTIGAS", [])]
    return MultiFernet([Fernet(k.encode()) for k in chaves])


def cifrar(texto):
    """Tranca o texto. Cada vez gera um resultado diferente (mesmo para o mesmo CPF)."""
    return _fernet().encrypt(texto.encode()).decode()


def decifrar(texto_cifrado):
    """Destranca. Se a chave estiver errada, o Fernet levanta InvalidToken."""
    return _fernet().decrypt(texto_cifrado.encode()).decode()


def recifrar(texto_cifrado):
    """Decifra com a chave antiga e cifra de novo com a ATUAL (usado na rotação de chave)."""
    return _fernet().rotate(texto_cifrado.encode()).decode()
