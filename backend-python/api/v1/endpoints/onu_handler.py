from fastapi import APIRouter, HTTPException
import asyncio
from core.config import settings
from schemas.onu_handler import (
    OnuDetailRequest, OnuDetailResponse
)

from services.telnet import TelnetClient
from core.olt_config import OLT_OPTIONS

router = APIRouter()

@router.get("/{olt_name}/onu/cek", response_model=OnuDetailResponse)
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
            data = await handler.get_onu_detail(request.interface),
        
        return OnuDetailResponse(result=data)
    
    except (ConnectionError, asyncio.TimeoutError) as e:
        raise HTTPException(status_code=504, detail=f"Gagal terhubung atau timeout saat koneksi ke OLT: {e}")
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Proses cek gagal: {e}")
    