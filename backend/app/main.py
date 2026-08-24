"""
CineSpine FastAPI Application Gateway.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.api.routes import router

app = FastAPI(
    title="CineSpine API",
    description="Append-Only Event Spine & 3-Axis Discrepancy Reconciliation Engine",
    version="0.1.0",
)

# Enable CORS for React frontend (local Vite port 5173 and Replit hosting)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
