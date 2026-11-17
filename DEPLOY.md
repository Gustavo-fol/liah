# Colocar a Liah no ar (PythonAnywhere) e mantê-la segura

Guia passo a passo. Troque **SEUUSUARIO** pelo seu nome de usuário do PythonAnywhere
(o site vai ficar em `https://SEUUSUARIO.pythonanywhere.com`).

> **Regras de ouro**
> - O `.env` **nunca** vai para o GitHub nem é colado em chat.
> - Backup do banco e cópia do `.env` ficam em **lugares diferentes**.
> - No seu PC, `DJANGO_DEBUG=True`. No servidor, `DJANGO_DEBUG=False`.

---

## Parte 0: antes de subir (no seu PC)

Dentro de `liah-backend`, com o `.venv` ativado:

```powershell
python manage.py test                 # todos os testes precisam passar (OK no final)
pip freeze | Set-Content -Encoding ascii requirements.txt
```

Se algum teste falhar, **não suba**: copie o erro e resolva primeiro.

---

## Parte 1: o que o plano gratuito tem (e não tem)

Contas grátis criadas a partir de 15/01/2026:

| Tem | Não tem |
|---|---|
| 1 site em `SEUUSUARIO.pythonanywhere.com` com HTTPS | Tarefas agendadas (por isso o backup é feito pelo próprio site) |
| 512 MB de disco | Acesso livre à internet (só sites de uma lista; OpenAI e Google estão nela, confira a lista oficial) |
| E-mail pelo Gmail (o único SMTP liberado) | Domínio próprio |

⚠️ **O site grátis expira todo mês.** Entre no PythonAnywhere, aba **Web**, e clique no botão
de estender (*Run until 1 month from today*) antes de vencer. Coloque um lembrete no celular.

---

## Parte 2: levar o código

**Opção A (recomendada): pelo GitHub**
1. No PC: confira que `git status` **não** mostra `.env`, `liah-bd/` nem `.venv`, e faça o push.
2. No PythonAnywhere, aba **Consoles** → **Bash**:
   ```bash
   git clone https://github.com/SEU-GITHUB/LIAH.git ~/LIAH
   ```

**Opção B: pelo .zip**
Compacte a pasta LIAH **sem** `.env`, `.venv` e `liah-bd`. Na aba **Files**, envie o .zip e, no Bash:
`cd ~ && unzip LIAH.zip`

---

## Parte 3: preparar o servidor (console Bash)

```bash
cd ~/LIAH
python3.13 -m venv ~/.virtualenvs/liah          # ambiente virtual com Python 3.13
source ~/.virtualenvs/liah/bin/activate
pip install -r liah-backend/requirements.txt
mkdir -p liah-bd
```

### O `.env` do servidor

Na aba **Files**, abra `~/LIAH/` → *New file* → `.env`. Use valores **novos** de produção:

```ini
DJANGO_SECRET_KEY=   (gere uma nova: python -c "import secrets; print(secrets.token_urlsafe(50))")
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=SEUUSUARIO.pythonanywhere.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://SEUUSUARIO.pythonanywhere.com
LIAH_IP_HEADER=HTTP_X_REAL_IP

LIAH_HMAC_KEY=       (nova: python -c "import secrets; print(secrets.token_hex(32))")
LIAH_FERNET_KEY=     (nova: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
LIAH_ADMIN_URL=      (um endereço difícil, ex.: gestao-7f3k9q2a/)

LIAH_EMAIL_MODO=gmail
GMAIL_USUARIO=liahrobo.oficial@gmail.com
GMAIL_SENHA_APP=     (a senha de app de 16 letras)
LIAH_ADMINS=seu.email@gmail.com          (recebe um e-mail quando o site der erro 500)

GOOGLE_CLIENT_ID=    (se for usar "Continuar com Google")
GOOGLE_CLIENT_SECRET=

# Feira / evento: todo mundo no mesmo Wi-Fi conta como UMA rede. Suba o teto por rede:
LIAH_VISITANTE_IP_DIA=5000
```

🔐 **Guarde uma cópia deste `.env` no Bitwarden** (em especial `LIAH_FERNET_KEY` e `LIAH_HMAC_KEY`):
se elas se perderem, os CPFs, as conversas e as chaves de IA cifradas ficam ilegíveis para sempre.

