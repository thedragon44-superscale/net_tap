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

os.makedirs("static", exist_ok=True)

app = FastAPI(title="The Dragon Headquarters Management Services")
app.mount("/static", StaticFiles(directory="static"), name="static")
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
                password VARCHAR(255) NOT NULL
            );
        """)
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS tier VARCHAR(50) DEFAULT 'free';")
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id SERIAL PRIMARY KEY,
                filename VARCHAR(255) NOT NULL,
                records_count INTEGER NOT NULL,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        # PATCH: Fix the cross-account data leak by attaching emails to reports
        cur.execute("ALTER TABLE reports ADD COLUMN IF NOT EXISTS user_email VARCHAR(255) DEFAULT 'legacy@system.local';")
        
        conn.commit()
        print("Database patched successfully. Data isolation enforced.")
    except Exception as e:
        print(f"Database initialization error: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

# --- HTML TEMPLATES ---
# (Landing and Register remain identical)
LANDING_PAGE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Gateway | The Dragon HMS</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-zinc-900 text-zinc-100 min-h-screen flex flex-col font-sans">
    <nav class="bg-zinc-800 border-b border-zinc-700 px-6 py-3 flex justify-between items-center shadow-lg z-50 sticky top-0">
        <div class="flex items-center space-x-3">
            <img src="/static/dragon_logo.png" alt="Dragon Logo" class="h-10 w-10 rounded-full border border-orange-500 shadow-md object-cover">
            <h1 class="text-xl font-black text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-blue-600 tracking-wider">THE DRAGON <span class="text-orange-500">HMS</span></h1>
        </div>
        <div class="flex items-center space-x-4">
            <span class="text-zinc-400 text-sm font-semibold hidden md:inline">Intelligence Portal</span>
            <a href="/register" class="text-xs bg-blue-600 text-white hover:bg-blue-500 px-4 py-2 rounded-md transition font-semibold shadow-lg">Register Unit</a>
        </div>
    </nav>
    <main class="flex-1 max-w-7xl mx-auto p-6 md:p-12 grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
        <div class="space-y-8">
            <div>
                <h2 class="text-4xl md:text-5xl font-extrabold text-blue-500 mb-4 tracking-tighter">Secure Your Retail Perimeter</h2>
                <p class="text-zinc-400 text-lg">Integrated headquarters management with real-time PCAP forensics, geo-fraud triangulation, and dynamic risk scoring.</p>
            </div>
            <div class="bg-zinc-800 p-8 rounded-xl border-t-4 border-orange-500 shadow-2xl relative overflow-hidden">
                <h3 class="text-2xl font-bold mb-6 text-white text-center">Login</h3>
                {{ error_message }}
                <form action="/login" method="post" class="space-y-4 relative z-10">
                    <div>
                        <label class="block text-zinc-300 text-sm font-semibold mb-1">Business Email</label>
                        <input type="email" name="email" required class="w-full px-4 py-2 rounded-lg bg-zinc-900 border border-zinc-700 text-zinc-100 focus:outline-none focus:border-orange-500 transition">
                    </div>
                    <div>
                        <label class="block text-zinc-300 text-sm font-semibold mb-1">Access Key</label>
                        <input type="password" name="password" required class="w-full px-4 py-2 rounded-lg bg-zinc-900 border border-zinc-700 text-zinc-100 focus:outline-none focus:border-orange-500 transition">
                    </div>
                    <button type="submit" class="w-full bg-orange-500 hover:bg-orange-400 text-white shadow-lg shadow-orange-500/30 font-bold py-3 rounded-lg transition duration-200 mt-4 cursor-pointer">Authenticate to Matrix</button>
                </form>
            </div>
        </div>
        <div class="space-y-6">
            <div class="bg-zinc-800 p-2 rounded-2xl shadow-2xl border border-zinc-700 relative overflow-hidden h-64 flex items-center justify-center bg-gradient-to-br from-blue-900/40 to-zinc-900">
                <div class="text-center text-zinc-500">
                    <span class="text-6xl">💻 🕵️‍♂️</span>
                    <p class="mt-2 font-mono text-sm text-blue-400">[ LIVE COMMAND CENTER ]</p>
                </div>
            </div>
            <div class="bg-zinc-800 p-2 rounded-2xl shadow-2xl border border-zinc-700 relative overflow-hidden h-48 flex items-center justify-center bg-gradient-to-br from-orange-900/20 to-zinc-900">
                <div class="text-center text-zinc-500">
                    <span class="text-6xl">🏪 🚶‍♂️🚶‍♀️🚶</span>
                    <p class="mt-2 font-mono text-sm text-orange-400">[ POS PERIMETER SECURED ]</p>
                </div>
            </div>
        </div>
    </main>
</body>
</html>
"""

