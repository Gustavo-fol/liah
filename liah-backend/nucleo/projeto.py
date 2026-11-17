"""
DADOS DO PROJETO Liah-Robo: versão, etapas e "o que já funciona".

Fica num arquivo só para que a página pública "Sobre a Liah" e a área interna
mostrem SEMPRE a mesma informação. Mudou de etapa? Mude aqui e pronto.
A situação de cada parte é calculada AO VIVO (ex.: se a IA está configurada agora).
"""
from django.conf import settings

VERSAO = "0.5-protótipo"
ETAPA_ATUAL = 2   # 1 = protótipo conversacional (concluída); 2 = IA avançada (agora)

ETAPAS = [
    ("Protótipo conversacional", "Regras, memória, API e a primeira interface."),
    ("Inteligência artificial avançada", "IA online, dicionário revisado por psicólogo e conversa com contexto."),
    ("Comunicação por voz", "Microfone, reconhecimento de fala e voz da Liah."),
    ("Construção do corpo", "Modelagem 3D, impressão e eletrônica."),
    ("Integração", "Software, display, sensores e movimentos juntos no Raspberry Pi."),
    ("Testes", "Usuários reais, avaliação com o psicólogo, falhas e ajustes."),
    ("Expansão", "Plano premium, automações, novas expressões e aplicações."),
]

# O caminho de cada mensagem (mesma ordem de processamento.processar_mensagem).
PIPELINE = [
    ("mensagem", "Mensagem", "texto limpo",
     "O texto chega pela página, pela voz ou (no futuro) pelo microfone do robô. "
     "É normalizado (minúsculas, sem acento) só para a análise; o original é guardado cifrado."),
    ("protecao", "Proteção", "sinais de risco",
     "Antes de tudo, a Liah procura sinais de risco. Se o risco é alto, ela NÃO usa IA: "
     "responde com o protocolo de crise (CVV 188, SAMU 192), sempre igual e revisável."),
    ("regras", "Regras", "frases conhecidas",
     "Sem nenhum sinal de risco, perguntas simples (saudação, quem é você, o que você faz, tchau) "
     "têm resposta fixa e instantânea, sem custo de IA."),
    ("ia", "IA principal", "com o dicionário",
     "Para o resto, a IA online responde com o histórico da conversa e as regras do dicionário "
     "aprovadas pelo psicólogo. Com sinal de atenção, a resposta sempre leva o caminho de ajuda."),
    ("reserva", "Reserva", "se a IA cair",
     "Se a IA estiver fora do ar, a Liah ainda responde com uma mensagem de acolhimento: "
     "a conversa nunca fica sem resposta."),
]

# origem da resposta (api) -> etapas do caminho que ela percorreu
CAMINHO_POR_ORIGEM = {
    "crise": ["mensagem", "protecao"],
    "regra": ["mensagem", "protecao", "regras"],
    "ia": ["mensagem", "protecao", "regras", "ia"],
    "basica": ["mensagem", "protecao", "regras", "ia", "reserva"],
}


def partes_do_sistema():
    """Tabela 'O que já funciona e o que ainda não existe', com a situação real de agora."""
    # Imports aqui dentro: este arquivo é lido quando o Django ainda está carregando os apps.
    from nucleo.models import ConfiguracaoIA, RegraDicionario

    cfg = ConfiguracaoIA.carregar()
    if not cfg.ativa:
        ia_principal = ("desligado", "Desligada pela equipe; a Liah responde pela reserva.")
    elif cfg.principal_pronta:
        ia_principal = ("funcionando", "Conversa natural com contexto e com o dicionário aprovado.")
    else:
        ia_principal = ("configurando", "Aguardando a chave da IA; enquanto isso a Liah usa a reserva.")
    aprovadas = RegraDicionario.objects.filter(status="aprovada").count()
    google = bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)

    return [
        ("Proteção e crise", "funcionando", "Detecta sinais de risco e mostra CVV 188 e SAMU 192. Nunca passa pela IA."),
        ("Regras fixas", "funcionando", "Saudação, identidade, capacidades, status, agradecimento e despedida."),
        ("IA principal", *ia_principal),
        ("Dicionário", "funcionando" if aprovadas else "em revisão",
         f"{aprovadas} regra(s) aprovada(s) pelo psicólogo. A IA secundária treina a principal no laboratório."),
        ("Contas e LGPD", "funcionando", "Cadastro com CPF cifrado, autorização de responsável, exportar e excluir dados."),
        ("Login com Google", "funcionando" if google else "planejado", "Entrar com a conta Google, sem criar senha."),
        ("Histórico", "funcionando", "Conversas salvas e cifradas na conta. Visitantes conversam sem salvar nada."),
        ("API v1", "funcionando", "Rotas de conversa, histórico e status, com login e limite de uso."),
        ("Interface web", "funcionando", "Chat, chat com robô, voz e voz com robô, tema claro e escuro."),
        ("Voz", "em teste", "Reconhecimento e fala pelo navegador. No robô, virá microfone e alto-falante."),
        ("Rosto da Liah", "simulado", "Expressões na tela; o display físico virá com o hardware."),
        ("Plano premium", "planejado", "Mensagens programadas por WhatsApp e e-mail com n8n."),
        ("Corpo e sensores", "planejado", "Estrutura impressa em 3D, servomotores e Raspberry Pi."),
    ]


def resumo():
    """Linha curta 'Servidor respondeu agora: ...' e os números da área interna."""
    from nucleo.models import ConfiguracaoIA, RegraDicionario

    cfg = ConfiguracaoIA.carregar()
    if not cfg.ativa:
        ia_txt = "IA desligada"
    elif cfg.principal_pronta:
        ia_txt = f"IA {cfg.get_provedor_principal_display()} ligada"
    else:
        ia_txt = "IA aguardando configuração"
    return {
        "versao": VERSAO,
        "etapa": ETAPA_ATUAL,
        "etapa_nome": ETAPAS[ETAPA_ATUAL - 1][0],
        "ia": ia_txt,
        "regras_aprovadas": RegraDicionario.objects.filter(status="aprovada").count(),
    }
