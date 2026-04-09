# Roteiro de Video - MCP CRM

> Versao enxuta, alinhada com o que foi validado de verdade no workspace.

## Visao Geral

O objetivo aqui nao e mostrar arquitetura no vacuo. O objetivo e provar execucao real com o caminho oficial do projeto:

- embedder `sentence-transformers`
- base oficial do NCM
- SQLite bootstrapado por JSON
- teste pelo proprio Copilot usando o servidor MCP do workspace

## Resultado Validado

| Etapa | Resultado |
| --- | --- |
| Exemplo local com `sentence-transformers` e NCM oficial | OK |
| Exemplo Docker com `sentence-transformers` e NCM oficial | OK |
| Pergunta via Copilot/MCP sobre a base oficial | OK |
| Suite local | 60 passed, 1 skipped |
| Ruff | OK |

## Setup Antes de Gravar

Use um runtime limpo para a parte Docker e limpe tambem o runtime padrao do workspace para a parte do Copilot.

### Bash

```bash
rm -rf .demo-runtime
mkdir -p .demo-runtime

rm -f data/runtime/users.db data/runtime/users.faiss
rm -rf data/runtime/import data/runtime/import-cache
mkdir -p data/runtime/import
cp /home/lira/Downloads/Tabela_NCM_Vigente_20260319.json data/runtime/import/
```

### Nushell

```nu
rm -rf .demo-runtime
mkdir .demo-runtime

rm -f data/runtime/users.db data/runtime/users.faiss
rm -rf data/runtime/import data/runtime/import-cache
mkdir data/runtime/import
cp /home/lira/Downloads/Tabela_NCM_Vigente_20260319.json data/runtime/import/
```

## Roteiro Principal

### 1. Abertura

**Na tela**  
Repositorio aberto e terminal na raiz.

**Fala**

> Hoje eu vou mostrar o MCP CRM rodando no caminho oficial do projeto.
>
> A demonstracao usa `sentence-transformers`, carrega a tabela oficial do NCM no SQLite e depois prova o mesmo servidor MCP sendo usado pelo Copilot no editor.

### 2. Build da imagem

**Comando**

```bash
docker build -t mcp-crm:latest .
```

**Fala**

> Primeiro eu garanto a imagem final que empacota o servidor e as dependencias do projeto.

### 3. Demo principal no container

**Comando**

```bash
docker run --rm \
  -e MCP_EMBEDDING_PROVIDER=sentence-transformers \
  -e MCP_LLM_PROVIDER=stub \
  -e MCP_IMPORT_SOURCE_PATH=/downloads/Tabela_NCM_Vigente_20260319.json \
  -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  -v /home/lira/Downloads:/downloads:ro \
  -v "$(pwd)/.demo-runtime:/app/data/runtime" \
  mcp-crm:latest python docs/client_example.py
```

**Fala**

> Esse e o fluxo principal no container.
>
> O servidor importa o NCM oficial, lista os primeiros registros, encontra o `0101.21.00`, busca pela descricao exata e fecha com `get_user`, `ask_crm` e `create_user`.

**Pontos para destacar**

- O provider aqui nao e o embedder de teste. E o `sentence-transformers` da configuracao oficial.
- O mount de `~/.cache/huggingface` evita redownload do modelo e reduz o risco de `429` do Hugging Face no meio da gravacao.
- No fluxo validado, `search_users` trouxe `0101.21.00` em primeiro lugar com score `1.0`.

### 4. Prova do MCP pelo Copilot

**Na tela**  
VS Code com o Chat aberto.

**Passos**

1. Rode `Developer: Reload Window`.
2. Rode `MCP: List Servers`.
3. Confirme que `mcp-crm` aparece carregado.
4. No Chat, envie exatamente:

```text
Considere a descricao exata '0101.21.00 | -- Reprodutores de raca pura'. Quais sao os registros mais relevantes na base importada?
```

**Fala**

