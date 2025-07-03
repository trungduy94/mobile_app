# ---------------------------  main.py  ---------------------------------------
import os, io, base64
from datetime import datetime, date, time, timedelta
from typing import List

import pandas as pd
import matplotlib.pyplot as plt
import yagmail

from fastapi import (
    FastAPI, HTTPException, Path, Body, BackgroundTasks
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, conint
from sqlalchemy import (
    create_engine, Column, Integer, Float, DateTime, Time,
    PrimaryKeyConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# ──────────────────────────────────────────────────────────────────────────────
# 1) DATABASE
# ──────────────────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://duytrung:SMaYMPiWq8yob1SBSctheuqlnQSjppR6@dpg-d1ihqlje5dus739s3hfg-a.singapore-postgres.render.com/dbappmobile"
)
engine  = create_engine(DATABASE_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine)
Base    = declarative_base()

# ──────────────────────────────────────────────────────────────────────────────
# 2) ORM MODELS
# ──────────────────────────────────────────────────────────────────────────────
class RelayOnLog(Base):
    __tablename__ = "relay_on_log"
    relay = Column(Integer)
    time  = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (PrimaryKeyConstraint('relay','time'),)

class RelayOffLog(Base):
    __tablename__ = "relay_off_log"
    relay = Column(Integer)
    time  = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (PrimaryKeyConstraint('relay','time'),)

class TempHumLog(Base):
    __tablename__ = "temp_hum_log"
    time      = Column(DateTime, primary_key=True, default=datetime.utcnow)
    nhiet_do  = Column(Float)
    do_am     = Column(Float)

class TempThreshold(Base):
    __tablename__ = "temp_threshold"
    id      = Column(Integer, primary_key=True, default=1)
    min_val = Column(Float)
    max_val = Column(Float)

class HumThreshold(Base):
    __tablename__ = "hum_threshold"
    id      = Column(Integer, primary_key=True, default=1)
    min_val = Column(Float)
    max_val = Column(Float)

class RelaySchedule(Base):
    __tablename__ = "relay_schedule"
    relay      = Column(Integer, primary_key=True)        # 1..4
    on_time    = Column(Time)                             # giờ bật
    duration_s = Column(Integer)                          # số giây bật

class RelayStatus(Base):
    __tablename__ = "relay_status"
    relay       = Column(Integer, primary_key=True)
    status      = Column(Integer)                         # 0 off, 1 on
    update_time = Column(DateTime, default=datetime.utcnow)

class OverTempLog(Base):
    __tablename__ = "over_temp_log"
    time  = Column(DateTime, primary_key=True, default=datetime.utcnow)
    value = Column(Float)

class OverHumLog(Base):
    __tablename__ = "over_hum_log"
    time  = Column(DateTime, primary_key=True, default=datetime.utcnow)
    value = Column(Float)

class RelayMode(Base):                                    # 0 auto / 1 manual
    __tablename__ = "relay_mode"
    relay       = Column(Integer, primary_key=True)
    mode        = Column(Integer, default=0)
    update_time = Column(DateTime, default=datetime.utcnow)

# ──────────────────────────────────────────────────────────────────────────────
# 3) FASTAPI
# ──────────────────────────────────────────────────────────────────────────────
app = FastAPI(title="Relay & Env API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"]
)

# ──────────────────────────────────────────────────────────────────────────────
# 4) SCHEMA
# ──────────────────────────────────────────────────────────────────────────────
class TempHumIn(BaseModel):
    nhiet_do: float
    do_am:   float
class TempHumOut(TempHumIn):
    time: datetime

class ThresholdIn(BaseModel):
    min_val: float
    max_val: float
class ThresholdOut(ThresholdIn): pass

class ScheduleIn(BaseModel):
    on_time: time
    duration_s: conint(gt=0)
class ScheduleOut(ScheduleIn):
    relay: int

class RelayStatusIn(BaseModel):
    status: conint(ge=0, le=1)
class RelayStatusOut(BaseModel):
    relay: int; status: int; update_time: datetime

class RelayModeIn(BaseModel):
    mode: conint(ge=0, le=1)
class RelayModeOut(BaseModel):
    relay: int; mode: int; update_time: datetime

class ReportRequest(BaseModel):
    email: str
    date:  str   # dd‑mm‑yyyy

# ──────────────────────────────────────────────────────────────────────────────
# 5) HELPERS
# ──────────────────────────────────────────────────────────────────────────────
def upsert(session, cls, pk_field, pk_value, **kw):
    obj = session.query(cls).get(pk_value)
    if obj:
        for k,v in kw.items(): setattr(obj,k,v)
    else:
        obj = cls(**{pk_field:pk_value}, **kw)
        session.add(obj)
    session.commit(); return obj

