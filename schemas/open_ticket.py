from . import BaseModel, Optional, Field


class OpenTicketRequest(BaseModel):
    query: str
    description: str
    priority: Optional[str] = "LOW"
    jenis: Optional[str] = "FREE"
    headless: Optional[bool] = True
    noc_username: Optional[str] = None
    noc_password: Optional[str] = None

    process_immediately: bool = Field(default=True, description="Proses ticket by NOC")

class OpenTicketResponse(BaseModel):
    success: bool
    message: str

class ProcessTicketRequest(BaseModel):
    query: str
    noc_username: Optional[str] = None
    noc_password: Optional[str] = None
    headless: Optional[bool] = True

class TicketClosePayload(BaseModel):
    close_reason: str
    headless_mode: Optional[bool] = True
    noc_user: str
    noc_pass: str
    query: str
    action_close_notes: Optional[str] = None


class ForwardTicketPayload(BaseModel):
    query: str
    service_impact: str
    root_cause: str
    network_impact: str
    recomended_action: str
    noc_username: str
    noc_password: str