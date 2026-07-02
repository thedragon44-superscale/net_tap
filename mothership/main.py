from fastapi import FastAPI, Depends, HTTPException, Header, Request, status, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, Session
import secrets
import datetime

# --- DATABASE CONFIGURATION ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./dragon_mothership.db" 
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- DATABASE MODELS ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    enterprise_api_key = Column(String, unique=True, index=True, nullable=True)

class Telemetry(Base):
    __tablename__ = "telemetry"
    id = Column(Integer, primary_key=True, index=True)
    owner_email = Column(String, index=True)
    scan_type = Column(String)
    timestamp = Column(String)
    records_count = Column(Integer)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- FASTAPI APP INITIALIZATION ---
app = FastAPI(title="Dragon HMS - Mothership API")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def get_current_user(db: Session = Depends(get_db)):
    user = db.query(User).first()
    if not user:
        user = User(email="operative@dragon.local", hashed_password="hashed123")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

# =====================================================================
# UI FRONTEND ROUTES
# =====================================================================

@app.get("/")
async def serve_gateway(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/register")
async def serve_register(request: Request):
    return templates.TemplateResponse(request=request, name="register.html")

@app.post("/register")
async def process_register(request: Request, email: str = Form(...), password: str = Form(...)):
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/login")
async def process_login(request: Request, email: str = Form(...), password: str = Form(...)):
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/logout")
async def process_logout(request: Request):
    """Safely terminates the session and returns to Gateway."""
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/dashboard")
async def serve_dashboard(request: Request, db: Session = Depends(get_db)):
    # Fetch the user and their actual telemetry history from the database
    user = get_current_user(db)
    user_history = db.query(Telemetry).filter(Telemetry.owner_email == user.email).order_by(Telemetry.id.desc()).limit(10).all()
    
    # Format the data for the HTML template
    formatted_history = []
    for record in user_history:
        formatted_history.append({
            "filename": f"{record.scan_type.upper()}_CAPTURE_{record.timestamp}.dat",
            "records_count": record.records_count
        })

    return templates.TemplateResponse(
        request=request, 
        name="dashboard.html", 
        context={
            "user_email": user.email,
            "user_tier": "enterprise",
            "rating_stars": "⭐⭐⭐⭐⭐",
            "rating_score": "5.0",
            "history": formatted_history # Dynamically inject real DB data!
        }
    )

@app.get("/profile")
async def serve_profile(request: Request):
    return templates.TemplateResponse(request=request, name="profile.html")

# =====================================================================
# API ENDPOINTS
# =====================================================================

@app.post("/api/users/generate-api-key")
async def generate_api_key(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    new_key = f"drgn_live_{secrets.token_urlsafe(32)}"
    try:
        current_user.enterprise_api_key = new_key
        db.commit()
        return {"success": True, "api_key": new_key}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

@app.post("/api/wiretap/ingest")
async def ingest_telemetry(
    request: Request,
    x_dragon_agent_key: str = Header(None), 
    db: Session = Depends(get_db)
):
    if not x_dragon_agent_key:
        raise HTTPException(status_code=401, detail="Missing Enterprise API Key header.")
        
    associated_user = db.query(User).filter(User.enterprise_api_key == x_dragon_agent_key).first()
    if not associated_user:
        raise HTTPException(status_code=403, detail="Invalid API Key.")
        
    payload = await request.json()
    scan_type = payload.get("scan_type", "unknown")
    scan_data = payload.get("scan_data", {})
    
    # Calculate how many rows/packets were uploaded
    record_count = len(scan_data) if isinstance(scan_data, (list, dict)) else 0
    
    # Save the telemetry event to the database
    new_telemetry = Telemetry(
        owner_email=associated_user.email,
        scan_type=scan_type,
        timestamp=datetime.datetime.now().strftime("%H:%M:%S"),
        records_count=record_count
    )
    db.add(new_telemetry)
    db.commit()
    
    return {"status": "success", "owner": associated_user.email}