### Banco, arquivos estáticos e admin

```bash
cd ~/LIAH/liah-backend
python manage.py check --deploy        # lista avisos de segurança (leia todos)
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
python manage.py importar_dicionario
python manage.py test                  # roda os testes também no servidor
```

---

## Parte 4: ligar o site (aba Web)

1. **Add a new web app** → *Manual configuration* → **Python 3.13**.
2. **Virtualenv:** `/home/SEUUSUARIO/.virtualenvs/liah`
3. **Source code** e **Working directory:** `/home/SEUUSUARIO/LIAH/liah-backend`
4. **WSGI configuration file** (clique no link e troque TODO o conteúdo por):
   ```python
   import os
   import sys

   caminho = "/home/SEUUSUARIO/LIAH/liah-backend"
   if caminho not in sys.path:
       sys.path.insert(0, caminho)

   os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"

   from django.core.wsgi import get_wsgi_application
   application = get_wsgi_application()
   ```
5. **Static files:** URL `/static/` → Directory `/home/SEUUSUARIO/LIAH/staticfiles`
6. **Security:** ligue **Force HTTPS**.
7. Clique em **Reload** e abra `https://SEUUSUARIO.pythonanywhere.com`.

Se aparecer erro: aba Web → **Error log** (a última linha diz o problema).

### Login com Google no servidor
No Google Cloud Console, em *Credenciais* → seu cliente OAuth, adicione o endereço de retorno:
`https://SEUUSUARIO.pythonanywhere.com/contas/google/retorno/`

### Depois de ligar
1. Entre como admin → **Área interna → IA** e cole as chaves (OpenAI e Gemini).
2. **Área interna → Painel**: confira se o backup automático apareceu.
3. Mande uma mensagem de teste no chat como visitante e outra logado.

---

## Parte 5: backups

### No servidor (automático)
O próprio site faz um backup quando alguém da equipe abre o **Painel** e o último tem mais de 24 h.
Os 10 últimos ficam em `~/LIAH/liah-bd/backups/`.

**Uma vez por semana**, baixe uma cópia: **Painel → Baixar o último backup**. Guarde no seu PC
ou na nuvem, **numa pasta diferente da cópia do `.env`**.

### No seu PC (Agendador de Tarefas do Windows)
1. Abra o **Agendador de Tarefas** → *Criar Tarefa Básica*.
2. Nome: `Backup Liah` · Disparador: **Diariamente** (ex.: 21:00).
3. Ação: **Iniciar um programa** → `C:\Users\quarto\Desktop\LIAH\ferramentas\backup_diario.bat`
4. Concluir. Para testar: clique com o botão direito na tarefa → **Executar**.
   O resultado fica em `liah-bd\backup-agendado.log`.

### Restaurar um backup (se precisar)
1. Pare o site (aba Web → *Disable*) ou o `runserver`.
2. Copie o backup escolhido por cima de `liah-bd/db.sqlite3` (guarde o atual antes, por segurança).
3. Use o **mesmo `.env`** da época do backup (as chaves precisam ser as mesmas).
4. Ligue o site de novo.

---

## Parte 6: atualizar o site depois de mudar o código

No PC: `python manage.py makemigrations` (se mudou algum model) → `python manage.py test` → commit
(**inclua as pastas `migrations/`**) → push. No Bash do PythonAnywhere:

```bash
cd ~/LIAH && git pull
source ~/.virtualenvs/liah/bin/activate
cd liah-backend
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py importar_dicionario
```

E clique em **Reload** na aba Web.

---

## Se der problema

| Sintoma | Onde olhar |
|---|---|
| Página de erro da Liah (500) | e-mail para `LIAH_ADMINS` + aba Web → Error log + `liah-bd/logs/liah.log` |
| "Bad Request (400)" | `DJANGO_ALLOWED_HOSTS` sem o seu endereço |
| "Página expirou" ao enviar formulário | `DJANGO_CSRF_TRUSTED_ORIGINS` sem o `https://...` |
| Site sem CSS | faltou `collectstatic` ou o mapeamento `/static/` na aba Web |
| E-mails não chegam | senha de app do Gmail; teste com `python manage.py testar_email` |
| Conta de outra pessoa bloqueada no login | normal após 5 senhas erradas: libera sozinha em 15 min |