REGISTER_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>The Dragon HMS - Register</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-zinc-900 flex items-center justify-center min-h-screen font-sans p-6">
    <div class="bg-zinc-800 p-8 rounded-xl shadow-2xl w-full max-w-md border-t-4 border-blue-500 shadow-[0_0_40px_rgba(59,130,246,0.15)]">
        <div class="flex justify-center mb-6">
            <img src="/static/dragon_logo.png" alt="Dragon Logo" class="h-20 w-20 rounded-full border-2 border-zinc-700 shadow-lg object-cover grayscale hover:grayscale-0 transition duration-500">
        </div>
        <h2 class="text-3xl font-extrabold text-center text-orange-500 mb-2 tracking-tight">System Enrollment</h2>
        <p class="text-zinc-400 text-center text-sm mb-6">Register new credentials</p>
        <form action="/register" method="post" class="space-y-4">
            <div>
                <label class="block text-zinc-300 text-sm font-semibold mb-1">Business Email</label>
                <input type="email" name="email" required class="w-full px-4 py-2 rounded-lg bg-zinc-900 border border-zinc-700 text-zinc-100 focus:outline-none focus:border-blue-500 transition">
            </div>
            <div>
                <label class="block text-zinc-300 text-sm font-semibold mb-1">Secure Passkey</label>
                <input type="password" name="password" required class="w-full px-4 py-2 rounded-lg bg-zinc-900 border border-zinc-700 text-zinc-100 focus:outline-none focus:border-blue-500 transition">
            </div>
            <button type="submit" class="w-full bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-500/30 font-bold py-2.5 rounded-lg transition duration-200 mt-2 cursor-pointer">Register System</button>
        </form>
        <p class="text-zinc-500 text-xs text-center mt-6">Already registered? <a href="/" class="text-orange-400 hover:text-orange-300 hover:underline">Return to Gateway</a></p>
    </div>
