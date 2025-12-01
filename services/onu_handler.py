# services/onu_handler.py

import logging
import re
from typing import Dict, Any, List
from services.telnet_client import TelnetClient
logging.basicConfig(level=logging.INFO)

class OnuHandler(TelnetClient):  # <--- Inherits connection logic
    """
    Handles ONU-specific logic.
    Connection, Login, and Execution are handled by TelnetClient.
    """

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
    # BUSINESS LOGIC METHODS
    # =================================================================

    async def get_onu_detail(self, interface: str) -> Dict[str, Any]:
        logging.info(f"Fetching ONU detail for interface: {interface}")
        cmd = f"show gpon onu detail-info {interface}"
        
        # Call the PARENT class method
        raw_output = await self.execute_command(cmd)

        if not raw_output or "No related information" in raw_output:
            raise LookupError(f"No ONU found for {interface}.")

        return OnuHandler._parse_onu_detail_output(raw_output)

    async def get_gpon_onu_state(self, olt_port: str, interface: str) -> str:
        cmd = f"show gpon onu state {interface}"
        raw_output = await self.execute_command(cmd)
        
        if not raw_output or "No related information" in raw_output:
            raise LookupError(f"No PORT found for {interface}.")
            
        return raw_output

    async def get_attenuation(self, interface_onu: str, interface: str = None) -> str:
        cmd = f"show pon power attenuation {interface_onu}"
        raw_output = await self.execute_command(cmd)
        
        if not raw_output or "No related information" in raw_output:
            return "N/A"
            
        return OnuHandler._parse_onu_attenuation(raw_output)

    async def get_onu_rx(self, olt_port: str, interface: str) -> str:
        cmd = f"show pon power onu-rx {interface}"
        raw_output = await self.execute_command(cmd)
        
        if not raw_output or "No related information" in raw_output:
             raise LookupError(f"No PORT found for {interface}.")
             
        return raw_output

    async def get_eth_port_statuses(self, interface: str) -> List[Dict]:
        prefix = "gpon_onu-" if self.is_c600 else "gpon-onu_"
        interface_cmd = f"{prefix}{interface}"
        cmd = f"show gpon remote-onu interface eth {interface_cmd}"
        
        try:
            raw_output = await self.execute_command(cmd)
            if "No related information" in raw_output:
                return []
            return OnuHandler._parse_all_interface_admin_statuses(raw_output)
        except Exception:
            return []

    async def get_onu_ip_host(self, interface_onu: str, interface: str = None) -> str:
        cmd = f"show gpon remote-onu ip-host {interface_onu}"
        try:
            raw_output = await self.execute_command(cmd)
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
                await self.execute_command(cmd)
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
                await self.execute_command(cmd)
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
                await self.execute_command(cmd)
            return "Reconfig Success"
        except Exception as e:
            logging.error(f"Regist SN failed for {interface_onu}: {e}")
            return f"Regist SN Failed: {e}"