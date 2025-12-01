import sys
import asyncio
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# --- 1. Import your API Router ---
# This single router already contains /customer, /ticket, /cli, etc.
from api.v1.api import api_router  

# --- 2. WINDOWS FIX (CRITICAL) ---
# This forces Windows to use the 'Proactor' loop which supports
# Subprocesses (cmd.exe/powershell.exe) and Pipes.
if sys.platform == 'win32':
    print(f"Setting Windows Proactor Event Loop Policy. Current policy: {type(asyncio.get_event_loop_policy())}")
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    print(f"New policy after setting: {type(asyncio.get_event_loop_policy())}")
    
    # Additional fix: Create a new event loop with the correct policy
    # This ensures the loop policy takes effect immediately
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        print(f"Created and set new event loop with type: {type(loop)}")
    except Exception as e:
        print(f"Error creating new event loop: {e}")

app = FastAPI(
    title="Lexxadata Customer Scraper API",
    description="A structured API to search and scrape customer data from the NMS portal.",
    version="1.0.0"
)

# --- 3. CORS Setup ---
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8001",
    "*" 
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 4. Mount Routers ---
# Mount the main API router once at /api/v1
# The CLI is already inside this router at /api/v1/cli
app.include_router(api_router, prefix="/api/v1")

@app.get("/")
def root():
    return {"message": "API is running"}

# --- 5. Execution Entry Point ---
if __name__ == "__main__":
    # Running via python main.py ensures the loop policy above is respected.
    # We use loop="asyncio" to prevent Uvicorn from overriding our policy.
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True, loop="asyncio")