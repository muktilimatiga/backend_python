#schemas/config.py

from pydantic import BaseModel
from typing import List, Optional

class UnconfiguredOnt(BaseModel):
    sn: str
    pon_port: str
    pon_slot: str

class CustomerInfo(BaseModel):
    name: str
    address: str
    pppoe_user: str
    pppoe_pass: str

class ConfigurationRequest(BaseModel):
    sn: str
    customer: CustomerInfo
    modem_type: str
    package: str
    eth_locks: List[bool]

class ConfigurationSummary(BaseModel):
    serial_number: str
    pppoe_user: str
    location: str
    profile: str

class ConfigurationResponse(BaseModel):
    message: str
    summary: Optional[ConfigurationSummary] = None
    logs: List[str]

class OptionsResponse(BaseModel):
    olt_options: List[str]
    modem_options: List[str]
    package_options: List[str]

# --- SCHEMA BARU UNTUK ONU DETAIL ---

class OnuLogEntry(BaseModel):
    """Mewakili satu baris log Authpass/Offline time dari ONU."""
    id: int
    auth_time: str
    offline_time: str
    cause: str

class OnuDetail(BaseModel):
    """
    Menggabungkan field yang diekstrak dari 'sh gpon onu detail-info'
    dan dua log modem terakhir.
    """
    # Field utama dari parsing
    onu_interface: Optional[str] = None
    type: Optional[str] = None
    phase_state: Optional[str] = None
    serial_number: Optional[str] = None
    onu_distance: Optional[str] = None
    online_duration: Optional[str] = None
    
    # Log modem terakhir
    modem_logs: List[OnuLogEntry] = []