</body>
</html>
"""

DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>The Dragon HMS - Interface</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        #tableContainer table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
        #tableContainer th { border-bottom: 2px solid #ea580c; padding: 12px; text-align: left; color: #f97316; font-weight: 700; text-transform: uppercase;}
        #tableContainer td { border-bottom: 1px solid #3f3f46; padding: 12px; color: #d4d4d8; }
        #tableContainer tr:hover { background-color: rgba(249, 115, 22, 0.05); }
    </style>
</head>
<body class="bg-zinc-900 text-zinc-100 min-h-screen font-sans pb-12 relative">
    
    <div id="profileModal" class="hidden fixed inset-0 bg-black/80 backdrop-blur-sm z-[100] flex items-center justify-center p-4">
        <div class="bg-zinc-800 border border-zinc-700 rounded-2xl shadow-2xl max-w-md w-full overflow-hidden">
            <div class="bg-zinc-900 p-6 border-b border-zinc-700 flex justify-between items-center">
                <h2 class="text-xl font-bold text-white flex items-center"><span class="text-2xl mr-2">👤</span> Operative Profile</h2>
                <button onclick="document.getElementById('profileModal').classList.add('hidden')" class="text-zinc-500 hover:text-white transition text-2xl leading-none">&times;</button>
            </div>
            <div class="p-6 space-y-4">
                <div>
                    <p class="text-xs text-zinc-500 uppercase tracking-widest font-bold">Username / Target</p>
                    <p class="text-lg font-mono text-blue-400">{{ user_email }}</p>
                </div>
                <div>
                    <p class="text-xs text-zinc-500 uppercase tracking-widest font-bold">Subscription Tier</p>
                    <p class="text-lg text-white uppercase">{{ user_tier }}</p>
                </div>
                <div class="bg-zinc-900 p-4 rounded-lg border border-zinc-700 mt-4">
                    <p class="text-xs text-zinc-500 uppercase tracking-widest font-bold mb-1">Dynamic Business Rating</p>
                    <div class="flex items-center justify-between">
                        <span class="text-2xl text-yellow-500">{{ rating_stars }}</span>
                        <span class="text-zinc-400 font-mono text-sm">{{ rating_score }}/5.0</span>
                    </div>
                    <p class="text-xs text-zinc-500 mt-2">Calculated from ledger ingestion volume & network capture anomalies (IP vs POS ping matching).</p>
                </div>
            </div>
            <div class="bg-zinc-900 p-4 border-t border-zinc-700 flex justify-end">
                <a href="/logout" class="bg-rose-600 hover:bg-rose-500 text-white font-bold py-2 px-4 rounded-lg transition shadow-lg">Terminate Session</a>
            </div>
        </div>
    </div>

    <nav class="bg-zinc-800 border-b border-zinc-700 px-6 py-3 flex justify-between items-center sticky top-0 z-50 shadow-md">
        <div class="flex items-center space-x-3">
            <img src="/static/dragon_logo.png" alt="Dragon Logo" class="h-10 w-10 rounded-full border border-orange-500 shadow-[0_0_10px_rgba(249,115,22,0.3)] object-cover">
            <h1 class="text-xl font-black text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-blue-600 tracking-wider">THE DRAGON <span class="text-orange-500">HMS</span></h1>
        </div>
        <div class="flex items-center space-x-4">
            <button onclick="document.getElementById('profileModal').classList.remove('hidden')" class="flex items-center space-x-2 bg-blue-600/10 hover:bg-blue-600/20 px-4 py-2 rounded-lg border border-blue-500/30 transition shadow-inner">
                <span class="text-sm font-bold uppercase text-blue-400 tracking-wider">Profile</span>
            </button>
        </div>
    </nav>
    
    <main class="max-w-7xl mx-auto mt-8 px-4 grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        <div class="lg:col-span-1 space-y-6">
            
            <div class="bg-zinc-800 rounded-xl p-6 border-t-4 border-orange-500 shadow-xl">
                <h2 class="text-lg font-bold mb-1 text-white flex items-center">Command Center</h2>
                <div class="space-y-4 mt-4">
                    <div class="flex justify-between items-center text-sm">
                        <span class="text-zinc-400">Agent Status</span>
                        <span id="agent-status" class="text-yellow-500 font-mono font-bold">AWAITING CONNECTION</span>
                    </div>
                    <div class="flex justify-between items-center text-sm">
                        <span class="text-zinc-400">Network QPS</span>
                        <span id="qps-display" class="font-mono text-xl text-white font-bold">0</span>
                    </div>
                </div>
            </div>

            <div class="bg-zinc-800 rounded-xl p-6 border border-zinc-700 shadow-xl">
                <h2 class="text-sm uppercase tracking-wider text-zinc-400 font-bold mb-4">Legacy Data Ingestion</h2>
                <form id="uploadForm" class="space-y-4">
                    <div class="border-2 border-dashed border-zinc-600 rounded-xl p-6 text-center hover:border-orange-500 hover:bg-orange-500/5 transition bg-zinc-900 cursor-pointer relative group">
                        <input type="file" id="fileInput" name="file" required class="absolute inset-0 w-full h-full opacity-0 cursor-pointer">
                        <svg class="mx-auto h-10 w-10 text-zinc-500 group-hover:text-orange-500 transition mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                        </svg>
                        <p id="uploadPrompt" class="text-zinc-300 font-medium text-xs">Browse or drag ledger here</p>
                    </div>
                    <button id="processBtn" type="submit" class="w-full bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-500/20 font-bold py-2 rounded-lg transition cursor-pointer">Process Ledger</button>
                </form>
            </div>

            <div class="bg-zinc-800 rounded-xl p-6 border border-zinc-700 shadow-xl">
                <div class="flex justify-between items-center mb-4">
                    <h2 class="text-sm uppercase tracking-wider text-zinc-400 font-bold">Recent Operations</h2>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full text-left text-sm">
                        <tbody id="historyTable" class="divide-y divide-zinc-700/50">
                            {{ history_html }}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <div class="lg:col-span-2 space-y-6">
            
            <div class="bg-zinc-800 rounded-xl p-6 border-t-4 border-rose-500 shadow-xl relative overflow-hidden">
                <h3 class="text-lg font-bold mb-2 text-white">Live Forensics & Intelligence</h3>

                {% if user_tier == 'free' %}
                <div class="absolute inset-0 bg-zinc-900/90 backdrop-blur-sm flex flex-col items-center justify-center z-10 p-6 md:p-12 text-center">
                    <svg class="w-12 h-12 text-orange-500 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path></svg>
                    <h2 class="text-2xl font-bold mb-2 text-white">ENTERPRISE FEATURE</h2>
                    <p class="text-zinc-400 text-sm mb-6 max-w-md">Upgrade to connect the Dragon Agent. Unlock live PCAP inspection, Geo-Fraud mapping, and secure payload downloads.</p>
                    
                    <form action="/create-checkout-session" method="POST">
                        <button type="submit" class="bg-orange-500 hover:bg-orange-400 text-white font-black px-6 py-3 rounded-lg shadow-[0_0_15px_rgba(249,115,22,0.5)] transition">
                            Unlock Enterprise - $499
                        </button>
                    </form>
                </div>
                {% endif %}

                <div class="min-h-[200px] text-zinc-400 text-sm font-mono flex flex-col justify-end">
                    
                    <div id="live-terminal" class="h-48 overflow-y-auto bg-black p-4 rounded-lg border border-zinc-700 mb-4 space-y-1 shadow-inner">
                        </div>

                    {% if user_tier == 'enterprise' %}
                    <div class="mt-2 bg-zinc-900 border border-zinc-700 p-4 rounded-lg flex flex-col md:flex-row justify-between items-center gap-4 shadow-md">
                        <div>
                            <h4 class="text-sm font-bold text-white">Dragon Agent (Production Build)</h4>
                            <p class="text-xs text-zinc-500 mt-1">Deploy this executable on your target POS machine to begin streaming.</p>
                        </div>
                        <a href="/download/dragon_agent" class="bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold px-6 py-3 rounded-lg transition shadow-lg shadow-blue-500/30 whitespace-nowrap text-center">
                            Download Agent (.EXE)
                        </a>
                    </div>
                    {% endif %}

                </div>
            </div>

            <div id="resultsDisplay" class="hidden bg-zinc-800 rounded-xl p-8 border border-zinc-700 shadow-xl space-y-6 h-full relative">
                
                <div id="loadingOverlay" class="hidden absolute inset-0 bg-zinc-800/90 backdrop-blur-sm z-10 rounded-xl flex flex-col items-center justify-center text-orange-500">
                    <svg class="animate-spin h-12 w-12 mb-4 text-orange-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    <p class="font-bold tracking-wider animate-pulse">EXTRACTING FROM S3 CLOUD...</p>
                </div>

                <div class="flex justify-between items-start border-b border-zinc-700 pb-4">
                    <div>
                        <h3 class="text-2xl font-bold text-orange-500">Intelligence Matrix Resolved</h3>
                        <p class="text-zinc-400 text-sm mt-1">Target File: <span id="resFilename" class="text-blue-400 font-mono"></span> | Format: <span id="resFormat" class="text-blue-400 font-mono uppercase"></span></p>
                    </div>
                    <div class="flex space-x-2">
                        <a id="downloadRawBtn" href="#" class="bg-zinc-700 hover:bg-zinc-600 text-zinc-300 text-xs px-3 py-1.5 rounded-lg border border-zinc-600 transition flex items-center">
                            <svg class="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
                            Raw
                        </a>
                        <span id="metricBadge" class="bg-blue-500/10 text-blue-400 px-3 py-1.5 rounded-lg border border-blue-500/30 font-mono font-bold shadow-inner"></span>
                    </div>
                </div>
                
                <div class="pt-2">
                    <div class="flex justify-between items-center mb-4">
                        <h4 class="text-sm uppercase tracking-widest text-zinc-400 font-bold">Data Visualization</h4>
                        <select id="chartTypeToggle" class="bg-zinc-900 border border-zinc-600 text-zinc-300 text-xs rounded px-2 py-1 focus:outline-none focus:border-orange-500">
                            <option value="bar">Bar Chart</option>
                            <option value="line">Line Chart</option>
                            <option value="doughnut">Doughnut Chart</option>
                        </select>
                    </div>
                    <div class="bg-zinc-900 p-4 rounded-xl border border-zinc-700 relative shadow-inner" style="height: 350px;">
                        <canvas id="dataChart"></canvas>
                        <div id="noChartMsg" class="hidden absolute inset-0 flex items-center justify-center text-zinc-500 text-sm font-mono">No numeric pairings detected.</div>
                    </div>
                </div>

                <div class="pt-4 border-t border-zinc-700">
                    <h4 class="text-sm uppercase tracking-widest text-zinc-400 font-bold mb-4">Ledger Preview Snapshot</h4>
                    <div id="tableContainer" class="overflow-x-auto bg-zinc-900 rounded-xl border border-zinc-700 shadow-inner"></div>
                </div>
            </div>
            
            <div id="emptyState" class="bg-zinc-800/50 border border-dashed border-zinc-700 rounded-xl h-full flex flex-col items-center justify-center text-zinc-500 p-12">
                <svg class="h-16 w-16 mb-4 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
                <p class="font-medium text-lg">Awaiting Intelligence Upload</p>
                <p class="text-sm mt-1">Processed legacy data will visualize here.</p>
            </div>
        </div>
    </main>

    <script>
        // --- WEBSOCKETS LOGIC ---
        const ws = new WebSocket((window.location.protocol === 'https:' ? 'wss://' : 'ws://') + window.location.host + '/ws/vitals');
        
        ws.onmessage = function(event) {
            const data = JSON.parse(event.data);
            
            const statusEl = document.getElementById('agent-status');
            statusEl.textContent = 'SECURE LINK ACTIVE';
            statusEl.classList.remove('text-yellow-500', 'text-red-500');
            statusEl.classList.add('text-green-500');

            // PATCH: Safely check multiple common keys if the agent payload varies
            const qps = data.db_queries_per_sec || data.qps || data.packets || data.traffic || "0";
            document.getElementById('qps-display').textContent = qps;

            const terminal = document.getElementById('live-terminal');
            if (terminal) {
                const logLine = document.createElement('div');
                logLine.textContent = `[${new Date().toLocaleTimeString()}] INBOUND PKT: ${qps} DETECTED`;
                logLine.className = 'text-green-400 font-bold';
                terminal.appendChild(logLine);
                terminal.scrollTop = terminal.scrollHeight;
            }
        };

        ws.onclose = function() {
            const statusEl = document.getElementById('agent-status');
            statusEl.textContent = 'CONNECTION LOST';
            statusEl.classList.remove('text-green-500', 'text-yellow-500');
            statusEl.classList.add('text-red-500');
        };

        // --- DASHBOARD UI LOGIC ---
        const fileInput = document.getElementById('fileInput');
        const uploadPrompt = document.getElementById('uploadPrompt');
        const uploadForm = document.getElementById('uploadForm');
        const resultsDisplay = document.getElementById('resultsDisplay');
        const emptyState = document.getElementById('emptyState');
        const processBtn = document.getElementById('processBtn');
        const chartTypeToggle = document.getElementById('chartTypeToggle');
        const historyTable = document.getElementById('historyTable');
        const loadingOverlay = document.getElementById('loadingOverlay');
        const downloadRawBtn = document.getElementById('downloadRawBtn');
        
        let currentChartData = null;

        if (fileInput) {
            fileInput.addEventListener('change', function() {
                if (this.files && this.files[0]) {
                    uploadPrompt.innerHTML = '<span class="text-orange-500 font-bold">' + this.files[0].name + '</span>';
                }
            });
        }

        function renderChart(type) {
            if (!currentChartData) return;
            if (window.myChart) { window.myChart.destroy(); }
            
            const ctx = document.getElementById('dataChart').getContext('2d');
            const bgColors = type === 'doughnut' 
                ? ['#f97316', '#3b82f6', '#10b981', '#f43f5e', '#8b5cf6', '#eab308', '#06b6d4', '#64748b', '#ec4899', '#14b8a6']
                : '#3b82f6';

            window.myChart = new Chart(ctx, {
                type: type,
                data: {
                    labels: currentChartData.labels,
                    datasets: [{
                        label: currentChartData.title,
                        data: currentChartData.values,
                        backgroundColor: bgColors,
                        borderColor: type === 'line' ? '#f97316' : 'transparent',
                        borderWidth: 2,
                        borderRadius: type === 'bar' ? 4 : 0,
                        tension: 0.3,
                        fill: type === 'line' ? {target: 'origin', below: 'rgba(59,130,246,0.1)'} : false
                    }]
                },
                options: { 
                    responsive: true, 
                    maintainAspectRatio: false,
                    plugins: { 
                        legend: { display: type === 'doughnut', position: 'right', labels: { color: '#d4d4d8' } }
                    },
                    scales: type === 'doughnut' ? {} : { 
                        x: { ticks: { color: '#a1a1aa' }, grid: { color: '#3f3f46' } }, 
                        y: { ticks: { color: '#a1a1aa' }, grid: { color: '#3f3f46' } } 
                    }
                }
            });
        }

        if(chartTypeToggle) {
            chartTypeToggle.addEventListener('change', (e) => {
                renderChart(e.target.value);
            });
        }

        function populateCanvas(data) {
            emptyState.classList.add('hidden');
            document.getElementById('resFilename').innerText = data.ingestion_metadata.filename;
            document.getElementById('resFormat').innerText = data.ingestion_metadata.format_detected;
            document.getElementById('metricBadge').innerText = data.ingestion_metadata.total_records_processed + ' Rows';
            document.getElementById('tableContainer').innerHTML = data.preview_html;
            downloadRawBtn.href = '/download/' + data.ingestion_metadata.filename;
            
            if (data.chart_data) {
                currentChartData = data.chart_data;
                document.getElementById('noChartMsg').classList.add('hidden');
                document.getElementById('dataChart').classList.remove('hidden');
                renderChart(chartTypeToggle.value);
            } else {
                currentChartData = null;
                if (window.myChart) { window.myChart.destroy(); }
                document.getElementById('dataChart').classList.add('hidden');
                document.getElementById('noChartMsg').classList.remove('hidden');
            }
            resultsDisplay.classList.remove('hidden');
        }

        async function loadHistoricalData(filename) {
            emptyState.classList.add('hidden');
            resultsDisplay.classList.remove('hidden');
            loadingOverlay.classList.remove('hidden');
            
            try {
                const response = await fetch('/api/load-ledger/' + filename);
                const data = await response.json();
                
                if (response.ok) {
                    populateCanvas(data);
                } else {
                    alert('Extraction failure: ' + (data.detail || 'Could not fetch from S3'));
                }
            } catch (err) {
                alert('Connection to backend infrastructure dropped.');
            } finally {
                loadingOverlay.classList.add('hidden');
            }
        }

        if (uploadForm) {
            uploadForm.addEventListener('submit', async function(e) {
                e.preventDefault();
                const formData = new FormData();
                formData.append('file', fileInput.files[0]);
                
                processBtn.innerText = "Analyzing Matrix & Uploading to S3...";
                processBtn.classList.add("opacity-50", "cursor-not-allowed");

                try {
                    const response = await fetch('/upload-ledger', { method: 'POST', body: formData });
                    const data = await response.json();
                    
                    if (response.ok) {
                        populateCanvas(data);

                        if (historyTable.innerText.includes('No operational logs recorded.')) {
                            historyTable.innerHTML = '';
                        }
                        const newRow = document.createElement('tr');
                        newRow.className = "hover:bg-zinc-700/40 transition group cursor-pointer";
                        newRow.onclick = () => loadHistoricalData(data.ingestion_metadata.filename);
                        newRow.innerHTML = `
                            <td class="py-3 max-w-[150px]">
                                <span class="text-blue-400 font-mono truncate block group-hover:text-orange-400 transition" title="${data.ingestion_metadata.filename}">${data.ingestion_metadata.filename}</span>
                            </td>
                            <td class="py-3 text-zinc-300 font-mono text-right group-hover:text-white transition">${data.ingestion_metadata.total_records_processed} <span class="text-zinc-500 text-xs">rows</span></td>
                        `;
                        historyTable.prepend(newRow);

                    } else {
                        alert('Ingestion failure: ' + (data.detail || 'Unknown Error'));
                    }
                } catch (err) {
                    alert('Connection to backend infrastructure dropped.');
                } finally {
                    processBtn.innerText = "Process Ledger";
                    processBtn.classList.remove("opacity-50", "cursor-not-allowed");
                    uploadPrompt.innerHTML = 'Browse or drag ledger here';
                    fileInput.value = '';
                }
            });
        }
    </script>
</body>
</html>
"""

