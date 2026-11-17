# Dicionário de contextos da Liah

Esta pasta é a **fonte da verdade** do que a Liah sabe perceber nas entrelinhas.
Você escreve aqui, no VS Code, e importa para o sistema com um comando.

## Como funciona

1. Cada arquivo `.toml` é **uma categoria** (`luto.toml`, `ansiedade.toml`...).
2. Dentro dele, cada bloco `[[contexto]]` é **uma situação** (não um tema genérico):
   "perda do animal de estimação" é diferente de "luto de pai ou mãe".
3. Rode no terminal, dentro de `liah-backend`:

   ```powershell
   python manage.py importar_dicionario --verificar   # só confere se está tudo certo
   python manage.py importar_dicionario               # grava no banco
   ```

   Se houver erro, o comando diz **o arquivo, o contexto e o problema**, e não grava nada.
4. A Liah já começa a usar os contextos **aprovados** na hora.

## Aprovação do psicólogo (obrigatória)

Todo contexto nasce com `aprovado = false`. Enquanto estiver assim:

- **NÃO** entra na conversa com usuários reais;
- **já pode** ser testado no Laboratório (área interna).

Depois que o psicólogo revisar, mude para:

```toml
aprovado = true
revisado_por = "Psic. Nome Sobrenome (CRP 00/00000), 20/11/2026"
```

Sem `revisado_por`, o comando recusa o `aprovado = true`.

## Como a Liah usa isso

A cada mensagem, a Liah dá uma nota para cada contexto aprovado (pelas `palavras_chave`
e pelas palavras das falas de exemplo) e manda para a IA **só os 5 mais ligados ao que a pessoa disse**,
completos, com a `resposta_modelo` como exemplo de como responder.
Por isso **palavras-chave boas são o mais importante**: pense em como a pessoa fala de verdade
("meu cachorro", "dog", "bichinho", "veterinário").

## Treino de verdade (fine-tuning)

```powershell
python manage.py exportar_treino
```

Gera em `liah-dicionario/exportacoes/`:

- `openai-conversa.jsonl`: fala -> resposta-modelo (para o fine-tuning da OpenAI)
- `openai-analise.jsonl`: fala -> contexto + risco (ensina a classificar, incluindo os "não confundir")
- `gemini-conversa.jsonl`: o mesmo da conversa, no formato do Gemini

Cada fala (direta e sutil) vira um exemplo. Quanto mais falas, melhor o treino:
o ideal é **10 ou mais falas sutis por contexto**.

## Regras de escrita (TOML)

- Texto curto entre aspas: `titulo = "Perda de animal de estimação"`
- Texto longo entre três aspas: `situacao = """ ... """`
- Listas entre colchetes, um item por linha, com vírgula no fim: `["frase 1", "frase 2",]`
- **Não use aspas duplas dentro de um texto**: troque por aspas simples ou “aspas curvas”.
- `#` começa um comentário (o sistema ignora).
- Arquivo que começa com `_` (como `_modelo.toml`) é ignorado: use para rascunhos.
- O `id` precisa ser **único** e nunca mudar (é ele que liga o arquivo ao banco).

## Valores aceitos

- `categoria`: luto, ansiedade, tristeza, ideacao, autolesao, isolamento, estresse,
  autoestima, sono, relacionamentos, violencia, outro
- `nivel_risco`: nenhum, atencao, alto (alto exige `encaminhamento = "emergencia"`)
- `encaminhamento`: nenhum, psicologo, psiquiatra, emergencia

## Segurança

- Nunca escreva métodos, meios ou detalhes de como alguém se machucaria.
- As falas são **fictícias**. Nunca copie conversas reais de usuários para cá.
