# Integracao do MCP com Copilot, VS Code e Codex

Este projeto expõe um servidor MCP em stdio via Python:

```bash
./.venv/bin/python -m mcp_crm.drivers.mcp_server
```

O repositório já traz duas configurações prontas:

- workspace do VS Code e GitHub Copilot em [../.vscode/mcp.json](../.vscode/mcp.json)
- projeto do Codex em [../.codex/config.toml](../.codex/config.toml)

## Pre-requisitos

- abrir o repositório na raiz do projeto
- ter o virtualenv do projeto disponível em `.venv`
- ter as dependências instaladas nesse virtualenv

Se precisar recriar o ambiente:

```bash
/bin/python -m venv .venv
./.venv/bin/pip install -e ".[dev]"
```

## GitHub Copilot no VS Code

O caminho recomendado neste repositório é usar a configuração de workspace já versionada.

1. Abra o projeto no VS Code.
2. Confirme que [../.vscode/mcp.json](../.vscode/mcp.json) está presente.
3. Abra o Chat do VS Code.
4. Rode o comando `MCP: List Servers`.
5. Verifique se `mcp-crm` aparece como servidor disponível.
6. Se o VS Code pedir confiança para iniciar o servidor, aprove.

Configuração usada no workspace:

```json
{
  "servers": {
    "mcp-crm": {
      "type": "stdio",
      "command": "${workspaceFolder}/.venv/bin/python",
      "args": ["-m", "mcp_crm.drivers.mcp_server"],
      "cwd": "${workspaceFolder}",
      "env": {
        "PYTHONPATH": "${workspaceFolder}/src"
      }
    }
  }
}
```

Observacoes importantes:

- em janela remota, o servidor MCP executa onde a configuracao foi definida
- se voce quer que o servidor rode na maquina remota, use configuracao de workspace ou `MCP: Open Remote User Configuration`
- se voce usar configuracao de perfil do usuario, o processo roda na maquina local do VS Code

## VS Code fora deste repositório

Se quiser acoplar este mesmo servidor a partir do seu perfil do VS Code, sem depender do arquivo versionado do projeto:

1. Rode `MCP: Open User Configuration`.
2. Adicione um servidor stdio apontando para este checkout.
3. Salve o arquivo e rode `MCP: List Servers`.

Exemplo de configuracao global:

```json
{
  "servers": {
    "mcp-crm": {
      "type": "stdio",
      "command": "/home/Alex/Development/mcp-register/.venv/bin/python",
      "args": ["-m", "mcp_crm.drivers.mcp_server"],
      "cwd": "/home/Alex/Development/mcp-register",
      "env": {
        "PYTHONPATH": "/home/Alex/Development/mcp-register/src"
      }
    }
  }
}
```

Use esse formato quando quiser disponibilizar o MCP em qualquer workspace do seu perfil.

## Codex

O Codex usa configuracao propria em `config.toml`. Neste repositório, ela já está pronta em [../.codex/config.toml](../.codex/config.toml).

Configuracao atual do projeto:

```toml
[mcp_servers.mcp_crm]
command = "./.venv/bin/python"
args = ["-m", "mcp_crm.drivers.mcp_server"]
cwd = "."
startup_timeout_sec = 20
tool_timeout_sec = 60

[mcp_servers.mcp_crm.env]
PYTHONPATH = "src"
```

Como validar no Codex:

1. Abra o projeto no Codex CLI ou na extensao Codex.
2. Rode `/mcp` na interface do Codex.
3. Verifique se `mcp_crm` aparece entre os servidores ativos.

Alternativa via CLI do Codex, sem editar arquivo manualmente:

```bash
cd /home/Alex/Development/mcp-register
codex mcp add mcp_crm --env PYTHONPATH=src -- ./.venv/bin/python -m mcp_crm.drivers.mcp_server
```

Para configurar globalmente no Codex, use `~/.codex/config.toml` com o mesmo bloco, mas trocando caminhos relativos por absolutos.

## Habilitando ask_crm

Por padrao, as configuracoes prontas sobem apenas o servidor. A tool `ask_crm` exige um provider de LLM configurado.

Para habilitar localmente com stub no VS Code ou no Copilot, acrescente no bloco `env`:

```json
{
  "MCP_LLM_PROVIDER": "stub"
}
```

Exemplo completo no `mcp.json`:

```json
{
  "servers": {
    "mcp-crm": {
      "type": "stdio",
      "command": "${workspaceFolder}/.venv/bin/python",
      "args": ["-m", "mcp_crm.drivers.mcp_server"],
      "cwd": "${workspaceFolder}",
      "env": {
        "PYTHONPATH": "${workspaceFolder}/src",
        "MCP_LLM_PROVIDER": "stub"
      }
    }
  }
}
```

Exemplo equivalente no Codex:

```toml
[mcp_servers.mcp_crm.env]
PYTHONPATH = "src"
MCP_LLM_PROVIDER = "stub"
```

Para usar provider compativel com OpenAI, voce tambem precisa definir:

- `MCP_LLM_PROVIDER=openai-compatible`
- `MCP_LLM_API_KEY`
- `MCP_LLM_MODEL`
- `MCP_LLM_BASE_URL`

## Troubleshooting rapido

- `MCP: List Servers` nao mostra `mcp-crm`: verifique se o arquivo de configuracao foi salvo no lugar certo e se o servidor nao foi desabilitado.
- servidor nao inicia: rode manualmente `./.venv/bin/python -m mcp_crm.drivers.mcp_server` na raiz do projeto.
- `ask_crm` indisponivel: faltou configurar `MCP_LLM_PROVIDER`.
- janela remota do VS Code: prefira `.vscode/mcp.json` ou configuracao remota para o processo rodar no host remoto.