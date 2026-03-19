# MCP CRM

Servidor MCP em Python para cadastro e busca semantica de usuarios com SQLite e FAISS.

## Escopo

Tools expostas pelo servidor:

| Tool | Descricao |
|---|---|
| `create_user` | Cria usuario, gera embedding e indexa no FAISS |
| `get_user` | Busca usuario por id |
| `search_users` | Busca semantica por similaridade |
| `list_users` | Listagem paginada |

## Stack

- Python 3.12, FastMCP, SQLite, FAISS CPU, sentence-transformers

## Arquitetura

Monolito modular orientado a fatias verticais:

```
src/mcp_crm/
  drivers/        # entrypoint MCP (stdio)
  shared/         # utilitarios sem acoplamento de dominio
  slices/users/
    domain/       # entidades e erros
    application/  # ports, service (use cases)
    infrastructure/ # SQLite, FAISS, embeddings, config, logging
```

- SQLite e a fonte de verdade; FAISS e indice derivado, reconstruido a partir do banco
- embeddings locais via sentence-transformers (sem API externa)
- logging estruturado em JSON (ou texto via `MCP_LOG_FORMAT=text`)

## Docker

Build:

```bash
docker build -t mcp-crm .
```

Execucao com persistencia:

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

Para manter CPU-only, o build instala torch pela wheel index de CPU do PyTorch.

## Exemplos de uso

Exemplos completos de chamada das tools estao em [docs/](docs/):

- [docs/client_example.py](docs/client_example.py) — script exercitando `create_user`, `get_user` e `search_users` via FastMCP Client

Executar o exemplo:

```bash
docker run --rm -it -v "$(pwd)/data/runtime:/app/data/runtime" mcp-crm python docs/client_example.py
```

```nu
docker run --rm -it -v $"(pwd)/data/runtime:/app/data/runtime" mcp-crm python docs/client_example.py
```

## Persistencia

- `data/runtime/users.db` — SQLite (fonte de verdade)
- `data/runtime/users.faiss` — indice vetorial (derivado)

A cada startup o indice e sincronizado com o banco. Se estiver ausente ou corrompido, o rebuild parte do SQLite.

## Testes

Depois de construir a imagem, rode a suite montando `tests/` do checkout local no container:

```bash
docker build -t mcp-crm .
docker run --rm -v "$(pwd)/tests:/app/tests" mcp-crm python -m pytest tests -q
```

```nu
docker build -t mcp-crm .
docker run --rm -v $"(pwd)/tests:/app/tests" mcp-crm python -m pytest tests -q
```

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

## Aderencia ao case

Esta implementacao atende ao case em [docs/case.md](docs/case.md):

- tools obrigatorias: `create_user`, `search_users`, `get_user`
- diferencial: `list_users`, validacao de email, Dockerfile, testes automatizados, logging estruturado
