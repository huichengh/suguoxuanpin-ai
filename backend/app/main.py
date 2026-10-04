"""苏果智选 —— AI 社区商超智能选品与品类优化平台

FastAPI 应用入口。
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.routers import admin, agent, analysis, auth, data, stores, subcategory
from .config import DEFAULT_STORE, DEMO_DISCLAIMER, DEMO_SOURCE
from .database import Base, engine, SessionLocal
from .models import Category, DataUpload, Store

app = FastAPI(
    title="苏果智选 —— AI 社区商超智能选品与品类优化平台",
    description=(
        "Suguo AI Assortment Intelligence\n\n"
        f"面向社区商超采购人员、品类经理、门店店长的 AI 智能选品决策平台。\n\n"
        f"⚠️ 数据说明：{DEMO_SOURCE}，{DEMO_DISCLAIMER}。"
    ),
    version="1.0.0",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(analysis.router)
app.include_router(stores.router)
app.include_router(subcategory.router)
app.include_router(data.router)
app.include_router(agent.router)
app.include_router(agent.new_router)
app.include_router(admin.approval_router)
app.include_router(admin.admin_router)
app.include_router(admin.report_router)
app.include_router(admin.router)


@app.on_event("startup")
def on_startup():
    """启动时自动建表并导入附件数据（若数据库为空）。"""
    from .seed import seed_all
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        need_seed = db.query(Store).count() == 0 or db.query(DataUpload).count() == 0
    finally:
        db.close()

    if need_seed:
        print("[苏果智选] 检测到数据库为空，正在导入项目附件演示数据……")
        try:
            res = seed_all(reset=False)
            for s in res.get("steps", []):
                print(f"  · {s}")
            print("[苏果智选] 演示数据导入完成。")
        except Exception as e:
            print(f"[苏果智选] 演示数据导入失败：{e}")
            print("[苏果智选] 请通过前端「数据中心」手动上传项目数据集。")


@app.get("/api/health")
def health_check():
    db = SessionLocal()
    try:
        ready = db.query(Store).count() > 0 and db.query(DataUpload).count() > 0
        stores = db.query(Store).count()
        datasets = db.query(DataUpload).count()
        categories = db.query(Category).count()
    finally:
        db.close()

    return {
        "status": "ok",
        "service": "苏果智选 AI 社区商超智能选品与品类优化平台",
        "data_ready": ready,
        "stores": stores,
        "datasets": datasets,
        "categories": categories,
        "default_store": DEFAULT_STORE,
        "demo_disclaimer": DEMO_DISCLAIMER,
        "demo_source": DEMO_SOURCE,
    }


@app.get("/")
def root():
    return {
        "platform": "苏果智选",
        "subtitle": "Suguo AI Assortment Intelligence",
        "positioning": "AI 辅助决策 + 数据驱动选品 + 人工最终确认",
        "docs": "/docs",
        "frontend": "http://localhost:5173",
        "demo_disclaimer": DEMO_DISCLAIMER,
    }


@app.exception_handler(ValueError)
def value_error_handler(request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})