# services/core_handler.py
import asyncio
from services.onu_handler import OnuHandler
from services.config_handler import OltHandler
from services.telnet_client import TelnetClient  # Import your TelnetClient
from core.config import settings

class CoreHandler:
    """Composition-based handler that delegates to specialized handlers"""
    
    def __init__(self, host: str, username: str, password: str, is_c600: bool = False):
        # Create single TelnetClient instance with credentials
        self.telnet = TelnetClient(
            host=host,
            username=settings.TELNET_USERNAME,
            password=settings.TELNET_PASSWORD,
            is_c600=is_c600
        )
        
        # Initialize specialized handlers with the shared connection
        self.onu_handler = OnuHandler(telnet_client=self.telnet)
        self.olt_handler = OltHandler(telnet_client=self.telnet)
        
        # Track creation loop ID for safety checks
        self._creation_loop_id = id(asyncio.get_running_loop())
    
    # Proxy methods to specialized handlers
    async def find_unconfigured_onts(self):
        return await self.onu_handler.find_unconfigured_onts()
    
    async def apply_configuration(self, request, vlan):
        return await self.olt_handler.apply_configuration(request, vlan)
    
    # Connection management methods
    async def connect(self):
        await self.telnet.connect()
    
    async def close(self, force=False):
        await self.telnet.close(force=force)
    
    @property
    def connected(self):
        return self.telnet.connected
    
    @property
    def _owner_loop(self):
        return self.telnet._owner_loop