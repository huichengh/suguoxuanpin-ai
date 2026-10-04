"""业务分析接口：驾驶舱 / 品类 / 比较 / 关联 / 预测"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...algorithms import advisor
from ...algorithms import association as assoc_algo
from ...algorithms import compare as cmp_algo
from ...algorithms.common import MissingFieldError
from ...config import DEMO_DISCLAIMER, DEMO_SOURCE
from ...database import get_db
from ...models import AnalysisJob, AuditLog, Category, ModelRunLog, User
from ...services import analytics as A
from ..deps import get_current_user, require_permission

router = APIRouter(prefix="/api", tags=["业务分析"])


# ---------- 驾驶舱 ----------
@router.get("/dashboard/summary")
def dashboard_summary(store_id: Optional[int] = None,
                      db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    from ...agents.tools import dashboard_summary as build
    d = build(db)
    health = A.health_rows(db)
    fcs = A.forecast_views(db)
    rules = A.rule_summary_for_advisor(db)
    params = A.risk_params(db)

    d["risk_alerts"] = advisor.risk_alerts(health, fcs, **params)
    d["suggestions"] = advisor.generate_daily_suggestions(
        health, fcs, rules, pending_approvals=d["kpi"]["pending_approvals"]
    )
    d["risk_params"] = params
    d["source_note"] = DEMO_SOURCE
    return d


@router.get("/categories")
def list_categories(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Category).order_by(Category.sort_order).all()
    health = {h["category"]: h for h in A.health_rows(db)}
    return [
        {
            "id": c.id, "code": c.code, "name": c.name,
            "category_role": c.category_role, "stp_target": c.stp_target,
            "positioning": c.positioning, "sort_order": c.sort_order,
            "health_score": health.get(c.name, {}).get("overall_score"),
            "health_grade": health.get(c.name, {}).get("grade"),
            "alert_light": health.get(c.name, {}).get("alert_light"),
            "is_demo": c.is_demo,
        }
        for c in rows
    ]


@router.get("/categories/health-all")
def all_categories_health(db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)):
    """一次性返回全部品类的健康度详情，避免前端逐个请求。"""
    rows = A.health_rows(db)
    sales = A.category_sales_agg(db)
    for r in rows:
        r["sales_summary"] = sales.get(r["category"], {})
    return {"items": rows, "count": len(rows), "demo_label": DEMO_DISCLAIMER}


@router.get("/categories/{category_id}/health")
def category_health(category_id: int, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(404, detail=f"品类 ID {category_id} 不存在")

    rows = A.health_rows(db)
    row = next((r for r in rows if r["category_id"] == category_id), None)
    if not row:
        raise HTTPException(404, detail=f"品类「{cat.name}」暂无健康度评分结果，请先调用重算接口")

    from ...agents.tools import category_trend
    trend = category_trend(db, cat.name)

    # 附上销售额/毛利额聚合，供详情页展示
    row = dict(row)
    row["sales_summary"] = A.category_sales_agg(db).get(cat.name, {})
    return {"health": row, "trend": trend, "demo_label": DEMO_DISCLAIMER}


@router.post("/categories/recalculate")
def recalculate_categories(db: Session = Depends(get_db),
                           user: User = Depends(require_permission("category_health"))):
    """用当前权重重新计算全部品类健康度。"""
    import pandas as pd

    from ...algorithms import health as health_algo
    from ...models import CategoryHealthResult, DataUpload
    from ...seed import _dataset_file, _read_csv

    weights = A.get_setting(db, "category_health_weights",
                            {"sales": 0.30, "margin": 0.30, "turnover": 0.20, "space": 0.20})
    p = _dataset_file("dataset_category_sales.csv")
    if not p:
        raise HTTPException(400, detail="未找到品类销售数据集，无法重算")

    t0 = datetime.utcnow()
    df = _read_csv(p)
    rows = health_algo.score_categories(df, weights, months_window=12)

    ds = db.query(DataUpload).filter(DataUpload.dataset_type == "category_sales").first()
    ds_id = ds.id if ds else None

    db.query(CategoryHealthResult).filter(CategoryHealthResult.source == "system").delete(
        synchronize_session=False)
    params = {**weights, "months_window": 12, "normalization": "minmax",
              "turnover_direction": "reverse(越低越好)"}
    for r in rows:
        c = db.query(Category).filter_by(name=r["category"]).first()
        if not c:
            continue
        db.add(CategoryHealthResult(
            category_id=c.id, source="system", overall_score=r["overall_score"],
            grade=r["grade"], stars=r["stars"], sales_score=r["sales_score"],
            margin_score=r["margin_score"], turnover_score=r["turnover_score"],
            space_score=r["space_score"], sales_contribution=r["sales_contribution"],
            margin_contribution=r["margin_contribution"],
            avg_turnover_days=r["avg_turnover_days"], avg_sales_per_sqm=r["avg_sales_per_sqm"],
            total_stockout=r["stockout_count"], sku_count=int(r["avg_sku_count"]),
            sales_trend=r["sales_trend"], margin_trend=r["margin_trend"],
            turnover_trend=r["turnover_trend"], space_trend=r["space_trend"],
            diagnosis=r["diagnosis"], suggestion=r["suggestion"], alert_light=r["alert_light"],
            source_dataset_id=ds_id, algorithm="品类健康度评分模型 v1.0", parameters=params,
        ))
    duration = int((datetime.utcnow() - t0).total_seconds() * 1000)

    db.add(ModelRunLog(algorithm="品类健康度评分模型", parameters=params,
                       dataset="category_sales", status="success",
                       output=f"{len(rows)} 个品类", duration_ms=duration))
    db.add(AnalysisJob(job_type="category_health", algorithm="品类健康度评分模型",
                       parameters=params, source_dataset_id=ds_id,
                       result_summary={"categories": len(rows)}, duration_ms=duration,
                       triggered_by=user.username))
    db.add(AuditLog(user=user.username, action="recalculate_health", target="categories",
                    detail=f"权重 {weights} → {len(rows)} 个品类", ip="127.0.0.1"))
    db.commit()
    return {"success": True, "count": len(rows), "weights": weights,
            "duration_ms": duration, "items": A.health_rows(db)}


# ---------- 选品比较 ----------
class CompareRequest(BaseModel):
    mode: str = "category"          # category | sku
    ids: List[str] = []
    category_ids: List[int] = []
    weights: Optional[dict] = None


@router.post("/compare")
def compare(body: CompareRequest, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    try:
        result = A.compare_payload(
            db, body.ids, body.mode, weights=body.weights,
            category_ids=body.category_ids,
        )
    except MissingFieldError as e:
        raise HTTPException(400, detail=str(e))
    except ValueError as e:
        raise HTTPException(400, detail=str(e))

    if not result.get("sufficient", True):
        return result

    from ...models import AiRecommendation
    top = result["items"][0]
    rec = AiRecommendation(
        code=f"REC-CMP-{datetime.utcnow().strftime('%H%M%S')}",
        source_module="选品比较中心",
        title=f"比较结果：{top['name']} 得分 {top['overall_score']} 排名第一",
        content=f"推荐优先级：{' > '.join(r['priority'] for r in result['items'])}。"
                f"{top['recommendation']['reason']} 建议动作：{top['recommendation']['action']}。",
        data_basis="；".join(
            f"{r['name']} 销量分{r['scores']['sales']}/毛利分{r['scores']['margin']}/"
            f"周转分{r['scores']['turnover']}/坪效分{r['scores']['space']}"
            for r in result["items"]
        ),
        affected_categories=",".join(r["name"] for r in result["items"]),
        priority="高", risk_level="Level 3", requires_approval=True,
        decision_status="待审", created_by=user.username,
        parameters=result["weights"],
    )
    db.add(rec)
    db.add(AuditLog(user=user.username, action="compare", target=body.mode,
                    detail=f"{len(result['items'])} 个对象", ip="127.0.0.1"))
    db.commit()
    result["recommendation_id"] = rec.id
    result["recommendation_code"] = rec.code
    return result


@router.get("/compare/options")
def compare_options(mode: str = "category", db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    if mode == "sku":
        status = A.sku_data_status(db)
        return {"mode": "sku", "status": status,
                "options": A.candidate_dicts(db) if status["sufficient"] else []}
    cats = db.query(Category).order_by(Category.sort_order).all()
    sales = A.category_sales_agg(db)
    return {
        "mode": "category",
        "options": [
            {"id": c.id, "code": c.code, "name": c.name,
             "health_score": None, "category_role": c.category_role,
             "has_data": c.name in sales}
            for c in cats
        ],
        "status": {"sufficient": True, "message": "品类级数据完整，可进行量化比较"},
    }


# ---------- 关联陈列 ----------
@router.get("/association-rules")
def get_association_rules(source: Optional[str] = None,
                          db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)):
    return A.association_rules(db, source)


class AprioriRequest(BaseModel):
    min_support: Optional[float] = None
    min_confidence: Optional[float] = None
    min_lift: Optional[float] = None
    top_n: Optional[int] = None
    group_by: Optional[str] = None
    save: bool = True


@router.post("/association-rules/recalculate")
def recalc_association(body: AprioriRequest = Body(default_factory=AprioriRequest),
                       db: Session = Depends(get_db),
                       user: User = Depends(require_permission("association"))):
    """用 SQL 直接取两列构建购物篮，避免把 2 万条明细实例化成 ORM 对象。"""
    from ...models import AssociationRule, Transaction, TransactionItem
    from sqlalchemy import func, select

    p = A.apriori_params(db)
    ms = float(body.min_support) if body.min_support is not None else p["min_support"]
    mc = float(body.min_confidence) if body.min_confidence is not None else p["min_confidence"]
    ml = float(body.min_lift) if body.min_lift is not None else p["min_lift"]
    tn = int(body.top_n) if body.top_n is not None else p["top_n"]
    gb = body.group_by or p["group_by"]
    # 逻辑键 → ORM 属性，避免用中文列名直接 select
    item_attr = {
        "product_name": TransactionItem.product_name,
        "sku_code": TransactionItem.sku_code,
    }[gb]
    item_label = assoc_algo.GROUP_BY_COLUMNS[gb]

    rows = db.execute(
        select(TransactionItem.transaction_id, item_attr)
    ).all()
    if not rows:
        raise HTTPException(400, detail="当前数据库没有交易明细数据，无法运行 Apriori")

    # 交易号文本只需查一次，避免 N+1
    tx_map = dict(db.execute(
        select(Transaction.id, Transaction.transaction_no)
    ).all())
    pairs = [(tx_map.get(tid) or str(tid), (name or "").strip())
             for tid, name in rows if name]

    t0 = datetime.utcnow()
    try:
        out = assoc_algo.run_from_pairs(pairs, ms, mc, ml, tn, gb)
    except assoc_algo.BasketKeyError as e:
        raise HTTPException(400, detail=str(e))
    duration = int((datetime.utcnow() - t0).total_seconds() * 1000)

    if body.save:
        db.query(AssociationRule).filter(AssociationRule.source == "realtime").delete(
            synchronize_session=False)
        ds_id = db.query(func.min(TransactionItem.source_dataset_id)).scalar()
        for r in out["rules"]:
            db.add(AssociationRule(
                antecedent=r["antecedent"], consequent=r["consequent"],
                support=r["support"], confidence=r["confidence"], lift=r["lift"],
                display_rule=r["display_rule"], display_suggestion=r["display_suggestion"],
                source="realtime", passes_threshold=True, item_count=r["item_count"],
                source_dataset_id=ds_id, algorithm="Apriori 实时重算",
                parameters={**out["params"], "basket_key": f"交易号 + {item_label}"},
            ))
        db.add(ModelRunLog(algorithm="Apriori 实时重算",
                           parameters={**out["params"], "basket_key": f"交易号 + {item_label}"},
                           dataset="transactions", status="success",
                           output=f"{len(out['rules'])} 条规则", duration_ms=duration))
        db.add(AnalysisJob(job_type="association", algorithm="Apriori",
                           parameters=out["params"], source_dataset_id=ds_id,
                           result_summary={"rules": len(out["rules"]),
                                           "baskets": out["basket_count"],
                                           "items": out["item_count"]},
                           duration_ms=duration, triggered_by=user.username))
        db.add(AuditLog(user=user.username, action="recalculate_association", target="association_rules",
                        detail=f"参数 sup={ms}/conf={mc}/lift={ml}/topN={tn} → {len(out['rules'])} 条",
                        ip="127.0.0.1"))
        db.commit()

    return {"success": True, "saved": body.save, "duration_ms": duration, **out,
            "demo_label": DEMO_DISCLAIMER}


@router.get("/association-rules/item/{item_name}")
def item_profile(item_name: str, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    data = A.association_rules(db, "realtime")
    prof = assoc_algo.item_profile({"rules": data["realtime_rules"]}, item_name)
    if not prof:
        raise HTTPException(404, detail=f"商品「{item_name}」在当前关联规则结果中没有出现")
    return prof


# ---------- 需求预测 ----------
@router.get("/forecast")
def get_forecast(category: Optional[str] = None, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    views = A.forecast_views(db)
    if category:
        v = next((x for x in views if x["category"] == category), None)
        if not v:
            raise HTTPException(404, detail=f"没有找到品类「{category}」的预测数据")
        return v
    return {"items": views, "count": len(views), "demo_label": DEMO_DISCLAIMER}


class ForecastRunRequest(BaseModel):
    category: str
    periods: int = 4
    method: str = "moving_average"


@router.post("/forecast/run")
def run_forecast(body: ForecastRunRequest, db: Session = Depends(get_db),
                 user: User = Depends(require_permission("forecast"))):
    """真实预测：使用历史数据跑移动平均。历史不足时明确拒绝，不伪造精度。"""
    from ...algorithms import forecast as fc
    from ...models import Category, DemandRecord

    cat = db.query(Category).filter_by(name=body.category).first()
    if not cat:
        raise HTTPException(404, detail=f"品类「{body.category}」不存在")

    rows = (db.query(DemandRecord)
            .filter(DemandRecord.category_id == cat.id, DemandRecord.data_type == "history")
            .order_by(DemandRecord.week_no).all())
    history = [r.actual_qty for r in rows if r.actual_qty is not None]

    if len(history) < 12:
        return {
            "success": False,
            "message": f"历史数据量有限（当前 {len(history)} 期，少于建议的 12 期），预测结果仅供趋势参考。",
            "history_periods": len(history),
            "required_periods": 12,
            "recommended_periods": fc.RECOMMENDED_MIN_PERIODS,
            "data_status": "insufficient",
            "missing": ["更长的需求历史数据（建议 24-36 个月）",
                        "外生变量：节假日、天气、促销、价格、季节因素"],
        }

    t0 = datetime.utcnow()
    preds = fc.moving_average_forecast(history, body.periods, window=4)
    duration = int((datetime.utcnow() - t0).total_seconds() * 1000)

    recent = sum(history[-4:]) / min(4, len(history))
    future_avg = round(sum(preds) / len(preds), 2)
    trend = fc.classify_trend(future_avg, recent)

    db.add(ModelRunLog(algorithm=f"移动平均预测({body.method})",
                       parameters={"periods": body.periods, "window": 4,
                                   "history_periods": len(history)},
                       dataset="demand_forecast", status="success",
                       output=f"预测均值 {future_avg}", duration_ms=duration))
    db.add(AuditLog(user=user.username, action="run_forecast", target=body.category,
                    detail=f"{len(history)} 期历史 → {body.periods} 期预测", ip="127.0.0.1"))
    db.commit()

    return {
        "success": True,
        "category": body.category,
        "method": "移动平均（window=4）",
        "history_periods": len(history),
        "predictions": preds,
        "future_avg": future_avg,
        "recent_avg": round(recent, 2),
        "trend": trend,
        "duration_ms": duration,
        "data_status": "limited" if len(history) < fc.RECOMMENDED_MIN_PERIODS else "sufficient",
        "note": (
            f"历史数据 {len(history)} 期，低于推荐的 {fc.RECOMMENDED_MIN_PERIODS} 期，"
            "预测结果仅供趋势参考。" if len(history) < fc.RECOMMENDED_MIN_PERIODS
            else f"历史数据 {len(history)} 期，满足建模要求。"
        ),
        "extensible": ["节假日", "天气", "促销", "价格", "季节", "重大活动"],
        "prophet_note": "环境安装 prophet 后可切换为 Prophet 模型；当前演示环境未安装，使用移动平均作为可解释的基线模型。",
    }


# ---------- 千店千面 / 自有品牌 ----------
@router.get("/stores")
def list_stores(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ...agents.tools import store_profile
    from ...models import Store

    rows = db.query(Store).all()
    out = []
    for s in rows:
        prof = store_profile(db, s.id)
        out.append({
            "id": s.id, "code": s.code, "name": s.name, "city": s.city,
            "district": s.district, "business_district": s.business_district,
            "store_type": s.store_type, "area_sqm": s.area_sqm,
            "is_default": s.is_default, "is_demo": s.is_demo,
            "profile": prof["profile"], "missing_fields": prof["missing_fields"],
            "profile_complete": prof["complete"], "note": prof["note"],
        })
    return {"items": out, "count": len(out),
            "module_status": "门店画像配置 + 数据待接入",
            "note": "当前附件未包含多门店人口、消费力与 POI 数据，平台不编造不存在的人口数量。",
            "demo_label": DEMO_DISCLAIMER}


@router.get("/private-label/opportunities")
def private_label_opportunities(db: Session = Depends(get_db),
                                user: User = Depends(get_current_user)):
    return advisor.private_label_opportunity(A.health_rows(db))