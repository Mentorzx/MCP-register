# MCP CRM

Servidor MCP em Python para cadastro, busca semantica e respostas assistidas por LLM sobre usuarios persistidos em SQLite.

## Nota sobre esta branch

Esta branch (`feat/sqlite-embeddings-llm-ready`) e um follow-up da entrega original do case.

- a release `v1.0.0` manteve FAISS como indice derivado
- esta branch remove o FAISS do runtime
- os embeddings continuam sendo gerados, mas ficam persistidos na propria tabela `users`
- a busca semantica passa a ser feita diretamente a partir do SQLite
- foi adicionada a tool `ask_crm` para testar um fluxo com LLM

## Escopo

Tools expostas pelo servidor:

| Tool | Descricao |
|---|---|
| `create_user` | Cria usuario, gera embedding e persiste tudo no SQLite |
| `get_user` | Busca usuario por id |
| `search_users` | Busca semantica por similaridade sobre embeddings persistidos |
| `list_users` | Listagem paginada |
| `ask_crm` | Busca usuarios relevantes e pede para uma LLM responder com base nesse contexto |

## Stack

- Python 3.12
- FastMCP
- SQLite
- sentence-transformers
- NumPy

## Arquitetura

Monolito modular orientado a fatias verticais:

```text
src/mcp_crm/
  drivers/          # entrypoint MCP
  slices/users/
    domain/         # entidades e erros
    application/    # services e ports
    infrastructure/ # SQLite, embeddings, llm, config, logging
```

- SQLite e a fonte de verdade e tambem o armazenamento dos embeddings
- a busca semantica calcula similaridade em memoria a partir dos embeddings salvos no banco
- o servidor pode bootstrapar o SQLite a partir de JSON em `data/runtime/import`, com cache Parquet em lote
- embeddings locais via `sentence-transformers`
- integracao com LLM isolada por adapter, com suporte a `stub` e `openai-compatible`
- logging estruturado em JSON (ou texto via `MCP_LOG_FORMAT=text`)

## Docker

Build:

```bash
docker build -t mcp-crm .
```

Execucao base:

```bash
docker run --rm -v "$(pwd)/data/runtime:/app/data/runtime" mcp-crm
```

```nu
docker run --rm -v $"(pwd)/data/runtime:/app/data/runtime" mcp-crm
```

Shell interativo:

```bash
docker run --rm -it -v "$(pwd)/data/runtime:/app/data/runtime" mcp-crm bash
```

## Configuracao de LLM

`ask_crm` funciona por padrao com o provider local `stub`.

### Modo `stub`

Usado para smoke tests e verificacao local sem dependencia externa:

```bash
docker run --rm \
  -v "$(pwd)/data/runtime:/app/data/runtime" \
  mcp-crm python docs/client_example.py
```

### Modo `openai-compatible`

Para testar com um endpoint compativel com a API de chat completions:

```bash
docker run --rm \
  -e MCP_LLM_PROVIDER=openai-compatible \
  -e MCP_LLM_API_KEY="$MCP_LLM_API_KEY" \
  -e MCP_LLM_MODEL="gpt-4.1-mini" \
  -e MCP_LLM_BASE_URL="https://api.openai.com/v1" \
  -v "$(pwd)/data/runtime:/app/data/runtime" \
  mcp-crm python docs/client_example.py
```

Variaveis relevantes:

- `MCP_EMBEDDING_PROVIDER`: `sentence-transformers` ou `deterministic`
- `MCP_LLM_PROVIDER`: `stub` (padrao), `disabled` ou `openai-compatible`
- `MCP_LLM_API_KEY`: obrigatoria no modo `openai-compatible`
- `MCP_LLM_MODEL`: modelo usado no modo `openai-compatible`
- `MCP_LLM_BASE_URL`: base URL do provedor compativel
- `MCP_LLM_SYSTEM_PROMPT`: sobrescreve o prompt de sistema padrao

## Exemplos de uso

O fluxo completo das tools esta em [docs/client_example.py](docs/client_example.py).

### Uso via Python

Exemplo em processo chamando `create_user`, `get_user`, `search_users`, `list_users` e `ask_crm`:

```python
from __future__ import annotations

import asyncio

from fastmcp import Client

from mcp_crm.drivers import mcp_server


async def main() -> None:
    async with Client(mcp_server.mcp) as client:
        created = await client.call_tool(
            "create_user",
            {
                "name": "Ana Silva",
                "email": "ana@example.com",
                "description": "Cliente premium interessada em investimentos.",
            },
        )
        print("create_user ->", created.data)

        found = await client.call_tool("get_user", {"user_id": created.data})
        print("get_user ->", found.data)

        results = await client.call_tool(
            "search_users",
            {"query": "cliente premium com foco em investimentos", "top_k": 2},
        )
        print("search_users ->", results.data)

        page = await client.call_tool("list_users", {"limit": 10, "offset": 0})
        print("list_users ->", page.data)

        answer = await client.call_tool(
            "ask_crm",
            {
                "question": "Quem no CRM parece mais interessado em investimentos?",
                "top_k": 1,
            },
        )
        print("ask_crm ->", answer.data)


asyncio.run(main())
```

