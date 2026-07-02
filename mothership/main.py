from fastapi import FastAPI, Depends, HTTPException, Header, Request, status, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker, Session
import secrets

# --- DATABASE CONFIGURATION ---
# Replace with your actual NeonDB / PostgreSQL connection string
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
    # The column required to link desktop agents to web accounts
    enterprise_api_key = Column(String, unique=True, index=True, nullable=True)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- FASTAPI APP INITIALIZATION ---
app = FastAPI(title="Dragon HMS - Mothership API")

# --- FRONTEND ASSET CONFIGURATION ---
# Mount the static directory so your dragon_logo.png loads
app.mount("/static", StaticFiles(directory="static"), name="static")
# Tell FastAPI where to find your HTML files
templates = Jinja2Templates(directory="templates")

# --- MOCK AUTHENTICATION ---
# In production, this should decode your JWT token to get the logged-in user
def get_current_user(db: Session = Depends(get_db)):
    user = db.query(User).first()
    if not user:
        # Create a dummy user for testing if the database is empty
        user = User(email="operative@dragon.local", hashed_password="hashed123")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

# =====================================================================
# UI FRONTEND ROUTES (RENDERING HTML)
# =====================================================================

@app.get("/")
async def serve_gateway(request: Request):
    """Serves the main login gateway."""
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/register")
async def serve_register(request: Request):
    """Serves the registration page."""
    return templates.TemplateResponse(request=request, name="register.html")

@app.post("/register")
async def process_register(request: Request, email: str = Form(...), password: str = Form(...)):
    """Handles form submission from register.html"""
    # Dummy redirect to login gateway after "registration"
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/login")
async def process_login(request: Request, email: str = Form(...), password: str = Form(...)):
    """Handles form submission from index.html (Login)"""
    # Dummy redirect straight to the dashboard on successful login
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/dashboard")
async def serve_dashboard(request: Request):
    """Serves the main Enterprise Dashboard."""
    return templates.TemplateResponse(
        request=request, 
        name="dashboard.html", 
        context={
            "user_email": "operative@dragon.local", # Static mock for now
            "user_tier": "enterprise",
            "rating_stars": "⭐⭐⭐⭐⭐",
            "rating_score": "5.0",
            "history": []
        }
    )

@app.get("/profile")
async def serve_profile(request: Request):
    """Serves the operator profile and API key generator."""
    return templates.TemplateResponse(request=request, name="profile.html")

# =====================================================================
# API ENDPOINTS (JSON BACKEND)
# =====================================================================

@app.post("/api/users/generate-api-key")
async def generate_api_key(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Generates a cryptographically secure key and assigns it to the user."""
    new_key = f"drgn_live_{secrets.token_urlsafe(32)}"
    
    try:
        current_user.enterprise_api_key = new_key
        db.commit()
        
        # Return plain text exactly once for the frontend modal
        return {"success": True, "api_key": new_key}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error during key generation.")

@app.post("/api/wiretap/ingest")
async def ingest_telemetry(
    request: Request,
    x_dragon_agent_key: str = Header(None), 
    db: Session = Depends(get_db)
):
    """Receives payloads from the desktop agent, authenticated via the header key."""
    if not x_dragon_agent_key:
        raise HTTPException(status_code=401, detail="Missing Enterprise API Key header.")
        
    # Verify the key exists in the database and find the owner
    associated_user = db.query(User).filter(User.enterprise_api_key == x_dragon_agent_key).first()
    
    if not associated_user:
        raise HTTPException(status_code=403, detail="Invalid or deactivated Enterprise API Key.")
        
    payload = await request.json()
    scan_type = payload.get("scan_type", "unknown")
    
    print(f"\n[+] SECURE UPLINK ESTABLISHED")
    print(f"[*] Account: {associated_user.email}")
    print(f"[*] Payload Type: {scan_type.upper()}")
    print(f"[*] Saving telemetry to database/S3...\n")
    
    # Add your S3 upload or database storage logic here
    
    return {"status": "success", "owner": associated_user.email}
