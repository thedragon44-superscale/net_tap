from fastapi import FastAPI, Depends, HTTPException, Header, Request, status, Form, Response, BackgroundTasks, WebSocket, WebSocketDisconnect
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
import urllib.request
import urllib.error
import jwt
from dotenv import load_dotenv

load_dotenv() 

# --- INFRASTRUCTURE CONFIGURATION ---
SQLALCHEMY_DATABASE_URL = os.getenv("NEON_DB_URL", "sqlite:///./dragon_mothership.db")
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_BUCKET_NAME = os.getenv("AWS_BUCKET_NAME")

# --- AUTH & API CONFIGURATION ---
BREVO_API_KEY = os.getenv("BREVO_API_KEY")
SMTP_USER = os.getenv("SMTP_USER", "flightg@thedragonhms.com") 
JWT_SECRET = os.getenv("JWT_SECRET", "fallback_dev_key_change_in_prod")
JWT_ALGORITHM = "HS256"

# --- DATABASE CONFIGURATION ---
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in SQLALCHEMY_DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    tier = Column(String, default="free") # 🟢 NEW: Account tier enforcement
    enterprise_api_key = Column(String, unique=True, index=True, nullable=True)
    otp_code = Column(String, nullable=True)
    otp_expires_at = Column(DateTime, nullable=True)

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

app = FastAPI(title="Dragon HMS - Mothership API")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# =====================================================================
# LIVE WEBSOCKET MANAGER 
# =====================================================================
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
# AUTHENTICATION & EMAIL HELPERS
# =====================================================================

def send_otp_email(target_email: str, code: str):
    if not BREVO_API_KEY:
        print("[!] EMAIL FAILURE: BREVO_API_KEY environment variable is missing.")
        return

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }
    
    payload = {
        "sender": {"name": "Dragon Command", "email": SMTP_USER},
        "to": [{"email": target_email}],
        "subject": "Dragon HMS - Authentication Code",
        "htmlContent": f"<p>Your Dragon HMS security clearance code is: <strong style='font-size: 24px; letter-spacing: 4px;'>{code}</strong></p><p>This code expires in 10 minutes.</p>"
    }
    
    data = json.dumps(payload).encode("utf-8")
    
    try:
        print(f"[*] Dispatching OTP to {target_email} via Brevo HTTP API...")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 201:
                print(f"[+] SUCCESS: OTP delivered to HTTP relay for {target_email}")
            else:
                print(f"[!] API Warning: Received unexpected status {response.status}")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"[!] BREVO API REJECTED REQUEST: {e.code} - {error_body}")
    except Exception as e:
        print(f"[!] CRITICAL HTTP EMAIL FAILURE: {e}")

