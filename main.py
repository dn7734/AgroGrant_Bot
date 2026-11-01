import os
import uuid
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, ForeignKey, String, create_engine
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from llm_service import LLMService
from doc_generator import create_grant_document

DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    agreed_to_privacy = Column(String, default="false")
    profile = relationship("EnterpriseProfile", back_populates="user", uselist=False)

class EnterpriseProfile(Base):
    __tablename__ = "enterprise_profiles"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True)
    region = Column(String, nullable=True)
    activity_type = Column(String, nullable=True)
    size_category = Column(String, nullable=True)
    employees_count = Column(String, nullable=True)
    investment_focus = Column(String, nullable=True)
    own_contribution_percent = Column(String, nullable=True)
    user = relationship("User", back_populates="profile")

Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

llm_service = LLMService()

class ChatRequest(BaseModel):
    message: str

@app.get("/")
def health_check():
    return {"status": "ok", "service": "AgroGrant API"}

@app.post("/chat/{user_id}")
async def chat_with_bot(user_id: uuid.UUID, request: ChatRequest):
    db = SessionLocal()
    try:
        db_user = db.query(User).filter(User.id == user_id).first()
        if not db_user:
            db_user = User(id=user_id, session_id=str(user_id))
            db.add(db_user)
            db.commit()

        db_profile = db.query(EnterpriseProfile).filter(EnterpriseProfile.user_id == user_id).first()
        if not db_profile:
            db_profile = EnterpriseProfile(user_id=user_id)
            db.add(db_profile)
            db.commit()
            db.refresh(db_profile)

        current_profile = {
            "region": db_profile.region,
            "activity_type": db_profile.activity_type,
            "size_category": db_profile.size_category,
            "employees_count": db_profile.employees_count,
            "investment_focus": db_profile.investment_focus,
            "own_contribution_percent": db_profile.own_contribution_percent
        }

        llm_response = await llm_service.generate_response(request.message, current_profile)
        extracted_data = llm_response.get("extracted_data", {})

        updated = False
        if isinstance(extracted_data, dict):
            for key, value in extracted_data.items():
                if value is not None and hasattr(db_profile, key) and getattr(db_profile, key) != str(value):
                    setattr(db_profile, key, str(value))
                    current_profile[key] = str(value)
                    updated = True

        if updated:
            db.commit()

        return {
            "reply": llm_response.get("reply", "Дякую."),
            "profile": current_profile,
            "is_error": llm_response.get("is_error", False)
        }
    except Exception as e:
        db.rollback()
        print(f"Error in chat endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/export/{user_id}")
def export_grant(user_id: uuid.UUID):
    db = SessionLocal()
    try:
        db_profile = db.query(EnterpriseProfile).filter(EnterpriseProfile.user_id == user_id).first()
        profile_data = {
            "region": db_profile.region if db_profile else None,
            "activity_type": db_profile.activity_type if db_profile else None,
            "size_category": db_profile.size_category if db_profile else None,
            "employees_count": db_profile.employees_count if db_profile else None,
            "investment_focus": db_profile.investment_focus if db_profile else None,
            "own_contribution_percent": db_profile.own_contribution_percent if db_profile else None
        }
        doc_stream = create_grant_document(profile_data)
        return StreamingResponse(
            doc_stream,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": "attachment; filename=AgroGrant_Application.docx"}
        )
    finally:
        db.close()