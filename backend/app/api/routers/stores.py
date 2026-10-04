"""多门店管理接口：录入 / 编辑 / 对比"""
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...config import DEMO_DISCLAIMER
from ...database import get_db
from ...models import Store, User
from ...services import store_ops
from ..deps import get_current_user, require_admin

router = APIRouter(prefix="/api/stores-ops", tags=["多门店管理"])


@router.get("/all")
def list_all(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    items = store_ops.list_stores(db)
    return {
        "items": items,
        "count": len(items),
        "ready_count": sum(1 for i in items if i["data_status"]["metrics_ready"]),
        "metrics_catalog": [
            {"key": k, "label": l, "unit": u, "higher_is_better": h, "description": d}
            for k, l, u, h, d in store_ops.STORE_METRICS
        ],
        "profile_catalog": [
            {"key": k, "label": l, "unit": u} for k, l, u in store_ops.PROFILE_FIELDS
        ],
        "data_caveat": (
            "附件仅提供黄金海岸广场店一家门店的经营数据。其余门店需人工录入，"
            "平台不会生成或推算任何经营数据。"
        ),
        "demo_label": DEMO_DISCLAIMER,
    }


class StoreCreate(BaseModel):
    name: str
    code: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    business_district: Optional[str] = None
    store_type: Optional[str] = None
    area_sqm: Optional[float] = None
    # 画像
    pop_3km: Optional[int] = None
    resident_ratio: Optional[float] = None
    office_ratio: Optional[float] = None
    student_ratio: Optional[float] = None
    senior_ratio: Optional[float] = None
    poi_residential: Optional[int] = None
    poi_office: Optional[int] = None
    poi_school: Optional[int] = None
    consumption_power: Optional[str] = None
    main_competitors: Optional[str] = None
    delivery_capability: Optional[str] = None
    # 经营指标
    sales_amount: Optional[float] = None
    gross_profit: Optional[float] = None
    gross_margin_rate: Optional[float] = None
    sales_qty: Optional[float] = None
    turnover_days: Optional[float] = None
    sales_per_sqm: Optional[float] = None
    sku_count: Optional[int] = None
    stockout_count: Optional[int] = None
    member_ratio: Optional[float] = None
    daily_customer_count: Optional[int] = None
    health_score: Optional[float] = None
    data_source: Optional[str] = None


@router.post("")
def create_store(body: StoreCreate, db: Session = Depends(get_db),
                 user: User = Depends(require_admin)):
    if not body.name.strip():
        raise HTTPException(400, detail="门店名称不能为空")
    dup = db.query(Store).filter(Store.name == body.name.strip()).first()
    if dup:
        raise HTTPException(400, detail=f"门店「{body.name}」已存在")
    s = store_ops.create_store(db, user.username, body.model_dump())
    return {
        "success": True,
        "store": next(i for i in store_ops.list_stores(db) if i["id"] == s.id),
        "message": f"门店「{s.name}」已创建。经营指标可稍后补充，未填字段在对比中显示「待接入」。",
    }


class StoreUpdate(BaseModel):
    store_id: int
    # 允许更新基础信息、画像与经营指标
    city: Optional[str] = None
    district: Optional[str] = None
    business_district: Optional[str] = None
    store_type: Optional[str] = None
    area_sqm: Optional[float] = None
    pop_3km: Optional[int] = None
    resident_ratio: Optional[float] = None
    office_ratio: Optional[float] = None
    student_ratio: Optional[float] = None
    senior_ratio: Optional[float] = None
    poi_residential: Optional[int] = None
    poi_office: Optional[int] = None
    poi_school: Optional[int] = None
    consumption_power: Optional[str] = None
    main_competitors: Optional[str] = None
    delivery_capability: Optional[str] = None
    sales_amount: Optional[float] = None
    gross_profit: Optional[float] = None
    gross_margin_rate: Optional[float] = None
    sales_qty: Optional[float] = None
    turnover_days: Optional[float] = None
    sales_per_sqm: Optional[float] = None
    sku_count: Optional[int] = None
    stockout_count: Optional[int] = None
    member_ratio: Optional[float] = None
    daily_customer_count: Optional[int] = None
    health_score: Optional[float] = None
    data_source: Optional[str] = None


@router.patch("/{store_id}")
def update_store(store_id: int, body: StoreUpdate, db: Session = Depends(get_db),
                 user: User = Depends(require_admin)):
    # 用 exclude_unset 而非 exclude_none：允许前端显式传 null 来清空某个字段
    payload = body.model_dump(exclude_unset=True, exclude={"store_id"})
    try:
        s = store_ops.update_store_metrics(db, user.username, store_id, payload)
    except ValueError as e:
        raise HTTPException(404, detail=str(e))
    return {
        "success": True,
        "store": next(i for i in store_ops.list_stores(db) if i["id"] == s.id),
        "message": f"门店「{s.name}」已更新",
    }


class CompareRequest(BaseModel):
    store_ids: List[int]


@router.post("/compare")
def compare_stores(body: CompareRequest, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    res = store_ops.compare_stores(db, body.store_ids)
    if not res.get("success"):
        raise HTTPException(400, detail=res.get("message"))
    return res
