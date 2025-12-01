import os
import pty
import select
import struct
import fcntl
import termios
import asyncio
import logging
import signal
from typing import Dict, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from starlette.websockets import WebSocketState

router = APIRouter()
logger = logging.getLogger("lexxa.cli")

# --- 1. Session Manager ---
class TerminalSession:
    def __init__(self, pid: int, master_fd: int):
        self.pid = pid
        self.master_fd = master_fd
        self.websocket: WebSocket = None

class SessionManager:
    def __init__(self):
        self.active_sessions: Dict[int, TerminalSession] = {}

    def register(self, pid: int, master_fd: int, websocket: WebSocket):
        session = TerminalSession(pid, master_fd)
        session.websocket = websocket
        self.active_sessions[pid] = session
        logger.info(f"Terminal session registered: PID {pid}")

    def unregister(self, pid: int):
        if pid in self.active_sessions:
            del self.active_sessions[pid]
            logger.info(f"Terminal session unregistered: PID {pid}")

    async def kill_session(self, pid: int):
        if pid in self.active_sessions:
            session = self.active_sessions[pid]
            try:
                if session.websocket.client_state == WebSocketState.CONNECTED:
                    await session.websocket.close()
            except Exception as e:
                logger.warning(f"Error closing socket for PID {pid}: {e}")
            
            try:
                os.kill(pid, signal.SIGTERM)
                try:
                    os.close(session.master_fd)
                except OSError:
                    pass
            except Exception as e:
                logger.warning(f"Error killing process PID {pid}: {e}")
            
            self.unregister(pid)
            return True
        return False

    def list_sessions(self):
        return [
            {"pid": pid, "status": "active"} 
            for pid in self.active_sessions.keys()
        ]

manager = SessionManager()

# --- 2. API Schemas ---
class SessionListResponse(BaseModel):
    count: int
    sessions: List[Dict[str, int]]

class KillResponse(BaseModel):
    pid: int
    message: str

# --- 3. HTTP Management Endpoints ---

@router.get("/sessions", response_model=SessionListResponse)
async def list_active_terminals():
    sessions = manager.list_sessions()
    return {
        "count": len(sessions),
        "sessions": sessions
    }

@router.delete("/sessions/{pid}", response_model=KillResponse)
async def kill_terminal(pid: int):
    success = await manager.kill_session(pid)
    if not success:
        raise HTTPException(status_code=404, detail=f"Session with PID {pid} not found")
    return {"pid": pid, "message": "Terminated successfully"}

# --- 4. WebSocket Endpoint ---

@router.websocket("/ws")
async def terminal_websocket(websocket: WebSocket):
    await websocket.accept()
    
    master_fd, slave_fd = pty.openpty()
    pid = os.fork()

    if pid == 0:
        # --- CHILD (Shell) ---
        os.setsid()
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        if master_fd > 2:
            os.close(master_fd)
        if slave_fd > 2:
            os.close(slave_fd)
        
        # Use a compatible terminal type
        os.environ["TERM"] = "xterm"
        # Run bash (or sh/zsh depending on availability)
        shell = os.environ.get("SHELL", "/bin/bash")
        os.execvp(shell, [shell])
    
    else:
        # --- PARENT (FastAPI) ---
        os.close(slave_fd)
        manager.register(pid, master_fd, websocket)

        try:
            loop = asyncio.get_running_loop()

            async def read_from_pty():
                """Reads output from the shell and sends it to the websocket."""
                while True:
                    await asyncio.sleep(0.01)
                    if pid not in manager.active_sessions:
                        break
                    try:
                        r, _, _ = select.select([master_fd], [], [], 0)
                        if master_fd in r:
                            data = os.read(master_fd, 10240)
                            if not data:
                                break
                            await websocket.send_text(data.decode("utf-8", "ignore"))
                    except OSError:
                        break

            async def write_to_pty():
                """Reads input from the websocket and writes it to the shell."""
                while True:
                    data = await websocket.receive_text()
                    
                    if pid not in manager.active_sessions:
                        break

                    # 1. Handle Window Resize (JSON)
                    if data.strip().startswith("{") and '"cols":' in data:
                        try:
                            import json
                            resize = json.loads(data)
                            winsize = struct.pack("HHHH", resize.get("rows", 24), resize.get("cols", 80), 0, 0)
                            fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
                            continue
                        except:
                            pass
                    
                    # 2. Handle Newlines
                    # Ensure standard "Enter" key (\r) is sent
                    if "\n" in data:
                        data = data.replace("\n", "\r")

                    # 3. [FIX] Smart Enter:
                    # If user sends a command string (len > 1) without an Enter key, add it automatically.
                    # This fixes the "nothing happened" issue with raw test tools.
                    if len(data) > 1 and "\r" not in data:
                        data += "\r"

                    os.write(master_fd, data.encode())

            await asyncio.gather(read_from_pty(), write_to_pty())

        except (WebSocketDisconnect, OSError):
            logger.info(f"WebSocket disconnected for PID {pid}")
        except Exception as e:
            logger.error(f"Error in terminal session PID {pid}: {e}")
        finally:
            await manager.kill_session(pid)