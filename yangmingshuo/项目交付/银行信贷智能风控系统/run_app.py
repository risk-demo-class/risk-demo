import subprocess,sys
from pathlib import Path
root=Path(__file__).parent
if not (root/"data/bank_risk.db").exists():
    subprocess.check_call([sys.executable,"scripts/init_db.py"],cwd=root)
    subprocess.check_call([sys.executable,"scripts/gen_business_data.py"],cwd=root)
subprocess.call([sys.executable,"-m","uvicorn","app.api:app","--host","127.0.0.1","--port","8000","--reload"],cwd=root)

