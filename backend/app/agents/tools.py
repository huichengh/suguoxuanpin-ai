"""Agent 可调用的后台工具实现（每个函数直接查数据库 / 跑算法）"""
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy.orm import Session

from ..algorithms import advisor, association as assoc_algo, data_quality as dq
from ..algorithms import forecast as fc_algo
from ..config import DEMO_DISCLAIMER, DEMO_SOURCE
from ..models import (
    AnalysisJob, ApprovalRequest, AssociationRule, AuditLog, CandidateProduct,
    Category, CategoryHealthResult, CategorySales, DataQualityReport, DataUpload,
    DemandRecord, ModelRunLog, ModelSetting, SkuProduct, Store, Transaction,
    TransactionItem, AiRecommendation,
)
from ..services import analytics as A


# ---------- 驾驶舱 ----------
def dashboard_summary(db: Session) -> Dict:
    health = A.health_rows(db)
    fcs = A.forecast_views(db)
    sales = A.category_sales_agg(db)
    rules = A.rule_summary_for_advisor(db)
    pending = db.query(ApprovalRequest).filter(ApprovalRequest.status == "待审批").count()
    up = [f for f in fcs if f.get("trend_level") in ("明显上涨", "温和上涨")]

    total_stockout = sum(s.get("stockout_count", 0) for s in sales.values())
    avg_turnover = round(sum(s["avg_turnover_days"] for s in sales.values()) / len(sales), 2) if sales else 0

    return {
        "store": db.query(Store).filter_by(is_default=True).first().name if db.query(Store).filter_by(is_default=True).first() else "",
        "kpi": {
            "category_total": len(health),
            "healthy_category": sum(1 for h in health if h["overall_score"] >= 70),
            "risk_category": sum(1 for h in health if h["below_three_star"]),
            "stockout_this_month": total_stockout,
            "avg_turnover_days": avg_turnover,
            "high_value_associations": len([r for r in rules["rules"] if (r.get("lift") or 0) >= 2.0]),
            "demand_rising_categories": len(up),
            "pending_approvals": pending,
        },
        "health_overview": [
            {"category": h["category"], "score": h["overall_score"], "grade": h["grade"],
             "stars": h["stars"], "alert": h["alert_light"]}
            for h in health
        ],
        "data_status": {
            "category_sales_rows": db.query(CategorySales).count(),
            "transaction_rows": db.query(TransactionItem).count(),
            "transaction_count": db.query(Transaction).count(),
            "demand_rows": db.query(DemandRecord).count(),
            "sku_count": db.query(SkuProduct).count(),
        },
        "demo_label": DEMO_DISCLAIMER,
        "source_note": DEMO_SOURCE,
    }


# ---------- 品类健康度 ----------
def health(db: Session) -> List[Dict]:
    return A.health_rows(db)


def category_trend(db: Session, category: str) -> Dict:
    cat = db.query(Category).filter_by(name=category).first()
    if not cat:
        return {"found": False, "message": f"没有找到品类「{category}」。"}
    rows = db.query(CategorySales).filter_by(category_id=cat.id).order_by(CategorySales.month).all()
    if not rows:
        return {"found": False, "message": f"品类「{category}」没有销售数据记录。"}
    return {
        "found": True,
        "category": category,
        "months": [r.month for r in rows],
        "sales_qty": [r.sales_qty for r in rows],
        "sales_amount": [r.sales_amount for r in rows],
        "gross_profit": [r.gross_profit for r in rows],
        "turnover_days": [r.turnover_days for r in rows],
        "sales_per_sqm": [r.sales_per_sqm for r in rows],
        "stockout": [r.stockout_count for r in rows],
    }


# ---------- 比较 ----------
def compare(db: Session, ids: List, mode: str = "category") -> Dict:
    if mode == "sku":
        payload = A.compare_payload(db, [str(i) for i in ids], "sku")
    else:
        payload = A.compare_payload(db, [], "category", category_ids=[int(i) for i in ids])
    return payload


# ---------- 关联规则 ----------
def rules(db: Session, source: Optional[str] = None, top_n: int = 10) -> Dict:
    data = A.association_rules(db, source)
    if source == "realtime":
        data["realtime_rules"] = data["realtime_rules"][:top_n]
        data["shown"] = data["realtime_rules"]
    elif source == "attachment":
        data["shown"] = data["attachment_rules"][:top_n]
    else:
        data["shown"] = data["shown"][:top_n]
    return data


