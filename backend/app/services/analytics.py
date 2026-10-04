"""业务服务层：把算法结果与数据库组装成 API 响应"""
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy.orm import Session

from ..algorithms import advisor, association as assoc_algo, compare as cmp_algo
from ..algorithms import data_quality as dq, forecast as fc_algo, health as health_algo
from ..config import DEMO_DISCLAIMER, DEMO_SOURCE
from ..models import (
    AnalysisJob, ApprovalRequest, AssociationRule, AuditLog, CandidateProduct,
    Category, CategoryHealthResult, CategorySales, DataQualityReport, DataUpload,
    DemandRecord, ModelRunLog, ModelSetting, SkuProduct, Store, Transaction,
)


# ---------------- 参数读写 ----------------

def get_setting(db: Session, key: str, default=None):
    s = db.query(ModelSetting).filter(ModelSetting.key == key).first()
    if s is None:
        return default
    return s.value


def set_setting(db: Session, key: str, value, user: str, reason: str = "") -> ModelSetting:
    s = db.query(ModelSetting).filter(ModelSetting.key == key).first()
    if s is None:
        s = ModelSetting(key=key, value=value)
        db.add(s)
    else:
        s.previous_value = s.value
        s.value = value
    s.updated_by = user
    s.updated_at = datetime.utcnow()
    s.change_reason = reason
    db.flush()
    return s


def apriori_params(db: Session) -> Dict:
    return {
        "min_support": float(get_setting(db, "apriori_min_support", 0.02)),
        "min_confidence": float(get_setting(db, "apriori_min_confidence", 0.50)),
        "min_lift": float(get_setting(db, "apriori_min_lift", 1.50)),
        "top_n": int(get_setting(db, "apriori_top_n", 20)),
        "group_by": get_setting(db, "apriori_group_by", "product_name"),
    }


def risk_params(db: Session) -> Dict:
    return {
        "stockout_threshold": int(get_setting(db, "risk_stockout_threshold", 8)),
        "turnover_threshold": float(get_setting(db, "risk_turnover_threshold", 45.0)),
        "space_threshold": float(get_setting(db, "risk_space_threshold", 600.0)),
        "score_threshold": float(get_setting(db, "risk_score_threshold", 55.0)),
    }


# ---------------- 品类健康度 ----------------

def _health_to_dict(r: CategoryHealthResult, extra: Dict = None) -> Dict:
    d = {
        "id": r.id,
        "category_id": r.category_id,
        "category": r.category.name if r.category else "",
        "source": r.source,
        "source_label": "附件预置参考结果" if r.source == "attachment" else "系统重算结果",
        "overall_score": r.overall_score,
        "grade": r.grade,
        "stars": r.stars,
        "sales_score": r.sales_score,
        "margin_score": r.margin_score,
        "turnover_score": r.turnover_score,
        "space_score": r.space_score,
        "sales_contribution": r.sales_contribution,
        "margin_contribution": r.margin_contribution,
        "avg_turnover_days": r.avg_turnover_days,
        "avg_sales_per_sqm": r.avg_sales_per_sqm,
        "total_stockout": r.total_stockout,
        "sku_count": r.sku_count,
        "sales_trend": r.sales_trend,
        "margin_trend": r.margin_trend,
        "turnover_trend": r.turnover_trend,
        "space_trend": r.space_trend,
        "diagnosis": r.diagnosis,
        "suggestion": r.suggestion,
        "alert_light": r.alert_light,
        "algorithm": r.algorithm,
        "parameters": r.parameters,
        "source_dataset_id": r.source_dataset_id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "demo_label": DEMO_DISCLAIMER,
    }
    if extra:
        d.update(extra)
    return d


