import asyncio
import re
import telnetlib3
import logging
from typing import Optional

class TelnetClient:
    """
    Base class that handles ONLY the raw Telnet connection, 
    Login, and Command Execution.
    """
    def __init__(self, host: str, username: str, password: str, is_c600: bool):
        self.host = host
        self.username = username
        self.password = password
        self.is_c600 = is_c600
        self.reader: Optional[telnetlib3.TelnetReader] = None
        self.writer: Optional[telnetlib3.TelnetWriter] = None
        self._prompt_re = re.compile(r"(.+[>#])\s*$")
        self._pagination_prompt = "--More--"

    def is_connected(self) -> bool:
        return self.writer is not None and not self.writer.is_closing()

    async def connect(self):
        if self.is_connected():
            return
        
        logging.info(f"Connecting to {self.host}...")
        try:
            self.reader, self.writer = await asyncio.wait_for(
                telnetlib3.open_connection(self.host, 23), timeout=20
            )
            await self._login()
            await self._disable_pagination()
        except Exception as e:
            await self.close()
            raise ConnectionError(f"Connection failed: {e}")

    async def close(self):
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
        self.writer = None
        self.reader = None

    async def _read_until_prompt(self, timeout: int = 20) -> str:
        if not self.reader: raise ConnectionError("Not connected")
        data = ""
        while True:
            chunk = await asyncio.wait_for(self.reader.read(1024), timeout=timeout)
            if not chunk: break
            data += chunk
            if re.search(self._prompt_re, data): break
            if self._pagination_prompt in data:
                self.writer.write(" ")
                await self.writer.drain()
                data = data.replace(self._pagination_prompt, "")
        return data

    async def _login(self, timeout: int = 20):
        await asyncio.wait_for(self.reader.readuntil(b'Username:'), timeout)
        self.writer.write(self.username + '\n')
        await asyncio.wait_for(self.reader.readuntil(b'Password:'), timeout)
        self.writer.write(self.password + '\n')
        await self._read_until_prompt(timeout)

    async def _disable_pagination(self):
        await self.execute_command("terminal length 0")

    async def execute_command(self, command: str, timeout: int = 20) -> str:
        if not self.is_connected(): raise ConnectionResetError("Connection closed")
        try:
            self.writer.write(command + "\n")
            await self.writer.drain()
            raw = await self._read_until_prompt(timeout)
            # Clean echo and prompt
            lines = raw.splitlines()
            return "\n".join([l for l in lines if command not in l and not re.search(self._prompt_re, l)])
        except Exception:
            raise ConnectionResetError(f"Lost connection to {self.host}")