def get_current_user_from_cookie(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("dragon_session")
    if not token:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        email = payload.get("sub")
        return db.query(User).filter(User.email == email).first()
    except:
        return None

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
async def process_register(request: Request, background_tasks: BackgroundTasks, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse(request=request, name="index.html", context={"error_message": "Email already registered."})
    
    new_user = User(email=email, hashed_password=password)
    
    otp = str(secrets.randbelow(899999) + 100000)
    new_user.otp_code = otp
    new_user.otp_expires_at = datetime.datetime.now() + datetime.timedelta(minutes=10)
    
    db.add(new_user)
    db.commit()
    
    background_tasks.add_task(send_otp_email, new_user.email, otp)
    
    redirect = RedirectResponse(url="/verify", status_code=status.HTTP_303_SEE_OTHER)
    redirect.set_cookie(key="pending_user", value=new_user.email, httponly=True)
    return redirect

@app.post("/login")
async def process_login(request: Request, background_tasks: BackgroundTasks, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    
    if not user or user.hashed_password != password:
        return templates.TemplateResponse(request=request, name="index.html", context={"error_message": "Invalid credentials."})

    if user.otp_code:
        otp = str(secrets.randbelow(899999) + 100000)
        user.otp_code = otp
        user.otp_expires_at = datetime.datetime.now() + datetime.timedelta(minutes=10)
        db.commit()
        
        background_tasks.add_task(send_otp_email, user.email, otp)
        
        redirect = RedirectResponse(url="/verify", status_code=status.HTTP_303_SEE_OTHER)
        redirect.set_cookie(key="pending_user", value=user.email, httponly=True)
        return redirect

    token_payload = {"sub": user.email, "exp": datetime.datetime.now() + datetime.timedelta(days=1)}
    session_token = jwt.encode(token_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    redirect = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    redirect.set_cookie(key="dragon_session", value=session_token, httponly=True)
    return redirect

@app.get("/verify")
async def serve_verify(request: Request):
    if not request.cookies.get("pending_user"):
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request=request, name="verify.html")

@app.post("/verify")
async def process_verify(request: Request, otp_code: str = Form(...), db: Session = Depends(get_db)):
    pending_email = request.cookies.get("pending_user")
    if not pending_email:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    user = db.query(User).filter(User.email == pending_email).first()
    
    if not user or user.otp_code != otp_code or user.otp_expires_at < datetime.datetime.now():
        return templates.TemplateResponse(request=request, name="index.html", context={"error_message": "Invalid or expired OTP."})

    user.otp_code = None
    user.otp_expires_at = None
    db.commit()

    token_payload = {"sub": user.email, "exp": datetime.datetime.now() + datetime.timedelta(days=1)}
    session_token = jwt.encode(token_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="dragon_session", value=session_token, httponly=True)
    response.delete_cookie("pending_user")
    return response

@app.get("/dashboard")
async def serve_dashboard(request: Request, session_id: str = None, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    # 🟢 NEW: Stripe Payment Success Handler
    if session_id and user.tier != "enterprise":
        try:
            # We catch the redirect from Stripe and upgrade the user
            user.tier = "enterprise"
            db.commit()
        except Exception as e:
            print(f"Failed to upgrade user: {e}")

    user_history = db.query(Telemetry).filter(Telemetry.owner_email == user.email).order_by(Telemetry.id.desc()).limit(10).all()
    formatted_history = [{"filename": f"{r.scan_type.upper()}_CAPTURE_{r.timestamp}.json", "records_count": r.records_count} for r in user_history]

    return templates.TemplateResponse(
        request=request, 
        name="dashboard.html", 
        context={
            "user_email": user.email,
            "user_tier": user.tier, # Passes the REAL tier to the frontend
            "rating_stars": "⭐⭐⭐⭐⭐",
            "rating_score": "5.0",
            "history": formatted_history 
        }
    )

@app.get("/logout")
async def process_logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("dragon_session")
    return response

# =====================================================================
# API ENDPOINTS
# =====================================================================

@app.post("/create-checkout-session")
async def create_checkout_session(request: Request):
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{'price_data': {'currency': 'usd', 'unit_amount': 49900, 'product_data': {'name': 'Dragon Enterprise Agent License'}}, 'quantity': 1}],
            mode='payment',
            success_url=str(request.base_url) + "dashboard?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=str(request.base_url) + "dashboard",
        )
        return RedirectResponse(url=checkout_session.url, status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/users/generate-api-key")
async def generate_api_key(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user_from_cookie(request, db)
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # 🟢 NEW: Backend enforcement. Only Enterprise accounts can generate keys.
    if current_user.tier != "enterprise":
        raise HTTPException(status_code=403, detail="Enterprise license required.")
        
    new_key = f"drgn_live_{secrets.token_urlsafe(32)}"
    try:
        current_user.enterprise_api_key = new_key
        db.commit()
        return {"success": True, "api_key": new_key}
    except:
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

    try:
        s3_client = boto3.client('s3', aws_access_key_id=AWS_ACCESS_KEY, aws_secret_access_key=AWS_SECRET_KEY)
        s3_client.put_object(Bucket=AWS_BUCKET_NAME, Key=file_name, Body=json.dumps(payload).encode('utf-8'))
    except Exception as e:
        print(f"[!] S3 Upload Failed: {str(e)}")

    new_telemetry = Telemetry(
        owner_email=associated_user.email,
        scan_type=scan_type,
        timestamp=timestamp,
        records_count=record_count
    )
    db.add(new_telemetry)
    db.commit()
    
    await manager.broadcast({"qps": record_count, "scan_type": scan_type})
    return {"status": "success", "owner": associated_user.email}
