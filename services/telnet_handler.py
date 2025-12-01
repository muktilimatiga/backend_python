import asyncio
import logging
from typing import Dict, Optional, TYPE_CHECKING
from fastapi import HTTPException
from core.config import settings
from core.olt_config import OLT_OPTIONS

# [CRITICAL] NO imports of CoreHandler/TelnetClient at top level
if TYPE_CHECKING:
    from services.core_handler import CoreHandler

class TelnetHandler:
    _instance: Optional["TelnetHandler"] = None
    connections: Dict[str, "CoreHandler"]
    locks: Dict[str, asyncio.Lock]
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TelnetHandler, cls).__new__(cls)
            cls._instance.connections = {}
            cls._instance.locks = {}
        return cls._instance

    def _get_lock(self, host: str):
        if host not in self.locks:
            self.locks[host] = asyncio.Lock()
        return self.locks[host]

    @staticmethod
    def get_olt_config_or_404(olt_name: str) -> dict:
        info = OLT_OPTIONS.get(olt_name.strip().upper())
        if not info:
            raise HTTPException(404, detail=f"OLT '{olt_name}' not found.")
        return info

    async def execute_action(self, olt_info: dict, action_callback):
        host = olt_info["ip"]
        lock = self._get_lock(host)

        async with lock:
            handler = self.connections.get(host)

            if not handler:
                # [CRITICAL] Lazy import inside method
                from services.core_handler import CoreHandler
                
                # [CRITICAL] Pass arguments required by TelnetClient.__init__
                handler = CoreHandler(
                    host=host,
                    username=settings.OLT_USERNAME,
                    password=settings.OLT_PASSWORD,
                    is_c600=olt_info.get("c600", False)
                )
                self.connections[host] = handler

            try:
                await handler.connect()
            except Exception as e:
                await handler.close()
                if host in self.connections: del self.connections[host]
                raise e

            try:
                return await action_callback(handler)
            except Exception as e:
                if isinstance(e, HTTPException): raise e
                logging.error(f"OLT Action Failed: {e}")
                raise HTTPException(status_code=500, detail=f"OLT Error: {str(e)}")

# This is the object your endpoints use
olt_manager = TelnetHandler()