"""日期维度与天气影响分析接口。

设计原则：
1. 只返回已在库中的真实数据，不生成估算值
2. 天气数据未接入时明确返回「待接入」状态与缺失字段清单
3. 备货建议按规律强度决定是否给出——波动不足时不给建议
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import Category, DailyCategoryStat, User
from ...services.date_pattern import (
    date_patterns, rebuild_daily_stats, stocking_advice, weather_status,
)
from ..deps import get_current_user

router = APIRouter(prefix="/api/date-pattern", tags=["日期与天气"])


class RebuildRequest(BaseModel):
    pass


@router.get("/status")
def status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """日期维度数据状态：是否已聚合、覆盖范围、天气是否接入。"""
    total = db.query(DailyCategoryStat).count()
    w = weather_status(db)
    if total == 0:
        return {
            "aggregated": False,
            "rows": 0,
            "weather": w,
            "hint": "尚未生成日期维度数据，请点击「生成日期维度数据」",
        }
    rows = db.query(DailyCategoryStat).all()
    dates = [r.stat_date for r in rows]
    return {
        "aggregated": True,
        "rows": total,
        "date_from": min(dates).isoformat(),
        "date_to": max(dates).isoformat(),
        "days": len(set(dates)),
        "categories": len({r.category_id for r in rows}),
        "weather": w,
    }


@router.post("/rebuild")
def rebuild(body: RebuildRequest = None, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    """从交易明细重建日期维度事实表。幂等，可重复执行。"""
    res = rebuild_daily_stats(db, user.username)
    res["success"] = True
    res["demo_label"] = "模拟演示数据，不代表华润苏果真实经营数据"
    return res


@router.get("/patterns")
def patterns(category_id: Optional[int] = None, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    """日期维度规律：星期、月份、月内旬。"""
    cat_name = None
    if category_id:
        c = db.get(Category, category_id)
        cat_name = c.name if c else None
    res = date_patterns(db, category_id)
    res["category"] = cat_name
    res["demo_label"] = "模拟演示数据，不代表华润苏果真实经营数据"
    return res


@router.get("/advice")
def advice(category_id: Optional[int] = None, db: Session = Depends(get_db),
           user: User = Depends(get_current_user)):
    """备货与排班参考。

    仅在规律强度达到阈值时给出建议；天气未接入时明确标注。
    """
    res = stocking_advice(db, category_id)
    res["demo_label"] = "模拟演示数据，不代表华润苏果真实经营数据"
    return res


@router.get("/daily")
def daily(category_id: Optional[int] = None, limit: int = 90,
          db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """按日销量序列，供前端绘制趋势图。"""
    q = db.query(DailyCategoryStat)
    if category_id:
        q = q.filter(DailyCategoryStat.category_id == category_id)
    rows = q.order_by(DailyCategoryStat.stat_date.desc()).limit(min(limit, 400)).all()

    # 同一天多品类需合并
    by_date = {}
    for r in rows:
        k = r.stat_date.isoformat()
        e = by_date.setdefault(k, {
            "date": k, "sales_qty": 0.0, "sales_amount": 0.0,
            "transaction_count": 0, "weekday": r.weekday,
            "day_type": r.day_type, "month": r.month, "season": r.season,
        })
        e["sales_qty"] += float(r.sales_qty or 0)
        e["sales_amount"] += float(r.sales_amount or 0)
        e["transaction_count"] += int(r.transaction_count or 0)

    out = sorted(by_date.values(), key=lambda x: x["date"])
    for e in out:
        e["sales_qty"] = round(e["sales_qty"], 1)
        e["sales_amount"] = round(e["sales_amount"], 2)
    return {"success": True, "count": len(out), "rows": out,
            "demo_label": "模拟演示数据，不代表华润苏果真实经营数据"}