> Aqui eu deixo de usar o cliente Python e provo o servidor MCP do jeito que ele sera consumido no editor.
>
> Eu recarrego a janela para garantir que o workspace sobe o servidor lendo a base NCM oficial que eu acabei de colocar em `data/runtime/import`.

_Pausa curta._

> E agora eu pego o proprio Copilot usando o MCP para responder sobre essa base.

**O que esperar**

- O `0101.21.00` aparece entre os mais relevantes.
- No fluxo validado aqui, ele apareceu na primeira posicao da resposta do MCP para essa pergunta.

### 5. Suite e qualidade

**Comandos**

```bash
./.venv/bin/python -m pytest tests -q
./.venv/bin/python -m ruff check .
```

**Fala**

> Depois da demo funcional, eu fecho com a prova de qualidade.
>
> Na validacao final desta base, a suite ficou em `60 passed, 1 skipped` e o Ruff passou limpo.

### 6. Fechamento

**Fala**

> Entao o que eu estou mostrando aqui nao e um caso artificial com provider de teste.
>
> E o caminho oficial do projeto, com o NCM oficial, rodando tanto em container quanto no proprio fluxo MCP consumido pelo Copilot.

## Comandos na Ordem do Video

### Bash

```bash
docker build -t mcp-crm:latest .

rm -rf .demo-runtime
mkdir -p .demo-runtime

rm -f data/runtime/users.db data/runtime/users.faiss
rm -rf data/runtime/import data/runtime/import-cache
mkdir -p data/runtime/import
cp /home/lira/Downloads/Tabela_NCM_Vigente_20260319.json data/runtime/import/

docker run --rm \
  -e MCP_EMBEDDING_PROVIDER=sentence-transformers \
  -e MCP_LLM_PROVIDER=stub \
  -e MCP_IMPORT_SOURCE_PATH=/downloads/Tabela_NCM_Vigente_20260319.json \
  -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  -v /home/lira/Downloads:/downloads:ro \
  -v "$(pwd)/.demo-runtime:/app/data/runtime" \
  mcp-crm:latest python docs/client_example.py

# No VS Code:
# 1. Developer: Reload Window
# 2. MCP: List Servers
# 3. Chat: Considere a descricao exata '0101.21.00 | -- Reprodutores de raca pura'. Quais sao os registros mais relevantes na base importada?

./.venv/bin/python -m pytest tests -q
./.venv/bin/python -m ruff check .
```

### Nushell

```nu
docker build -t mcp-crm:latest .

rm -rf .demo-runtime
mkdir .demo-runtime

rm -f data/runtime/users.db data/runtime/users.faiss
rm -rf data/runtime/import data/runtime/import-cache
mkdir data/runtime/import
cp /home/lira/Downloads/Tabela_NCM_Vigente_20260319.json data/runtime/import/

docker run --rm \
  -e MCP_EMBEDDING_PROVIDER=sentence-transformers \
  -e MCP_LLM_PROVIDER=stub \
  -e MCP_IMPORT_SOURCE_PATH=/downloads/Tabela_NCM_Vigente_20260319.json \
  -v /home/lira/.cache/huggingface:/root/.cache/huggingface \
  -v /home/lira/Downloads:/downloads:ro \
  -v $"(pwd)/.demo-runtime:/app/data/runtime" \
  mcp-crm:latest python docs/client_example.py

# No VS Code:
# 1. Developer: Reload Window
# 2. MCP: List Servers
# 3. Chat: Considere a descricao exata '0101.21.00 | -- Reprodutores de raca pura'. Quais sao os registros mais relevantes na base importada?

./.venv/bin/python -m pytest tests -q
./.venv/bin/python -m ruff check .
```

## Observacoes Finais

- O primeiro warm-up local do modelo oficial pode baixar artefatos do Hugging Face.
- Para o container, montar `~/.cache/huggingface` deixa a demo muito mais previsivel.
- O `ask_crm` continua com provider `stub` neste roteiro; o foco aqui e provar a integracao MCP sobre a base oficial, nao um endpoint externo de LLM.