def health_rows(db: Session, source: str = "system") -> List[Dict]:
    """返回系统重算结果，并补上附件参考结果做差异对比。"""
    rows = (
        db.query(CategoryHealthResult)
        .filter(CategoryHealthResult.source == source)
        .all()
    )
    attachment = {
        r.category_id: r for r in
        db.query(CategoryHealthResult).filter(CategoryHealthResult.source == "attachment").all()
    }
    sales_agg = category_sales_agg(db)
    out = []
    for r in rows:
        agg = sales_agg.get(r.category.name, {})
        extra = {
            "rank": None,
            "months": agg.get("months", 12),
            "total_qty": agg.get("total_qty"),
            "total_amount": agg.get("total_amount"),
            "total_profit": agg.get("total_profit"),
            "gross_margin_rate": agg.get("gross_margin_rate"),
            "avg_sku_count": r.sku_count,
            "below_three_star": bool(r.overall_score < 55),
        }
        if agg:
            extra["stockout_count"] = agg.get("stockout_count")
        att = attachment.get(r.category_id)
        if att:
            diff = round((r.overall_score or 0) - (att.overall_score or 0), 2)
            extra["attachment_reference"] = {
                "overall_score": att.overall_score,
                "grade": att.grade,
                "stars": att.stars,
                "suggestion": att.suggestion,
                "alert_light": att.alert_light,
                "source_label": "附件预置参考结果",
            }
            extra["diff_vs_attachment"] = diff
            extra["consistent_with_attachment"] = abs(diff) < 5
        out.append(_health_to_dict(r, extra))

    out.sort(key=lambda x: -(x["overall_score"] or 0))
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out


def category_sales_agg(db: Session, months: int = 12) -> Dict[str, Dict]:
    """从 category_sales 表实时聚合，作为 KPI 与比较的数据源。"""
    from ..models import Category

    rows = db.query(CategorySales).all()
    if not rows:
        return {}
    by_cat: Dict[str, List[CategorySales]] = {}
    for r in rows:
        name = r.category.name if r.category else "未知"
        by_cat.setdefault(name, []).append(r)

    out = {}
    for name, items in by_cat.items():
        items = sorted(items, key=lambda x: x.month)[-months:]
        total_qty = sum(i.sales_qty or 0 for i in items)
        total_amt = sum(i.sales_amount or 0 for i in items)
        total_profit = sum(i.gross_profit or 0 for i in items)
        out[name] = {
            "months": len(items),
            "total_qty": round(total_qty, 2),
            "total_amount": round(total_amt, 2),
            "total_profit": round(total_profit, 2),
            "gross_margin_rate": round(total_profit / total_amt * 100, 2) if total_amt else 0,
            "avg_turnover_days": round(sum(i.turnover_days or 0 for i in items) / len(items), 2),
            "avg_sales_per_sqm": round(sum(i.sales_per_sqm or 0 for i in items) / len(items), 2),
            "stockout_count": int(sum(i.stockout_count or 0 for i in items)),
            "avg_sku_count": round(sum(i.sku_count or 0 for i in items) / len(items), 1),
        }
    return out


# ---------------- 需求预测 ----------------

def forecast_views(db: Session) -> List[Dict]:
    rows = db.query(DemandRecord).order_by(DemandRecord.category_id, DemandRecord.week_no).all()
    by_cat: Dict[int, Dict] = {}
    for r in rows:
        g = by_cat.setdefault(r.category_id, {"history": [], "forecast": []})
        item = {"week_no": r.week_no, "period_label": r.period_label,
                "actual_qty": r.actual_qty, "forecast_qty": r.forecast_qty,
                "lower_bound": r.lower_bound, "upper_bound": r.upper_bound}
        g["history" if r.data_type == "history" else "forecast"].append(item)

    sales = category_sales_agg(db)
    out = []
    for cid, g in by_cat.items():
        cat = db.query(Category).filter_by(id=cid).first()
        if cat is None:
            continue
        agg = sales.get(cat.name, {})
        out.append(fc_algo.build_forecast_view(
            cat.name, g["history"], g["forecast"],
            stockout_count=agg.get("stockout_count"),
        ))
    out.sort(key=lambda x: -(x.get("change_pct") or 0))
    return out


# ---------------- 关联规则 ----------------

