@echo off
REM ============================================================
REM  BACKUP DIARIO DA LIAH (Windows)
REM  Use no Agendador de Tarefas do Windows (veja o DEPLOY.md, parte 5).
REM  Guarda os 30 ultimos backups em LIAH\liah-bd\backups\
REM  Para uma 2a copia na nuvem, acrescente no fim da linha do python:
REM     --copiar-para "C:\Users\quarto\OneDrive\Liah-backups"
REM ============================================================
cd /d "%~dp0..\liah-backend"
"..\.venv\Scripts\python.exe" manage.py backup_banco --manter 30 >> "..\liah-bd\backup-agendado.log" 2>&1
