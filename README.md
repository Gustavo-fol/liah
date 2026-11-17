# Liah · robô de apoio emocional

Protótipo de software do **Liah-Robo**: uma IA de apoio emocional que conversa por texto e por voz
e que vai morar num pequeno robô (Raspberry Pi + display + microfone + alto-falante).

## Pastas

| Pasta | O que tem |
|---|---|
| `liah-backend/` | Django: `nucleo` (cérebro, API, IA), `contas` (cadastro, LGPD), `interno` (área da equipe) |
| `liah-interface/` | Páginas (templates) e arquivos estáticos (CSS/JS) |
| `liah-dicionario/` | Dicionário de contextos (TOML) usado no treino das IAs |
| `liah-bd/` | Banco SQLite, backups, cache e logs (**nunca vai para o GitHub**) |

## Rodar no PC (Windows)

```powershell
cd liah-backend
..\.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Configure o `.env` na pasta `LIAH` (modelo no `DEPLOY.md`). **Segredos nunca entram no código nem no GitHub.**

## Comandos úteis

| Comando | Para quê |
|---|---|
| `python manage.py test` | roda todos os testes |
| `python manage.py backup_banco` | backup do banco em `liah-bd/backups/` |
| `python manage.py manutencao` | apaga sessões vencidas e registros de segurança com mais de 180 dias |
| `python manage.py rotacionar_chave` | troca a chave de criptografia (instruções no próprio arquivo) |
| `python manage.py importar_dicionario` | carrega o dicionário de contextos |
| `python manage.py conversar` | conversa com a Liah pelo terminal |

## Ajustes pelo `.env` (opcionais)

| Variável | Padrão | Uso |
|---|---|---|
| `LIAH_VISITANTE_DIA` | 15 | mensagens grátis por dia, sem conta |
| `LIAH_VISITANTE_IP_DIA` | 1000 | teto por rede (**na feira, suba para 5000**: todos usam o mesmo Wi-Fi) |
| `LIAH_LIMITE_DIA_GRATUITO` | 150 | mensagens por dia, conta gratuita |
| `LIAH_LIMITE_DIA_PREMIUM` | 1000 | mensagens por dia, conta premium |
| `LIAH_ADMINS` | | e-mails que recebem aviso de erro 500 no servidor |
| `LIAH_FERNET_KEYS_ANTIGAS` | | só durante a troca de chave |

## Segurança (resumo)

- CPF, mensagens e chaves das IAs **criptografados** (Fernet); CPF duplicado detectado por HMAC.
- CSP com nonce, Permissions-Policy (microfone só na Liah), HTTPS/HSTS em produção.
- Limites: por minuto, por dia e por plano; bloqueio de força bruta no login e no "esqueci a senha".
- Risco alto (crise) **nunca** passa pela IA: resposta fixa com CVV 188 e SAMU 192.
- A equipe não vê o conteúdo das conversas.
