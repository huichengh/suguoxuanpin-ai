"""小类相关接口：列表 / 比较 / ABC分类 / 货架空间优化"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...algorithms import shelf as shelf_algo
from ...algorithms import sub_compare as sub_cmp
from ...config import DEMO_DISCLAIMER, DEMO_SOURCE
from ...database import get_db
from ...models import AuditLog, ModelRunLog, SubCategory, User
from ...services import subcategory as sub_svc
from ..deps import get_current_user, require_permission

router = APIRouter(prefix="/api/subcategories", tags=["小类分析"])


@router.get("")
def list_subcategories(category_id: Optional[int] = None, keyword: Optional[str] = None,
                        db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    items = sub_svc.subcategory_list(db, category_id, keyword)
    if not items:
        return {
            "items": [], "count": 0,
            "message": "数据库中没有小类数据，请先点击「重新聚合」或导入含商品名称的交易明细",
        }
    return {
        "items": items,
        "count": len(items),
        "params": sub_svc.SUB_PARAMS,
        "data_status": items[0]["data_status"],
        "demo_label": DEMO_DISCLAIMER,
    }


@router.post("/rebuild")
def rebuild(db: Session = Depends(get_db),
            user: User = Depends(require_permission("association"))):
    """从交易明细重新聚合小类指标并跑 ABC 分类。"""
    res = sub_svc.rebuild_subcategories(db, user.username)
    db.add(AuditLog(user=user.username, action="rebuild_subcategories", target="sub_categories",
                    detail=f"聚合 {res.get('count')} 个小类", ip="127.0.0.1"))
    db.commit()
    return res


# ---------- 小类比较 ----------

class SubCompareRequest(BaseModel):
    ids: List[int]                     # SubCategory.id
    weights: Optional[dict] = None


@router.post("/compare")
def compare_sub(body: SubCompareRequest, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    rows = db.query(SubCategory).filter(SubCategory.id.in_(body.ids)).all()
    if len(rows) != len(set(body.ids)):
        found = {r.id for r in rows}
        missing = [i for i in body.ids if i not in found]
        raise HTTPException(400, detail=f"小类 ID 不存在：{missing}")

    cands = [
        {
            "id": r.id, "name": r.name,
            "category": r.category.name if r.category else None,
            "sales_qty": r.sales_qty, "sales_amount": r.sales_amount,
            "avg_price": r.avg_price, "transaction_count": r.transaction_count,
            "qty_per_transaction": r.qty_per_transaction,
            "association_count": r.association_count, "max_lift": r.max_lift,
            "top_partner": r.top_partner,
            "gross_profit": r.gross_profit,
            "turnover_days": r.turnover_days,
            "sales_per_sqm": r.sales_per_sqm,
            "abc_class": (r.cluster_label or "").replace("ABC-", "") or None,
        }
        for r in rows
    ]

    if len(cands) < 2:
        return {"success": False, "message": "至少需要 2 个比较对象"}

    result = sub_cmp.compare_subcategories(cands, body.weights)
    if not result.get("success"):
        return result

    result["demo_label"] = DEMO_DISCLAIMER
    return result


@router.get("/compare/options")
def compare_options(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """返回可选小类清单，按大类分组。"""
    items = sub_svc.subcategory_list(db)
    grouped: dict = {}
    for it in items:
        grouped.setdefault(it["category"], []).append({
            "id": it["id"], "name": it["name"],
            "sales_amount": it["sales_amount"], "sales_qty": it["sales_qty"],
            "abc_class": it["abc_class"],
        })
    return {
        "count": len(items),
        "groups": [{"category": k, "items": v} for k, v in grouped.items()],
        "data_status": items[0]["data_status"] if items else None,
    }


# ---------- ABC 分类 ----------

class AbcRequest(BaseModel):
    a_threshold: float = 0.70
    b_threshold: float = 0.90
    by_category: bool = False
    save: bool = True


@router.get("/abc")
def get_abc(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    subs = db.query(SubCategory).all()
    if not subs:
        return {"success": False, "message": "请先点击「重新聚合」生成小类数据"}
    items = [
        {"name": s.name, "category": s.category.name if s.category else None,
         "sales_amount": s.sales_amount, "sales_qty": s.sales_qty}
        for s in subs
    ]
    from ...algorithms import abc as abc_algo
    return abc_algo.abc_classify(items)


@router.post("/abc/recalculate")
def recalc_abc(body: AbcRequest = Body(default_factory=AbcRequest), db: Session = Depends(get_db),
                user: User = Depends(require_permission("association"))):
    from ...algorithms import abc as abc_algo

    subs = db.query(SubCategory).all()
    if not subs:
        raise HTTPException(400, detail="请先点击「重新聚合」生成小类数据")

    items = [
        {"name": s.name, "category": s.category.name if s.category else None,
         "sales_amount": s.sales_amount, "sales_qty": s.sales_qty}
        for s in subs
    ]
    result = abc_algo.abc_classify(items, body.a_threshold, body.b_threshold)
    if not result.get("success"):
        raise HTTPException(400, detail=result.get("message"))

    if body.save:
        sub_svc.apply_abc(db, user.username)
        db.add(ModelRunLog(
            algorithm="ABC 分类",
            parameters={"A": body.a_threshold, "B": body.b_threshold},
            dataset="sub_categories", status="success",
            output=result["summary"][:80], duration_ms=0,
        ))
        db.add(AuditLog(user=user.username, action="recalc_abc", target="sub_categories",
                        detail=f"阈值 A={body.a_threshold}/B={body.b_threshold}", ip="127.0.0.1"))
        db.commit()

    if body.by_category:
        result["by_category"] = abc_algo.abc_by_category(items, body.a_threshold, body.b_threshold)

    return result


# ---------- 货架空间优化 ----------

class ShelfRequest(BaseModel):
    total_area: float = 20.0
    alpha: float = 0.65
    category_id: Optional[int] = None
    save: bool = False


@router.post("/shelf")
def optimize_shelf(body: ShelfRequest, db: Session = Depends(get_db),
                   user: User = Depends(require_permission("association"))):
    q = db.query(SubCategory)
    if body.category_id:
        q = q.filter(SubCategory.category_id == body.category_id)
    subs = q.all()
    if not subs:
        raise HTTPException(400, detail="请先点击「重新聚合」生成小类数据")

    items = [
        {"name": s.name, "category": s.category.name if s.category else None,
         "sales_amount": s.sales_amount, "sales_qty": s.sales_qty}
        for s in subs
    ]
    result = shelf_algo.allocate_shelf_space(
        items, total_area=body.total_area, alpha=body.alpha)
    if not result.get("success"):
        raise HTTPException(400, detail=result.get("message"))

    if body.save:
        by_name = {r["name"]: r for r in result["items"]}
        for s in subs:
            r = by_name.get(s.name)
            if r:
                s.shelf_area = r["suggest_area"]
                s.updated_at = datetime.utcnow()
        db.add(ModelRunLog(
            algorithm="货架空间优化",
            parameters={"total_area": body.total_area, "alpha": body.alpha},
            dataset="sub_categories", status="success",
            output=f"{len(result['items'])} 个小类面积分配", duration_ms=0,
        ))
        db.commit()
        result["saved"] = True

    result["demo_label"] = DEMO_DISCLAIMER
    return result


@router.get("/shelf/categories")
def shelf_category_areas(total_area: float = 20.0, db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)):
    """先按大类分配面积，再在各大类内分配到小类（二级分配）。"""
    subs = db.query(SubCategory).all()
    if not subs:
        return {"success": False, "message": "请先点击「重新聚合」生成小类数据"}

    items = [
        {"name": s.name, "category": s.category.name if s.category else None,
         "sales_amount": s.sales_amount, "sales_qty": s.sales_qty}
        for s in subs
    ]
    first = shelf_algo.allocate_shelf_space(items, total_area=total_area, alpha=0.65)
    cat_area: dict = {}
    for r in first["items"]:
        cat_area[r["category"]] = cat_area.get(r["category"], 0) + r["suggest_area"]

    detail = shelf_algo.reallocate_by_category(items, cat_area)
    return {
        "success": True,
        "total_area": total_area,
        "category_areas": [
            {"category": k, "area": round(v, 3), "share_pct": round(v / total_area * 100, 2)}
            for k, v in sorted(cat_area.items(), key=lambda x: -x[1])
        ],
        "items": detail,
        "demo_label": DEMO_DISCLAIMER,
    }
