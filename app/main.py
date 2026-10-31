from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.routers.auth import router as auth_router
from app.routers.projects import router as projects_router
from app.routers.chats import router as chats_router
from app.routers.documents import router as document_router

app = FastAPI(title="Blue Backend")
# SESSION_DURATION_HOURS = 24

app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(chats_router)
app.include_router(document_router)
@app.get("/")
def home():
    return {"message": "Blue API is running"}  #THIS IS JUST TO CHECK WHETHER ENDPOINT IS CONNECTED OR NOT.

@app.get("/api/v1/health/database")
def health_database(db: Session = Depends(get_db)):  #HEALTH OF THE DATABASE, AND GETTING THE STATUS OF THE CONNECTION.
    result = db.execute(
        text("SELECT current_database()")
    )
    database_name = result.scalar_one()
    return {
        "status": "connected",
        "database": database_name,
    }
