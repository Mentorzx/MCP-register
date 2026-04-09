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
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$(pwd)/data/runtime:/app/data/runtime" mcp-crm
```

```nu
docker run --rm -v $"(pwd)/data/runtime:/app/data/runtime" mcp-crm
```

Shell interativo:

```bash
docker run --rm -it --user "$(id -u):$(id -g)" \
  -v "$(pwd)/data/runtime:/app/data/runtime" mcp-crm bash
```

Em bind mounts para `data/runtime` no Linux, prefira rodar o container com o `uid:gid` do host para nao deixar arquivos root-owned no checkout.

## Configuracao de LLM

`ask_crm` funciona por padrao com o provider local `stub`.

O exemplo em [docs/client_example.py](docs/client_example.py) assume por padrao:

- `MCP_EMBEDDING_PROVIDER=sentence-transformers`
- `MCP_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2`
- `MCP_LLM_PROVIDER=stub`
- `MCP_IMPORT_SOURCE_PATH=docs/ncm_demo.json` quando o bootstrap de importacao esta ligado e nenhum caminho foi informado

Esse e o caminho oficial do projeto. Na primeira execucao, o provider pode baixar o modelo localmente.
Se quiser um caminho mais rapido para smoke ou testes automatizados, sobrescreva para `deterministic` via variavel de ambiente.

### Modo `stub`

Usado para smoke tests e verificacao local sem dependencia externa:

```bash
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e HF_HOME=/tmp/huggingface \
  -v "$HOME/.cache/huggingface:/tmp/huggingface" \
  -v "$(pwd)/data/runtime:/app/data/runtime" \
  mcp-crm python docs/client_example.py
```

Se o modelo oficial ainda nao estiver no cache local, a primeira execucao pode baixar arquivos do Hugging Face. Para demo ao vivo, monte `~/.cache/huggingface` no container e faca um warm-up local antes.

Para rodar o mesmo exemplo com o arquivo oficial baixado localmente:

```bash
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e MCP_IMPORT_SOURCE_PATH=/downloads/Tabela_NCM_Vigente_20260319.json \
  -e HF_HOME=/tmp/huggingface \
  -v "$HOME/.cache/huggingface:/tmp/huggingface" \
  -v /home/lira/Downloads:/downloads:ro \
  -v "$(pwd)/data/runtime:/app/data/runtime" \
  mcp-crm python docs/client_example.py
```

### Modo `openai-compatible`

Para testar com um endpoint compativel com a API de chat completions:

```bash
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e HF_HOME=/tmp/huggingface \
  -e MCP_LLM_PROVIDER=openai-compatible \
  -e MCP_LLM_API_KEY="$MCP_LLM_API_KEY" \
  -e MCP_LLM_MODEL="gpt-4.1-mini" \
  -e MCP_LLM_BASE_URL="https://api.openai.com/v1" \
  -v "$HOME/.cache/huggingface:/tmp/huggingface" \
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
Na base atual, o exemplo bootstrapa uma amostra NCM, lista os primeiros registros, localiza o alvo `0101.21.00`, reutiliza a descricao importada desse item em `search_users`, consulta o registro via `get_user`, usa `ask_crm` sobre a base importada e fecha com um `create_user` para provar o caminho de escrita.

### Uso via Python

Exemplo em processo chamando `list_users`, `search_users`, `get_user`, `ask_crm` e `create_user` sobre a base NCM bootstrapada:

```python
from __future__ import annotations

import asyncio
import os

from fastmcp import Client

from mcp_crm.drivers import mcp_server


async def main() -> None:
  os.environ.setdefault("MCP_EMBEDDING_PROVIDER", "sentence-transformers")
  os.environ.setdefault(
    "MCP_EMBEDDING_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2",
  )
  os.environ.setdefault("MCP_LLM_PROVIDER", "stub")
  os.environ.setdefault("MCP_IMPORT_SOURCE_PATH", "docs/ncm_demo.json")

  async with Client(mcp_server.mcp) as client:
    page = await client.call_tool("list_users", {"limit": 25, "offset": 0})
    target = next(item for item in page.data if item.name == "0101.21.00")

    results = await client.call_tool(
      "search_users",
      {"query": target.description, "top_k": 5},
    )
    found = await client.call_tool("get_user", {"user_id": results.data[0].id})

    answer = await client.call_tool(
      "ask_crm",
      {
        "question": "O que o NCM 0101.21.00 representa na base importada?",
        "top_k": 3,
      },
    )

    created = await client.call_tool(
      "create_user",
      {
        "name": "Monitoramento NCM 0101.21.00",
        "email": "ncm-monitor@example.com",
        "description": "Cadastro auxiliar para acompanhar o codigo 0101.21.00.",
      },
    )

    print("list_users ->", page.data)
    print("search_users ->", results.data)
    print("get_user ->", found.data)
    print("ask_crm ->", answer.data)
    print("create_user ->", created.data)


asyncio.run(main())
```

Para rodar o exemplo pronto do repositorio:

```bash
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e HF_HOME=/tmp/huggingface \
  -v "$HOME/.cache/huggingface:/tmp/huggingface" \
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

Para provar o fluxo do proprio Copilot com o servidor MCP do workspace, prepare `data/runtime/import` com o JSON oficial do NCM, rode `Developer: Reload Window`, confirme `mcp-crm` em `MCP: List Servers` e entao faca uma pergunta no Chat como: `Considere a descricao exata '0101.21.00 | -- Reprodutores de raca pura'. Quais sao os registros mais relevantes na base importada?`.

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