def rule_to_dict(r: AssociationRule, params: Dict) -> Dict:
    passes = (r.confidence or 0) >= params["min_confidence"] and (r.lift or 0) >= params["min_lift"]
    explanation = assoc_algo.business_explanation({
        "antecedent": r.antecedent, "consequent": r.consequent,
        "lift": r.lift, "confidence": r.confidence,
    }) if r.source == "realtime" else f"附件预置的参考结果，支持度 {r.support}、置信度 {r.confidence}、提升度 {r.lift}。该结果由附件直接给出，未经平台算法重算。"
    return {
        "id": r.id,
        "antecedent": r.antecedent,
        "consequent": r.consequent,
        "display_rule": r.display_rule,
        "support": r.support,
        "confidence": r.confidence,
        "lift": r.lift,
        "item_count": r.item_count,
        "strength": assoc_algo.strength_label(r.lift or 0, r.confidence or 0),
        "display_suggestion": r.display_suggestion or assoc_algo.display_suggestion(
            {"antecedent": r.antecedent, "consequent": r.consequent}),
        "business_explanation": explanation,
        "source": r.source,
        "source_label": "附件参考关联规则" if r.source == "attachment" else "根据交易数据实时重算的关联规则",
        "passes_threshold": passes,
        "threshold_check": (
            f"置信度 {r.confidence:.3f} {'≥' if (r.confidence or 0) >= params['min_confidence'] else '<'} "
            f"{params['min_confidence']}，提升度 {r.lift:.2f} {'≥' if (r.lift or 0) >= params['min_lift'] else '<'} "
            f"{params['min_lift']}"
        ),
        "algorithm": r.algorithm,
        "parameters": r.parameters,
        "source_dataset_id": r.source_dataset_id,
    }


def association_rules(db: Session, source: Optional[str] = None) -> Dict:
    params = apriori_params(db)
    q = db.query(AssociationRule)
    if source:
        q = q.filter(AssociationRule.source == source)
    rows = q.all()

    items = [rule_to_dict(r, params) for r in rows]
    attachment = [r for r in items if r["source"] == "attachment"]
    realtime = [r for r in items if r["source"] == "realtime"]

    realtime.sort(key=lambda x: -(x["lift"] or 0))
    shown = realtime if source == "realtime" else (realtime + attachment)

    network = build_network(shown[:40])
    return {
        "params": params,
        "attachment_rules": sorted(attachment, key=lambda x: -(x["lift"] or 0)),
        "realtime_rules": realtime[: params["top_n"]],
        "shown": shown,
        "network": network,
        "summary": {
            "attachment_count": len(attachment),
            "attachment_passed": sum(1 for r in attachment if r["passes_threshold"]),
            "realtime_count": len(realtime),
            "items": realtime[0]["antecedent"] if realtime else None,
        },
        "data_note": (
            "附件参考关联规则为原始文件内容，平台原样保留、不做修改；"
            "实时重算结果按当前算法阈值过滤。两者差异通常来自阈值设置、时间范围与商品聚合口径。"
        ),
        "demo_label": DEMO_DISCLAIMER,
    }


def build_network(rules: List[Dict]) -> Dict:
    """构建关联网络图节点与连线。"""
    nodes: Dict[str, Dict] = {}
    edges = []
    for r in rules:
        a, b = r["antecedent"], r["consequent"]
        if " + " in a:
            continue
        for n in (a, b):
            if n not in nodes:
                nodes[n] = {"name": n, "value": 0, "category": ""}
            nodes[n]["value"] += 1
        edges.append({
            "source": a, "target": b,
            "lift": r["lift"], "confidence": r["confidence"], "support": r["support"],
            "strength": r["strength"], "value": round(r["lift"] or 0, 3),
        })
    return {"nodes": list(nodes.values()), "edges": edges}


def rule_summary_for_advisor(db: Session) -> Dict:
    params = apriori_params(db)
    rows = db.query(AssociationRule).filter(AssociationRule.source == "realtime").all()
    items = sorted([rule_to_dict(r, params) for r in rows], key=lambda x: -(x["lift"] or 0))
    basket_count = db.query(Transaction).count()
    return {
        "rules": items,
        "basket_count": basket_count,
        "item_count": len({n["name"] for n in build_network(items)["nodes"]}),
        "params": params,
    }


