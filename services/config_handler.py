import asyncio
import re
import telnetlib3
import yaml
import logging
from jinja2 import Environment, FileSystemLoader
from typing import List, Optional, Dict, Any
from core.config import settings
from core.olt_config import PACKAGE_OPTIONS, OLT_OPTIONS
from schemas.config_handler import UnconfiguredOnt, ConfigurationRequest

# --- Jinja2 Environment ---
try:
    jinja_env = Environment(loader=FileSystemLoader('templates'), trim_blocks=True, lstrip_blocks=True)
except Exception as e:
    logging.error(f"[FATAL ERROR] Tidak dapat memuat folder 'templates' Jinja2: {e}")
    jinja_env = None

class OltHandler:
    def __init__(self, host: str, username: str, password: str, is_c600: bool):
        self.host = host
        self.username = username
        self.password = password
        self.is_c600 = is_c600
        self.reader: Optional[telnetlib3.TelnetReader] = None
        self.writer: Optional[telnetlib3.TelnetWriter] = None
        # --- FIX: Using the simpler, more reliable regex from onu_handler.py ---
        self._prompt_re = re.compile(r"(.+[>#])\s*$")
        self._pagination_prompt = "--More--"

    async def __aenter__(self):
        try:
            self.reader, self.writer = await asyncio.wait_for(
                telnetlib3.open_connection(self.host, 23), timeout=20
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
            try:
                self.writer.write("\nexit\n")
            except Exception:
                pass
            self.writer.close()
            try:
                await asyncio.wait_for(self.writer.wait_closed(), timeout=2)
            except Exception:
                pass
        self.writer = None
        self.reader = None

    # --- FIX: Using the more robust _read_until_prompt from onu_handler.py ---
    async def _read_until_prompt(self, timeout: int = 20) -> str:
        if not self.reader:
            raise ConnectionError("Telnet reader is not available.")
        try:
            data = ""
            while True:
                chunk = await asyncio.wait_for(self.reader.read(1024), timeout=timeout)
                if not chunk:
                    break
                data += chunk

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
            raise
        except Exception as e:
            raise ConnectionError(f"Error reading from OLT {self.host}: {e}")

    # --- FIX: Using the more robust _login from onu_handler.py ---
    async def _login(self, timeout: int = 20):
        try:
            await asyncio.wait_for(self.reader.readuntil(b'Username:'), timeout=timeout)
            self.writer.write(self.username + '\n')
            
            await asyncio.wait_for(self.reader.readuntil(b'Password:'), timeout=timeout)
            self.writer.write(self.password + '\n')

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

    # --- FIX: Using the more robust _execute_command from onu_handler.py ---
    async def _execute_command(self, command: str, timeout: int = 20) -> str:
        if not self.reader or not self.writer:
            raise ConnectionError("Connection not established to execute command.")
        if not command:
            return ""
        
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
    
    # --- Kept your original (unchanged) methods below ---

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
        command = f"show pon bandwidth dba interface {interface}"
        output = await self._execute_command(command)
        if self.is_c600:
            pattern = rf"{re.escape(interface)}\s+\S+\s+\d+\s+\d+\s+\S*\s*(\d+(?:\.\d+)?)"
        else:
            pattern = rf"{re.escape(interface)}\s+\S+\s+\d+\s+\d+\s+(\d+(?:\.\d+)?)"
        match = re.search(pattern, output)
        return float(match.group(1)) if match else 0.0

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
        iface_onu = f"{'gpon_onu-1' if self.is_c600 else 'gpon-onu_1'}/{target_ont.pon_slot}/{target_ont.pon_port}:{onu_id}"
        if self.is_c600:
            iface_onu = f"gpon_onu-1/{target_ont.pon_port}/{target_ont.pon_slot}:{onu_id}"
        
        context = { "interface_olt": base_iface, 
        "interface_onu": iface_onu, 
        "pon_slot": target_ont.pon_slot, 
        "pon_port": target_ont.pon_port, 
        "onu_id": onu_id, 
        "sn": config_request.sn, 
        "customer": config_request.customer, 
        "vlan": vlan, "up_profile": up_paket, 
        "down_profile": down_paket, 
        "jenismodem": "ZTEG-F670" if config_request.modem_type in ["F670L"] else "ALL", 
        "eth_locks": config_request.eth_locks }
        
        template_name = "config_c600.yaml" if self.is_c600 else "config_c300.yaml"
        
        def _render_and_parse_yaml():
            if jinja_env is None:
                raise RuntimeError("Jinja2 environment not loaded.")
            template = jinja_env.get_template(template_name)
            rendered = template.render(context)
            return yaml.safe_load(rendered)
        
        commands = await asyncio.to_thread(_render_and_parse_yaml)
        
        logs = [f"Memulai konfigurasi untuk SN: {config_request.sn} di {iface_onu}"]
        
        for cmd in commands:
            logs.append(f"CMD > {cmd}")
            output = await self._execute_command(cmd)
            if output:
                logs.append(f"LOG < {output}")
            await asyncio.sleep(0.1) 

        summary = {
            "serial_number": config_request.sn,
            "pppoe_user": config_request.customer.pppoe_user,
            "location": iface_onu,
            "profile": f"UP-{up_paket} / DOWN-{down_paket}"
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