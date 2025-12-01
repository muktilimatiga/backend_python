import asyncio
import re
import yaml
import logging
from jinja2 import Environment, FileSystemLoader
from core.olt_config import PACKAGE_OPTIONS
from schemas.config_handler import UnconfiguredOnt, ConfigurationRequest
from services.telnet_handler import TelnetHandler # <--- Import Base

# --- Jinja2 Environment ---
try:
    jinja_env = Environment(loader=FileSystemLoader('templates'), trim_blocks=True, lstrip_blocks=True)
except Exception as e:
    logging.error(f"[FATAL ERROR] Tidak dapat memuat folder 'templates' Jinja2: {e}")
    jinja_env = None

class OltHandler(TelnetHandler): # <--- Inherit from TelnetClient
    
    async def find_unconfigured_onts(self) -> list[UnconfiguredOnt]:
        command = "show pon onu uncfg" if self.is_c600 else "show gpon onu uncfg"
        
        # FIX: Use self.execute_command (Public method from Parent)
        full_output = await self.execute_command(command)
        
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
        
        # FIX: Use self.execute_command
        output = await self.execute_command(cmd)
        
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
        
        # FIX: Use self.execute_command
        output = await self.execute_command(command)
        
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
        
        context = { 
            "interface_olt": base_iface, 
            "interface_onu": iface_onu, 
            "pon_slot": target_ont.pon_slot, 
            "pon_port": target_ont.pon_port, 
            "onu_id": onu_id, 
            "sn": config_request.sn, 
            "customer": config_request.customer, 
            "vlan": vlan, "up_profile": up_paket, 
            "down_profile": down_paket, 
            "jenismodem": "ZTEG-F670" if config_request.modem_type in ["F670L"] else "ALL", 
            "eth_locks": config_request.eth_locks 
        }
        
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
            # FIX: Use self.execute_command
            output = await self.execute_command(cmd)
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