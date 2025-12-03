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
        
        # --- LOOP GUARD VARIABLES ---
        self._owner_loop = None  # Tracks which loop created the connection
        self._lock = None        # Async lock for command execution
        self._creation_loop_id = id(asyncio.get_running_loop())  # Track creation loop ID

    def _reset_telnetlib3_state(self):
        if hasattr(self.reader, '_waiter') and self.reader._waiter:
            self.reader._waiter.cancel()
            self.reader._waiter = None
        
        if hasattr(self.writer, '_waiter') and self.writer._waiter:
            self.writer._waiter.cancel()
            self.writer._waiter = None
        
        # Clear internal buffers
        if hasattr(self.reader, '_buffer'):
            self.reader._buffer.clear()
        
        # Reset encoding state
        if hasattr(self.reader, '_decoder'):
            self.reader._decoder = None

    async def _ensure_lock(self):
        """Ensure we have a lock that belongs to the CURRENT event loop."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def connect(self):
        current_loop = asyncio.get_running_loop()

        # LOOP GUARD: If connected but on a different loop, force close and reconnect
        if self.connected and self._owner_loop and self._owner_loop is not current_loop:
            logging.warning(f"⚠️ Loop switch detected for {self.host}. Reconnecting on new loop.")
            await self.close(force=True)

        # HARDENING: Ensure state is absolutely clean before proceeding
        if self.connected or self.reader or self.writer:
             # This handles cases where close() might have partially failed or state drifted
             logging.warning(f"⚠️ Stale connection state detected for {self.host} during connect. Forcing cleanup.")
             self.connected = False
             self.reader = None
             self.writer = None
             self._owner_loop = None

        # Ensure lock exists for this loop
        await self._ensure_lock()

        try:
            timeout = settings.TELNET_TIMEOUT if hasattr(settings, 'TELNET_TIMEOUT') else 15
            
            # Update owner loop to current
            self._owner_loop = current_loop
            
            # Pass loop=current_loop to be explicit
            self.reader, self.writer = await asyncio.wait_for(
            telnetlib3.open_connection(
                self.host, 23, encoding='latin1'  # REMOVED loop=current_loop
            ), 
            timeout=timeout
)
            
            # Login Flow
            await self.read_until(["Username:", "Login:", "login:", "user:"], timeout)
            self.writer.write(self.username + "\n")
            
            await self.read_until(["Password:", "password:"], timeout)
            self.writer.write(self.password + "\n")
            
            await self.read_until([">", "#"], timeout)
            
            # Disable paging
            self.writer.write("terminal length 0\n")
            await self.read_until([">", "#"], timeout)
            
            self.connected = True
            logging.info(f"Connected to {self.host}")
            logging.debug(
            f"Connecting to {self.host} on loop {id(asyncio.get_running_loop())} "
            f"(created on loop {self._creation_loop_id})"
)

        except Exception as e:
            logging.error(f"Failed to connect to {self.host}: {e}")
            self.connected = False
            self._owner_loop = None
            raise ConnectionError(f"Telnet connection failed: {e}")

    async def execute_command(self, cmd: str) -> str:
        # Check loop mismatch BEFORE trying to acquire lock
        current_loop = asyncio.get_running_loop()
        if self.connected and self._owner_loop is not current_loop:
             logging.warning("Loop mismatch in execute_command. Reconnecting...")
             await self.close(force=True)

        lock = await self._ensure_lock()

        async with lock:
            if not self.connected or not self.writer:
                await self.connect()

            try:
                self.writer.write(cmd + "\n")
                timeout = settings.TELNET_TIMEOUT if hasattr(settings, 'TELNET_TIMEOUT') else 15
                output = await self.read_until([">", "#"], timeout=timeout)
                return output
            except Exception as e:
                # If ANY error happens (including the loop error), force a reset
                logging.error(f"Error executing command '{cmd}': {e}")
                await self.close(force=True)
                raise

    async def read_until(self, expected_list, timeout=5):
        if isinstance(expected_list, str):
            expected_list = [expected_list]
            
        buffer = ""
        try:
            while True:
                data = await asyncio.wait_for(self.reader.read(4096), timeout=timeout)
                if not data:
                    if buffer: return buffer
                    raise ConnectionError("Connection closed by remote host")
                
                buffer += data
                for exp in expected_list:
                    if exp in buffer:
                        return buffer
        except asyncio.TimeoutError:
            return buffer
        return buffer

    async def close(self, force=False):
        current_loop = asyncio.get_running_loop()
        
        # 1. Nuclear reset of telnetlib3 internal state
        if self.reader or self.writer:
            self._reset_telnetlib3_state()
        
        # 2. Kill pending reads
        if self.reader:
            try:
                self.reader.feed_eof()
            except Exception as e:
                logging.debug(f"Ignored feed_eof error: {e}")
        
        # 3. Close socket
        should_close_socket = self.writer and (not force or self._owner_loop is current_loop)
        if should_close_socket:
            try:
                self.writer.close()
                await asyncio.wait_for(self.writer.wait_closed(), timeout=2.0)
            except Exception as e:
                logging.debug(f"Ignored socket close error: {e}")
        
        # 4. Full state reset
        self.connected = False
        self.reader = None
        self.writer = None
        self._owner_loop = None
        logging.info(f"Fully reset connection to {self.host} (force={force})")