Para rodar o exemplo pronto do repositorio:

```bash
docker run --rm \
  -e MCP_LLM_PROVIDER=stub \
  -v "$(pwd)/data/runtime:/app/data/runtime" \
  mcp-crm python docs/client_example.py
```

## Uso com VS Code e Codex

Este repositorio ja inclui configuracao pronta para clientes MCP baseados em stdio:

- VS Code + GitHub Copilot usam `.vscode/mcp.json`
- Codex CLI e extensao Codex usam `.codex/config.toml`

Os arquivos versionados acima usam o venv local. Se voce prefere Docker-only, o guia em [docs/mcp-clients.md](docs/mcp-clients.md) traz os blocos equivalentes com `docker run` para VS Code, Copilot e Codex.

No VS Code, abra o Chat e use `MCP: List Servers` para verificar se `mcp-crm` foi carregado.
No Copilot Chat do VS Code, o comando `/mcp` nao aparece.
No Codex, a configuracao de projeto passa a valer neste checkout e o servidor aparece em `/mcp`.

Observacao: `ask_crm` ja funciona por padrao com `stub`; configure `openai-compatible` se quiser respostas via API externa.

Guia detalhado de acoplamento:

- [docs/mcp-clients.md](docs/mcp-clients.md)

Validacao rapida do servidor usando so Docker:

```bash
docker build -t mcp-crm .
docker run --rm \
  -v mcp-crm-runtime:/app/data/runtime \
  mcp-crm python docs/client_example.py
```

## Persistencia

- `data/runtime/users.db` — SQLite com usuarios e embeddings
- `data/runtime/import/*.json` — inbox opcional para bootstrap automatico do banco
- `data/runtime/import-cache/*.parquet` — cache rapido para reconstruir o banco sem re-embedar

Os embeddings ficam armazenados na coluna `users.embedding` como `BLOB` `float32`.

## Bootstrap de JSON

Se voce largar um arquivo `.json`, `.jsonl` ou `.ndjson` em `data/runtime/import` e reiniciar o `mcp-crm`, o servidor vai:

1. normalizar os registros com Polars
2. gerar embeddings em batch
3. gravar um cache Parquet com `name`, `email`, `description` e `embedding`
4. reconstruir `data/runtime/users.db`

Nos reinicios seguintes, se o JSON nao mudou, o servidor reutiliza o Parquet e consegue restaurar o SQLite sem recalcular embeddings.

Se a pasta `data/runtime` nao estiver gravavel neste checkout, o servidor cai automaticamente para `.tmp/runtime`. Fora isso, o bootstrap usa apenas a inbox configurada ou um caminho explicito em `MCP_IMPORT_SOURCE_PATH`.

Variaveis opcionais para esse fluxo:

- `MCP_IMPORT_DIR` — sobrescreve a inbox padrao
- `MCP_IMPORT_CACHE_DIR` — sobrescreve a pasta de cache Parquet
- `MCP_IMPORT_SOURCE_PATH` — aponta para um JSON especifico, sem depender da inbox
- `MCP_IMPORT_BATCH_SIZE` — controla o batch de embeddings e carga no SQLite
- `MCP_IMPORT_ENABLED=false` — desliga o bootstrap automatico

## Testes

Suite principal dentro do container:

```bash
docker build -t mcp-crm .
docker run --rm -v "$(pwd):/app" -w /app mcp-crm /opt/venv/bin/python -m pytest tests -q
```

```nu
docker build -t mcp-crm .
docker run --rm -v $"(pwd):/app" -w /app mcp-crm /opt/venv/bin/python -m pytest tests -q
```

Smoke E2E do fluxo Docker real:

```bash
RUN_DOCKER_SMOKE=1 pytest tests/smoke -m smoke -q
```

O smoke reaproveita `mcp-crm:latest` quando a imagem ja existe, ou faz o build se ela ainda nao estiver disponivel. Depois monta o checkout atual em `/app`, roda o `docs/client_example.py` com `MCP_LLM_PROVIDER=stub`, exercita todas as tools e verifica a persistencia do SQLite.
No smoke, `MCP_EMBEDDING_PROVIDER=deterministic` e usado para evitar download de modelo e manter o E2E reproduzivel.

Lint:

```bash
docker run --rm mcp-crm python -m ruff check .
```

## Reset

Limpa artefatos locais sem apagar o repositorio:

```bash
docker rmi -f mcp-crm 2>/dev/null; docker builder prune -af
rm -rf data/runtime && mkdir -p data/runtime
docker build --no-cache -t mcp-crm .
```

```nu
do { docker rmi -f mcp-crm | ignore }; docker builder prune -af
rm -rf data/runtime; mkdir data/runtime
docker build --no-cache -t mcp-crm .
```