# ──────────────────────────────────────────────────────────────────────────────
# 6) ENDPOINTS
# ──────────────────────────────────────────────────────────────────────────────
@app.post("/api/post_env", tags=["env"])
def post_env(d: TempHumIn):
    with Session() as db:
        db.add(TempHumLog(nhiet_do=d.nhiet_do, do_am=d.do_am))
        db.commit()
    return {"msg":"logged"}

@app.get("/api/get_env", response_model=List[TempHumOut], tags=["env"])
def get_env(limit:int=50):
    with Session() as db:
        return (db.query(TempHumLog)
                 .order_by(TempHumLog.time.desc())
                 .limit(limit).all())

# threshold --------------------------------------------------
@app.post("/api/post_threshold_temp", tags=["threshold"])
def post_th_temp(t:ThresholdIn):
    with Session() as db:
        upsert(db,TempThreshold,'id',1,min_val=t.min_val,max_val=t.max_val)
    return {"msg":"saved"}
@app.get("/api/get_threshold_temp", response_model=ThresholdOut,
         tags=["threshold"])
def get_th_temp():
    with Session() as db:
        obj = db.query(TempThreshold).get(1)
        if not obj:
            raise HTTPException(status_code=404, detail="no data")
        return obj                       # ← tách ra dòng riêng
# ↳  độ ẩm
@app.post("/api/post_threshold_hum", tags=["threshold"])
def post_th_hum(t:ThresholdIn):
    with Session() as db:
        upsert(db,HumThreshold,'id',1,min_val=t.min_val,max_val=t.max_val)
    return {"msg":"saved"}
@app.get("/api/get_threshold_hum", response_model=ThresholdOut,
         tags=["threshold"])
def get_th_hum():
    with Session() as db:
        obj = db.query(HumThreshold).get(1)
        if not obj:
            raise HTTPException(status_code=404, detail="no data")
        return obj

# schedule ---------------------------------------------------
@app.post("/api/post_schedule_relay/{relay_id}", tags=["schedule"])
def post_schedule(relay_id:int=Path(...,ge=1,le=4), s:ScheduleIn=...):
    with Session() as db:
        upsert(db,RelaySchedule,'relay',relay_id,
               on_time=s.on_time,duration_s=s.duration_s)
    return {"msg":"saved"}
@app.get("/api/get_schedule_relay/{relay_id}", response_model=ScheduleOut,
         tags=["schedule"])
def get_schedule(relay_id: int = Path(..., ge=1, le=4)):
    with Session() as db:
        obj = db.query(RelaySchedule).get(relay_id)
        if not obj:
            raise HTTPException(status_code=404, detail="no schedule")
        return obj

# status & log ----------------------------------------------
# status -----------------------------------------------------
@app.get(
    "/api/get_relay_status/{relay_id}",
    response_model=RelayStatusOut,
    tags=["relay"],
)
def get_status(relay_id: int = Path(..., ge=1, le=4)):
    """
    Trả về trạng thái relay.  
    Nếu chưa có bản ghi → tạo mặc định status = 0 (False) rồi trả về.
    """
    now = datetime.utcnow()
    with Session() as db:
        obj = db.query(RelayStatus).get(relay_id)

        # ➊ Chưa tồn tại → khởi tạo mặc định
        if obj is None:
            obj = RelayStatus(relay=relay_id, status=0, update_time=now)
            db.add(obj)
            db.commit()
            db.refresh(obj)   # đảm bảo obj có PK & update_time mới nhất

        return obj


# mode (auto/manual) ----------------------------------------
@app.post("/api/post_relay_mode/{relay_id}", tags=["relay"])
def post_mode(relay_id:int=Path(...,ge=1,le=4), m:RelayModeIn=...):
    now=datetime.utcnow()
    with Session() as db:
        upsert(db,RelayMode,'relay',relay_id,mode=m.mode,update_time=now)
    return {"msg":f"relay{relay_id} set to {'MANUAL' if m.mode else 'AUTO'}"}
@app.get("/api/get_relay_mode/{relay_id}", response_model=RelayModeOut,
         tags=["relay"])
def get_mode(relay_id: int = Path(..., ge=1, le=4)):
    with Session() as db:
        obj = db.query(RelayMode).get(relay_id)
        if not obj:
            raise HTTPException(status_code=404, detail="no mode")
        return obj

# over‑limit log --------------------------------------------
@app.post("/api/post_over_temp/{value}", tags=["alert"])
def post_ot(value:float):
    with Session() as db:
        db.add(OverTempLog(value=value)); db.commit()
    return {"msg":"logged"}
@app.post("/api/post_over_hum/{value}", tags=["alert"])
def post_oh(value:float):
    with Session() as db:
        db.add(OverHumLog(value=value)); db.commit()
    return {"msg":"logged"}

