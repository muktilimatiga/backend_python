import asyncio
from fastapi import HTTPException
from typing import Dict, Optional
from services.onu_handler import OnuHandler
from services.core_hanlder import CoreHandler
from core.config import settings
from core.olt_config import OLT_OPTIONS
import logging

class TelnetHandler:
    # 1. Define types here for Pylance
    _instance: Optional["TelnetHandler"] = None
    connections: Dict[str, CoreHandler]
    locks: Dict[str, asyncio.Lock]
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TelnetHandler, cls).__new__(cls)
            # 2. Assign values here
            cls._instance.connections = {}
            cls._instance.locks = {}
        return cls._instance

    def _get_lock(self, host: str):
        if host not in self.locks:
            self.locks[host] = asyncio.Lock()
        return self.locks[host]

    def get_olt_config_or_404(olt_name: str) -> dict:
    # 1. Normalize input: specific keys in OLT_OPTIONS are UPPERCASE
    #    This ensures "boyolangu", "Boyolangu", and "BOYOLANGU" all work.
        key = olt_name.strip().upper()
        
        # 2. Safe Lookup
        olt_info = OLT_OPTIONS.get(key)
        
        # 3. Error Handling
        if not olt_info:
            raise HTTPException(
                status_code=404, 
                detail=f"OLT Configuration for '{olt_name}' not found. Available: {list(OLT_OPTIONS.keys())}"
            )
            
        return olt_info

    async def execute_action(self, olt_info: dict, action_callback):
        host = olt_info["ip"]
        lock = self._get_lock(host)

        # 1. Wait for your turn (Locking)
        async with lock:
            handler = self.connections.get(host)

            # 2. Create Handler if it doesn't exist
            if not handler:
                handler = CoreHandler(
                    host=olt_info["ip"],
                    username=settings.OLT_USERNAME,
                    password=settings.OLT_PASSWORD,
                    is_c600=olt_info["c600"]
                )
                self.connections[host] = handler

            # 3. Ensure Connected
            try:
                await handler.connect()
            except Exception as e:
                await handler.close()
                if host in self.connections:
                    del self.connections[host]
                raise e

            # 4. Run Command & Auto-Heal
            try:
                return await action_callback(handler)
            except HTTPException as http_exc:
                # Pass through HTTP exceptions (like 500 Reboot Failed)
                raise http_exc 
            except Exception as e:
                # Catch unexpected Telnet errors
                logging.error(f"OLT Action Failed: {e}")
                raise HTTPException(status_code=500, detail=f"OLT Error: {str(e)}")

olt_manager = TelnetBase()