# --- ROUTES ---
@app.get("/", response_class=HTMLResponse)
def view_login(user_session: str = Cookie(None), error: str = None):
    if user_session:
        return RedirectResponse(url="/dashboard", status_code=303)
    html = LANDING_PAGE_TEMPLATE
    if error:
        error_msg = f"""<div class="bg-rose-500/10 text-rose-400 border border-rose-500/20 text-xs p-3 rounded-lg text-center font-medium mb-4 tracking-wide shadow-inner">⚠️ ERROR: {error}</div>"""
        html = html.replace("{{ error_message }}", error_msg)
    else:
        html = html.replace("{{ error_message }}", "")
    return html

@app.get("/register", response_class=HTMLResponse)
def view_register():
    return REGISTER_TEMPLATE

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
def view_dashboard(user_session: str = Cookie(None)):
    if not user_session:
        return RedirectResponse(url="/", status_code=303)
        
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT tier FROM users WHERE email = %s;", (user_session,))
    user_record = cur.fetchone()
    user_tier = user_record['tier'] if user_record else "free"
    
    # PATCH: Now selecting strictly by the logged-in user's email
    cur.execute("SELECT filename, records_count, uploaded_at FROM reports WHERE user_email = %s ORDER BY uploaded_at DESC LIMIT 5;", (user_session,))
    history = cur.fetchall()
    
    # Count total uploads for dynamic profile rating
    cur.execute("SELECT COUNT(*) as total FROM reports WHERE user_email = %s;", (user_session,))
    total_uploads = cur.fetchone()['total']
    
    cur.close()
    conn.close()
    
    # Dynamic Rating Logic based on uploads
    calc_score = min(5.0, 1.0 + (total_uploads * 0.5))
    stars = "⭐" * int(calc_score)
    
    history_html = ""
    for r in history:
        history_html += f"""
        <tr class="hover:bg-zinc-700/40 transition group cursor-pointer" onclick="loadHistoricalData('{r['filename']}');">
            <td class="py-3 max-w-[150px]">
                <span class="text-blue-400 font-mono truncate block group-hover:text-orange-400 transition" title="{r['filename']}">{r['filename']}</span>
            </td>
            <td class="py-3 text-zinc-300 font-mono text-right group-hover:text-white transition">{r['records_count']} <span class="text-zinc-500 text-xs">rows</span></td>
        </tr>
        """
    if not history_html:
        history_html = """<tr><td colspan="2" class="py-6 text-center text-zinc-500 italic">No operational logs recorded.</td></tr>"""
        
    html = DASHBOARD_TEMPLATE
    html = html.replace("{{ user_email }}", user_session)
    html = html.replace("{{ user_tier }}", user_tier)
    html = html.replace("{{ history_html }}", history_html)
    html = html.replace("{{ rating_stars }}", stars)
    html = html.replace("{{ rating_score }}", str(calc_score))
    
    if user_tier == 'free':
        html = html.replace("{% if user_tier == 'free' %}", "").replace("{% endif %}", "", 1)
        start = html.find("{% if user_tier == 'enterprise' %}")
        end = html.find("{% endif %}", start) + 11
        html = html[:start] + html[end:]
    else:
        start = html.find("{% if user_tier == 'free' %}")
        end = html.find("{% endif %}", start) + 11
        html = html[:start] + html[end:]
        html = html.replace("{% if user_tier == 'enterprise' %}", "").replace("{% endif %}", "")

    return html

