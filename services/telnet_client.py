import asyncio
import logging
import telnetlib3
from core.config import settings

class TelnetClient:
    def __init__(self, host: str, username: str, password: str, is_c600: bool = False):
        self.host = host
        self.username = username
        self.password = password
        self.is_c600 = is_c600
        self.reader = None
        self.writer = None
        self.connected = False

    async def connect(self):
        if self.connected:
            return

        try:
            # Use configured timeout or default to 15
            timeout = settings.TELNET_TIMEOUT if hasattr(settings, 'TELNET_TIMEOUT') else 15
            
            self.reader, self.writer = await asyncio.wait_for(
                telnetlib3.open_connection(self.host, 23, encoding='ascii'), 
                timeout=timeout
            )
            
            # Login Flow
            await self.read_until(["Username:", "Login:", "login:"], timeout)
            self.writer.write(self.username + "\n")
            
            await self.read_until(["Password:", "password:"], timeout)
            self.writer.write(self.password + "\n")
            
            await self.read_until([">", "#"], timeout)
            
            # Disable paging
            self.writer.write("terminal length 0\n")
            await self.read_until([">", "#"], timeout)
            
            self.connected = True
            logging.info(f"Connected to {self.host}")

        except Exception as e:
            logging.error(f"Failed to connect to {self.host}: {e}")
            self.connected = False
            raise ConnectionError(f"Telnet connection failed: {e}")

    async def execute_command(self, cmd: str) -> str:
        if not self.connected or not self.writer:
            await self.connect()

        try:
            self.writer.write(cmd + "\n")
            timeout = settings.TELNET_TIMEOUT if hasattr(settings, 'TELNET_TIMEOUT') else 15
            output = await self.read_until([">", "#"], timeout=timeout)
            return output
        except Exception as e:
            logging.error(f"Error executing command '{cmd}': {e}")
            self.connected = False
            raise

    async def read_until(self, expected_list, timeout=5):
        if isinstance(expected_list, str):
            expected_list = [expected_list]
            
        buffer = ""
        try:
            while True:
                data = await asyncio.wait_for(self.reader.read(1024), timeout=timeout)
                if not data:
                    break
                buffer += data
                for exp in expected_list:
                    if exp in buffer:
                        return buffer
        except asyncio.TimeoutError:
            return buffer
        return buffer

    async def close(self):
        if self.writer:
            try:
                self.writer.close()
            except Exception:
                pass
        self.connected = False
        logging.info(f"Disconnected from {self.host}")