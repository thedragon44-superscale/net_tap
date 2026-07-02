from fastapi import FastAPI, Depends, HTTPException, Header, Request, status, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, Session
import secrets
import datetime
import os
import json
import boto3
import stripe
from dotenv import load_dotenv

# --- SECURE CREDENTIAL LOADING ---
load_dotenv() # Loads variables from your local .env file

# Pull from .env, fallback to local sqlite if missing
SQLALCHEMY_DATABASE_URL = os.getenv("NEON_DB_URL", "sqlite:///./dragon_mothership.db")
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_BUCKET_NAME = os.getenv("AWS_BUCKET_NAME")

# --- DATABASE CONFIGURATION ---
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in SQLALCHEMY_DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

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

# =====================================================================
# LIVE WEBSOCKET MANAGER (Keeping your real-time broadcast intact)
# =====================================================================
from fastapi import WebSocket, WebSocketDisconnect

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

@app.websocket("/ws/vitals")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# =====================================================================
# UI FRONTEND ROUTES
# =====================================================================

def get_current_user(db: Session = Depends(get_db)):
    user = db.query(User).first()
    if not user:
        user = User(email="operative@dragon.local", hashed_password="hashed123")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

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
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/dashboard")
async def serve_dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(db)
    user_history = db.query(Telemetry).filter(Telemetry.owner_email == user.email).order_by(Telemetry.id.desc()).limit(10).all()
    
    formatted_history = []
    for record in user_history:
        formatted_history.append({
            "filename": f"{record.scan_type.upper()}_CAPTURE_{record.timestamp}.json",
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
            "history": formatted_history 
        }
    )

@app.get("/profile")
async def serve_profile(request: Request):
    return templates.TemplateResponse(request=request, name="profile.html")

# =====================================================================
# API ENDPOINTS (AWS S3 & STRIPE INTEGRATION)
# =====================================================================

@app.post("/create-checkout-session")
async def create_checkout_session(request: Request):
    """Triggers when a free user clicks 'Unlock Enterprise'."""
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'unit_amount': 49900, # $499.00
                    'product_data': {
                        'name': 'Dragon Enterprise Agent License',
                    },
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=str(request.base_url) + "dashboard?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=str(request.base_url) + "dashboard",
        )
        return RedirectResponse(url=checkout_session.url, status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
    record_count = len(scan_data) if isinstance(scan_data, (list, dict)) else 0
    
    timestamp = datetime.datetime.now().strftime("%H%M%S")
    file_name = f"{associated_user.id}/{scan_type}_CAPTURE_{timestamp}.json"

    # --- AWS S3 UPLOAD LOGIC ---
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY,
            aws_secret_access_key=AWS_SECRET_KEY
        )
        # Convert the dictionary back to a JSON string for storage
        payload_bytes = json.dumps(payload).encode('utf-8')
        s3_client.put_object(Bucket=AWS_BUCKET_NAME, Key=file_name, Body=payload_bytes)
    except Exception as e:
        print(f"[!] S3 Upload Failed: {str(e)}")
        # We don't raise an HTTPException here so the DB/Websocket logic still runs even if S3 fails during testing

    # --- DATABASE RECORD LOGIC ---
    new_telemetry = Telemetry(
        owner_email=associated_user.email,
        scan_type=scan_type,
        timestamp=timestamp,
        records_count=record_count
    )
    db.add(new_telemetry)
    db.commit()
    
    # --- LIVE UI BROADCAST ---
    await manager.broadcast({
        "qps": record_count,
        "scan_type": scan_type
    })
    
    return {"status": "success", "owner": associated_user.email}
