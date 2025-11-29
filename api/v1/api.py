from fastapi import APIRouter, Depends
from api.v1.endpoints import (
    cli, customer_scrapper, open_ticket, config_handler,
    users,onu_handler,
    auth
)
from api.v1.deps import get_current_user, get_current_user_optional

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])

api_router.include_router(
    users.router,
    prefix="/users",
    tags=["NOC"]
)

api_router.include_router(
    cli.router,
    prefix="/cli",
    tags=["cli"],
    dependencies=[Depends(get_current_user_optional)]
)

# Handle Invoices
api_router.include_router(
    customer_scrapper.router,
    prefix="/customer",
    tags=["Customer"],
    dependencies=[Depends(get_current_user_optional)]
)

# Handle Open Ticket
api_router.include_router(
    open_ticket.router,
    prefix="/ticket",
    tags=["Ticket"],
    dependencies=[Depends(get_current_user_optional)]
)

#Handle Config
api_router.include_router(
    config_handler.router,
    prefix="/config",
    tags=["Config"],
    dependencies=[Depends(get_current_user_optional)]
)

#Handle ONU 
api_router.include_router(
    onu_handler.router,
    prefix="/onu",
    tags=["ONU"],
    dependencies=[Depends(get_current_user_optional)]
)