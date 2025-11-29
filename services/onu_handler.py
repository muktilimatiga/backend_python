# services/onu_handler.py

import asyncio
import re
import telnetlib3
import logging
from typing import Optional, Dict, Any, List

logging.basicConfig(level=logging.INFO)

class OnuHandler:
    def __init__(self, host: str, username: str, password: str, is_c600: bool):
        self.host = host
        self.username = username
        self.password = password
        self.is_c600 = is_c600
        
        # State management
        self.reader: Optional[telnetlib3.TelnetReader] = None
        self.writer: Optional[telnetlib3.TelnetWriter] = None
        
        # Regex patterns
        self._prompt_re = re.compile(r"(.+[>#])\s*$")
        self._pagination_prompt = "--More--"

    # =================================================================
    # CONNECTION MANAGEMENT
    # =================================================================

    def is_connected(self) -> bool:
        """Check if the Telnet writer is active and not closing."""
        return self.writer is not None and not self.writer.is_closing()

    async def connect(self):
        """
        Explicit connection initiator.
        Called by OLTConnectionManager.
        """
        if self.is_connected():
            return
            
        logging.info(f"Initiating new connection to {self.host}...")
        try:
            self.reader, self.writer = await asyncio.wait_for(
                telnetlib3.open_connection(self.host, 23),
                timeout=20
            )
            await self._login()
            await self._disable_pagination()
            logging.info(f"Connection established to {self.host}")
            
        except Exception as e:
            # If login fails, ensure we close the socket
            await self.close()
            raise ConnectionError(f"Failed to connect to OLT {self.host}: {e}")

    async def close(self):
        """
        Gracefully closes the connection.
        """
        if self.writer:
            logging.info(f"Closing connection to {self.host}...")
            self.writer.close()
            try:
                await asyncio.wait_for(self.writer.wait_closed(), timeout=2)
            except Exception:
                pass # Ignore errors during close
                
        self.writer = None
        self.reader = None

    # =================================================================
    # INTERNAL HELPERS (Login, Read, Execute)
    # =================================================================

    async def _read_until_prompt(self, timeout: int = 20) -> str:
        """
        Reads the stream until the command prompt (e.g., 'OLT-1#') is found.
        Handles '--More--' pagination automatically.
        """
        if not self.reader:
            raise ConnectionError("Telnet reader is not available.")
        
        try:
            data = ""
            while True:
                chunk = await asyncio.wait_for(self.reader.read(1024), timeout=timeout)
                if not chunk:
                    # Connection closed by remote
                    break
                data += chunk

                # Check for Prompt
                if re.search(self._prompt_re, data):
                    break
                
                # Check for Pagination
                if self._pagination_prompt in data:
                    if not self.writer:
                        raise ConnectionError("Writer closed during pagination.")
                    # Send space to load more
                    self.writer.write(" ")
                    await self.writer.drain()
                    # Remove the '--More--' text from the buffer
                    data = data.replace(self._pagination_prompt, "")
            return data
            
        except asyncio.TimeoutError:
            logging.warning(f"Timeout waiting for prompt from {self.host}")
            raise
        except Exception as e:
            raise ConnectionError(f"Error reading from OLT {self.host}: {e}")

    async def _login(self, timeout: int = 20):
        """
        Handles the Username/Password interaction.
        """
        try:
            await asyncio.wait_for(self.reader.readuntil(b'Username:'), timeout=timeout)
            self.writer.write(self.username + '\n')
            
            await asyncio.wait_for(self.reader.readuntil(b'Password:'), timeout=timeout)
            self.writer.write(self.password + '\n')

            # Wait for the first prompt to confirm login success
            await self._read_until_prompt(timeout=timeout)
            
        except Exception as e:
            raise ConnectionError(f"Login failed: {e}")

    async def _disable_pagination(self):
        """
        Sets terminal length 0 to prevent --More-- during commands.
        """
        await self._execute_command("terminal length 0", timeout=20)

    async def _execute_command(self, command: str, timeout: int = 20) -> str:
        """
        Sends a command and returns the output.
        If connection drops, it raises ConnectionResetError for the Manager to catch.
        """
        if not self.is_connected():
            raise ConnectionResetError("Connection is closed")
        
        try:
            logging.debug(f"Sending command to {self.host}: {command}")
            
            # 1. Write Command
            self.writer.write(command + "\n")
            await asyncio.wait_for(self.writer.drain(), timeout=10)
            
            # 2. Read Response
            raw_output = await self._read_until_prompt(timeout=timeout)
            
            # 3. Clean Output
            cleaned_lines = []
            lines = raw_output.splitlines()

            for line in lines:
                stripped = line.strip()
                # Remove the echo of the command itself
                if stripped == command:
                    continue
                # Remove the prompt line at the end
                if re.search(self._prompt_re, stripped):
                    continue
                # Add valid content
                if stripped:
                    cleaned_lines.append(stripped)
            
            return "\n".join(cleaned_lines)
    
        except (ConnectionResetError, BrokenPipeError, asyncio.TimeoutError):
            # We don't close self here; we raise error so the Manager handles the retry logic
            raise ConnectionResetError(f"Lost connection to {self.host} during command execution.")

    # =================================================================
    # DATA PARSERS (Static Methods)
    # =================================================================

    @staticmethod
    def _parse_onu_detail_output(raw_output: str) -> Dict[str, Any]:
        kv_regex = re.compile(r'^\s*([^:]+?):\s+(.*?)\s*$')
        log_regex = re.compile(r'^\s*(\d+)\s+([\d-]{10}\s[\d:]{8})\s+([\d-]{10}\s[\d:]{8})\s*(.*)$')
        
        parsed_data = {}
        log_lines = []

        for line in raw_output.splitlines():
            log_match = log_regex.search(line)
            if log_match:
                log_lines.append(line)
                continue
                
            kv_match = kv_regex.search(line)
            if kv_match:
                key = kv_match.group(1).strip()
                value = kv_match.group(2).strip()
                if value:
                    parsed_data[key] = value

        final_result = {
            'type': parsed_data.get('Type'),
            'phase_state': parsed_data.get('Phase state'),
            'serial_number': parsed_data.get('Serial number'),
            'onu_distance': parsed_data.get('ONU Distance'),
            'online_duration': parsed_data.get('Online Duration'),
            'modem_logs': "\n".join(log_lines[-2:]) # Last 2 logs
        }
        return final_result

    @staticmethod
    def _parse_onu_ip_host(raw_output: str) -> str:
        ip_regex = re.compile(r"^\s*Current IP address:\s+(\S+)", re.MULTILINE)
        matches = ip_regex.finditer(raw_output)
        
        for match in matches:
            ip_address = match.group(1)
            if ip_address and ip_address not in ["0.0.0.0", "N/A"]:
                return ip_address
        return "0.0.0.0"

    @staticmethod
    def _parse_onu_attenuation(raw_output: str) -> str:
        attenuation_regex = re.compile(r"^\s*down\s+.*\s+(Rx:[-.\d]+\(dbm\))", re.MULTILINE)
        match = attenuation_regex.search(raw_output)
        return match.group(1) if match else "N/A"

    @staticmethod
    def _parse_all_interface_admin_statuses(raw_output: str) -> List[Dict]:
        results = []
        parser_regex = re.compile(r"Interface\s+:\s+(eth_\d+/\d+).*?Admin status\s+:\s+(\S+)", re.DOTALL)
        matches = parser_regex.finditer(raw_output)
        
        for match in matches:
            interface_name = match.group(1)
            admin_status_str = match.group(2)
            results.append({
                "interface": interface_name,
                "is_unlocked": admin_status_str.lower() == "unlock"
            })
        return results

    # =================================================================
    # BUSINESS LOGIC METHODS (Called by Router)
    # =================================================================

    async def get_onu_detail(self, interface: str) -> Dict[str, Any]:
        logging.info(f"Fetching ONU detail for interface: {interface}")
        cmd = f"show gpon onu detail-info {interface}"
        raw_output = await self._execute_command(cmd)

        if not raw_output or "No related information" in raw_output:
            raise LookupError(f"No ONU found for {interface}.")

        return OnuHandler._parse_onu_detail_output(raw_output)

    async def get_gpon_onu_state(self, olt_port: str, interface: str) -> str:
        # interface passed is full string e.g. "gpon-olt_1/2/3"
        cmd = f"show gpon onu state {interface}"
        raw_output = await self._execute_command(cmd)
        
        if not raw_output or "No related information" in raw_output:
            raise LookupError(f"No PORT found for {interface}.")
            
        return raw_output

    async def get_attenuation(self, interface_onu: str, interface: str = None) -> str:
        # interface param unused, kept for compatibility
        cmd = f"show pon power attenuation {interface_onu}"
        raw_output = await self._execute_command(cmd)
        
        if not raw_output or "No related information" in raw_output:
            # Not raising error here, just returning N/A to keep dashboard loading
            return "N/A"
            
        return OnuHandler._parse_onu_attenuation(raw_output)

    async def get_onu_rx(self, olt_port: str, interface: str) -> str:
        cmd = f"show pon power onu-rx {interface}"
        raw_output = await self._execute_command(cmd)
        
        if not raw_output or "No related information" in raw_output:
             raise LookupError(f"No PORT found for {interface}.")
             
        return raw_output

    async def get_eth_port_statuses(self, interface: str) -> List[Dict]:
        # Expects "1/2/3:4" (interface string without prefix)
        prefix = "gpon_onu-" if self.is_c600 else "gpon-onu_"
        interface_cmd = f"{prefix}{interface}"
        cmd = f"show gpon remote-onu interface eth {interface_cmd}"
        
        try:
            raw_output = await self._execute_command(cmd)
            if "No related information" in raw_output:
                return []
            return OnuHandler._parse_all_interface_admin_statuses(raw_output)
        except Exception:
             # If command fails (e.g., model doesn't support it), return empty list
            return []

    async def get_onu_ip_host(self, interface_onu: str, interface: str = None) -> str:
        cmd = f"show gpon remote-onu ip-host {interface_onu}"
        
        try:
            raw_output = await self._execute_command(cmd)
            if "No related information" in raw_output:
                return "0.0.0.0"
            return OnuHandler._parse_onu_ip_host(raw_output)
        except Exception:
            return "0.0.0.0"
    
    # --- WRITE/ACTION COMMANDS ---

    async def send_reboot_command(self, interface: str, interface_onu: str) -> str:
        commands_to_send = [
            "configure terminal",
            f"interface {interface_onu}"
        ]
        
        if self.is_c600:
            commands_to_send.extend(["admin disable", "admin enable", "exit"])
        else:
            commands_to_send.extend(["shut", "no shut", "exit"])

        try:
            for cmd in commands_to_send:
                await self._execute_command(cmd)
            return "Reboot success"
        except Exception as e:
            logging.error(f"Reboot failed for {interface}: {e}")
            return f"Reboot failed: {e}"
    
    async def send_no_onu(self, olt_port: str, interface_olt: str, onu_id: int) -> str:
        commands_to_send = [
            "configure terminal",
            f"interface {interface_olt}",
            f"no onu {onu_id}",
            "exit",
            "exit"
        ]

        try:
            for cmd in commands_to_send:
                await self._execute_command(cmd)
            return "No Onu Success"
        except Exception as e:
            logging.error(f"No Onu failed for {interface_olt}: {e}")
            return f"No Onu Failed: {e}"
    
    async def send_new_sn(self, interface: str, interface_onu: str, sn: str) -> str:
        commands_to_send = [
            "configure terminal",
            f"interface {interface_onu}",
            f"registration-method sn {sn}",
            "exit",
        ]

        try:
            for cmd in commands_to_send:
                await self._execute_command(cmd)
            return "Reconfig Success"
        except Exception as e:
            logging.error(f"Regist SN failed for {interface_onu}: {e}")
            return f"Regist SN Failed: {e}"