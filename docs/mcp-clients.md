# Integracao do MCP com Copilot, VS Code e Codex

Se voce nao quer depender do venv local, o caminho mais simples para este projeto e usar Docker.

O servidor MCP sobe em stdio a partir da imagem `mcp-crm`:

```bash
docker build -t mcp-crm .
docker run --rm -i -v mcp-crm-runtime:/app/data/runtime mcp-crm
```

Observacao importante:

- no GitHub Copilot Chat do VS Code, o comando `/mcp` nao aparece; ali a verificacao e feita por `MCP: List Servers`
- o comando `/mcp` e do Codex

## Pre-requisitos

- abrir o repositorio na raiz do projeto
- ter Docker disponivel na maquina onde o MCP vai rodar
- gerar a imagem antes de configurar o cliente

Build inicial:

```bash
docker build -t mcp-crm .
```

## Teste rapido local

Antes de abrir VS Code, Copilot ou Codex, valide o fluxo principal so com Docker:

```bash
docker build -t mcp-crm .
docker run --rm \
  -v mcp-crm-runtime:/app/data/runtime \
  mcp-crm python docs/client_example.py
```

Esse comando exercita `create_user`, `get_user`, `search_users`, `list_users` e `ask_crm` sem usar o venv do host.
Como ele usa um volume nomeado do Docker, nao escreve direto no checkout e nao sofre com arquivos `root-owned` no repositorio.
Se voce trocar esse volume por um bind mount para `data/runtime` ou `.demo-runtime` no Linux, rode o container com `--user "$(id -u):$(id -g)"` no Bash ou `--user $"((^id -u | str trim)):((^id -g | str trim))"` no Nushell.
Se o destino do bind mount for `.demo-runtime`, crie esse diretorio no host antes do `docker run`; se ele nao existir, o Docker pode cria-lo como `root` e o servidor passa a usar o fallback temporario em `/tmp/mcp-crm-runtime/...` sem persistir o `users.db` no checkout.

## GitHub Copilot no VS Code

Se voce quer Docker-only no Copilot do VS Code, use um `mcp.json` com `docker run`.

O arquivo versionado [../.vscode/mcp.json](../.vscode/mcp.json) continua apontando para o venv local. Se a sua preferencia e evitar isso, substitua pelo bloco abaixo.

1. Abra o projeto no VS Code.
2. Rode `docker build -t mcp-crm .` na raiz do repositorio.
3. Edite [../.vscode/mcp.json](../.vscode/mcp.json) com a configuracao Docker abaixo.
4. Abra o Chat do VS Code.
5. Rode o comando `MCP: List Servers`.
6. Verifique se `mcp-crm` aparece como servidor disponível.
7. Se o VS Code pedir confiança para iniciar o servidor, aprove.

Configuracao Docker para workspace:

```json
{
  "servers": {
    "mcp-crm": {
      "type": "stdio",
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-v",
        "mcp-crm-runtime:/app/data/runtime",
        "mcp-crm"
      ]
    }
  }
}
```

Se quiser explicitar o provider local `stub`, acrescente estes argumentos antes do nome da imagem:

```json
[
  "-e",
  "MCP_LLM_PROVIDER=stub"
]
```

Observacoes importantes:

- no Copilot do VS Code, use `MCP: List Servers`; nao use `/mcp`
- em janela remota, o `docker` executa onde a configuracao foi definida
- se voce alterar o codigo do servidor, refaca `docker build -t mcp-crm .`

## Demo com o NCM oficial no Copilot

Se a ideia e demonstrar o MCP pelo proprio Chat do Copilot, use o runtime padrao do workspace para que o servidor e o Chat enxerguem a mesma base.
Aqui o bootstrap roda no proprio checkout, entao os comandos de `docker run` com bind mount para `data/runtime` devem seguir o padrao documentado no README e no roteiro do video, com o `uid:gid` do host no Linux.

### Bash

```bash
rm -f data/runtime/users.db data/runtime/users.faiss
rm -rf data/runtime/import data/runtime/import-cache
mkdir -p data/runtime/import
cp /home/lira/Downloads/Tabela_NCM_Vigente_20260319.json data/runtime/import/
```

### Nushell

```nu
rm -f data/runtime/users.db data/runtime/users.faiss
rm -rf data/runtime/import data/runtime/import-cache
mkdir data/runtime/import
cp /home/lira/Downloads/Tabela_NCM_Vigente_20260319.json data/runtime/import/
```

Depois disso:

1. Rode `Developer: Reload Window` para reiniciar o servidor MCP do workspace sem reaproveitar cache antigo.
2. Rode `MCP: List Servers` e confirme que `mcp-crm` esta carregado.
3. No Chat do Copilot, peca algo como: `Considere a descricao exata '0101.21.00 | -- Reprodutores de raca pura'. Quais sao os registros mais relevantes na base importada?`.
4. Se quiser uma segunda pergunta, siga com: `Agora resuma o que esse resultado indica sobre o NCM 0101.21.00 dentro da base importada.`

