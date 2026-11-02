import os
import re
import uuid
from datetime import datetime
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, create_engine, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from llm_service import LLMService
from doc_generator import create_grant_document
from grant_scraper import DEFAULT_GRANTS, evaluate_grants, scrape_and_normalize_grants

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
    status = Column(String, default="Зареєстровано (Діюче)")

class GrantProgram(Base):
    __tablename__ = "grant_programs"
    code = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    donor = Column(String, nullable=False)
    max_amount = Column(String, nullable=False)
    min_own_percent = Column(Integer, default=0)
    target_kveds = Column(String, nullable=True)
    land_req = Column(String, nullable=True)
    keywords = Column(String, nullable=True)
    requirements = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

with engine.connect() as conn:
    for col in ["edrpou", "company_name", "kved"]:
        try:
            conn.execute(text(f"ALTER TABLE enterprise_profiles ADD COLUMN IF NOT EXISTS {col} VARCHAR"))
            conn.commit()
        except Exception as e:
            print(f"Migration check for {col}: {e}")

SEED_COMPANIES = [
    {
        "edrpou": "03728915",
        "company_name": "ФГ «ПОДІЛЬСЬКИЙ КОЛОС»",
        "kved": "01.11 Вирощування зернових і технічних культур",
        "region": "Вінницька область",
        "activity_type": "Вирощування зернових (кукурудза, пшениця, соняшник)",
        "size_category": "Середнє підприємство (320 га)",
        "employees_count": "14 працівників"
    },
    {
        "edrpou": "38492014",
        "company_name": "ТОВ «ВІННИЦЯ-АГРОСАД»",
        "kved": "01.24 Вирощування зерняткових і кісточкових фруктів",
        "region": "Вінницька область",
        "activity_type": "Садівництво та ягідництво (інтенсивний яблуневий сад і лохина)",
        "size_category": "Мале підприємство (18 га)",
        "employees_count": "9 працівників"
    },
    {
        "edrpou": "41258963",
        "company_name": "ТОВ «АГРО-ЕКО ПЕРЕРОБКА»",
        "kved": "10.41 Виробництво олії та тваринних жирів",
        "region": "Черкаська область",
        "activity_type": "Переробка соняшнику та сої, елеваторне зберігання",
        "size_category": "Середнє підприємство (450 га + олійниця)",
        "employees_count": "26 працівників"
    },
    {
        "edrpou": "29481052",
        "company_name": "ФГ «ЗЕЛЕНА ТЕПЛИЦЯ ПОЛТАВЩИНИ»",
        "kved": "01.13 Вирощування овочів і баштанних культур",
        "region": "Полтавська область",
        "activity_type": "Тепличне господарство (вирощування томатів та зелені)",
        "size_category": "Мале підприємство (2.0 га)",
        "employees_count": "11 працівників"
    }
]

def seed_initial_data():
    db = SessionLocal()
    try:
        for comp in SEED_COMPANIES:
            exists = db.query(EDRPOURegistry).filter(EDRPOURegistry.edrpou == comp["edrpou"]).first()
            if not exists:
                db.add(EDRPOURegistry(**comp))
        for g in DEFAULT_GRANTS:
            exists_g = db.query(GrantProgram).filter(GrantProgram.code == g["code"]).first()
            if not exists_g:
                db.add(GrantProgram(
                    code=g["code"],
                    title=g["title"],
                    donor=g["donor"],
                    max_amount=g["max_amount"],
                    min_own_percent=g["min_own_percent"],
                    target_kveds=g["target_kveds"],
                    land_req=g["land_req"],
                    keywords=",".join(g["keywords"]) if isinstance(g["keywords"], list) else g["keywords"],
                    requirements=g["requirements"]
                ))
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Seed warning: {e}")
    finally:
        db.close()

seed_initial_data()

def lookup_or_create_edrpou(db, code: str) -> EDRPOURegistry:
    record = db.query(EDRPOURegistry).filter(EDRPOURegistry.edrpou == code).first()
    if record:
        return record
    fallback = EDRPOURegistry(
        edrpou=code,
        company_name=f"ФГ «АГРО-ЛАН {code[:4]}»",
        kved="01.11 Вирощування зернових культур (крім рису), бобових і насіння олійних культур",
        region="Вінницька область",
        activity_type="Рослинництво та переробка агропродукції",
        size_category="Мале агропідприємство (120 га)",
        employees_count="8 працівників"
    )
    db.add(fallback)
    db.commit()
    db.refresh(fallback)
    return fallback

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

@app.api_route("/", methods=["GET", "HEAD"])
def health_check():
    return {"status": "ok", "service": "AgroGrant API"}

@app.get("/edrpou/{code}")
def get_edrpou_info(code: str):
    clean_code = re.sub(r"\D", "", code)
    if len(clean_code) != 8:
        raise HTTPException(status_code=400, detail="Код ЄДРПОУ повинен містити 8 цифр")
    db = SessionLocal()
    try:
        rec = lookup_or_create_edrpou(db, clean_code)
        return {
            "edrpou": rec.edrpou,
            "company_name": rec.company_name,
            "kved": rec.kved,
            "region": rec.region,
            "activity_type": rec.activity_type,
            "size_category": rec.size_category,
            "employees_count": rec.employees_count,
            "status": rec.status
        }
    finally:
        db.close()