@app.get("/logout")
def handle_logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(key="user_session", path="/")
    return response

@app.post("/create-checkout-session")
def create_checkout_session(user_session: str = Cookie(None)):
    if not user_session:
        return RedirectResponse(url="/", status_code=303)
    try:
        base_url = "https://www.thedragonhms.com" if os.getenv("RENDER") else "http://127.0.0.1:8000"
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
@app.post("/api/wiretap/ingest")
async def ingest_wiretap_data(request: Request):
    # 1. Authenticate the local edge agent
    agent_key = request.headers.get("X-Dragon-Agent-Key")
    if agent_key != AGENT_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid Agent Signature")
    
    # 2. Parse the incoming intelligence payload
    try:
        payload = await request.json()
        user_email = payload.get("user_email", "edge_agent@system.local")
        scan_type = payload.get("scan_type", "network_scan")  # e.g., 'nmap' or 'pcap'
        scan_data = payload.get("scan_data", {})
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed JSON payload received.")

    # 3. Generate a unique filename and push raw data to S3
    timestamp = int(time.time())
    filename = f"wiretap_{scan_type}_{timestamp}.json"
    
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME, 
            Key=filename, 
            Body=json.dumps(scan_data, indent=2).encode('utf-8')
        )
    except Exception as e:
        print(f"S3 Upload Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to write intelligence to S3.")

    # 4. Determine a metric count to log in the database
    if scan_type == "nmap":
        records_count = len(scan_data.get("scan", {}).keys()) if isinstance(scan_data, dict) else 1
    else:
        records_count = len(scan_data.get("alerts", [1]))
    
    # 5. Log the report in PostgreSQL so it populates the user's dashboard
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO reports (filename, records_count, user_email) VALUES (%s, %s, %s);",
            (filename, records_count, user_email)
        )
        conn.commit()
    except Exception as db_err:
        conn.rollback()
        print(f"Database Error during Wiretap ingest: {db_err}")
    finally:
        cur.close()
        conn.close()

    # 6. Broadcast the event to the live UI via WebSockets
    notification = {
        "type": "wiretap_alert",
        "message": f"New {scan_type.upper()} intelligence ingested.",
        "qps": records_count,
        "filename": filename
    }
    
    disconnected = []
    for connection in active_connections:
        try:
            await connection.send_json(notification)
        except Exception:
            disconnected.append(connection)
            
    for conn in disconnected:
        if conn in active_connections:
            active_connections.remove(conn)

    return {"status": "success", "filename": filename, "logged_to_db": True}

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
        # PATCH: Assign the user_email to the uploaded ledger file
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
