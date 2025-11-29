import uvicorn
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from api.v1.api import api_router
from core.security import protect_docs

app = FastAPI(
    title="Lexxadata Customer Scraper API",
    description="A structured API to search and scrape customer data from the NMS portal.",
    version="1.0.0",
    docs_url=None,
    redoc_url=None
)

# --- FIX: Define specific origins instead of "*" ---
origins = [
    "http://localhost:3000",     # React (localhost)
    "http://127.0.0.1:3000",     # React (127.0.0.1)
    "http://localhost:8001",     # Swagger UI internal calls
    # Add your production domain here later, e.g., "https://dashboard.lexxa.com"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,       # Use the specific list here
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")

# --- NEW PROTECTED DOCS ROUTES ---
@app.get("/docs", include_in_schema=False)
async def get_protected_docs(authorized: bool = Depends(protect_docs)):
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI"
    )

@app.get("/redoc", include_in_schema=False)
async def get_protected_redoc(authorized: bool = Depends(protect_docs)):
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=app.title + " - ReDoc"
    )

# --- YOUR API ROUTERS ---
@app.get("/")
def root():
    return {"API is running"}

@app.get("/dev/auth-status")
def auth_status():
    from core.config import settings
    return {
        "auth_disabled": settings.DISABLE_AUTH,
        "message": "JWT authentication is disabled" if settings.DISABLE_AUTH else "JWT authentication is enabled"
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True, loop="asyncio")