def get_grants_from_db(db):
    db_grants = db.query(GrantProgram).all()
    grants_list = []
    for g in db_grants:
        grants_list.append({
            "code": g.code,
            "title": g.title,
            "donor": g.donor,
            "max_amount": g.max_amount,
            "min_own_percent": g.min_own_percent,
            "target_kveds": g.target_kveds,
            "land_req": g.land_req,
            "keywords": g.keywords.split(",") if g.keywords else [],
            "requirements": g.requirements
        })
    return grants_list

@app.get("/grants/sync")
async def sync_grants():
    db = SessionLocal()
    try:
        grants = await scrape_and_normalize_grants(llm_service.api_key)
        added = 0
        for g in grants:
            exists = db.query(GrantProgram).filter(GrantProgram.code == g["code"]).first()
            if not exists:
                new_prog = GrantProgram(
                    code=g["code"],
                    title=g["title"],
                    donor=g["donor"],
                    max_amount=g["max_amount"],
                    min_own_percent=int(g.get("min_own_percent", 0)),
                    target_kveds=g.get("target_kveds", ""),
                    land_req=g.get("land_req", ""),
                    keywords=",".join(g.get("keywords", [])) if isinstance(g.get("keywords"), list) else g.get("keywords", ""),
                    requirements=g.get("requirements", "")
                )
                db.add(new_prog)
                added += 1
        db.commit()
        return {"status": "synced", "total_parsed": len(grants), "new_added": added}
    finally:
        db.close()

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

        edrpou_match = re.search(r"\b(\d{8})\b", request.message)
        edrpou_note = ""
        if edrpou_match:
            found_code = edrpou_match.group(1)
            reg_company = lookup_or_create_edrpou(db, found_code)
            db_profile.edrpou = reg_company.edrpou
            db_profile.company_name = reg_company.company_name
            db_profile.kved = reg_company.kved
            db_profile.region = reg_company.region
            db_profile.activity_type = reg_company.activity_type
            db_profile.size_category = reg_company.size_category
            db_profile.employees_count = reg_company.employees_count
            db.commit()
            edrpou_note = (
                f" [СИСТЕМНЕ ПОВІДОМЛЕННЯ: Підтягнуто ЄДРПОУ {found_code}: {reg_company.company_name}, "
                f"КВЕД {reg_company.kved}. Запитай лише про напрям інвестицій та % власного внеску.]"
            )

        current_profile = {
            "edrpou": db_profile.edrpou,
            "company_name": db_profile.company_name,
            "kved": db_profile.kved,
            "region": db_profile.region,
            "activity_type": db_profile.activity_type,
            "size_category": db_profile.size_category,
            "employees_count": db_profile.employees_count,
            "investment_focus": db_profile.investment_focus,
            "own_contribution_percent": db_profile.own_contribution_percent
        }

        # Отримуємо гранти з бази для скорингу
        grants_list = get_grants_from_db(db)
        scored_for_llm = evaluate_grants(current_profile, grants_list)
        
        top_grants_hint = ""
        if scored_for_llm:
            top_grants_hint = (
                f" [Рекомендації: 1) {scored_for_llm[0]['title']} (сумісність {scored_for_llm[0]['score']}%); "
                f"2) {scored_for_llm[1]['title'] if len(scored_for_llm) > 1 else ''}]"
            )

        enriched_message = request.message + edrpou_note + top_grants_hint
        llm_response = await llm_service.generate_response(enriched_message, current_profile)
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

        # Фінальний скоринг з новими даними
        final_scored = evaluate_grants(current_profile, grants_list)

        return {
            "reply": llm_response.get("reply", "Дані оновлено."),
            "profile": current_profile,
            "grants": final_scored,
            "is_error": llm_response.get("is_error", False)
        }
    except Exception as e:
        db.rollback()
        print(f"Error in chat endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.api_route("/export/{user_id}", methods=["GET", "HEAD"])
def export_grant(user_id: uuid.UUID):
    db = SessionLocal()
    try:
        db_profile = db.query(EnterpriseProfile).filter(EnterpriseProfile.user_id == user_id).first()
        profile_data = {
            "edrpou": db_profile.edrpou if db_profile else None,
            "company_name": db_profile.company_name if db_profile else None,
            "kved": db_profile.kved if db_profile else None,
            "region": db_profile.region if db_profile else None,
            "activity_type": db_profile.activity_type if db_profile else None,
            "size_category": db_profile.size_category if db_profile else None,
            "employees_count": db_profile.employees_count if db_profile else None,
            "investment_focus": db_profile.investment_focus if db_profile else None,
            "own_contribution_percent": db_profile.own_contribution_percent if db_profile else None
        }
        grants_list = get_grants_from_db(db)
        doc_stream = create_grant_document(profile_data, grants_list)
        return StreamingResponse(
            doc_stream,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": "attachment; filename=AgroGrant_Analytical_Report.docx"}
        )
    finally:
        db.close()