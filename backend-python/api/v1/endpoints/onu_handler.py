from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import PlainTextResponse
import re
import asyncio
from core.config import settings
from schemas.onu_handler import (
    OnuDetailRequest, OnuDetailResponse, OnuFullResponse
)

from services.telnet import TelnetClient
from services.connection_manager import olt_manager
from core.olt_config import OLT_OPTIONS

router = APIRouter()

def _parse_interface(interface: str) -> str:
    """
    Parsing interface from example 1/1/1:1 to 1/1/1
    """
    pattern = r".*(\d+/\d+/\d+):(\d+)"
    match = re.search(pattern, interface)
    if not match:
         raise ValueError(f"Invalid interface format: {interface}")
    return interface.split(":")[0]
    

# ✅ FIX 1: Add 'olt_name: str' to arguments
@router.post("/{olt_name}/onu/cek", response_model=OnuFullResponse)
async def cek_onu(olt_name: str, request: OnuDetailRequest):
    target_olt = olt_name.upper() # Use the path param, not request.olt_name
    olt_info = OLT_OPTIONS.get(target_olt)
    if not olt_info:
        raise HTTPException(status_code=404, detail=f"OLT {olt_name} tidak ditemukan!")
    
    try:
        handler = await olt_manager.get_connection(
            host=olt_info["ip"],
            username=settings.OLT_USERNAME,
            password=settings.OLT_PASSWORD,
            is_c600=olt_info["c600"]
        )
            
        detail_data = await handler.get_onu_detail(request.interface)
        attenuation = await handler.get_attenuation(request.interface)
        
        return OnuFullResponse(
            detail_data=detail_data,
            attenuation_data=attenuation)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Proses cek gagal: {e}")
    

# ✅ FIX 2: Add 'olt_name: str' here too. 
# Also, for GET requests, it is better to use 'Depends' for the model or individual query params.
@router.get("/{olt_name}/onu/reboot")
async def reboot_onu(olt_name: str, request: OnuDetailRequest = Depends()):
    target_olt = olt_name.upper()
    olt_info = OLT_OPTIONS.get(target_olt)
    if not olt_info:
        raise HTTPException(
            status_code=404, 
            detail=f"OLT {olt_name} tidak ditemukan!")
    
    try:
        async with TelnetClient(
            host = olt_info["ip"],  
            username=settings.OLT_USERNAME,
            password=settings.OLT_PASSWORD,
            is_c600=olt_info["c600"],
        ) as handler:
            data = await handler.send_reboot_command(request.interface)
        
        return OnuDetailResponse(result=data)
    
    except (ConnectionError, asyncio.TimeoutError) as e:
        raise HTTPException(status_code=504, detail=f"Gagal terhubung atau timeout: {e}")
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Proses cek gagal: {e}")
    

# ✅ FIX 3: Add 'olt_name: str' here
@router.get("/{olt_name}/onu/no-onu", response_model=OnuDetailResponse)
async def no_onu(olt_name: str, request: OnuDetailRequest = Depends()):
    target_olt = olt_name.upper()
    olt_info = OLT_OPTIONS.get(target_olt)
    if not olt_info:
        raise HTTPException(
            status_code=404, 
            detail=f"OLT {olt_name} tidak ditemukan!")
    
    try:
        async with TelnetClient(
            host = olt_info["ip"],  
            username=settings.OLT_USERNAME,
            password=settings.OLT_PASSWORD,
            is_c600=olt_info["c600"],
        ) as handler:
            data = await handler.send_no_onu(request.interface)
        
        return OnuDetailResponse(result=data)
    
    except (ConnectionError, asyncio.TimeoutError) as e:
        raise HTTPException(status_code=504, detail=f"Gagal terhubung atau timeout: {e}")
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Proses cek gagal: {e}")
    

# ✅ FIX 4: Add 'olt_name: str' here (POST request)
@router.post("/{olt_name}/onu/port_state", response_class=PlainTextResponse)
async def cek_1_port(olt_name: str, request: OnuDetailRequest):
    target_olt = olt_name.upper()
    olt_info = OLT_OPTIONS.get(target_olt)
    
    try:
        handler = await olt_manager.get_connection(
            host=olt_info["ip"],
            username=settings.OLT_USERNAME,
            password=settings.OLT_PASSWORD,
            is_c600=olt_info["c600"]
        )
        
        base_interface = _parse_interface(request.interface)
        data = await handler.get_gpon_onu_state(base_interface)

        return PlainTextResponse(content=data)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

# ✅ FIX 5: Add 'olt_name: str' here (POST request)
@router.post("/{olt_name}/onu/port_rx", response_class=PlainTextResponse)
async def cek_1_port_rx(olt_name: str, request: OnuDetailRequest):
    target_olt = olt_name.upper()
    olt_info = OLT_OPTIONS.get(target_olt)
    
    try:
        handler = await olt_manager.get_connection(
            host=olt_info["ip"],
            username=settings.OLT_USERNAME,
            password=settings.OLT_PASSWORD,
            is_c600=olt_info["c600"]
        )
        
        base_interface = _parse_interface(request.interface)
        data = await handler.get_onu_rx(base_interface)

        return PlainTextResponse(content=data)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))