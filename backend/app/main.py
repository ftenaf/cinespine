"""
CineSpine FastAPI Application Gateway.
"""
from dotenv import load_dotenv

# Load local environment variables from .env if present
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.api.routes import router

app = FastAPI(
    title="CineSpine API",
    description="Append-Only Event Spine & 3-Axis Discrepancy Reconciliation Engine",
    version="0.1.0",
)

# Initialize OpenTelemetry
from backend.app.core.telemetry import (
    backport_fastapi_route_details,
    configure_structured_logging,
    setup_otlp,
)
setup_otlp()
# After setup_otlp: the logging instrumentation it installs reformats the root
# handler, and this has the last word on what stdout looks like.
configure_structured_logging()

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

# Before instrument_app: the 0.63b1 route walker 500s on a wrong-method
# request to any included route. See the function for why 0.64b0 is not here.
backport_fastapi_route_details()
FastAPIInstrumentor.instrument_app(app)
HTTPXClientInstrumentor().instrument()

# Enable CORS for the React frontend (local Vite dev server on 5173; the
# Cloud Run deployment itself is same-origin and doesn't need this).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import Request

app.include_router(router)

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "cinespine"}

# Mount static previz directory
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    previz_dir = os.path.join(static_dir, "previz")
    if os.path.exists(previz_dir):
        app.mount("/previz", StaticFiles(directory=previz_dir), name="previz")

# Serve the compiled frontend build for the unified single-service deployment
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
if os.path.exists(frontend_dist):
    assets_dir = os.path.join(frontend_dist, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend_assets")
        
    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"])
    async def serve_frontend(request: Request, full_path: str):
        # We don't want this catching /api/ routes, but since router is included above, 
        # /api/ routes take precedence.
        
        # Check if the requested file exists (like favicon.ico, robots.txt, etc.)
        file_path = os.path.join(frontend_dist, full_path)
        if os.path.isfile(file_path) and full_path:
            return FileResponse(file_path)
            
        # Fallback to index.html for React Router
        index_path = os.path.join(frontend_dist, "index.html")
        if os.path.isfile(index_path):
            return FileResponse(index_path)
            
        return {"detail": "Not Found"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