Esse fluxo usa o provider oficial `sentence-transformers` porque o workspace ja sobe o MCP com esse provider em [../.vscode/mcp.json](../.vscode/mcp.json).

## VS Code fora deste repositório

Se quiser acoplar este mesmo servidor a partir do seu perfil do VS Code, sem depender do checkout atual:

1. Rode `docker build -t mcp-crm /caminho/do/repositorio`.
2. Rode `MCP: Open User Configuration`.
3. Adicione um servidor stdio usando Docker.
4. Salve o arquivo e rode `MCP: List Servers`.

Exemplo de configuracao global:

```json
{
  "servers": {
    "mcp-crm": {
      "type": "stdio",
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-v",
        "mcp-crm-runtime:/app/data/runtime",
        "mcp-crm"
      ]
    }
  }
}
```

Use esse formato quando quiser disponibilizar o MCP no seu perfil sem depender de um Python local configurado.

## Codex

No Codex, o comando de inspecao e `/mcp`.

Se voce quer Docker-only, use um `config.toml` com `docker run`.

O arquivo versionado [../.codex/config.toml](../.codex/config.toml) continua apontando para o venv local. Se a sua preferencia e evitar isso, substitua pelo bloco abaixo.

Configuracao Docker para projeto:

```toml
[mcp_servers.mcp_crm]
command = "docker"
args = ["run", "-i", "--rm", "-v", "mcp-crm-runtime:/app/data/runtime", "mcp-crm"]
startup_timeout_sec = 20
tool_timeout_sec = 60
```

Como validar no Codex:

1. Rode `docker build -t mcp-crm .`.
2. Abra o projeto no Codex CLI ou na extensao Codex.
3. Rode `/mcp`.
4. Verifique se `mcp_crm` aparece entre os servidores ativos.

Alternativa via CLI do Codex, sem editar arquivo manualmente:

```bash
codex mcp add mcp_crm -- docker run -i --rm -v mcp-crm-runtime:/app/data/runtime mcp-crm
```

Para explicitar `ask_crm` com `stub` no Codex, adicione `-e MCP_LLM_PROVIDER=stub` antes do nome da imagem.

## Provider do ask_crm

Por padrao, o servidor sobe com o provider local `stub`. Para trocar o provider no fluxo Docker, passe variaveis com `docker run -e`.

Exemplo no VS Code ou Copilot:

```json
{
  "servers": {
    "mcp-crm": {
      "type": "stdio",
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e",
        "MCP_LLM_PROVIDER=stub",
        "-v",
        "mcp-crm-runtime:/app/data/runtime",
        "mcp-crm"
      ]
    }
  }
}
```

Exemplo equivalente no Codex:

```toml
[mcp_servers.mcp_crm]
command = "docker"
args = [
  "run",
  "-i",
  "--rm",
  "-e",
  "MCP_LLM_PROVIDER=stub",
  "-v",
  "mcp-crm-runtime:/app/data/runtime",
  "mcp-crm"
]
startup_timeout_sec = 20
tool_timeout_sec = 60
```

Para usar provider compativel com OpenAI, troque ou acrescente:

- `-e MCP_LLM_PROVIDER=openai-compatible`
- `-e MCP_LLM_API_KEY=...`
- `-e MCP_LLM_MODEL=...`
- `-e MCP_LLM_BASE_URL=...`

## Troubleshooting rapido

- no Copilot do VS Code, `/mcp` nao aparece mesmo; use `MCP: List Servers`
- `MCP: List Servers` nao mostra `mcp-crm`: confira se o `mcp.json` salvo no VS Code esta usando o bloco Docker correto
- o Codex nao mostra o servidor em `/mcp`: confira se o `config.toml` esta usando `docker run`
- servidor nao inicia: rode manualmente `docker run --rm -i -v mcp-crm-runtime:/app/data/runtime mcp-crm`
- bind mount para `.demo-runtime` nao persistiu `users.db`: crie o diretorio no host antes do `docker run`; se ele nao existir, o Docker pode cria-lo como `root` e o servidor usa o fallback em `/tmp/mcp-crm-runtime/...`
- limpeza falha com `Permission denied` em `.demo-runtime` ou `data/runtime/import-cache`: um run antigo criou arquivos `root-owned`; repita os bind mounts com `--user` e, se precisar limpar uma vez, rode `docker run --rm --pull=missing --network none --mount type=bind,src="$(pwd)",dst=/repo busybox:1.36 sh -euxc 'rm -rf /repo/.demo-runtime'`
- alterou o codigo do servidor: refaca `docker build -t mcp-crm .`
