from fastapi import APIRouter, HTTPException
from typing import List
import asyncio

from core.config import settings
from schemas.config_handler import (
    UnconfiguredOnt, ConfigurationRequest, ConfigurationResponse, 
    ConfigurationSummary, OptionsResponse, BatchConfigurationRequest, BatchConfigResult
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
    
# Config Batch
@router.post("/api/olts/{olt_name}/configure-batch", response_model=BatchConfigResult)
async def run_configuration_batch(olt_name: str, payload: BatchConfigurationRequest):
# 1. Validate OLT
    olt_info = OLT_OPTIONS.get(olt_name.upper())
    if not olt_info:
        raise HTTPException(status_code=404, detail=f"OLT '{olt_name}' not found.")
        
    # 2. Define the Batch Task
    async def batch_task(handler):
        results = {
            "success": [],
            "failed": []
        }
        
        # [FIX] Get VLAN from config
        vlan = olt_info["vlan"]
        total = len(payload.configs)
        
        for index, config_item in enumerate(payload.configs):
            try:
                # Log progress
                print(f"Processing {index + 1}/{total}: SN {config_item.sn}")
                
                # [FIX] Pass the required 'vlan' argument
                logs, summary = await handler.apply_configuration(config_item, vlan=vlan)
                
                results["success"].append(summary)
                
                # Optional: slight delay between configs to let OLT process
                await asyncio.sleep(0.5)
                
            except Exception as e:
                # If one fails, catch it, log it, and continue to the next one
                error_msg = str(e)
                results["failed"].append({
                    "sn": config_item.sn,
                    "customer": config_item.customer.name,
                    "error": error_msg
                })
                
        return results

    # 3. Execute with Lock
    # This ensures no one else interrupts the OLT while this batch is running.
    try:
        return await olt_manager.execute_action(olt_info, batch_task)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch execution failed: {e}")