import json
from fastapi import Depends,FastAPI,Form,HTTPException,Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models_risk import RiskAssessment,RiskCase
from app.service.event import process_event

app=FastAPI(title="银行信贷智能风控系统",version="1.0.0"); templates=Jinja2Templates("templates")
def get_db():
    db=SessionLocal()
    try: yield db
    finally: db.close()
@app.get("/health")
def health(): return {"status":"ok"}
@app.get("/",response_class=HTMLResponse)
def dashboard(request:Request,db:Session=Depends(get_db)):
    rows=db.scalars(select(RiskAssessment).order_by(RiskAssessment.created_at.desc()).limit(10)).all()
    stats={"total":db.scalar(select(func.count()).select_from(RiskAssessment)) or 0,"high":db.scalar(select(func.count()).select_from(RiskAssessment).where(RiskAssessment.score>=50)) or 0,"cases":db.scalar(select(func.count()).select_from(RiskCase).where(RiskCase.status=="待审核")) or 0}
    return templates.TemplateResponse(request,"dashboard.html",{"rows":rows,"stats":stats})
@app.get("/risk-check",response_class=HTMLResponse)
def check_page(request:Request): return templates.TemplateResponse(request,"risk_check.html",{})
@app.post("/api/risk-check")
def risk_check(event_type:str=Form(...),source_id:str=Form(...),user_id:str|None=Form(None),db:Session=Depends(get_db)):
    try:
        x=process_event(db,event_type,source_id,user_id); return {"assessment_id":x.assessment_id,"score":x.score,"risk_level":x.risk_level,"decision":x.decision,"rules":json.loads(x.hit_rules),"features":json.loads(x.features)}
    except ValueError as e: raise HTTPException(400,str(e))
@app.get("/cases",response_class=HTMLResponse)
def cases(request:Request,db:Session=Depends(get_db)): return templates.TemplateResponse(request,"cases.html",{"rows":db.scalars(select(RiskCase).order_by(RiskCase.created_at.desc())).all()})
@app.get("/assessments",response_class=HTMLResponse)
def assessments(request:Request,db:Session=Depends(get_db)): return templates.TemplateResponse(request,"assessments.html",{"rows":db.scalars(select(RiskAssessment).order_by(RiskAssessment.created_at.desc())).all()})

