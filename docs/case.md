# Case Técnico — Desenvolvedor de IA

## Servidor MCP com Persistência e Busca Vetorial

### Objetivo

Desenvolver um servidor MCP (Model Context Protocol) que permita a um agente de IA:

- Criar usuários e armazená-los com busca vetorial
- Realizar busca semântica sobre os dados armazenados
- Expor essas funcionalidades como ferramentas MCP

### Contexto

Uma empresa deseja construir um assistente inteligente de CRM capaz de:

- Registrar usuários
- Armazenar informações sobre eles
- Encontrar usuários semelhantes semanticamente

O assistente utilizará MCP tools para interagir com um backend.

Você deverá implementar esse backend.

### Requisitos

#### Servidor MCP

O servidor deve expor pelo menos duas ferramentas.

##### Ferramenta 1 — Criar usuário

**Nome da tool:** `create_user`

**Campos:**

- `name`: string
- `email`: string
- `description`: string

A função deve:

- Salvar o usuário em SQLite
- Gerar um embedding da description
- Armazenar o embedding em um índice FAISS
- Retornar o ID do usuário criado

##### Ferramenta 2 — Busca semântica

**Nome da tool:** `search_users`

**Campos:**

- `query`: string
- `top_k`: int

A função deve:

- Gerar embedding da query
- Buscar no índice FAISS
- Retornar os usuários mais semelhantes

**Formato esperado da resposta:**

```json
[
  {
    "id": int,
    "name": string,
    "email": string,
    "description": string,
    "score": float
  }
]
```

##### Ferramenta 3 — Buscar usuário por ID

**Nome da tool:** `get_user`

**Campos:**

- `user_id`: int

A função deve:

- Buscar o usuário no banco de dados pelo ID
- Retornar os dados do usuário encontrado ou erro se não existir

**Formato esperado da resposta:**

```json
{
  "id": int,
  "name": string,
  "email": string,
  "description": string
}
```

#### Requisitos técnicos

Recomenda-se:

- **Linguagem:** Python
- **Framework MCP:** fastmcp ou implementação própria
- **Banco de dados:** SQLite com vector extension OU PostgreSQL com pgvector
- **Embeddings:** Pode utilizar sentence-transformers, OpenAI embeddings ou modelo local

**Opções de implementação:**

1. **SQLite + vector**: Usar SQLite com a extensão vector para armazenar e buscar embeddings
2. **PostgreSQL + pgvector**: Usar PostgreSQL com a extensão pgvector para buscas vetoriais

#### Estrutura sugerida

```
project/
├── server.py
├── database.py
├── embeddings.py
├── vector_store.py
├── models.py
├── faiss_index/
└── README.md
```

### Diferenciais

Não obrigatórios:

- Suporte a ambas as opções (SQLite + vector OU PostgreSQL + pgvector)
- Endpoint para listar usuários
- Validação de email
- Dockerfile
- Tests automatizados
- Logging estruturado

### Critérios de avaliação

- Arquitetura do código
- Clareza e organização
- Integração MCP
- Uso correto de FAISS
- Tratamento de erros
- Documentação

### Entrega

Enviar:

- Link do repositório
- Instruções para rodar o projeto
- Exemplos de uso