import os
<<<<<<< HEAD
import sys
import asyncio
import logging
import json
import traceback
import platform
from typing import Dict, List, Optional
=======
import pty
import select
import struct
import fcntl
import termios
import asyncio
import logging
import signal
from typing import Dict, List
>>>>>>> 246021dae7ea5ebb524edb429f96d21864ad7c99
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from starlette.websockets import WebSocketState

<<<<<<< HEAD
# --- Platform Specific Imports ---
# We guard these so the code doesn't crash on Windows immediately
if os.name == 'posix':
    import pty
    import tty
    import termios
    import fcntl
    import struct
    import signal
    import select

router = APIRouter()
logger = logging.getLogger("cli")

# ===========================
# 1. SCHEMAS
# ===========================
class SessionListResponse(BaseModel):
    count: int
    sessions: List[Dict]

class KillResponse(BaseModel):
    pid: int
    message: str

class CommandPayload(BaseModel):
    command: str

# ===========================
# 2. SESSION MANAGER
# ===========================
class TerminalSession:
    def __init__(self, pid: int):
        self.pid = pid
        self.websocket: Optional[WebSocket] = None
        # Linux specific
        self.master_fd: Optional[int] = None 
        # Windows specific
        self.process: Optional[asyncio.subprocess.Process] = None 

class SessionManager:
    def __init__(self):
        self.active_sessions: Dict[int, TerminalSession] = {}

    def register_linux(self, pid: int, master_fd: int, websocket: WebSocket):
        session = TerminalSession(pid)
        session.master_fd = master_fd
        session.websocket = websocket
        self.active_sessions[pid] = session
        logger.info(f"Linux Terminal registered: PID {pid}")

    def register_windows(self, pid: int, process, websocket: WebSocket):
        session = TerminalSession(pid)
        session.process = process
        session.websocket = websocket
        self.active_sessions[pid] = session
        logger.info(f"Windows Terminal registered: PID {pid}")

    def unregister(self, pid: int):
        if pid in self.active_sessions:
            del self.active_sessions[pid]
            logger.info(f"Terminal unregistered: PID {pid}")

    async def write_to_terminal(self, pid: int, text: str):
        """Sends text to the running process (API Endpoint support)"""
        if pid not in self.active_sessions: return False
        session = self.active_sessions[pid]
        
        if os.name == 'posix':
            # LINUX
            try:
                os.write(session.master_fd, text.encode())
                return True
            except OSError:
                return False
        else:
            # WINDOWS
            try:
                if session.process and session.process.stdin:
                    # Windows usually needs explicit \r\n
                    if "\r" in text and "\n" not in text:
                        text = text.replace("\r", "\n")
                    
                    session.process.stdin.write(text.encode())
                    await session.process.stdin.drain()
                    return True
            except Exception as e:
                logger.error(f"Windows write error: {e}")
                return False
        return False
=======
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
>>>>>>> 246021dae7ea5ebb524edb429f96d21864ad7c99

    async def kill_session(self, pid: int):
        if pid not in self.active_sessions: return False
        session = self.active_sessions[pid]
        
        # Close WebSocket
        try:
<<<<<<< HEAD
            if session.websocket and session.websocket.client_state == WebSocketState.CONNECTED:
                await session.websocket.close()
        except: pass

        # Kill Process
        if os.name == 'posix':
            try:
                os.kill(pid, signal.SIGTERM)
                if session.master_fd: os.close(session.master_fd)
            except: pass
        else:
            try:
                if session.process: session.process.terminate()
            except: pass

        self.unregister(pid)
        return True

    def list_sessions(self):
        return [{"pid": pid, "platform": os.name} for pid in self.active_sessions.keys()]

manager = SessionManager()

# ===========================
# 3. HTTP ENDPOINTS
# ===========================
@router.get("/sessions", response_model=SessionListResponse)
async def list_active_terminals():
    sessions = manager.list_sessions()
    return {"count": len(sessions), "sessions": sessions}

