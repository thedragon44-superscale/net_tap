import os
import io
import time
import json
import stripe
import psycopg2
from psycopg2.extras import RealDictCursor
import pandas as pd
import boto3
from botocore.config import Config
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Cookie, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# --- LOAD LOCAL VAULT ---
load_dotenv()

# --- CONFIGURATION ---
AWS_REGION = os.getenv("AWS_REGION", "")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
AGENT_SECRET_KEY = os.getenv("AGENT_SECRET_KEY", "dragon_production_key_999")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_u2Uvh8dFMcCl@ep-broad-block-ahjzaleh.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require"
)

stripe.api_key = STRIPE_SECRET_KEY

s3_client = boto3.client(
    's3',
    region_name=AWS_REGION.strip(),
    aws_access_key_id=AWS_ACCESS_KEY_ID.strip(),
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY.strip(),
    config=Config(signature_version='s3v4', region_name=AWS_REGION.strip(), s3={'addressing_style': 'virtual'})
)

# --- APP INITIALIZATION ---
os.makedirs("static", exist_ok=True)

app = FastAPI(title="The Dragon Headquarters Management Services")
app.mount("/static", StaticFiles(directory="static"), name="static")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

active_connections = []

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

@app.on_event("startup")
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                tier VARCHAR(50) DEFAULT 'free'
            );
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id SERIAL PRIMARY KEY,
                filename VARCHAR(255) NOT NULL,
                records_count INTEGER NOT NULL,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_email VARCHAR(255) DEFAULT 'legacy@system.local'
            );
        """)
        
        conn.commit()
        print("Database initialized successfully. Data isolation enforced.")
    except Exception as e:
        print(f"Database initialization error: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

# --- FRONTEND UI ROUTES ---

@app.get("/", response_class=HTMLResponse)
def view_login(request: Request, user_session: str = Cookie(None), error: str = None):
    if user_session:
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse("index.html", {"request": request, "error_message": error})

@app.get("/register", response_class=HTMLResponse)
def view_register(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
def handle_register(email: str = Form(...), password: str = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO users (email, password, tier) VALUES (%s, %s, 'free');", (email, password))
        conn.commit()
        response = RedirectResponse(url="/dashboard", status_code=303)
        response.set_cookie(key="user_session", value=email, path="/")
        return response
    except psycopg2.IntegrityError:
        conn.rollback()
        return RedirectResponse(url="/?error=Email already registered.", status_code=303)
    finally:
        cur.close()
        conn.close()

@app.post("/login")
def handle_login(email: str = Form(...), password: str = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = %s AND password = %s;", (email, password))
    user = cur.fetchone()
    cur.close()
    conn.close()
    if user:
        redirect = RedirectResponse(url="/dashboard", status_code=303)
        redirect.set_cookie(key="user_session", value=email, path="/")
        return redirect
    return RedirectResponse(url="/?error=Invalid credentials.", status_code=303)

@app.get("/dashboard", response_class=HTMLResponse)
def view_dashboard(request: Request, user_session: str = Cookie(None)):
    if not user_session:
        return RedirectResponse(url="/", status_code=303)
        
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT tier FROM users WHERE email = %s;", (user_session,))
    user_record = cur.fetchone()
    user_tier = user_record['tier'] if user_record else "free"
    
    cur.execute("SELECT filename, records_count, uploaded_at FROM reports WHERE user_email = %s ORDER BY uploaded_at DESC LIMIT 5;", (user_session,))
    history = cur.fetchall()
    
    cur.execute("SELECT COUNT(*) as total FROM reports WHERE user_email = %s;", (user_session,))
    total_uploads = cur.fetchone()['total']
    
    cur.close()
    conn.close()
    
    calc_score = min(5.0, 1.0 + (total_uploads * 0.5))
    stars = "⭐" * int(calc_score)
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user_email": user_session,
        "user_tier": user_tier,
        "history": history,
        "rating_stars": stars,
        "rating_score": str(calc_score)
    })

@app.get("/logout")
def handle_logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(key="user_session", path="/")
    return response

# --- STRIPE INTEGRATION ---

@app.post("/create-checkout-session")
def create_checkout_session(user_session: str = Cookie(None)):
    if not user_session:
        return RedirectResponse(url="/", status_code=303)
    try:
        base_url = "https://net-tap.onrender.com" if os.getenv("RENDER") else "http://127.0.0.1:8000"
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': 'Dragon HMS - Enterprise Tier',
                        'description': 'Unlocks live agent telemetry, PCAP tracking, and secure payload downloads.',
                    },
                    'unit_amount': 49900,
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=f"{base_url}/dashboard?payment=success",
            cancel_url=f"{base_url}/dashboard?payment=cancelled",
            client_reference_id=user_session, 
        )
        return RedirectResponse(url=session.url, status_code=303)
    except Exception as e:
        return HTMLResponse(f"Error creating checkout session: {str(e)}", status_code=500)

@app.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    try:
        event = json.loads(payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid payload")

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        customer_email = session.get('client_reference_id')
        if customer_email:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("UPDATE users SET tier = 'enterprise' WHERE email = %s;", (customer_email,))
            conn.commit()
            cur.close()
            conn.close()
    return {"status": "success"}

# --- INTELLIGENCE API ---

@app.websocket("/ws/vitals")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections.remove(websocket)

@app.post("/api/agent/telemetry")
async def receive_telemetry(request: Request):
    agent_key = request.headers.get("X-Dragon-Agent-Key")
    if agent_key != AGENT_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid Agent Signature")

    data = await request.json()
    disconnected = []
    for connection in active_connections:
        try:
            await connection.send_json(data)
        except Exception:
            disconnected.append(connection)
    for conn in disconnected:
        active_connections.remove(conn)
    return {"status": "received", "code": 200}

@app.post("/upload-ledger")
async def upload_ledger(file: UploadFile = File(...), user_session: str = Cookie(None)):
    if not user_session:
        raise HTTPException(status_code=401, detail="Access Denied.")
        
    original_filename = file.filename
    extension = original_filename.split(".")[-1].lower() if "." in original_filename else ""
    file_content = await file.read()
    
    unique_filename = f"{int(time.time())}_{original_filename}"
    try:
        s3_client.put_object(Bucket=S3_BUCKET_NAME, Key=unique_filename, Body=file_content)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to upload to AWS Cloud Storage.")
    
    try:
        if extension == "csv":
            df = pd.read_csv(io.BytesIO(file_content))
        elif extension in ["xlsx", "xls"]:
            df = pd.read_excel(io.BytesIO(file_content))
        elif extension == "json":
            df = pd.read_json(io.BytesIO(file_content))
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format: .{extension}")
    except Exception as e:
        raise HTTPException(status_code=422, detail="Parse Error: Ensure file is structurally sound.")
        
    preview_html = df.head(5).to_html(index=False, border=0)
    numeric_cols = df.select_dtypes(include='number').columns.tolist()
    categorical_cols = df.select_dtypes(exclude='number').columns.tolist()
    
    chart_data = None
    if numeric_cols and categorical_cols:
        try:
            cat_col = categorical_cols[0]
            num_col = numeric_cols[0]
            summary = df.groupby(cat_col)[num_col].sum().reset_index().head(10)
            chart_data = {
                "labels": summary[cat_col].astype(str).tolist(),
                "values": summary[num_col].tolist(),
                "title": f"Sum of {num_col} by {cat_col}"
            }
        except Exception as graph_err:
            pass
            
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO reports (filename, records_count, user_email) VALUES (%s, %s, %s);",
            (unique_filename, len(df), user_session)
        )
        conn.commit()
    except Exception as db_err:
        conn.rollback()
    finally:
        cur.close()
        conn.close()

    return {
        "status": "success",
        "ingestion_metadata": {
            "filename": unique_filename,
            "format_detected": extension,
            "total_records_processed": len(df)
        },
        "preview_html": preview_html,
        "chart_data": chart_data
    }

@app.get("/api/load-ledger/{filename}")
def load_historical_ledger(filename: str, user_session: str = Cookie(None)):
    if not user_session:
        raise HTTPException(status_code=401, detail="Access Denied.")
        
    try:
        obj = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=filename)
        file_content = obj['Body'].read()
    except Exception as e:
        raise HTTPException(status_code=404, detail="Could not retrieve file from AWS.")
        
    extension = filename.split(".")[-1].lower() if "." in filename else ""
    
    try:
        if extension == "csv":
            df = pd.read_csv(io.BytesIO(file_content))
        elif extension in ["xlsx", "xls"]:
            df = pd.read_excel(io.BytesIO(file_content))
        elif extension == "json":
            df = pd.read_json(io.BytesIO(file_content))
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format: .{extension}")
    except Exception as e:
        raise HTTPException(status_code=422, detail="Parse Error: Ensure file is structurally sound.")
        
    preview_html = df.head(5).to_html(index=False, border=0)
    numeric_cols = df.select_dtypes(include='number').columns.tolist()
    categorical_cols = df.select_dtypes(exclude='number').columns.tolist()
    
    chart_data = None
    if numeric_cols and categorical_cols:
        try:
            cat_col = categorical_cols[0]
            num_col = numeric_cols[0]
            summary = df.groupby(cat_col)[num_col].sum().reset_index().head(10)
            chart_data = {
                "labels": summary[cat_col].astype(str).tolist(),
                "values": summary[num_col].tolist(),
                "title": f"Sum of {num_col} by {cat_col}"
            }
        except Exception as graph_err:
            pass

    return {
        "status": "success",
        "ingestion_metadata": {
            "filename": filename,
            "format_detected": extension,
            "total_records_processed": len(df)
        },
        "preview_html": preview_html,
        "chart_data": chart_data
    }

@app.get("/download/{filename}")
def download_file(filename: str, user_session: str = Cookie(None)):
    if not user_session:
        return RedirectResponse(url="/", status_code=303)
    if filename.startswith("dragon_agent"):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT tier FROM users WHERE email = %s;", (user_session,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        if not user or user['tier'] != 'enterprise':
            raise HTTPException(status_code=403, detail="Enterprise subscription required to download agent payload.")
    try:
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET_NAME, 'Key': filename},
            ExpiresIn=3600
        )
        return RedirectResponse(url=presigned_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Could not retrieve file from AWS.")