def run_apriori(db: Session, user: str, min_support=None, min_confidence=None,
                min_lift=None, top_n=None) -> Dict:
    """用给定参数实时重跑 Apriori，不落库（预览）。"""
    from sqlalchemy import select

    p = A.apriori_params(db)
    ms = float(min_support) if min_support is not None else p["min_support"]
    mc = float(min_confidence) if min_confidence is not None else p["min_confidence"]
    ml = float(min_lift) if min_lift is not None else p["min_lift"]
    tn = int(top_n) if top_n is not None else p["top_n"]

    item_attr = {
        "product_name": TransactionItem.product_name,
        "sku_code": TransactionItem.sku_code,
    }[p["group_by"]]
    item_label = assoc_algo.GROUP_BY_COLUMNS[p["group_by"]]
    rows = db.execute(select(TransactionItem.transaction_id, item_attr)).all()
    if not rows:
        return {"found": False, "message": "当前数据库没有交易明细数据，无法运行 Apriori。"}

    tx_map = dict(db.execute(select(Transaction.id, Transaction.transaction_no)).all())
    pairs = [(tx_map.get(tid) or str(tid), (name or "").strip())
             for tid, name in rows if name]

    t0 = datetime.utcnow()
    out = assoc_algo.run_from_pairs(pairs, ms, mc, ml, tn, p["group_by"])
    duration = int((datetime.utcnow() - t0).total_seconds() * 1000)

    db.add(ModelRunLog(algorithm="Apriori 实时重算(预览)",
                       parameters={**out["params"], "basket_key": f"交易号 + {item_label}"},
                       dataset="transactions", status="success",
                       output=f"{len(out['rules'])} 条规则", duration_ms=duration))
    db.add(AuditLog(user=user, action="run_apriori", target="association",
                    detail=f"参数 sup={ms}/conf={mc}/lift={ml} → {len(out['rules'])} 条规则", ip="127.0.0.1"))
    db.commit()
    return {"found": True, **out, "duration_ms": duration}


# ---------- 需求预测 ----------
def forecast(db: Session, category: Optional[str] = None) -> Dict:
    views = A.forecast_views(db)
    if category:
        views = [v for v in views if v["category"] == category]
        if not views:
            return {"found": False, "message": f"没有找到品类「{category}」的预测数据。"}
    return {"found": True, "items": views, "count": len(views)}


# ---------- 缺货风险 ----------
def stockout_risk(db: Session, top_n: int = 5) -> Dict:
    sales = A.category_sales_agg(db)
    rows = sorted(sales.items(), key=lambda x: -x[1]["stockout_count"])[:top_n]
    return {
        "items": [
            {"category": k, "stockout_count": v["stockout_count"], "months": v["months"],
             "avg_turnover_days": v["avg_turnover_days"], "sku_count": v["avg_sku_count"]}
            for k, v in rows
        ]
    }


# ---------- 数据质量 ----------
def data_quality(db: Session, dataset_type: Optional[str] = None) -> Dict:
    q = db.query(DataQualityReport)
    if dataset_type:
        q = q.filter(DataQualityReport.dataset_type == dataset_type)
    rows = q.all()
    if not rows:
        return {"items": [], "message": "尚未生成数据质量报告。"}
    return {
        "items": [
            {
                "dataset_type": r.dataset_type, "version": r.dataset_version,
                "total_rows": r.total_rows, "completeness": r.completeness,
                "consistency": r.consistency, "validity": r.validity,
                "uniqueness": r.uniqueness, "timeliness": r.timeliness,
                "overall_score": r.overall_score, "issues": r.issues or [],
                "checked_at": r.checked_at.isoformat() if r.checked_at else None,
            }
            for r in rows
        ]
    }


# ---------- 门店画像 ----------
def store_profile(db: Session, store_id: Optional[int] = None) -> Dict:
    q = db.query(Store)
    if store_id:
        q = q.filter(Store.id == store_id)
    store = q.first()
    if not store:
        return {"found": False, "message": "没有找到门店记录。"}
    profile_fields = {
        "3公里人口": store.pop_3km, "居民占比": store.resident_ratio,
        "办公人群占比": store.office_ratio, "学生占比": store.student_ratio,
        "中老年占比": store.senior_ratio, "消费能力": store.consumption_power,
        "住宅POI": store.poi_residential, "办公POI": store.poi_office,
        "学校POI": store.poi_school, "主要竞品": store.main_competitors,
        "配送能力": store.delivery_capability,
    }
    missing = [k for k, v in profile_fields.items() if v in (None, "", "待接入")]
    return {
        "found": True,
        "store": {"id": store.id, "name": store.name, "city": store.city,
                   "district": store.district, "business_district": store.business_district,
                   "store_type": store.store_type, "area_sqm": store.area_sqm},
        "profile": profile_fields,
        "missing_fields": missing,
        "complete": len(missing) == 0,
        "note": "当前附件未包含门店周边人口与 POI 数据，千店千面模块为「门店画像配置 + 数据待接入」状态，平台不会自行编造人口数量。",
    }


