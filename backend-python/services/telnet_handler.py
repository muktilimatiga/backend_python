import asyncio
import logging
from typing import Dict, Optional, TYPE_CHECKING, Tuple
from fastapi import HTTPException
from core.config import settings
from core.olt_config import OLT_OPTIONS

if TYPE_CHECKING:
    from services.core_handler import CoreHandler

class TelnetHandler:
    _instance: Optional["TelnetHandler"] = None
    connections: Dict[str, "CoreHandler"]
    locks: Dict[str, Tuple[asyncio.Lock, asyncio.AbstractEventLoop]]
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TelnetHandler, cls).__new__(cls)
            cls._instance.connections = {}
            cls._instance.locks = {}
        return cls._instance

    def _get_lock(self, host: str) -> asyncio.Lock:
        current_loop = asyncio.get_running_loop()
        
        # 1. Check if we have a lock, and if it belongs to THIS loop
        if host in self.locks:
            lock, lock_loop = self.locks[host]
            if lock_loop is not current_loop:
                logging.warning(f"Loop changed for host {host}. Clearing locks and connections.")
                del self.locks[host]
                if host in self.connections:
                    del self.connections[host]

        # 2. Create new lock if needed
        if host not in self.locks:
            self.locks[host] = (asyncio.Lock(), current_loop)
            
        return self.locks[host][0]

    @staticmethod
    def get_olt_config_or_404(olt_name: str) -> dict:
        info = OLT_OPTIONS.get(olt_name.strip().upper())
        if not info:
            raise HTTPException(status_code=404, detail=f"OLT '{olt_name}' not found.")
        return info

    async def execute_action(self, olt_info: dict, action_callback):
            host = olt_info["ip"]
            current_loop = asyncio.get_running_loop()
            current_loop_id = id(current_loop)  # Critical: use actual ID
            
            lock = self._get_lock(host)
            async with lock:
                handler = self.connections.get(host)
                
                # 🔥 NEW: Verify handler belongs to CURRENT loop ID
                if handler and getattr(handler, '_creation_loop_id', None) != current_loop_id:
                    logging.warning(
                        f"Handler for {host} belongs to dead loop "
                        f"(cached: {handler._creation_loop_id}, current: {current_loop_id}). Discarding."
                    )
                    if host in self.connections:
                        del self.connections[host]
                    handler = None
                
                if not handler:
                    from services.core_handler import CoreHandler
                    handler = CoreHandler(...)
                    # Store creation loop ID on handler
                    handler._creation_loop_id = current_loop_id  # Add this attribute
                    self.connections[host] = handler

                    try:
                        await handler.connect()
                    except Exception as e:
                        if host in self.connections: 
                            del self.connections[host]
                        raise e

            try:
                return await action_callback(handler)
            except Exception as e:
                # Clean up on connection errors
                if isinstance(e, (ConnectionError, OSError)):
                     logging.error(f"Connection error during action: {e}. clearing connection.")
                     if host in self.connections: 
                         del self.connections[host]
                
                if isinstance(e, HTTPException): raise e
                logging.error(f"OLT Action Failed: {e}")
                raise HTTPException(status_code=500, detail=f"OLT Error: {str(e)}")

olt_manager = TelnetHandler()