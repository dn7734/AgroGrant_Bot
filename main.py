import os
import uuid
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, ForeignKey, String, create_engine
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.exc import IntegrityError
from llm_service import LLMService

DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)

engine = create_engine(DATABASE_URL)
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

@app.post("/chat/{user_id}")
async def chat_with_bot(user_id: uuid.UUID, request: ChatRequest):
    db = SessionLocal()
    try:
        # Гарантовано створюємо користувача, якщо його немає
        db_user = db.query(User).filter(User.id == user_id).first()
        if not db_user:
            db_user = User(id=user_id, session_id=str(user_id))
            db.add(db_user)
            db.commit()

        # Гарантовано створюємо профіль, якщо його немає
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
        for key, value in extracted_data.items():
            if value is not None and hasattr(db_profile, key) and getattr(db_profile, key) != value:
                setattr(db_profile, key, value)
                updated = True
                
        if updated:
            db.commit()
            
        return {"reply": llm_response.get("reply", "Дякую.")}
    except Exception as e:
        db.rollback()
        print(f"Error in chat endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        db.close()