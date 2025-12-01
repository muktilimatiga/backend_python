from typing import List, Dict
from pydantic import BaseModel

# --- 1. Session Manager ---

class SessionListResponse(BaseModel):
    count: int
    sessions: List[Dict[str, int]]

class KillResponse(BaseModel):
    pid: int
    message: str

# [NEW] Payload for sending commands
class CommandPayload(BaseModel):
    command: str