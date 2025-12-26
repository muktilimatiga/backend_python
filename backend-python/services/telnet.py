import asyncio
import re
import telnetlib3
import logging
from typing import Optional, Dict, Any
from jinja2 import Environment, FileSystemLoader
from core.olt_config import PACKAGE_OPTIONS, OLT_OPTIONS
from schemas.config_handler import UnconfiguredOnt, ConfigurationRequest, ConfigurationBridgeRequest
import yaml

logging.basicConfig(level=logging.INFO)

# --- Removed SessionLoggedOutError ---

try:
    jinja_env = Environment(loader=FileSystemLoader('templates'), trim_blocks=True, lstrip_blocks=True)
except Exception as e:
    logging.error(f"[FATAL ERROR] Tidak dapat memuat folder 'templates' Jinja2: {e}")
    jinja_env = None

class TelnetClient:
    def __init__(self, host: str, username: str, password: str, is_c600: bool):
        self.host = host
        self.username = username
        self.password = password
        self.is_c600 = is_c600
        self.reader: Optional[telnetlib3.TelnetReader] = None
        self.writer: Optional[telnetlib3.TelnetWriter] = None
        self._prompt_re = re.compile(r"(.+[>#])\s*$")
        self._pagination_prompt = "--More--"

    async def __aenter__(self):
        try:
            self.reader, self.writer = await asyncio.wait_for(
                telnetlib3.open_connection(self.host, 23),
                timeout=20
            )
            await self._login()
            await self._disable_pagination()
            return self
        except Exception as e:
            await self._cleanup_connection()
            raise ConnectionError(f"Failed to connect or login to OLT {self.host}: {e}")
            
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._cleanup_connection()

    async def _cleanup_connection(self):
        if self.writer and not self.writer.is_closing():
            self.writer.close()
            try:
                await asyncio.wait_for(self.writer.wait_closed(), timeout=2)
            except Exception:
                pass
        self.writer = None
        self.reader = None

    async def _read_until_prompt(self, timeout: int = 20) -> str:
        """
        Simplified reader. It ONLY looks for the main prompt.
        It does NOT check for "Username:"
        """
        if not self.reader:
            raise ConnectionError("Telnet reader is not available.")
        try:
            data = ""
            while True:
                chunk = await asyncio.wait_for(self.reader.read(1024), timeout=timeout)
                if not chunk:
                    break
                data += chunk

                # --- Re-login check is REMOVED ---

                if re.search(self._prompt_re, data):
                    break
                
                if self._pagination_prompt in data:
                    if not self.writer:
                        raise ConnectionError("Writer closed during pagination.")
                    self.writer.write(" ")
                    await self.writer.drain()
                    data = data.replace(self._pagination_prompt, "")
            return data
        except asyncio.TimeoutError:
            logging.warning(f"Timeout waiting for prompt from {self.host}")
            # This will now just raise the error and fail the request,
            # which is what you want.
            raise
        except Exception as e:
            raise ConnectionError(f"Error reading from OLT {self.host}: {e}")

    async def _login(self, timeout: int = 20):
        """
        Simple, one-time login function.
        """
        try:
            await asyncio.wait_for(self.reader.readuntil(b'Username:'), timeout=timeout)
            self.writer.write(self.username + '\n')
            
            await asyncio.wait_for(self.reader.readuntil(b'Password:'), timeout=timeout)
            self.writer.write(self.password + '\n')

            # Use the simple reader to wait for the main prompt
            await self._read_until_prompt(timeout=timeout)
            
            logging.info(f"Successfully logged in to OLT {self.host}")
            
        except asyncio.TimeoutError:
            await self._cleanup_connection()
            raise ConnectionError(f"Timeout during login to {self.host}")
        except Exception as e:
            await self._cleanup_connection()
            raise ConnectionError(f"Failed to login: {e}")

    async def _disable_pagination(self):
        if not self.writer:
            raise ConnectionError("Writer not available to disable pagination.")
        
        logging.info(f"Disabling pagination on {self.host}...")
        await self._execute_command("terminal length 0", timeout=20)
        logging.info(f"Pagination disabled on {self.host}.")

    async def _execute_command(self, command: str, timeout: int = 20) -> str:
        """
        Simplified executor. It does NOT try to re-login.
        """
        if not self.reader or not self.writer:
            raise ConnectionError("Connection not established to execute command.")
        if not command:
            return ""
        
        # --- Re-login try/except block is REMOVED ---
        
        self.writer.write(command + "\n")
        await asyncio.wait_for(self.writer.drain(), timeout=10)
        raw_output = await self._read_until_prompt(timeout=timeout)
        
        cleaned_lines = []
        lines = raw_output.splitlines()

        if len(lines) > 2:
            for line in lines[1:-1]:
                stripped = line.strip()
                if stripped:
                    cleaned_lines.append(stripped)
        
        return "\n".join(cleaned_lines)
    
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
            'modem_logs': "\n".join(log_lines[-2:])
        }
        
        return final_result

    @staticmethod
    def _parse_onu_ip_host(raw_output: str) -> str:
        # Regex to find lines starting with "Current IP address:"
        # and capture the value
        ip_regex = re.compile(
            r"^\s*Current IP address:\s+(\S+)", 
            re.MULTILINE
        )
        
        # Find all matches (because there can be multiple Host IDs)
        matches = ip_regex.finditer(raw_output)
        
        for match in matches:
            ip_address = match.group(1)
            # Check if it's a real, assigned IP
            if ip_address and ip_address != "0.0.0.0" and ip_address != "N/A":
                return ip_address # Return the first valid IP found
        
        # If no valid IP was found, return a default
        return "0.0.0.0"

    @staticmethod
    def _parse_onu_attenuation(raw_output: str) -> str:
        # Regex to find the line starting with "down",
        # then capture the (Rx:...) part
        attenuation_regex = re.compile(
            r"^\s*down\s+.*\s+(Rx:[-.\d]+\(dbm\))", 
            re.MULTILINE
        )
        
        match = attenuation_regex.search(raw_output)
        
        if match:
            # Return the captured group, e.g., "Rx:-24.317(dbm)"
            return match.group(1)
        
        # Return N/A if the line wasn't found
        return "N/A"

    @staticmethod
    def _parse_interface_admin_status(raw_output: str, target_interface:str) -> dict:
        
        parser_regex = re.compile(
            rf"Interface\s+:\s+({re.escape(target_interface)}).*?Admin status\s+:\s+(\S+)",
            re.DOTALL
        )
        
        match = parser_regex.search(raw_output)
        
        is_unlocked_status = False 
        
        if match:
            admin_status_str = match.group(2)
            
            if admin_status_str.lower() == "unlock":
                is_unlocked_status = True
            
        return {
            "is_unlocked": is_unlocked_status
        }
    
    @staticmethod
    def _parse_all_interface_admin_statuses(raw_output: str) -> list[dict]:
        """
        Parses all eth ports and their admin status.
        """
        results = []
        
        # Regex to find all "Interface" and "Admin status" pairs
        parser_regex = re.compile(
            r"Interface\s+:\s+(eth_\d+/\d+).*?Admin status\s+:\s+(\S+)",
            re.DOTALL
        )
        
        matches = parser_regex.finditer(raw_output)
        
        for match in matches:
            interface_name = match.group(1)
            admin_status_str = match.group(2)
            is_unlocked = admin_status_str.lower() == "unlock"
            
            results.append({
                "interface": interface_name,
                "is_unlocked": is_unlocked
            })
            
        return results
        
    async def get_onu_detail(self, interface: str) -> Dict[str, Any]:
        logging.info(f"Fetching ONU detail for interface: {interface}")

        prefix = "gpon_onu-" if self.is_c600 else "gpon-onu_"

        if not interface.startswith("gpon"):
            full_interface = f"{prefix}{interface}"
        else:
            full_interface = interface

        cmd = f"show gpon onu detail-info {full_interface}"
        raw_output = await self._execute_command(cmd)

        logging.debug(f"Raw output from OLT for {full_interface}: {raw_output}")

        if not raw_output or "No related information" in raw_output:
            raise LookupError(f"No ONU found or no information returned for {full_interface}.")

        parsed_data = TelnetClient._parse_onu_detail_output(raw_output)
        
        logging.info(f"Parsed data for {full_interface}: {parsed_data}")
        return parsed_data

    async def get_gpon_onu_state(self, base_interface: str) -> str:
        """
        Cek 1 port
        """
        
        prefix = "gpon_olt-" if self.is_c600 else "gpon-olt_"
        
        if not base_interface.startswith("gpon"):
            full_interface = f"{prefix}{interface}"
        else:
            full_interface = interface

        interface = f"{prefix}{full_interface}"

        cmd = f"show gpon onu state {interface}"
        raw_output = await self._execute_command(cmd)

        if not raw_output or "No related information" in raw_output:
            raise LookupError(f"No PORT found or no information returned for {interface}.")

        return raw_output

    async def get_attenuation(self, interface_onu: str,interface) -> str:
        prefix = "gpon_onu-" if self.is_c600 else "gpon-onu_"
        interface_onu = f"{prefix}{interface}"
        cmd = f"show pon power attenuation {interface_onu}"
        raw_output = await self._execute_command(cmd)
        logging.info(f"{raw_output}")

        if not raw_output or "No related information" in raw_output:
            raise LookupError(f"No ONU found or no information returned for {interface_onu}.")
    
        parsed_data = TelnetClient._parse_onu_attenuation(raw_output)
        logging.info(f"{parsed_data}")
        
        return parsed_data


    async def get_onu_rx(self, olt_port:str, interface: str) -> str:
        prefix = "gpon_olt-" if self.is_c600 else "gpon-olt_"
        interface = f"{prefix}{olt_port}"
        cmd = f"show pon power onu-rx {interface}"
        raw_output = await self._execute_command(cmd)

        if not raw_output or "No related information" in raw_output:
            raise LookupError(f"No PORT found or no information returned for {interface}.")

        return raw_output
    
    async def send_reboot_command(self, interface:str, interface_onu:str) -> str:
        """
        Memberi perintah reboot ke onu
        """
        
        prefix = "gpon_onu-" if self.is_c600 else "gpon-onu_"

        if not interface.startswith("gpon"):
            full_interface = f"{prefix}{interface}"
        else:
            full_interface = interface
        
        full_interface = f"{prefix}{interface}"
        commands_to_send = [
            "configure terminal",
            f"interface {full_interface}"
        ]
        
        if self.is_c600:
            commands_to_send.extend(["admin disable", "admin enable", "exit"])
        else:
            commands_to_send.extend(["shut", "no shut", "exit"])

        try:
            # 2. Execute each command
            for cmd in commands_to_send:
                await self._execute_command(cmd)
            return "Reboot success"
            
        except Exception as e:
            # 4. If any command fails, return an error
            logging.error(f"Failed during reboot command sequence for {interface}: {e}")
            return f"Reboot failed: {e}"
    
    async def send_no_onu(self, olt_port:str, interface_olt:str, onu_id:int) -> str:
        prefix = "gpon_olt-" if self.is_c600 else "gpon-olt_"
        interface_olt = f"{prefix}{olt_port}"
        commands_to_send = [
            "configure terminal",
            f"interface {interface_olt}",
            f"no onu {onu_id}"
            "exit",
            "exit"
        ]

        try:
            for cmd in commands_to_send:
                await self._execute_command(cmd)
            logging.info(f"{commands_to_send}")
            logging.info(f"{commands_to_send.extend}")
            
            return "No Onu Succes"
            
        except Exception as e:
            logging.error(f"Failed during reboot command sequence for {interface_olt}: {e}")
            return f"No Onu Failed: {e}"
    
    async def send_new_sn(self, interface:str, interface_omu:str, sn:str) -> str:
        prefix = "gpon_onu-" if self.is_c600 else "gpon-onu_"
        interface_onu = f"{prefix}{interface}"
        commands_to_send = [
            "configure terminal",
            f"interface {interface_onu}",
            f"registration-method sn {sn}"
            "exit",
        ]

        try:
            for cmd in commands_to_send:
                await self._execute_command(cmd)
            logging.info(f"{commands_to_send}")
            logging.info(f"{commands_to_send.extend}")
            
            return "Reconfig Succes"
            
        except Exception as e:
            logging.error(f"Failed during reboot command sequence for {interface_onu}: {e}")
            return f"No Onu Failed: {e}"
        
    async def get_eth_port_statuses(self, interface: str) -> list[dict]:
        """
        Gets the admin status for all eth ports on an ONU.
        'interface' is the core ID, e.g., "1/2/4:10"
        """
        prefix = "gpon_onu-" if self.is_c600 else "gpon-onu_"
        interface_cmd = f"{prefix}{interface}"
        cmd = f"show gpon remote-onu interface eth {interface_cmd}"
        raw_output = await self._execute_command(cmd)

        if not raw_output or "No related information" in raw_output:
            raise LookupError(f"No interface info found for {interface_cmd}.")
    
        # Call the new "scan-all" parser
        parsed_statuses = TelnetClient._parse_all_interface_admin_statuses(raw_output)
        
        return parsed_statuses
    
    async def get_onu_ip_host(self, interface:str, interface_onu: str) -> str:

        prefix = "gpon_onu-" if self.is_c600 else "gpon-onu_"
        interface_onu = f"{prefix}{interface}"
        cmd = f"show gpon remote-onu ip-host {interface_onu}"
        raw_output = await self._execute_command(cmd)

        if not raw_output or "No related information" in raw_output:
            raise LookupError(f"No ONU found or no IP host info for {interface_onu}.")
        logging.info(f"{raw_output}")
    
        parsed_ip = TelnetClient._parse_onu_ip_host(raw_output)
        
        return parsed_ip
    
    async def get_interface_admin_status(self, interface_onu: str, interface: str) -> dict:

            prefix = "gpon_onu-" if self.is_c600 else "gpon-onu_"
            interface_onu = f"{prefix}{interface}"
            cmd = f"show gpon remote-onu interface eth {interface_onu}"
            raw_output = await self._execute_command(cmd)

            if not raw_output or "No related information" in raw_output:
                raise LookupError(f"No interface info found for {interface_onu}.")
            logging.info(f"{raw_output}")
            
            parsed_status = TelnetClient._parse_interface_admin_status(raw_output)
            
            return parsed_status
    
    # Config

    async def find_unconfigured_onts(self) -> list[UnconfiguredOnt]:
        command = "show pon onu uncfg" if self.is_c600 else "show gpon onu uncfg"
        full_output = await self._execute_command(command)
        found_onts = []
        
        for item in full_output.strip().splitlines():
            if ('GPON' in item and self.is_c600) or ('unknown' in item and not self.is_c600):
                pon_slot, pon_port, sn = None, None, None
                try:
                    if self.is_c600:
                        parts = re.split(r'\s+', item.strip())
                        if len(parts) >= 2:
                            interface_str, sn = parts[0], parts[1]
                            match = re.search(r'1/(\d+)/(\d+)', interface_str)
                            if match: pon_port, pon_slot = match.groups()
                    else:
                        x = item.replace("        ", " ").replace(" ", ';')
                        splitter_1 = re.split(";", x)
                        splitter_2 = re.split("/", splitter_1[0])
                        splitter_3 = re.split(":", splitter_2[2])
                        sn = splitter_1[1] if int(splitter_3[0]) >= 10 else splitter_1[2]
                        pon_slot, pon_port = splitter_2[1], splitter_3[0]
                    
                    if all((pon_slot, pon_port, sn)):
                        found_onts.append(UnconfiguredOnt(sn=sn, pon_port=pon_port, pon_slot=pon_slot))
                except (IndexError, ValueError): 
                    continue
        
        logging.info(f"📱 Ditemukan {len(found_onts)} ONT uncfg.")
        return found_onts

    async def find_next_available_onu_id(self, interface: str) -> int:
        logging.info(f"🔍 Mencari ID ONU yang kosong di {interface}...")
        cmd = f"show gpon onu state {interface}"
        output = await self._execute_command(cmd)
        active_onus = []
        identifier = 'enable' if self.is_c600 else '1(GPON)'
        
        for line in output.splitlines():
            if identifier in line:
                try:
                    splitter_1 = re.split(r"\s+", line.strip())[0]
                    splitter_2 = re.split(":", splitter_1)[-1]
                    active_onus.append(int(splitter_2))
                except (IndexError, ValueError):
                    continue
        
        if not active_onus:
            return 1
        
        active_onus.sort()
        calculation = 1
        for onu_id in active_onus:
            if onu_id != calculation:
                break
            calculation += 1

        if calculation > 128:
            raise ValueError(f"Port PON {interface} penuh.")
        
        logging.info(f"✅ Onu ID kosong ditemukan pada {interface}:{calculation}")
        return calculation

    async def get_dba_rate(self, interface: str) -> float:
        # The command to check bandwidth
        command = f"show pon bandwidth dba interface {interface}"
        
        # FIX: Increase timeout to 20 seconds because OLT CPU is slow to calculate this
        # You might need to adjust your _execute_command method to accept a 'timeout' arg
        # If your class doesn't support it, hardcode the read_until timeout in the class.
        output = await self._execute_command(command) 
        
        # Debug log to see what the script actually saw (remove later)
        logging.info(f"DBA OUTPUT RAW: {output}")

        # Your Regex (It is correct based on your output)
        if self.is_c600:
             # C600 usually has an extra column or different spacing, keep as is if tested
            pattern = rf"{re.escape(interface)}\s+\S+\s+\d+\s+\d+\s+\S*\s*(\d+(?:\.\d+)?)"
        else:
            # Matches: interface | channel | config | free | RATE (79.3)
            pattern = rf"{re.escape(interface)}\s+\S+\s+\d+\s+\d+\s+(\d+(?:\.\d+)?)"
        
        match = re.search(pattern, output)
        
        if match:
            rate_str = match.group(1)
            logging.info(f"DBA Rate found: {rate_str}%")
            return float(rate_str)
        else:
            logging.warning(f"Could not parse DBA rate for {interface}. Defaulting to 0.0")
            return 0.0

    async def apply_configuration(self, config_request: ConfigurationRequest, vlan: str):
        ont_list = await self.find_unconfigured_onts()
        target_ont = next((ont for ont in ont_list if ont.sn == config_request.sn), None)
        if not target_ont:
            raise LookupError(f"ONT dengan SN {config_request.sn} tidak ditemukan.")
        
        base_iface = f"gpon-olt_1/{target_ont.pon_slot}/{target_ont.pon_port}"
        if self.is_c600:
            base_iface = f"gpon_olt-1/{target_ont.pon_port}/{target_ont.pon_slot}"
        
        onu_id = await self.find_next_available_onu_id(base_iface)
        rate = await self.get_dba_rate(base_iface)
        up_profile_suffix = "-MBW" if rate > 75.0 else "-FIX"
        base_paket_name = PACKAGE_OPTIONS[config_request.package]
        up_paket = f"{base_paket_name}{up_profile_suffix}"
        down_paket = base_paket_name.replace("MB", "M")
        olt_profile_type = "F670" if config_request.modem_type == "ZTEG-F670" else "ALL"
        
        iface_onu = f"{'gpon_onu-1' if self.is_c600 else 'gpon-onu_1'}/{target_ont.pon_slot}/{target_ont.pon_port}:{onu_id}"
        if self.is_c600:
            iface_onu = f"gpon_onu-1/{target_ont.pon_port}/{target_ont.pon_slot}:{onu_id}"
        
        # --- FIX START: PREPARE LOCKS BEFORE CONTEXT ---
        # 1. Extract the locks from the request
        locks = config_request.eth_locks
        
        # 2. Force the list to have 4 items
        if len(locks) == 1:
            locks = locks * 4  # [True] becomes [True, True, True, True]
        elif len(locks) < 4:
            # Fill remaining with False (Unlock)
            locks.extend([False] * (4 - len(locks)))
        # --- FIX END ---

        context = { 
            "interface_olt": base_iface, 
            "interface_onu": iface_onu, 
            "pon_slot": target_ont.pon_slot, 
            "pon_port": target_ont.pon_port, 
            "onu_id": onu_id, 
            "sn": config_request.sn, 
            "customer": config_request.customer, 
            "vlan": vlan, 
            "up_profile": up_paket, 
            "down_profile": down_paket, 
            "jenismodem": olt_profile_type,
            "eth_locks": locks  # <--- PASS THE PROCESSED LIST HERE
        }
        
        template_name = "config_c600.yaml" if self.is_c600 else "config_c300.yaml"
        
        def _render_and_parse_yaml():
            if jinja_env is None:
                raise RuntimeError("Jinja2 environment not loaded.")
            template = jinja_env.get_template(template_name)
            rendered = template.render(context)
            
            # Debugging logs to verify data
            logging.info(f"🔍 DEBUG CHECK: eth_locks content = {context['eth_locks']}")
            logging.info(f"🔍 DEBUG CHECK: eth_locks length = {len(context['eth_locks'])}")
            
            return yaml.safe_load(rendered)
        
        commands = await asyncio.to_thread(_render_and_parse_yaml)
        
        logs = [f"Memulai konfigurasi untuk SN: {config_request.sn} di {iface_onu}"]
        logging.info(f"🚀 Starting configuration loop. Total commands: {len(commands)}")
        
        for cmd in commands:
            logs.append(f"CMD > {cmd}")
            logging.info(f"➡️ Executing: {cmd}")
            output = await self._execute_command(cmd)
            if output:
                logs.append(f"LOG < {output}")
            await asyncio.sleep(0.3) 

        summary = {
            "Serial Number": config_request.sn,
            "ID Pelanggan": config_request.customer.pppoe_user,
            "Nama Pelanggan": config_request.customer.name,
            "OLT dan ONU": iface_onu,
            "Profil yang dipakai": f"UP-{up_paket} / DOWN-{down_paket}"
        }

        logs.extend([
            "",
            "KONFIGURASI SELESAI",
            "=========================================================",
            f"Serial Number         : {config_request.sn}",
            f"ID pelanggan          : {config_request.customer.pppoe_user}",
            f"Nama pelanggan        : {config_request.customer.name}",
            f"OLT dan ONU           : {iface_onu}",
            f"Profil yang dipakai   : UP-{up_paket} / DOWN-{down_paket}",
            "========================================================="
        ])

        return logs, summary
    

