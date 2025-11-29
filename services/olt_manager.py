import asyncio
from typing import Dict, Optional
from services.telnet_client import TelnetHandler
from core.config import settings
from fastapi import HTTPException

class OLTConnectionManager:
    _instance: Optional["OLTConnectionManager"] = None
    connections: Dict[str, OLTConnectionManager]
    locks: Dict[str, asyncio.Lock]
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OLTConnectionManager, cls).__new__(cls)
            cls._instance.connections = {}
            cls._instance.locks = {}
        return cls._instance

    def _get_lock(self, host: str):
        if host not in self.locks: self.locks[host] = asyncio.Lock()
        return self.locks[host]

    async def execute_action(self, olt_info: dict, action_callback):
        host = olt_info["ip"]
        lock = self._get_lock(host)

        async with lock:
            handler = self.connections.get(host)
            if not handler:
                # Initialize the MASTER handler
                handler = OLTConnectionManager(
                    host=host,
                    username=settings.OLT_USERNAME,
                    password=settings.OLT_PASSWORD,
                    is_c600=olt_info["c600"]
                )
                self.connections[host] = handler

            try:
                await handler.connect() # Uses logic from TelnetClient
                return await action_callback(handler)
            except Exception as e:
                # Auto-recovery
                await handler.close()
                if host in self.connections: del self.connections[host]
                raise HTTPException(status_code=500, detail=f"OLT Error: {e}")

olt_manager = OLTConnectionManager()