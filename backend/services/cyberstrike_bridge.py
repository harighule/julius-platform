"""
CyberStrike MCP Bridge for Julius
Connects to CyberStrike's Bolt server and exposes tools to AutoGen.
Gracefully degrades — JULIUS works fine without CyberStrike installed.
"""

import asyncio
import json
import logging
from typing import Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("julius.cyberstrike")

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    logger.debug("httpx not available for CyberStrike bridge")


@dataclass
class CyberStrikeConfig:
    bolt_url: str = "http://localhost:3001"
    api_key: Optional[str] = None
    timeout: int = 120  # Scans can take time


class CyberStrikeBridge:
    """Bridge between Julius and CyberStrike's MCP tool server."""

    def __init__(self, config: CyberStrikeConfig = None):
        self.config = config or CyberStrikeConfig()
        self._client = None
        self._available_tools: list[dict] = []

    def _get_client(self):
        if not HTTPX_AVAILABLE:
            return None
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.config.bolt_url,
                timeout=self.config.timeout
            )
        return self._client

    async def initialize(self) -> bool:
        """Connect to Bolt and discover available tools."""
        client = self._get_client()
        if client is None:
            logger.warning("CyberStrike bridge: httpx not available")
            return False
        try:
            resp = await client.post("/mcp", json={
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 1
            })
            data = resp.json()
            self._available_tools = data.get("result", {}).get("tools", [])
            logger.info(
                f"CyberStrike connected: {len(self._available_tools)} tools available"
            )
            return True
        except Exception as e:
            logger.warning(f"CyberStrike Bolt not available: {e}")
            return False

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call a CyberStrike tool via MCP protocol."""
        client = self._get_client()
        if client is None:
            return {"error": "CyberStrike bridge not available (httpx missing)"}
        try:
            resp = await client.post("/mcp", json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                },
                "id": 2
            })
            result = resp.json()

            if "error" in result:
                return {"error": result["error"].get("message", str(result["error"]))}

            return {
                "tool": tool_name,
                "result": result.get("result", {}),
                "success": True
            }
        except Exception as e:
            return {"error": str(e)}

    def get_available_tools(self) -> list[dict]:
        """Return tool definitions for AutoGen registration."""
        return self._available_tools

    async def health_check(self) -> dict:
        """Check if Bolt server is running."""
        client = self._get_client()
        if client is None:
            return {"status": "unavailable", "tools": 0}
        try:
            resp = await client.get("/health")
            return {"status": "connected", "tools": len(self._available_tools)}
        except Exception:
            return {"status": "disconnected", "tools": 0}


# Singleton instance
_bridge: Optional[CyberStrikeBridge] = None


def get_cyberstrike_bridge() -> CyberStrikeBridge:
    global _bridge
    if _bridge is None:
        import os
        config = CyberStrikeConfig(
            bolt_url=os.getenv("CYBERSTRIKE_BOLT_URL", "http://localhost:3001"),
            timeout=int(os.getenv("CYBERSTRIKE_TIMEOUT", "120")),
        )
        _bridge = CyberStrikeBridge(config)
    return _bridge
