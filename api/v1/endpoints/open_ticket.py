from . import (
    APIRouter, 
    HTTPException, 
    logging, 
    OpenTicketRequest, 
    TicketClosePayload, 
    ForwardTicketPayload, 
    ProcessTicketRequest,
    asyncio,
    create_ticket_as_cs,
    process_ticket_as_noc,
    close_ticket_as_noc,
    forward_ticket_as_noc,
    extract_search_results,
    build_driver,
    maybe_login,
    search_user,
    settings
)
from sqlalchemy.orm import Session
from fastapi import Depends
from services.database import get_db
from services import db_data_fiber as crud

log = logging.getLogger(__name__)
router = APIRouter()

async def run_creation_async(cs_user, cs_pass, query, desc, prio, jenis, headless):
    return await asyncio.to_thread(create_ticket_as_cs, cs_username=cs_user, cs_password=cs_pass, query=query, description=desc, priority=prio, jenis=jenis, headless=headless)

async def run_processing_async(noc_user, noc_pass, query, headless):
    return await asyncio.to_thread(process_ticket_as_noc, noc_username=noc_user, noc_password=noc_pass, query=query, headless=headless)

async def run_ticket_close_async(noc_username, noc_password, query, onu_sn, action_close_notes, headless):
    return await asyncio.to_thread(
        close_ticket_as_noc,
        noc_username=noc_username,
        noc_password=noc_password,
        query=query,
        onu_sn=onu_sn,
        action_close_notes=action_close_notes,
        headless=headless
    )
async def run_ticket_forward_async(noc_username, noc_password, ticket_page_url, query, service_impact, root_cause, network_impact, onu_index, sn_modem, priority, person_in_charge, recomended_action, headless):
    return await asyncio.to_thread(forward_ticket_as_noc, noc_username=noc_username, noc_password=noc_password, ticket_page_url=ticket_page_url, query=query, service_impact=service_impact, root_cause=root_cause, network_impact=network_impact, onu_index=onu_index, sn_modem=sn_modem, priority=priority, person_in_charge=person_in_charge, recomended_action=recomended_action, headless=headless)


@router.get("/search", response_model=dict)
async def search_ticket(query: str):
    def _search():
        driver = build_driver(headless=True)
        try:
            maybe_login(driver, settings.BILLING_MODULE_BASE, settings.NMS_USERNAME_BILING, settings.NMS_PASSWORD_BILING)
            search_user(driver, query)
            return extract_search_results(driver)
        finally:
            driver.quit()
    results = await asyncio.to_thread(_search)
    return {"query": query, "results": results}

@router.post("/", response_model=dict)
async def open_and_process_ticket(req: OpenTicketRequest):
    headless_mode = req.headless if req.headless is not None else True
    creation_msg = await run_creation_async(
        cs_user=settings.NMS_USERNAME_BILING,
        cs_pass=settings.NMS_PASSWORD_BILING,
        query=req.query,
        desc=req.description,
        prio=req.priority,
        jenis=req.jenis,
        headless=headless_mode,
    )

    if not creation_msg.startswith("OK:"):
        raise HTTPException(status_code=400, detail=f"Step 1 (Creation) Failed: {creation_msg}")

    if not req.process_immediately:
        return {"success": True, "message": creation_msg, "detail": "NOC processing was not requested."}

    if not req.noc_username or not req.noc_password:
        raise HTTPException(status_code=400, detail="NOC credentials are required for immediate processing.")

    processing_msg = await run_processing_async(
        noc_user=req.noc_username,
        noc_pass=req.noc_password,
        query=req.query,
        headless=headless_mode,
    )

    if not processing_msg.startswith("OK:"):
        raise HTTPException(status_code=400, detail=f"Step 2 (Processing) Failed: {processing_msg}. Note: Ticket was created but not processed.")

    return {
        "success": True,
        "message": "Ticket created and processed successfully.",
        "creation_result": creation_msg,
        "processing_result": processing_msg,
    }

@router.post("/proses-ticket/", response_model=dict)
async def process_ticket(req: ProcessTicketRequest):
    headless_mode = req.headless if req.headless is not None else True

    if not req.noc_username or not req.noc_password:
        raise HTTPException(status_code=400, detail="NOC credentials are required for processing.")

    processing_msg = await run_processing_async(
        noc_user=req.noc_username,
        noc_pass=req.noc_password,
        query=req.query,
        headless=headless_mode,
    )

    if not processing_msg.startswith("OK:"):
        raise HTTPException(status_code=400, detail=f"Processing Failed: {processing_msg}")

    return {
        "success": True,
        "message": f"Ticket processed for {req.query} successfully.",
        "processing_result": processing_msg,
    }

@router.post("/close-ticket/")
async def close_ticket(req: TicketClosePayload, db: Session = Depends(get_db)):
    customers = crud.search_customers(db, req.query)
    if not customers:
        raise HTTPException(status_code=404, detail=f"Customer '{req.query}' not found in the database")

    customer_data = customers[0]
    onu_sn = customer_data.onu_sn
    if not onu_sn:
        raise HTTPException(status_code=404, detail=f"onu_sn data for '{req.query}' not found in the database")
    try:
        closed_ticket_msg = await run_ticket_close_async(
            noc_username=req.noc_username,
            noc_password=req.noc_password,
            query=req.query,
            onu_sn=onu_sn,
            action_close_notes=req.close_reason,
            headless=False,
        )
        
        if not closed_ticket_msg.startswith("OK:"):
            raise HTTPException(status_code=400, detail=f"Step 3 (Closing) Failed: {closed_ticket_msg}.")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred during ticket closing: {e}")

    return {"success": True, "message": "Ticket closed successfully.", "closing_result": closed_ticket_msg}

@router.post("/forward-ticket/")
async def forward_ticket_endpoint(payload: ForwardTicketPayload, db: Session = Depends(get_db)):
    customers = crud.search_customers(db, payload.query)
    if not customers:
        raise HTTPException(status_code=404, detail=f"Customer with PPPoE '{payload.query}' not found")

    customer_data = customers[0]
    interface = customer_data.interface
    sn_modem = customer_data.onu_sn

    if not interface or not sn_modem:
        raise HTTPException(status_code=400, detail="Database record for customer is incomplete (missing interface or onu_sn).")

    onu_index = f"gpon-onu_{interface}"

    result = await run_ticket_forward_async(
        noc_username=payload.noc_username,
        noc_password=payload.noc_password,
        ticket_page_url=settings.TICKET_NOC_URL,
        query=payload.query,
        service_impact=payload.service_impact,
        root_cause=payload.root_cause,
        network_impact=payload.network_impact,
        onu_index=onu_index,
        sn_modem=sn_modem,
        priority="HIGH",
        person_in_charge="ALL TECHNICIANS",
        recomended_action=payload.recomended_action,
        headless=True
    )
    if "Failed" in result:
        raise HTTPException(status_code=500, detail=result)
    return {"message": result}