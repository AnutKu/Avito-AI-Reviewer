from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import SessionLocal, engine
from .models import Base
from .routers import auth, common, methodist, reviewer, student
from .seed import seed_demo
from .services.review_pipeline import recover_orphaned_detections, recover_orphaned_reviews


@asynccontextmanager
async def lifespan(app: FastAPI):
    del app
    Base.metadata.create_all(bind=engine)
    if settings.seed_on_start:
        with SessionLocal() as db:
            seed_demo(db)
    # AI-ревью выполняется в BackgroundTasks этого же процесса, поэтому всё, что
    # осталось в running, умерло вместе с предыдущим процессом. Без этого запись
    # висит в running навсегда и её нельзя ни перезапустить, ни завершить.
    recover_orphaned_reviews()
    recover_orphaned_detections()
    yield


app = FastAPI(
    title="Avito AI Reviewer Core API",
    version="0.1.0",
    description="Core domain integrated with the isolated AI reviewer service.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router, prefix="/api")
app.include_router(common.router, prefix="/api")
app.include_router(student.router, prefix="/api")
app.include_router(reviewer.router, prefix="/api")
app.include_router(methodist.router, prefix="/api")


@app.get("/health", tags=["system"])
def health() -> dict:
    return {
        "status": "ok",
        "service": "core-api",
        "ai_reviewer_url": settings.ai_reviewer_url,
        "ai_model": settings.ai_reviewer_model,
    }
