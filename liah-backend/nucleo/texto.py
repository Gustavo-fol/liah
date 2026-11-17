"""
Ferramentas de TEXTO usadas pelas regras e pela detecção de risco.

normalizar() deixa a frase num formato "padrão" para comparar:
  "NÃO aguento   mais!!" -> "nao aguento mais"
Assim uma regra escrita uma vez pega todas as variações de acento e maiúscula.
"""
import re
import unicodedata


def normalizar(texto):
    texto = (texto or "").lower()
    # NFKD separa a letra do acento ("ã" vira "a" + "~"); depois jogamos o acento fora.
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)   # tira pontuação e emojis
    return re.sub(r"\s+", " ", texto).strip()     # junta espaços repetidos


def contem(texto_normalizado, padroes):
    """Devolve a lista de padrões (regex) que aparecem no texto."""
    return [p for p in padroes if re.search(p, texto_normalizado)]