async def config_bridge(self, config_bridge_request: ConfigurationBridgeRequest, vlan: str):
    ont_list = await self.find_unconfigured_onts()
    target_ont = next((ont for ont in ont_list if ont.sn == config_bridge_request.sn), None)
    if not target_ont:
        raise LookupError(f"ONT dengan SN {config_bridge_request.sn} tidak ditemukan.")
    
    base_iface = f"gpon-olt_1/{target_ont.pon_slot}/{target_ont.pon_port}"
    if self.is_c600:
        base_iface = f"gpon_olt-1/{target_ont.pon_slot}/{target_ont.pon_port}"

    onu_id = await self.find_next_available_onu_id(base_iface)
    package = PACKAGE_OPTIONS[config_bridge_request.package]
    olt_profile_type = "F670" if config_bridge_request.modem_type == "ZTEG-F670" else "ALL"
    vlan = vlan(config_bridge_request.vlan)

    iface_onu = f"{'gpon_onu-1' if self.is_c600 else 'gpon-onu_1'}/{target_ont.pon_slot}/{target_ont.pon_port}:{onu_id}"
    if self.is_c600:
        iface_onu = f"gpon_onu-1/{target_ont.pon_port}/{target_ont.pon_slot}:{onu_id}"
    
        context = { 
        "interface_olt": base_iface, 
        "interface_onu": iface_onu, 
        "pon_slot": target_ont.pon_slot, 
        "pon_port": target_ont.pon_port, 
        "onu_id": onu_id, 
        "sn": config_bridge_request.sn, 
        "customer": config_bridge_request.customer, 
        "vlan": config_bridge_request.vlan, 
        "paket" : config_bridge_request.package,
        "jenismodem": olt_profile_type,
    }
        
    template_name = "config_bridge.yaml"
    
    def _render_and_parse_yaml():
        if jinja_env is None:
            raise RuntimeError("Jinja2 environment not loaded!")
        template = jinja_env(template_name)
        rendered = template.render(context)

    commands = await asyncio.to_thread(_render_and_parse_yaml)
    logs = [f"Memulai konfigurasi untuk SN: {config_bridge_request.sn} di {iface_onu}"]
    logging.info(f"Memulai konfigurasi. Total Command: {len(commands)}")

    for cmd in commands:
        logs.append(f"CMD > {cmd}")
        logging.info(f"EXECUTING: {cmd}")
        output = await self._execute_command(cmd)
        if output:
            logs.append(f"LOG < {output}")
        await asyncio.sleep(0.3)

    summary = {
        "Serial Number": config_bridge_request.sn,
        "ID Pelanggan": config_bridge_request.customer.pppoe_user,
        "Nama Pelanggan": config_bridge_request.customer,
        "OLT dan ONU": iface_onu,
        "Profil yang dipakai": config_bridge_request.package
    }

    logs.extend([
                    "KONFIGURASI SELESAI",
            "=========================================================",
            f"Serial Number         : {config_bridge_request.sn}",
            f"ID pelanggan          : {config_bridge_request.customer.pppoe_user}",
            f"Nama pelanggan        : {config_bridge_request.customer.name}",
            f"OLT dan ONU           : {iface_onu}",
            f"Profil yang dipakai   : {config_bridge_request.package}",
            "========================================================="
    ])

    return logs, summary