# ---------- 自有品牌 ----------
def private_label(db: Session) -> Dict:
    return advisor.private_label_opportunity(A.health_rows(db))


# ---------- 新品 ----------
def new_products(db: Session, limit: int = 10) -> Dict:
    rows = db.query(CandidateProduct).order_by(CandidateProduct.created_at.desc()).limit(limit).all()
    return {
        "items": [
            {"id": r.id, "name": r.name, "category": r.category.name if r.category else "",
             "brand": r.brand, "supplier": r.supplier,
             "potential_level": r.potential_level, "completeness_score": r.completeness_score,
             "is_private_label": r.is_private_label}
            for r in rows
        ],
        "count": len(rows),
        "note": "新品评估使用解释型等级（高潜力/中等潜力/谨慎试销），不输出成功概率等虚构精度。",
    }


# ---------- 审批 ----------
def create_approval(db: Session, user: str, title: str, content: str, data_basis: str,
                    risk_level: str = "Level 3", affected: str = "") -> Dict:
    """Level 3 高影响建议必须走人工审批。"""
    now = datetime.utcnow()
    seq = db.query(ApprovalRequest).count() + 1
    code = f"AR-{now.strftime('%Y%m%d')}-{seq:04d}"

    rec = AiRecommendation(
        code=f"REC-{seq:04d}", source_module="AI选品助手", title=title,
        content=content, data_basis=data_basis, affected_categories=affected,
        priority="高", risk_level=risk_level, requires_approval=True,
        decision_status="待审", created_by=user, created_at=now,
        parameters={"level": risk_level},
    )
    db.add(rec)
    db.flush()
    ar = ApprovalRequest(
        code=code, recommendation_id=rec.id, source_module="AI选品助手",
        ai_suggestion=f"{title}\n\n{content}", data_basis=data_basis,
        risk_level=risk_level, applicant=user, status="待审批", submitted_at=now,
    )
    db.add(ar)
    db.add(AuditLog(user=user, action="create_approval", target=code,
                    detail=f"{risk_level} 建议提交审批", ip="127.0.0.1"))
    db.commit()
    return {"found": True, "code": code, "risk_level": risk_level,
            "message": f"已提交审批（编号 {code}）。AI 不能自动执行该操作，需采购人员或管理员审批。"}


# ---------- 分析记录 ----------
def analysis_history(db: Session, limit: int = 10) -> Dict:
    jobs = db.query(AnalysisJob).order_by(AnalysisJob.created_at.desc()).limit(limit).all()
    runs = db.query(ModelRunLog).order_by(ModelRunLog.created_at.desc()).limit(limit).all()
    return {
        "jobs": [
            {"type": j.job_type, "status": j.status, "algorithm": j.algorithm,
             "created_at": j.created_at.isoformat() if j.created_at else None,
             "summary": j.result_summary}
            for j in jobs
        ],
        "runs": [
            {"algorithm": r.algorithm, "status": r.status, "dataset": r.dataset,
             "duration_ms": r.duration_ms, "output": r.output,
             "created_at": r.created_at.isoformat() if r.created_at else None,
             "parameters": r.parameters}
            for r in runs
        ],
    }


# ---------- 风险预警 ----------
def risk_alerts(db: Session) -> Dict:
    return {"items": advisor.risk_alerts(A.health_rows(db), A.forecast_views(db), **A.risk_params(db))}


# ---------- 模型参数 ----------
def model_settings(db: Session) -> Dict:
    rows = db.query(ModelSetting).all()
    return {
        "items": [
            {"key": r.key, "value": r.value, "description": r.description,
             "updated_by": r.updated_by, "updated_at": r.updated_at.isoformat() if r.updated_at else None,
             "previous_value": r.previous_value, "change_reason": r.change_reason}
            for r in rows
        ]
    }