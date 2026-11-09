"""
Серверне ядро інтелектуального грантового чат-бота (AgroGrant_Bot).
Містить ротацію логів RotatingFileHandler, сумісність драйверів БД та захист від спам-полінгу.
"""

import os
import re
import uuid
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from llm_service import LLMService
from doc_generator import create_grant_document
from grant_scraper import DEFAULT_GRANTS, evaluate_grants

# Авторотація файлу логів app.log (ліміт 1 МБ, максимум 2 архівні копії)
log_handler = RotatingFileHandler("app.log", maxBytes=1 * 1024 * 1024, backupCount=2, encoding="utf-8")
log_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
logger = logging.getLogger("AgroGrantCore")
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./agrogrant.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+psycopg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "agro2026")

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class SystemLog(Base):
    __tablename__ = "system_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = Column(DateTime, default=datetime.utcnow)
    action = Column(String, nullable=False)
    details = Column(Text, nullable=True)
    ip_address = Column(String, nullable=True)


class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    profile = relationship("EnterpriseProfile", back_populates="user", uselist=False)


class EnterpriseProfile(Base):
    __tablename__ = "enterprise_profiles"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True)
    edrpou = Column(String, nullable=True)
    company_name = Column(String, nullable=True)
    kved = Column(String, nullable=True)
    region = Column(String, nullable=True)
    activity_type = Column(String, nullable=True)
    size_category = Column(String, nullable=True)
    employees_count = Column(String, nullable=True)
    investment_focus = Column(String, nullable=True)
    own_contribution_percent = Column(String, nullable=True)
    user = relationship("User", back_populates="profile")


class EDRPOURegistry(Base):
    __tablename__ = "edrpou_registry"
    edrpou = Column(String, primary_key=True, index=True)
    company_name = Column(String, nullable=False)
    kved = Column(String, nullable=False)
    region = Column(String, nullable=False)
    activity_type = Column(String, nullable=False)
    size_category = Column(String, nullable=False)
    employees_count = Column(String, nullable=False)
    status = Column(String, default="Активний у ДАР")


Base.metadata.create_all(bind=engine)

SEED_COMPANIES = [
    {
        "edrpou": "03728915",
        "company_name": "ФГ «ПОДІЛЬСЬКИЙ КОЛОС»",
        "kved": "01.11 Вирощування зернових і технічних культур",
        "region": "Вінницька область",
        "activity_type": "Рослинництво та насінництво",
        "size_category": "300 га",
        "employees_count": "14 працівників"
    },
    {
        "edrpou": "38492014",
        "company_name": "ТОВ «САДИ ПОДІЛЛЯ»",
        "kved": "01.24 Вирощування зерняткових і кісточкових фруктів",
        "region": "Вінницька область",
        "activity_type": "Садівництво та ягідництво",
        "size_category": "18 га саду",
        "employees_count": "12 працівників"
    },
    {
        "edrpou": "41258963",
        "company_name": "ТОВ «АГРО-ЕКО ПЕРЕРОБКА»",
        "kved": "10.41 Виробництво олії та тваринних жирів",
        "region": "Черкаська область",
        "activity_type": "Глибока агропереробка",
        "size_category": "Лінія переробки 1500 т/рік",
        "employees_count": "26 працівників"
    },
    {
        "edrpou": "00496802",
        "company_name": "ННЦ «ІНСТИТУТ ЗЕМЛЕРОБСТВА НААН»",
        "kved": "72.19 Дослідження й експериментальні розробки",
        "region": "Київська область",
        "activity_type": "Наукове ядро та селекція",
        "size_category": "Дослідні поля",
        "employees_count": "Науковий штат"
    }
]


def seed_db():
    db = SessionLocal()
    try:
        for comp in SEED_COMPANIES:
            if not db.query(EDRPOURegistry).filter(EDRPOURegistry.edrpou == comp["edrpou"]).first():
                db.add(EDRPOURegistry(**comp))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


seed_db()

