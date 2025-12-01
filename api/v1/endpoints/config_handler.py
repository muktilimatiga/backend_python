#/api/v1/endpoints/config

from fastapi import APIRouter, HTTPException
from typing import List
import asyncio

from core.config import settings
from schemas.config_handler import (
    UnconfiguredOnt, ConfigurationRequest, ConfigurationResponse, 
    ConfigurationSummary, OptionsResponse, OnuDetail
)
from services.config_handler import OltHandler
from services.telnet_handler import olt_manager
from core.olt_config import OLT_OPTIONS, MODEM_OPTIONS, PACKAGE_OPTIONS

router = APIRouter()

# Endpoint for showling LIST of OLT
@router.get("/api/options", response_model=OptionsResponse)
async def get_options():
    """Mengembalikan semua opsi yang dibutuhkan untuk form di frontend."""
    return {
        "olt_options": list(OLT_OPTIONS.keys()),
        "modem_options": MODEM_OPTIONS,
        "package_options": list(PACKAGE_OPTIONS.keys())
    }

# Endpoint show uncfg config
@router.get("/api/olts/{olt_name}/detect-onts", response_model=List[UnconfiguredOnt])
async def detect_uncfg_onts(olt_name: str):
    """Mendeteksi semua unconfigured ONT pada OLT yang dipilih."""
    olt_info = OLT_OPTIONS.get(olt_name.upper())
    if not olt_info:
        raise HTTPException(status_code=404, detail=f"OLT '{olt_name}' tidak ditemukan.")
    
    try:
        async with OltHandler(
            host=olt_info["ip"],
            username=settings.OLT_USERNAME,
            password=settings.OLT_PASSWORD,
            is_c600=olt_info["c600"]
        ) as handler:
            ont_list = await handler.find_unconfigured_onts()
            return ont_list
    except ConnectionError as e:
        raise HTTPException(status_code=504, detail=f"Gagal terhubung ke OLT: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Terjadi error internal: {e}")

# Endpoint handle config
@router.post("/api/olts/{olt_name}/configure", response_model=ConfigurationResponse)
async def run_configuration(olt_name: str, request: ConfigurationRequest):
    """Menjalankan proses konfigurasi untuk satu ONT."""
    olt_info = OLT_OPTIONS.get(olt_name.upper())
    if not olt_info:
        raise HTTPException(status_code=404, detail=f"OLT '{olt_name}' tidak ditemukan.")
        
    try:
        async with OltHandler(
            host=olt_info["ip"],
            username=settings.OLT_USERNAME,
            password=settings.OLT_PASSWORD,
            is_c600=olt_info["c600"]
        ) as handler:
            logs, summary = await handler.apply_configuration(request, vlan=olt_info["vlan"])
            logs.append("INFO < Database save functionality not yet implemented.")
            
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
        raise HTTPException(status_code=500, detail=f"Proses konfigurasi gagal: {e}")
    