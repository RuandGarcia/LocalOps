"""Read-only MCP server (streamable HTTP) that the OpenClaw agent `localops` calls for data.

Runs on the private Docker network only; it is never published through the proxy.
Usage: uvicorn localops_api.mcp_server:app --port 8100
Env: LOCALOPS_MCP_HOSTS — allowed Host headers, comma separated (default "127.0.0.1:8100,localhost:8100").
"""
from __future__ import annotations

import os

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from localops_api import ferramentas

servidor = MCPServer(
    "localops",
    instructions="Dados reais de incidentes da Locaweb (2025), só leitura. Toda resposta traz o campo `fonte`.",
)
_SO_LEITURA = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
for _f in ferramentas.FERRAMENTAS.values():
    servidor.tool(annotations=_SO_LEITURA, structured_output=False)(_f)

_hosts = os.environ.get("LOCALOPS_MCP_HOSTS", "127.0.0.1:8100,localhost:8100").split(",")
app = servidor.streamable_http_app(
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(allowed_hosts=[h.strip() for h in _hosts if h.strip()]),
)
