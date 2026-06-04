# =============================================
# SMART KOS DATA WAREHOUSE — GOOGLE COLAB
# =============================================
# Buka Google Colab, buat notebook baru.
# Salin 2 cell di bawah ke notebook tersebut.
# =============================================

# ========== CELL 1 ==========
# Salin baris-baris berikut (tanpa tanda #) ke cell pertama:
#
# !git clone https://github.com/Zerosab0/Warehouse-Project.git
# %cd Warehouse-Project
# !pip install -q streamlit duckdb pandas plotly pyngrok


# ========== CELL 2 ==========
# Salin kode di bawah ini ke cell kedua, lalu Run:

import subprocess, time
from pyngrok import ngrok

# *** GANTI DENGAN TOKEN NGROK KAMU ***
NGROK_TOKEN = "PASTE_TOKEN_DISINI"

ngrok.set_auth_token(NGROK_TOKEN)

proc = subprocess.Popen([
    "streamlit", "run", "app.py",
    "--server.port=8501",
    "--server.headless=true",
    "--server.address=0.0.0.0",
    "--browser.gatherUsageStats=false"
])

time.sleep(8)

public_url = ngrok.connect(8501)
print("=" * 50)
print(f"BUKA DASHBOARD: {public_url}")
print("=" * 50)

# Biarkan berjalan, jangan close cell ini
try:
    proc.wait()
except KeyboardInterrupt:
    proc.terminate()
    ngrok.kill()
