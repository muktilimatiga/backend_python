from fastapi import APIRouter, HTTPException
import re
import asyncio
from core.config import settings
from schemas.onu_handler import (
    OnuDetailRequest, OnuDetailResponse, OnuFullResponse
)

from services.telnet import TelnetClient
from core.olt_config import OLT_OPTIONS

router = APIRouter()

def _parse_interface(interface: str) -> str:
    """
    Parsing interface from example 1/1/1:1 to 1/1/1
    """
    # Pattern looks for: numbers / numbers / numbers : numbers
    pattern = r".*(\d+/\d+/\d+):(\d+)"
    
    match = re.search(pattern, interface)
    if not match:
         raise ValueError(f"Invalid interface format: {interface}")
    
    # Return the port part (Group 1)
    return interface.split(":")[0]
    

@router.get("/{olt_name}/onu/cek", response_model=OnuFullResponse)
async def cek_onu(request: OnuDetailRequest ):
    target_olt = request.olt_name.upper()
    olt_info = OLT_OPTIONS.get(target_olt)
    if not olt_info:
        raise HTTPException(
            status_code=404, 
            detail=f"OLT {request.olt_name} tidak ditemukan!")
    
    try:
        async with TelnetClient(
            host = olt_info["ip"],  
            username=settings.OLT_USERNAME,
            password=settings.OLT_PASSWORD,
            is_c600=olt_info["c600"],
            interface=request.interface,
        ) as handler:
            detail_data = await handler.get_onu_detail(request.interface),
            attenuation_data = await handler.get_attenuation(request.interface)
        
        return OnuFullResponse(
            detail_data=detail_data,
            attenuation_data=attenuation_data
            )
    
    except (ConnectionError, asyncio.TimeoutError) as e:
        raise HTTPException(status_code=504, detail=f"Gagal terhubung atau timeout saat koneksi ke OLT: {e}")
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Proses cek gagal: {e}")
    
@router.get("/{olt_name}/onu/reboot")
async def reboot_onu(request: OnuDetailRequest):
    target_olt = request.olt_name.upper()
    olt_info = OLT_OPTIONS.get(target_olt)
    if not olt_info:
        raise HTTPException(
            status_code=404, 
            detail=f"OLT {request.olt_name} tidak ditemukan!")
    
    try:
        async with TelnetClient(
            host = olt_info["ip"],  
            username=settings.OLT_USERNAME,
            password=settings.OLT_PASSWORD,
            is_c600=olt_info["c600"],
        ) as handler:
            data = await handler.send_reboot_command(request.interface),
        
        return OnuDetailResponse(result=data)
    
    except (ConnectionError, asyncio.TimeoutError) as e:
        raise HTTPException(status_code=504, detail=f"Gagal terhubung atau timeout saat koneksi ke OLT: {e}")
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Proses cek gagal: {e}")
    
@router.get("/{olt_name}/onu/no-onu")
async def no_onu(request: OnuDetailRequest):
    target_olt = request.olt_name.upper()
    olt_info = OLT_OPTIONS.get(target_olt)
    if not olt_info:
        raise HTTPException(
            status_code=404, 
            detail=f"OLT {request.olt_name} tidak ditemukan!")
    
    try:
        async with TelnetClient(
            host = olt_info["ip"],  
            username=settings.OLT_USERNAME,
            password=settings.OLT_PASSWORD,
            is_c600=olt_info["c600"],
        ) as handler:
            data = await handler.send_no_onu(request.interface),
        
        return OnuDetailResponse(result=data)
    
    except (ConnectionError, asyncio.TimeoutError) as e:
        raise HTTPException(status_code=504, detail=f"Gagal terhubung atau timeout saat koneksi ke OLT: {e}")
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Proses cek gagal: {e}")
    

@router.get("/{olt_name}/onu/port_state")
async def cek_1_port(request: OnuDetailRequest):
    target_olt = request.olt_name.upper()
    olt_info = OLT_OPTIONS.get(target_olt)
    if not olt_info:
        raise HTTPException(
            status_code=400,
            detail= f"{request.olt_name} tidak ditemukan!"
        )
    
    try:
        async with TelnetClient(
            host = olt_info["ip"],
            username=settings.OLT_USERNAME,
            password=settings.OLT_PASSWORD,
            is_c600=olt_info["c600"],
        ) as handler:
            base_interface = await _parse_interface(request.interface)

            data = await handler.get_gpon_onu_state(base_interface)

        return OnuDetailResponse(result=data)
    
    except (ConnectionError, asyncio.TimeoutError) as e:
        raise HTTPException(status_code=504, detail=f"Gagal terhubung atau timeout saat koneksi ke OLT: {e}")
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Proses cek gagal: {e}")