@router.delete("/sessions/{pid}", response_model=KillResponse)
async def kill_terminal(pid: int):
    success = await manager.kill_session(pid)
    if not success: raise HTTPException(status_code=404, detail=f"Session {pid} not found")
    return {"pid": pid, "message": "Terminated successfully"}

@router.post("/sessions/{pid}/send_text")
async def send_text_to_terminal(pid: int, payload: CommandPayload):
    cmd = payload.command
    if not cmd.endswith("\r") and not cmd.endswith("\n"):
        cmd += "\n" if os.name == 'nt' else "\r"
    success = await manager.write_to_terminal(pid, cmd)
    if not success: raise HTTPException(status_code=404, detail="Session not found")
    return {"message": f"Sent command: {payload.command}"}

# ===========================
# 4. WEBSOCKET HANDLER
# ===========================
@router.websocket("/ws")
async def terminal_websocket(websocket: WebSocket):
    await websocket.accept()
    
    # Check OS and route to correct handler
    if os.name == 'posix':
        await handle_linux_terminal(websocket)
    else:
        await handle_windows_terminal(websocket)

# --- WINDOWS HANDLER ---
async def handle_windows_terminal(websocket: WebSocket):
    shell = "powershell.exe" # Or "cmd.exe"

    try:
        # DIAGNOSTIC: Log event loop information
        current_loop = asyncio.get_running_loop()
        logger.info(f"Current event loop type: {type(current_loop)}")
        logger.info(f"Event loop policy: {type(asyncio.get_event_loop_policy())}")
        
        # DIAGNOSTIC: Check if shell exists
        import shutil
        shell_path = shutil.which(shell)
        logger.info(f"Shell path resolved to: {shell_path}")
        if not shell_path:
            logger.error(f"Shell '{shell}' not found in PATH")
            # Try cmd.exe as fallback
            shell_path = shutil.which("cmd.exe")
            if shell_path:
                logger.info(f"Using fallback shell: cmd.exe at {shell_path}")
                shell = "cmd.exe"
            else:
                logger.error("Neither powershell.exe nor cmd.exe found in PATH")
                raise RuntimeError("No suitable shell found")
        
        # DIAGNOSTIC: Log environment
        logger.info(f"PATH environment: {os.environ.get('PATH', 'Not set')}")
        
        # FIX: Use the full path to the shell to avoid PATH issues
        shell_full_path = shutil.which(shell)
        if not shell_full_path:
            raise RuntimeError(f"Could not find full path for shell: {shell}")
            
        logger.info(f"Using shell at full path: {shell_full_path}")
        
        # FIX: Always use subprocess module directly for Windows
        # This bypasses asyncio event loop issues entirely
        logger.info("Using subprocess module directly for Windows")
        import subprocess
        
        # Create process using subprocess module
        proc = subprocess.Popen(
            [shell_full_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=False,  # We want bytes for consistency
            bufsize=0,  # Unbuffered
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )
        
        # Create a wrapper that mimics asyncio.subprocess.Process
        class AsyncioSubprocessWrapper:
            def __init__(self, subprocess_proc):
                self.proc = subprocess_proc
                self.pid = subprocess_proc.pid
                self.stdin = AsyncioStreamWrapper(subprocess_proc.stdin)
                self.stdout = AsyncioStreamWrapper(subprocess_proc.stdout)
                self.stderr = AsyncioStreamWrapper(subprocess_proc.stderr)
                
            async def wait(self):
                return await current_loop.run_in_executor(None, self.proc.wait)
                
            def terminate(self):
                self.proc.terminate()
                
            def kill(self):
                self.proc.kill()
                
            def poll(self):
                return self.proc.poll()
                
            @property
            def returncode(self):
                return self.proc.returncode
        
        class AsyncioStreamWrapper:
            def __init__(self, stream):
                self.stream = stream
                
            async def read(self, size=-1):
                return await current_loop.run_in_executor(None, self.stream.read, size)
                
            async def write(self, data):
                return await current_loop.run_in_executor(None, self.stream.write, data)
                
            async def drain(self):
                # subprocess streams don't have drain, but we'll include it for compatibility
                pass
                
            def at_eof(self):
                return self.stream.closed if hasattr(self.stream, 'closed') else False
        
        process = AsyncioSubprocessWrapper(proc)
        logger.info(f"Created subprocess with PID: {process.pid}")
        
        pid = process.pid
        manager.register_windows(pid, process, websocket)
        
        # Initial wakeup command to ensure shell is ready
        process.stdin.write(b"\r\n")
        await process.stdin.drain()

        async def read_stdout():
            try:
                while True:
                    if process.stdout.at_eof(): break
                    data = await process.stdout.read(1024)
                    if not data: break
                    
                    # Decoding magic for Windows
                    try:
                        text = data.decode('cp437') 
                    except:
                        text = data.decode('utf-8', 'ignore')
                    
                    # Debug Print
                    print(f"[WIN-OUT]: {text.strip()}") 
                    await websocket.send_text(text)
            except Exception as e:
                logger.error(f"Windows Read Loop Error: {e}")

        async def write_stdin():
            try:
                while True:
                    data = await websocket.receive_text()
                    
                    # Ignore resize metadata (Windows pipes don't support it)
                    if data.strip().startswith("{") and '"cols":' in data: continue
                    
                    print(f"[WIN-IN]: {repr(data)}")

                    # Ensure correct newline for Windows
                    if "\r" in data and "\n" not in data:
                        data = data.replace("\r", "\n")
                    
                    process.stdin.write(data.encode())
                    await process.stdin.drain()
            except WebSocketDisconnect:
                pass
            except Exception as e:
                logger.error(f"Windows Write Loop Error: {e}")

        await asyncio.gather(read_stdout(), write_stdin())

    except Exception as e:
        logger.error(f"Windows Terminal Setup Error: {e}")
        # Print full trace to console to see EXACT error if it fails
        traceback.print_exc() 
    finally:
        if 'pid' in locals():
            await manager.kill_session(pid)

# --- LINUX/MAC HANDLER ---
async def handle_linux_terminal(websocket: WebSocket):
    master_fd, slave_fd = pty.openpty()
    pid = os.fork()

    if pid == 0:
        # Child Process
        os.setsid()
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        if master_fd > 2: os.close(master_fd)
        if slave_fd > 2: os.close(slave_fd)
        os.environ["TERM"] = "xterm"
        shell = os.environ.get("SHELL", "/bin/bash")
        os.execvp(shell, [shell])
    else:
        # Parent Process
        os.close(slave_fd)
        manager.register_linux(pid, master_fd, websocket)
        try:
            async def read_from_pty():
                while True:
                    await asyncio.sleep(0.01)
                    if pid not in manager.active_sessions: break
                    try:
                        r, _, _ = select.select([master_fd], [], [], 0)
                        if master_fd in r:
                            data = os.read(master_fd, 10240)
                            if not data: break
                            await websocket.send_text(data.decode("utf-8", "ignore"))
                    except OSError: break

            async def write_to_pty():
                while True:
                    data = await websocket.receive_text()
                    if pid not in manager.active_sessions: break
                    
                    # Handle Resizing
                    if data.strip().startswith("{") and '"cols":' in data:
                        try:
                            resize = json.loads(data)
                            winsize = struct.pack("HHHH", resize.get("rows", 24), resize.get("cols", 80), 0, 0)
                            fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
                            continue
                        except: pass
                    
                    os.write(master_fd, data.encode())

            await asyncio.gather(read_from_pty(), write_to_pty())
        except (WebSocketDisconnect, OSError):
            pass
=======
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
>>>>>>> 246021dae7ea5ebb524edb429f96d21864ad7c99
        finally:
            await manager.kill_session(pid)