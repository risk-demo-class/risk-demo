from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.database import Base,engine
import app.models_business,app.models_risk
Base.metadata.create_all(engine)
print(f"init_db 完成，共创建 {len(Base.metadata.tables)} 张表")

