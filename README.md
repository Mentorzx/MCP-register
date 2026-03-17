# MCP CRM

Servidor MCP em Python para cadastro e busca semantica de usuarios com SQLite e FAISS.

## Escopo

- create_user
- search_users
- get_user
- list_users

## Aderencia ao case

Esta implementacao atende ao case original em [docs/case.md](docs/case.md) com as seguintes decisoes objetivas:

- expoe as tres tools obrigatorias: create_user, search_users e get_user
- adiciona list_users como diferencial opcional
- usa SQLite como fonte de verdade e FAISS como indice vetorial derivado e reconstruivel
- usa embeddings locais com sentence-transformers e empacotamento via Docker

## Stack

- Python 3.12
- FastMCP
- SQLite
- FAISS CPU
- sentence-transformers

## Arquitetura

O projeto segue monolito modular orientado a fatias.

- mcp_crm/slices/users concentra o caso de uso de CRM
- mcp_crm/drivers contem o entrypoint MCP
- mcp_crm/shared fica restrito a utilitarios pequenos e desacoplados

## Ambiente local

Este projeto usa venv local em .venv dentro de MCP.

O fluxo padrao de desenvolvimento deve sempre usar o ambiente virtual local ou a imagem Docker do projeto. Nao execute os comandos com o Python global.

Exemplo em Nushell:

```nu
cd /home/lira/Projetos/MCP
uv sync --extra dev
uv run pytest tests -q
uv run python -m mcp_crm.drivers.mcp_server
```

Exemplo equivalente usando o executavel do venv:

```bash
cd /home/lira/Projetos/MCP
./.venv/bin/python -m pytest tests -q
./.venv/bin/python -m mcp_crm.drivers.mcp_server
```

## Persistencia

- SQLite e a fonte de verdade em data/runtime/users.db
- FAISS e um indice derivado em data/runtime/users.faiss
- a cada inicializacao do repositorio, o indice FAISS e sincronizado a partir do SQLite
- se o arquivo do indice estiver ausente, desatualizado ou corrompido, o rebuild parte do banco

## Logging

- o formato padrao de log e JSON estruturado
- para voltar ao formato texto, defina MCP_LOG_FORMAT=text

## Docker

Build:

```bash
cd /home/lira/Projetos/MCP
docker build -t mcp-crm .
```

Execucao com persistencia local dos dados:

```bash
cd /home/lira/Projetos/MCP
docker run --rm \
  -v "$(pwd)/data/runtime:/app/data/runtime" \
  mcp-crm
```

O container tambem usa um venv interno em /opt/venv, mantendo o mesmo principio de isolamento adotado no ambiente local.

Para manter a imagem alinhada com CPU-only, o build instala torch pela wheel index de CPU do PyTorch antes de instalar o projeto.

## Tests

Suite atual:

- unitarios para validacoes e paginacao da camada de aplicacao
- integracao para persistencia SQLite e rebuild do indice FAISS
- integracao do driver MCP para registro e chamada das tools
- smoke test opt-in para build e execucao Docker com persistencia real

Execucao padrao no venv:

```bash
cd /home/lira/Projetos/MCP
./.venv/bin/python -m pytest tests -q
./.venv/bin/python -m ruff check .
```

Smoke test Docker:

```bash
cd /home/lira/Projetos/MCP
docker build -t mcp-crm .
RUN_DOCKER_SMOKE=1 ./.venv/bin/python -m pytest tests/smoke -m smoke -q
```

No Nushell, use `;` entre comandos em vez de `&&`.

## Exemplos MCP

Exemplo real com cliente FastMCP em processo, sem mocks:

```python
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
    found = await client.call_tool("get_user", {"user_id": created.data})
    results = await client.call_tool(
      "search_users",
      {"query": "cliente premium com foco em investimentos", "top_k": 1},
    )

    print(created.data)
    print(found.data)
    print(results.data)


asyncio.run(main())
```

Execucao:

```bash
cd /home/lira/Projetos/MCP
./.venv/bin/python docs/client_example.py
```

Criacao de usuario:

```json
{
  "name": "Ana Silva",
  "email": "ana@example.com",
  "description": "Cliente premium interessada em investimentos e seguro de vida."
}
```

Resposta esperada:

```json
1
```

Busca semantica:

```json
{
  "query": "perfil premium focado em investimentos",
  "top_k": 2
}
```

Resposta esperada:

```json
[
  {
    "id": 1,
    "name": "Ana Silva",
    "email": "ana@example.com",
    "description": "Cliente premium interessada em investimentos e seguro de vida.",
    "score": 0.95
  }
]
```

Busca por id:

```json
{
  "user_id": 1
}
```

Resposta esperada:

```json
{
  "id": 1,
  "name": "Ana Silva",
  "email": "ana@example.com",
  "description": "Cliente premium interessada em investimentos e seguro de vida."
}
```

Listagem:

```json
{
  "limit": 20,
  "offset": 0
}
```

## Validacao ponta a ponta com Docker

Exemplo de duas execucoes reaproveitando o mesmo volume de dados:

```bash
cd /home/lira/Projetos/MCP
docker build -t mcp-crm .
mkdir -p data/runtime
docker run --rm -v "$(pwd)/data/runtime:/app/data/runtime" mcp-crm python -c "from mcp_crm.slices.users.infrastructure.embeddings import DeterministicTestEmbedder; from mcp_crm.slices.users.infrastructure.faiss_store import FaissStore; from mcp_crm.slices.users.infrastructure.sqlite_repository import SQLiteUserRepository; repo = SQLiteUserRepository('/app/data/runtime/users.db', FaissStore('/app/data/runtime/users.faiss', 16)); embedder = DeterministicTestEmbedder(); print(repo.create_user(name='Ana', email='ana@example.com', description='Cliente premium', embedding=embedder.embed('Cliente premium')))"
docker run --rm -v "$(pwd)/data/runtime:/app/data/runtime" mcp-crm python -c "from mcp_crm.slices.users.infrastructure.embeddings import DeterministicTestEmbedder; from mcp_crm.slices.users.infrastructure.faiss_store import FaissStore; from mcp_crm.slices.users.infrastructure.sqlite_repository import SQLiteUserRepository; repo = SQLiteUserRepository('/app/data/runtime/users.db', FaissStore('/app/data/runtime/users.faiss', 16)); embedder = DeterministicTestEmbedder(); print(repo.search_users(embedder.embed('premium'), top_k=1)[0].user.email)"
```

## Import seguro

O projeto tem teste automatizado para garantir que importar o driver MCP nao cria arquivos de runtime nem configura logging global prematuramente.

Validacao isolada:

```bash
cd /home/lira/Projetos/MCP
./.venv/bin/python -m pytest tests/integration/test_import_safety.py -q
```

## Performance

- qualquer uso de Rust deve ser precedido por profiling
- o primeiro alvo de otimização e manter o fluxo simples em Python
- Polars pode entrar em etapas futuras se houver carga tabular relevante

## Reuso de PFF

O projeto pode copiar e adaptar utilitarios do shared de PFF quando houver ganho objetivo e baixo acoplamento. Nesta fase, apenas o helper de import do FAISS foi reaproveitado em versao adaptada.