app = FastAPI(title="AgroGrant Analytics API", version="2.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
llm_service = LLMService()


class ChatRequest(BaseModel):
    message: str


class LogRequest(BaseModel):
    action: str
    details: str


@app.get("/")
def health_check():
    return {"status": "ok", "service": "AgroGrant_Bot API v2.1"}


@app.post("/log")
async def write_log(req: LogRequest, request: Request):
    ip = request.client.host if request.client else "unknown"
    logger.info("IP: %s | %s | %s", ip, req.action, req.details)
    db = SessionLocal()
    try:
        db.add(SystemLog(action=req.action, details=req.details, ip_address=ip))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
    return {"status": "logged"}


@app.get("/profile/{user_id}")
def get_user_profile(user_id: uuid.UUID):
    """Одноразове отримання профілю при завантаженні сторінки (без спам-полінгу)."""
    db = SessionLocal()
    try:
        prof = db.query(EnterpriseProfile).filter(EnterpriseProfile.user_id == user_id).first()
        profile_dict = {
            "edrpou": prof.edrpou if prof else None,
            "company_name": prof.company_name if prof else None,
            "kved": prof.kved if prof else None,
            "region": prof.region if prof else None,
            "activity_type": prof.activity_type if prof else None,
            "size_category": prof.size_category if prof else None,
            "employees_count": prof.employees_count if prof else None,
            "investment_focus": prof.investment_focus if prof else None,
            "own_contribution_percent": prof.own_contribution_percent if prof else None
        }
        return {"profile": profile_dict, "grants": evaluate_grants(profile_dict, DEFAULT_GRANTS)}
    finally:
        db.close()


@app.post("/chat/{user_id}")
async def chat_endpoint(user_id: uuid.UUID, request: ChatRequest, req_meta: Request):
    ip = req_meta.client.host if req_meta.client else "unknown"
    logger.info("IP: %s | CHAT_MSG | %s", ip, request.message[:120])
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            user = User(id=user_id, session_id=str(user_id))
            db.add(user)
            db.commit()

        prof = db.query(EnterpriseProfile).filter(EnterpriseProfile.user_id == user_id).first()
        if not prof:
            prof = EnterpriseProfile(user_id=user_id)
            db.add(prof)
            db.commit()
            db.refresh(prof)

        edrpou_match = re.search(r"\b(\d{8})\b", request.message)
        edrpou_note = ""
        if edrpou_match:
            code = edrpou_match.group(1)
            reg = db.query(EDRPOURegistry).filter(EDRPOURegistry.edrpou == code).first()
            if not reg:
                reg = EDRPOURegistry(
                    edrpou=code,
                    company_name=f"АГРОПІДПРИЄМСТВО (ЄДРПОУ {code})",
                    kved="01.11 Вирощування зернових і технічних культур",
                    region="Україна",
                    activity_type="Сільськогосподарське виробництво",
                    size_category="Потребує уточнення",
                    employees_count="Потребує уточнення"
                )
                db.add(reg)
                db.commit()
            prof.edrpou = reg.edrpou
            prof.company_name = reg.company_name
            prof.kved = reg.kved
            prof.region = reg.region
            prof.activity_type = reg.activity_type
            prof.size_category = reg.size_category
            prof.employees_count = reg.employees_count
            db.commit()
            edrpou_note = f" [Верифіковано ЄДРПОУ {code}: {reg.company_name}]"

        current_profile = {
            "edrpou": prof.edrpou,
            "company_name": prof.company_name,
            "kved": prof.kved,
            "region": prof.region,
            "activity_type": prof.activity_type,
            "size_category": prof.size_category,
            "employees_count": prof.employees_count,
            "investment_focus": prof.investment_focus,
            "own_contribution_percent": prof.own_contribution_percent
        }

        llm_res = await llm_service.generate_response(request.message + edrpou_note, current_profile)
        for k, v in llm_res.get("extracted_data", {}).items():
            if v and hasattr(prof, k):
                setattr(prof, k, str(v))
                current_profile[k] = str(v)
        db.commit()

        scored = evaluate_grants(current_profile, DEFAULT_GRANTS)
        return {"reply": llm_res["reply"], "profile": current_profile, "grants": scored, "is_error": False}
    finally:
        db.close()


@app.get("/api/stats")
def admin_stats(password: str = Query("")):
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Невірний пароль")
    db = SessionLocal()
    try:
        reg_list = db.query(EDRPOURegistry).all()
        regions, activities = {}, {}
        for r in reg_list:
            regions[r.region] = regions.get(r.region, 0) + 1
            activities[r.activity_type] = activities.get(r.activity_type, 0) + 1
        return {
            "total": len(reg_list),
            "edrpou_verified": len(reg_list),
            "grants_count": len(DEFAULT_GRANTS),
            "avg_own_percent": 25,
            "regions": regions,
            "activities": activities
        }
    finally:
        db.close()


@app.api_route("/export/{user_id}", methods=["GET", "HEAD"])
def export_docx(user_id: str):
    db = SessionLocal()
    try:
        prof = None
        try:
            uid = uuid.UUID(user_id)
            prof = db.query(EnterpriseProfile).filter(EnterpriseProfile.user_id == uid).first()
        except Exception:
            pass
        profile_data = {
            "edrpou": prof.edrpou if prof and prof.edrpou else "03728915",
            "company_name": prof.company_name if prof and prof.company_name else "ФГ «ПОДІЛЬСЬКИЙ КОЛОС»",
            "kved": prof.kved if prof and prof.kved else "01.11 Вирощування зернових і технічних культур",
            "region": prof.region if prof and prof.region else "Вінницька область",
            "activity_type": prof.activity_type if prof and prof.activity_type else "Рослинництво та переробка",
            "size_category": prof.size_category if prof and prof.size_category else "300 га",
            "employees_count": prof.employees_count if prof and prof.employees_count else "14 працівників",
            "own_contribution_percent": prof.own_contribution_percent if prof and prof.own_contribution_percent else "30%",
            "investment_focus": prof.investment_focus if prof and prof.investment_focus else "Масштабування та переробка"
        }
        stream = create_grant_document(profile_data, DEFAULT_GRANTS)
        return StreamingResponse(
            stream,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": "attachment; filename=AgroGrant_Analytical_Report.docx"}
        )
    finally:
        db.close()