# ---------------- SKU 数据充分性 ----------------

def sku_data_status(db: Session) -> Dict:
    count = db.query(SkuProduct).count()
    with_metrics = db.query(SkuProduct).filter(
        SkuProduct.sales_qty.isnot(None), SkuProduct.gross_profit.isnot(None),
        SkuProduct.turnover_days.isnot(None), SkuProduct.sales_per_sqm.isnot(None),
    ).count()
    return {
        "sku_count": count,
        "sku_with_metrics": with_metrics,
        "sufficient": count > 0 and with_metrics == count,
        "message": (
            "当前数据足以进行完整 SKU 量化评价。" if count > 0 and with_metrics == count
            else "当前数据不足以进行完整SKU量化评价"
        ),
        "missing": [
            "SKU 级销量", "SKU 级毛利额", "SKU 级库存周转天数", "SKU 级坪效",
        ] if count == 0 else [],
        "upload_hint": "请在「数据中心」上传 SKU 候选商品数据（dataset_sku_products.csv 模板），字段包含采购价、零售价、销量、销售额、毛利率、周转等，导入后本模块自动启用完整量化评价。",
    }


def candidate_dicts(db: Session) -> List[Dict]:
    rows = db.query(SkuProduct).all()
    return [
        {
            "id": r.sku_code, "name": r.product_name,
            "brand": r.brand,
            "is_private_label": r.is_private_label,
            "purchase_price": r.purchase_price,
            "retail_price": r.retail_price,
            "supplier": r.supplier,
            "sales_qty": r.sales_qty,
            "sales_amount": r.sales_amount,
            "gross_profit": r.gross_profit,
            "turnover_days": r.turnover_days,
            "sales_per_sqm": r.sales_per_sqm,
            "stockout_count": r.stockout_count,
            "category": r.category.name if r.category else "",
        }
        for r in rows
    ]


def compare_payload(db: Session, ids: List[str], mode: str, weights: Optional[Dict] = None,
                    category_ids: Optional[List[int]] = None) -> Dict:
    """构建比较输入。mode=sku 时若数据不足直接返回不足提示，不编造。"""
    w = weights or get_setting(db, "compare_weights", {"sales": 0.30, "margin": 0.30, "turnover": 0.20, "space": 0.20})

    if mode == "sku":
        status = sku_data_status(db)
        if not status["sufficient"]:
            return {
                "sufficient": False,
                "mode": mode,
                "message": "当前数据不足以进行完整SKU量化评价",
                "status": status,
                "weights": w,
            }
        all_c = {c["id"]: c for c in candidate_dicts(db)}
        cands = [all_c[i] for i in ids if i in all_c]
    else:
        sales = category_sales_agg(db)
        health = {h["category"]: h for h in health_rows(db)}
        fc = {f["category"]: f for f in forecast_views(db)}
        cands = []
        for cid in (category_ids or []):
            cat = db.query(Category).filter_by(id=cid).first()
            if not cat:
                continue
            agg = sales.get(cat.name)
            if not agg:
                continue
            h = health.get(cat.name, {})
            f = fc.get(cat.name, {})
            cands.append({
                "id": cat.code, "name": cat.name,
                "sales_qty": agg["total_qty"], "sales_amount": agg["total_amount"],
                "gross_profit": agg["total_profit"], "turnover_days": agg["avg_turnover_days"],
                "sales_per_sqm": agg["avg_sales_per_sqm"],
                "stockout_count": agg["stockout_count"], "sku_count": agg["avg_sku_count"],
                "category_health_score": h.get("overall_score"),
                "demand_trend": f.get("trend_level"),
                "category_role": cat.category_role,
                "gross_margin_rate": agg["gross_margin_rate"],
            })

    result = cmp_algo.compare_candidates(cands, w, mode)
    result["sufficient"] = True
    result["demo_label"] = DEMO_DISCLAIMER
    result["ai_judgement"] = cmp_algo.build_ai_judgement(result)
    return result