# ────────────────────────────────────────────────────────────
# 7)  REPORT (Excel + chart) & EMAIL
# ────────────────────────────────────────────────────────────
SENDER = os.getenv("GMAIL_USER","rungto123321@gmail.com")
APP_PWD = os.getenv("GMAIL_APP_PWD","bxpldzprwtilnmox")

def _build_report(d:date) -> str:
    """Tạo file Excel + chart, trả về đường dẫn file."""
    day_start = datetime.combine(d, time.min)
    day_end   = datetime.combine(d, time.max)

    with Session() as db:
        temps = (db.query(TempHumLog)
                   .filter(TempHumLog.time.between(day_start,day_end))
                   .order_by(TempHumLog.time).all())
        onlog = (db.query(RelayOnLog)
                   .filter(RelayOnLog.time.between(day_start,day_end)).all())
        offlog= (db.query(RelayOffLog)
                   .filter(RelayOffLog.time.between(day_start,day_end)).all())

    if not temps: raise Exception("Không có dữ liệu nhiệt ẩm ngày này")

    # dataframe nhiệt ẩm
    df_env = pd.DataFrame([{
        "timestamp": t.time, "nhiet_do": t.nhiet_do, "do_am": t.do_am
    } for t in temps])

    # dataframe relay log
    def _df(logs, act):   # act = ON/OFF
        return pd.DataFrame([{
            "relay": l.relay, "action": act, "time": l.time
        } for l in logs])
    df_relay = pd.concat([_df(onlog,"ON"), _df(offlog,"OFF")]) \
                   .sort_values("time")

    #  ▸ Ghi ra Excel
    fname = f"baocao_{d.strftime('%d-%m-%Y')}.xlsx"
    with pd.ExcelWriter(fname, engine="openpyxl") as xls:
        df_env.to_excel(xls, sheet_name="Env24h", index=False)
        df_relay.to_excel(xls, sheet_name="RelayLog", index=False)

    #  ▸ Vẽ chart
    plt.figure(figsize=(7,3))
    plt.plot(df_env["timestamp"], df_env["nhiet_do"], label="Nhiệt độ (°C)")
    plt.plot(df_env["timestamp"], df_env["do_am"],  label="Độ ẩm (%)")
    plt.title(f"Nhiệt độ / Độ ẩm – {d.strftime('%d-%m-%Y')}")
    plt.legend(); plt.tight_layout()
    chart_png = f"chart_{d.strftime('%d%m%Y')}.png"
    plt.savefig(chart_png, dpi=140); plt.close()
    return fname, chart_png

def _send_email(to_addr:str, file_xlsx:str, file_png:str, d:date):
    yag = yagmail.SMTP(SENDER, APP_PWD)
    yag.send(
        to=to_addr,
        subject=f"Báo cáo ngày {d.strftime('%d-%m-%Y')}",
        contents=[
            "Chào sếp đẹp zai, đây là báo cáo tình hình thiết bị trong nhà ạ",
            yagmail.inline(file_png)
        ],
        attachments=[file_xlsx]
    )

@app.post("/api/send_report", tags=["report"])
def send_report(req:ReportRequest, bg:BackgroundTasks):
    try:
        rpt_day = datetime.strptime(req.date,"%d-%m-%Y").date()
    except ValueError:
        raise HTTPException(400,"Định dạng date phải dd‑mm‑yyyy")

    def _job():
        try:
            xlsx, png = _build_report(rpt_day)
            _send_email(req.email, xlsx, png, rpt_day)
            os.remove(xlsx); os.remove(png)
            print("✔️ sent report ->",req.email)
        except Exception as e:
            print("❌ report error:", e)

    bg.add_task(_job)
    return {"msg":f"Sẽ gửi báo cáo {req.date} tới {req.email}"}

# ────────────────────────────────────────────────────────────
# 8)  AUTO‑CREATE TABLE & SEED
# ────────────────────────────────────────────────────────────
def _seed():
    with Session() as db:
        if not db.query(TempThreshold).get(1):
            db.add(TempThreshold(id=1,min_val=0,max_val=0))
        if not db.query(HumThreshold).get(1):
            db.add(HumThreshold(id=1,min_val=0,max_val=0))
        for r in range(1,5):
            if not db.query(RelayStatus).get(r):
                db.add(RelayStatus(relay=r,status=0))
            if not db.query(RelayMode).get(r):
                db.add(RelayMode(relay=r,mode=0))
            if not db.query(RelaySchedule).get(r):
                db.add(RelaySchedule(relay=r,on_time=time(0,0,0),duration_s=0))
        db.commit()

@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)
    _seed()
    print("DB ready ✔")

# ────────────────────────────────────────────────────────────
# 9)  RUN
# ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app", host="0.0.0.0",
        port=int(os.getenv("PORT",8000)), reload=True
    )
