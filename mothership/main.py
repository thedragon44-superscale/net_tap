from fastapi import FastAPI, Depends, HTTPException, Header, Request, status
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from pydantic import BaseModel
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
    # The new column required to link desktop agents to web accounts
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

# --- ENDPOINT 1: GENERATE ENTERPRISE KEY ---
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

# --- ENDPOINT 2: INGEST AGENT TELEMETRY ---
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
