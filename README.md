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

Este projeto foi documentado para uso via Docker, executando os comandos a partir da raiz do repositorio clonado.

Isso evita depender de Python global, `.venv` local ou de um nome fixo para a pasta onde o projeto foi clonado.

Fluxo base:

- build da imagem com `docker build`
- execucao do servidor com `docker run`
- execucao de scripts Python com `docker run ... python ...`
- execucao de testes e lint, quando existirem, com `docker run ... python -m ...`

Build em Bash:

```bash
docker build -t mcp-crm .
```

Build em Nushell:

```nu
docker build -t mcp-crm .
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

O Docker ja contem um ambiente Python isolado proprio dentro da imagem, em `/opt/venv`. Isso significa que o container nao depende de `.venv` local para subir ou executar scripts dentro do container.

Em outras palavras:

- para executar o servidor via container, o Docker faz tudo sozinho
- para executar scripts Python sem instalar Python no host, rode esses scripts dentro do container
- voce nao e obrigado a criar `.venv` se for usar o fluxo documentado aqui

Build em Bash:

```bash
docker build -t mcp-crm .
```

Build em Nushell:

```nu
docker build -t mcp-crm .
```

Execucao com persistencia local dos dados em Bash:

```bash
docker run --rm \
  -v "$(pwd)/data/runtime:/app/data/runtime" \
  mcp-crm
```

Execucao com persistencia local dos dados em Nushell:

```nu
docker run --rm -v $"(pwd)/data/runtime:/app/data/runtime" mcp-crm
```

Abrir um shell interativo no container em Bash:

```bash
docker run --rm -it \
  -v "$(pwd)/data/runtime:/app/data/runtime" \
  mcp-crm \
  bash
```

Abrir um shell interativo no container em Nushell:

```nu
docker run --rm -it -v $"(pwd)/data/runtime:/app/data/runtime" mcp-crm bash
```

Para manter a imagem alinhada com CPU-only, o build instala torch pela wheel index de CPU do PyTorch antes de instalar o projeto.

## Tests

Suite atual:

- unitarios para validacoes e paginacao da camada de aplicacao
- integracao para persistencia SQLite e rebuild do indice FAISS
- integracao do driver MCP para registro e chamada das tools
- smoke test opt-in para build e execucao Docker com persistencia real, quando a pasta `tests/` existir no checkout

No estado atual deste repositorio, nao existe pasta `tests/`. Portanto, os comandos abaixo so valem quando os testes estiverem presentes em um checkout futuro.

Execucao de testes em Bash:

```bash
docker run --rm -it mcp-crm python -m pytest tests -q
docker run --rm -it mcp-crm python -m ruff check .
```

Execucao de testes em Nushell:

```nu
docker run --rm -it mcp-crm python -m pytest tests -q
docker run --rm -it mcp-crm python -m ruff check .
```

Smoke test Docker em Bash:

```bash
docker build -t mcp-crm .
docker run --rm -it -e RUN_DOCKER_SMOKE=1 mcp-crm python -m pytest tests/smoke -m smoke -q
```

Smoke test Docker em Nushell:

```nu
docker build -t mcp-crm .
docker run --rm -it -e RUN_DOCKER_SMOKE=1 mcp-crm python -m pytest tests/smoke -m smoke -q
```

Se voce tiver apenas Docker, isso ja e suficiente para o fluxo documentado neste README.

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

Execucao em Bash:

```bash
docker run --rm -it \
  -v "$(pwd)/data/runtime:/app/data/runtime" \
  mcp-crm \
  python docs/client_example.py
```

Execucao em Nushell:

```nu
docker run --rm -it -v $"(pwd)/data/runtime:/app/data/runtime" mcp-crm python docs/client_example.py
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
docker build -t mcp-crm .
mkdir -p data/runtime
docker run --rm -v "$(pwd)/data/runtime:/app/data/runtime" mcp-crm python -c "from mcp_crm.slices.users.infrastructure.embeddings import DeterministicTestEmbedder; from mcp_crm.slices.users.infrastructure.faiss_store import FaissStore; from mcp_crm.slices.users.infrastructure.sqlite_repository import SQLiteUserRepository; repo = SQLiteUserRepository('/app/data/runtime/users.db', FaissStore('/app/data/runtime/users.faiss', 16)); embedder = DeterministicTestEmbedder(); print(repo.create_user(name='Ana', email='ana@example.com', description='Cliente premium', embedding=embedder.embed('Cliente premium')))"
docker run --rm -v "$(pwd)/data/runtime:/app/data/runtime" mcp-crm python -c "from mcp_crm.slices.users.infrastructure.embeddings import DeterministicTestEmbedder; from mcp_crm.slices.users.infrastructure.faiss_store import FaissStore; from mcp_crm.slices.users.infrastructure.sqlite_repository import SQLiteUserRepository; repo = SQLiteUserRepository('/app/data/runtime/users.db', FaissStore('/app/data/runtime/users.faiss', 16)); embedder = DeterministicTestEmbedder(); print(repo.search_users(embedder.embed('premium'), top_k=1)[0].user.email)"
```

Equivalente em Nushell:

```nu
docker build -t mcp-crm .
mkdir data/runtime
docker run --rm -v $"(pwd)/data/runtime:/app/data/runtime" mcp-crm python -c "from mcp_crm.slices.users.infrastructure.embeddings import DeterministicTestEmbedder; from mcp_crm.slices.users.infrastructure.faiss_store import FaissStore; from mcp_crm.slices.users.infrastructure.sqlite_repository import SQLiteUserRepository; repo = SQLiteUserRepository('/app/data/runtime/users.db', FaissStore('/app/data/runtime/users.faiss', 16)); embedder = DeterministicTestEmbedder(); print(repo.create_user(name='Ana', email='ana@example.com', description='Cliente premium', embedding=embedder.embed('Cliente premium')))"
docker run --rm -v $"(pwd)/data/runtime:/app/data/runtime" mcp-crm python -c "from mcp_crm.slices.users.infrastructure.embeddings import DeterministicTestEmbedder; from mcp_crm.slices.users.infrastructure.faiss_store import FaissStore; from mcp_crm.slices.users.infrastructure.sqlite_repository import SQLiteUserRepository; repo = SQLiteUserRepository('/app/data/runtime/users.db', FaissStore('/app/data/runtime/users.faiss', 16)); embedder = DeterministicTestEmbedder(); print(repo.search_users(embedder.embed('premium'), top_k=1)[0].user.email)"
```

## Import seguro

O projeto tem teste automatizado para garantir que importar o driver MCP nao cria arquivos de runtime nem configura logging global prematuramente.

Validacao isolada em Bash:

```bash
docker run --rm -it mcp-crm python -m pytest tests/integration/test_import_safety.py -q
```

Validacao isolada em Nushell:

```nu
docker run --rm -it mcp-crm python -m pytest tests/integration/test_import_safety.py -q
```

## Performance

- qualquer uso de Rust deve ser precedido por profiling
- o primeiro alvo de otimização e manter o fluxo simples em Python
- Polars pode entrar em etapas futuras se houver carga tabular relevante

## Reuso de PFF

O projeto pode copiar e adaptar utilitarios do shared de PFF quando houver ganho objetivo e baixo acoplamento. Nesta fase, apenas o helper de import do FAISS foi reaproveitado em versao adaptada.
