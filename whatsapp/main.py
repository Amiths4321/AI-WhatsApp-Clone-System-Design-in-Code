# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from db.database import create_tables
from api.routes.auth          import router as auth_router
from api.routes.conversations import router as conv_router, presence_router
from api.routes.messages      import router as msg_router
from config.settings import APP_TITLE, APP_VERSION


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting WhatsApp Clone...")
    create_tables()
    print("Database tables ready")
    yield

app = FastAPI(
    title    = APP_TITLE,
    version  = APP_VERSION,
    lifespan = lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

@app.get("/health", tags=["System"])
def health():
    return {"status": "healthy", "version": APP_VERSION}

app.include_router(auth_router)
app.include_router(conv_router)
app.include_router(msg_router)
app.include_router(presence_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
