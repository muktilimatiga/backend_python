# routers/onu_router.py

from fastapi import APIRouter, HTTPException
from schemas import onu_handler as schemas
from services.telnet_handler import olt_manager # <--- The Singleton we made
from core.olt_config import OLT_OPTIONS
from core.config import settings

router = APIRouter()

# --- Helper Function (DRY: Don't Repeat Yourself) ---
def get_olt_config_or_404(olt_name: str):
    info = OLT_OPTIONS.get(olt_name.upper())
    if not info:
        raise HTTPException(
            status_code=404, 
            detail=f"OLT '{olt_name}' configuration not found."
        )
    return info

@router.post("/detail-search", response_model=schemas.CustomerOnuDetail)
async def get_customer_details(payload: schemas.OnuTargetPayload):
    # 1. Get Config
    olt_info = get_olt_config_or_404(payload.olt_name)

    # 2. Define the Work (The "Business Logic")
    async def task(handler):
        # Calculate prefix once
        prefix = "gpon_onu-" if olt_info["c600"] else "gpon-onu_"
        full_interface = f"{prefix}{payload.interface}"

        # Execute multiple commands in parallel or sequence
        olt_data = await handler.get_onu_detail(full_interface)
        redaman = await handler.get_attenuation(full_interface, payload.interface)
        ip = await handler.get_onu_ip_host(full_interface, payload.interface)
        ports = await handler.get_eth_port_statuses(payload.interface)

        # Combine results
        return {
            **olt_data,
            "redaman": redaman,
            "ip_remote": ip,
            "eth_port": ports
        }

    # 3. Hand it to the Manager
    return await olt_manager.execute_action(olt_info, task)


@router.post("/onu-state", response_model=schemas.OnuStateRespons)
async def get_state(payload: schemas.PortTargetPayload):
    olt_info = get_olt_config_or_404(payload.olt_name)

    async def task(handler):
        prefix = "gpon_olt-" if olt_info["c600"] else "gpon-olt_"
        full_interface = f"{prefix}{payload.olt_port}"
        
        data = await handler.get_gpon_onu_state(payload.olt_port, full_interface)
        return {"onu_state_data": data}

    return await olt_manager.execute_action(olt_info, task)


@router.post("/onu-rx", response_model=schemas.OnuRxRespons)
async def get_rx(payload: schemas.PortTargetPayload):
    olt_info = get_olt_config_or_404(payload.olt_name)

    async def task(handler):
        prefix = "gpon_olt-" if olt_info["c600"] else "gpon-olt_"
        full_interface = f"{prefix}{payload.olt_port}"
        
        data = await handler.get_onu_rx(payload.olt_port, full_interface)
        return {"onu_rx_data": data}

    return await olt_manager.execute_action(olt_info, task)


@router.post("/reboot-onu", response_model=schemas.RebootResponse)
async def reboot_onu(payload: schemas.OnuTargetPayload):
    olt_info = get_olt_config_or_404(payload.olt_name)

    async def task(handler):
        prefix = "gpon_onu-" if olt_info["c600"] else "gpon-onu_"
        full_interface = f"{prefix}{payload.interface}"
        
        status = await handler.send_reboot_command(payload.interface, full_interface)
        
        if "failed" in status.lower():
            raise HTTPException(status_code=500, detail=status)
        return {"status": status}

    return await olt_manager.execute_action(olt_info, task)


@router.post("/no-onu", response_model=schemas.NoOnuResponse)
async def remove_onu(payload: schemas.NoOnuPayload):
    olt_info = get_olt_config_or_404(payload.olt_name)

    async def task(handler):
        prefix = "gpon_olt-" if olt_info["c600"] else "gpon-olt_"
        full_interface = f"{prefix}{payload.olt_port}"
        
        status = await handler.send_no_onu(payload.olt_port, full_interface, payload.onu_id)
        
        if "failed" in status.lower():
            raise HTTPException(status_code=500, detail=status)
        return {"status": status}

    return await olt_manager.execute_action(olt_info, task)


@router.post("/regist-sn", response_model=schemas.RegistSnResponse)
async def register_sn(payload: schemas.RegistSnPayload):
    olt_info = get_olt_config_or_404(payload.olt_name)

    async def task(handler):
        prefix = "gpon_onu-" if olt_info["c600"] else "gpon-onu_"
        full_interface = f"{prefix}{payload.interface}"
        
        status = await handler.send_new_sn(payload.interface, full_interface, payload.sn)
        
        if "failed" in status.lower():
            raise HTTPException(status_code=500, detail=status)
        return {"status": status}

    return await olt_manager.execute_action(olt_info, task)