# ---------------- 新品评估 ----------------

def evaluate_new_product(db: Session, payload: Dict) -> Dict:
    """解释型等级评估，不输出虚构的成功概率。"""
    fields = [
        ("name", "商品名称", 10), ("category_id", "所属品类", 10), ("brand", "品牌", 8),
        ("purchase_price", "采购价", 8), ("suggested_retail_price", "建议零售价", 8),
        ("expected_margin_rate", "预计毛利率", 8), ("supplier", "供应商", 8),
        ("target_consumer", "目标消费者", 8), ("spec", "规格", 6),
        ("packaging", "包装", 5), ("season", "季节", 4), ("selling_point", "新品卖点", 9),
        ("is_private_label", "自有品牌属性", 4), ("reference_sku", "参考同类SKU", 4),
    ]
    filled, missing = [], []
    score = 0.0
    for key, label, weight in fields:
        v = payload.get(key)
        has = v not in (None, "", [])
        if has:
            filled.append(label)
            score += weight
        else:
            missing.append(label)
    completeness = round(score / 100 * 100, 1)

    cat_health = None
    category_name = None
    if payload.get("category_id"):
        cat = db.query(Category).filter_by(id=payload["category_id"]).first()
        if cat:
            category_name = cat.name
            cat_health = next((h for h in health_rows(db) if h["category"] == cat.name), None)
    fc = next((f for f in forecast_views(db) if f["category"] == category_name), None)

    reasons = []
    level = "谨慎试销"
    if cat_health:
        reasons.append(
            f"所属品类「{category_name}」健康度 {cat_health['overall_score']} 分（{cat_health['grade']}），"
            f"毛利贡献 {cat_health['margin_contribution']}%，坪效 {cat_health['avg_sales_per_sqm']} 元/㎡/月"
        )
    if fc:
        reasons.append(
            f"该品类需求趋势为{fc['trend_level']}"
            + (f"（{fc['change_pct']:+.1f}%）" if fc.get("change_pct") is not None else "")
        )
    if completeness < 60:
        reasons.append(f"新品资料完整度仅 {completeness}%，缺少{'、'.join(missing[:4])}，评估置信度有限")

    score_val = 0
    if cat_health:
        score_val += cat_health["overall_score"] * 0.5
        if cat_health["overall_score"] >= 70:
            score_val += 20
    if fc and fc["trend_level"] in ("明显上涨", "温和上涨"):
        score_val += 20
    if fc and fc["trend_level"] in ("明显下降", "温和下降"):
        score_val -= 15
    score_val += completeness * 0.2

    if score_val >= 75:
        level = "高潜力"
    elif score_val >= 55:
        level = "中等潜力"
    else:
        level = "谨慎试销"

    if level == "高潜力":
        reasons.append("综合品类健康度、需求趋势与资料完整度，具备试销条件")
    elif level == "中等潜力":
        reasons.append("综合条件中等，建议小范围试销后复评")
    else:
        reasons.append("当前条件不支持扩大投入，建议先补齐资料再评估")

    return {
        "completeness_score": completeness,
        "filled_fields": filled,
        "missing_fields": missing,
        "potential_level": level,
        "category_health": cat_health["overall_score"] if cat_health else None,
        "category_health_grade": cat_health["grade"] if cat_health else None,
        "demand_trend": fc["trend_level"] if fc else "该品类暂无预测数据",
        "reasons": reasons,
        "risks": [
            "缺少同类 SKU 实际销售数据，无法给出量化成功概率" if not payload.get("reference_sku")
            else "参考同类 SKU 表现仍需结合实际试销验证",
            "新品上市初期销量存在不确定性，建议设置退出条件",
        ],
        "trial_suggestion": (
            "建议在 2-3 家门店设置 4-6 周试销期，试销期结束后对比同品类存量 SKU 的坪效与周转，达标再铺开。"
        ),
        "note": "本评估为规则型解释结论，不输出成功概率等精确数值。缺少数据时不做推测。",
    }