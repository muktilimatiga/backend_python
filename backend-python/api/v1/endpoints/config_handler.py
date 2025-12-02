from fastapi import APIRouter, HTTPException
from typing import List
import asyncio

from core.config import settings
from schemas.config_handler import (
    UnconfiguredOnt, ConfigurationRequest, ConfigurationResponse, 
    ConfigurationSummary, OptionsResponse
)
from services.telnet_handler import olt_manager 
from core.olt_config import OLT_OPTIONS, MODEM_OPTIONS, PACKAGE_OPTIONS

router = APIRouter()

@router.get("/api/options", response_model=OptionsResponse)
async def get_options():
    return {
        "olt_options": list(OLT_OPTIONS.keys()),
        "modem_options": MODEM_OPTIONS,
        "package_options": list(PACKAGE_OPTIONS.keys())
    }

@router.get("/api/olts/{olt_name}/detect-onts", response_model=List[UnconfiguredOnt])
async def detect_uncfg_onts(olt_name: str):
    olt_info = OLT_OPTIONS.get(olt_name.upper())
    if not olt_info:
        raise HTTPException(status_code=404, detail=f"OLT '{olt_name}' not found.")
    
    async def task(handler):
        return await handler.find_unconfigured_onts()

    try:
        return await olt_manager.execute_action(olt_info, task)
    except ConnectionError as e:
        raise HTTPException(status_code=504, detail=f"Gagal terhubung ke OLT: {e}")
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=f"Terjadi error internal: {e}")

@router.post("/api/olts/{olt_name}/configure", response_model=ConfigurationResponse)
async def run_configuration(olt_name: str, request: ConfigurationRequest):
    olt_info = OLT_OPTIONS.get(olt_name.upper())
    if not olt_info:
        raise HTTPException(status_code=404, detail=f"OLT '{olt_name}' not found.")
        
    async def task(handler):
        logs, summary = await handler.apply_configuration(request, vlan=olt_info["vlan"])
        logs.append("INFO < Database save functionality not yet implemented.")
        return logs, summary

    try:
        logs, summary = await olt_manager.execute_action(olt_info, task)
        return ConfigurationResponse(
            message="Konfigurasi berhasil.",
            summary=ConfigurationSummary(**summary),
            logs=logs
        )
    except (ConnectionError, asyncio.TimeoutError) as e:
        raise HTTPException(status_code=504, detail=f"Gagal terhubung atau timeout saat koneksi ke OLT: {e}")
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=f"Proses konfigurasi gagal: {e}")