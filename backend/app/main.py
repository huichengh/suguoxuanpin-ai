"""苏果智选 —— AI 社区商超智能选品与品类优化平台

FastAPI 应用入口。

单端口部署说明：
本文件同时承担 API 服务与前端页面托管两职。若 frontend/dist 存在，
则前端构建产物被挂载到根路径，整个平台只需启动一个端口即可访问，
无需再单独启动前端开发服务器。前端使用 HashRouter，因此不需要 history fallback 路由。
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.routers import admin, agent, analysis, auth, data, stores, subcategory
from .config import DEFAULT_STORE, DEMO_DISCLAIMER, DEMO_SOURCE
from .database import Base, engine, SessionLocal
from .models import Category, DataUpload, Store

# 前端构建产物目录。优先用 frontend/dist；打包部署时可能放在 backend/static。
_FRONTEND_CANDIDATES = [
    Path(__file__).resolve().parent.parent.parent / "frontend" / "dist",
    Path(__file__).resolve().parent.parent / "static",
]
FRONTEND_DIST = next((p for p in _FRONTEND_CANDIDATES if p.is_dir()), None)

app = FastAPI(
    title="苏果智选 —— AI 社区商超智能选品与品类优化平台",
    description=(
        "Suguo AI Assortment Intelligence\n\n"
        f"面向社区商超采购人员、品类经理、门店店长的 AI 智能选品决策平台。\n\n"
        f"⚠️ 数据说明：{DEMO_SOURCE}，{DEMO_DISCLAIMER}。"
    ),
    version="1.3.0",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    # 本地开发端口 + 线上部署域名。线上单端口部署时前端与接口同源，不触发跨域；
    # 此处保留是为了兼容前后端分开部署的场景。
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?|https://[\w.-]*workbuddy\.(cn|link)",
    allow_credentials=True,
    allow_methods=["*"],
    # 放行自定义令牌头，前端会同时发送 Authorization 与 X-Auth-Token
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


# ============ 前端静态托管（单端口部署）============
# 顺序要求：本块必须位于根路由 @app.get("/") 之前。
# Starlette 按注册顺序匹配：根路由若先注册，GET / 会命中它并返回 JSON，
# 前端页面就访问不到。挂载点 "/" 为前缀匹配，注册在此可接管根路径与全部
# 静态资源；而 /api/* 已在上方 include_router 中注册（顺序更早），不受影响。
if FRONTEND_DIST is not None:
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
    print(f"[苏果智选] 已挂载前端页面：{FRONTEND_DIST}")
else:
    print("[苏果智选] 未找到前端构建产物，仅提供 API 服务。"
          "如需单端口访问，请在 frontend 目录执行 npm run build。")


@app.get("/")
def root():
    """平台信息接口。仅在未构建前端时会被命中；已构建前端时 GET / 由静态挂载接管，返回 index.html。"""
    return {
        "platform": "苏果智选",
        "subtitle": "Suguo AI Assortment Intelligence",
        "positioning": "AI 辅助决策 + 数据驱动选品 + 人工最终确认",
        "docs": "/docs",
        "api_health": "/api/health",
        "frontend_built": FRONTEND_DIST is not None,
        "demo_disclaimer": DEMO_DISCLAIMER,
    }


@app.exception_handler(ValueError)
def value_error_handler(request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})
