"""小类比较引擎

与大类比较的关键差异：小类层没有毛利、周转、坪效数据（附件交易明细不含这些字段），
因此采用两维评分模型：
    Score = 销量得分×0.50 + 销售额得分×0.50

平台不会用大类数据摊派到小类，也不会伪造指标。
若后续在数据中心上传 SKU 级数据（含毛利率、周转），模型自动切换回四维。
"""
from typing import Dict, List, Optional

from .common import minmax_normalize, validate_weights

# 小类层可用的两维权重
SUB_WEIGHTS = {"sales_qty": 0.50, "sales_amount": 0.50}

SUB_REQUIRED = ["sales_qty", "sales_amount"]

SUB_DIMENSION_LABELS = {
    "sales_qty": "销量",
    "sales_amount": "销售额",
}

# 大类模型的四维权重，用于说明差异
FULL_WEIGHTS = {"sales": 0.30, "margin": 0.30, "turnover": 0.20, "space": 0.20}

# 四维模型需要的字段
FULL_REQUIRED = ["sales_qty", "sales_amount", "gross_profit", "turnover_days", "sales_per_sqm"]


FIELD_CN = {
    "gross_profit": "毛利额",
    "turnover_days": "周转天数",
    "sales_per_sqm": "坪效",
    "sales_qty": "销量",
    "sales_amount": "销售额",
}


def resolve_model(candidates: List[Dict]) -> Dict:
    """判断能否用四维模型，不能则降级为两维。"""
    if not candidates:
        return {
            "mode": "unavailable",
            "weights": SUB_WEIGHTS,
            "missing": SUB_REQUIRED,
            "reason": "没有选择任何比较对象",
        }

    missing = []
    for c in candidates:
        for f in FULL_REQUIRED:
            if c.get(f) is None:
                missing.append(f)
    has_full = len(missing) == 0

    if has_full:
        return {
            "mode": "full",
            "weights": FULL_WEIGHTS,
            "missing": [],
            "reason": "数据完整，采用四维模型（销量30% + 毛利30% + 周转20% + 坪效20%）",
        }

    # 降级：检查两维是否可用
    missing_sub = []
    for c in candidates:
        for f in SUB_REQUIRED:
            if c.get(f) is None:
                missing_sub.append(f)
    if missing_sub:
        return {
            "mode": "unavailable",
            "weights": SUB_WEIGHTS,
            "missing": list(set(missing_sub)),
            "reason": f"比较对象缺少必要字段：{', '.join(sorted(set(missing_sub)))}",
        }

    uniq = sorted(set(missing))
    return {
        "mode": "reduced",
        "weights": SUB_WEIGHTS,
        "missing": uniq,
        "reason": (
            f"小类层数据不含 {'、'.join(FIELD_CN.get(m, m) for m in uniq)}，"
            "平台不做推算，已降级为两维模型（销量50% + 销售额50%）"
        ),
        "upgrade_hint": (
            "在「数据中心」上传 SKU 级数据（含毛利率、库存周转天数、坪效）后，"
            "本模块会自动切换回四维模型"
        ),
    }


def compare_subcategories(
    candidates: List[Dict],
    weights: Optional[Dict[str, float]] = None,
) -> Dict:
    """小类比较主函数。

    candidates 每项需含 name、sales_qty、sales_amount。
    可选：category、avg_price、transaction_count、qty_per_transaction、
          association_count、max_lift、abc_class
    """
    if len(candidates) < 2:
        return {"success": False, "message": "至少需要 2 个比较对象"}
    if len(candidates) > 6:
        return {"success": False, "message": "最多支持 6 个比较对象"}

    model = resolve_model(candidates)
    if model["mode"] == "unavailable":
        return {
            "success": False,
            "message": model["reason"],
            "model": model,
        }

    items = list(candidates)
    w = validate_weights(weights or model["weights"])

    if model["mode"] == "full":
        qty_s = minmax_normalize([c["sales_qty"] for c in items], True)
        amt_s = minmax_normalize([c["sales_amount"] for c in items], True)
        profit_s = minmax_normalize([c["gross_profit"] for c in items], True)
        # 周转天数逆向标准化
        turn_s = minmax_normalize([c["turnover_days"] for c in items], False)
        space_s = minmax_normalize([c["sales_per_sqm"] for c in items], True)
        dims = [
            {"key": "sales_qty", "label": "销量", "weight": w["sales"]},
            {"key": "sales_amount", "label": "销售额", "weight": w["margin"]},
            {"key": "gross_profit", "label": "毛利额", "weight": w["turnover"]},
            {"key": "turnover_days", "label": "库存周转", "weight": w["space"]},
            {"key": "sales_per_sqm", "label": "坪效", "weight": 0},
        ]
    else:
        qty_s = minmax_normalize([c["sales_qty"] for c in items], True)
        amt_s = minmax_normalize([c["sales_amount"] for c in items], True)
        dims = [
            {"key": "sales_qty", "label": "销量", "weight": w["sales_qty"]},
            {"key": "sales_amount", "label": "销售额", "weight": w["sales_amount"]},
        ]

    rows = []
    for i, c in enumerate(items):
        if model["mode"] == "full":
            scores = {
                "sales_qty": qty_s[i], "sales_amount": amt_s[i],
                "gross_profit": profit_s[i], "turnover_days": turn_s[i],
                "sales_per_sqm": space_s[i],
            }
            overall = round(
                scores["sales_qty"] * w["sales"]
                + scores["sales_amount"] * w["margin"]
                + scores["gross_profit"] * w["turnover"]
                + scores["sales_per_sqm"] * w["space"], 2)
        else:
            scores = {"sales_qty": qty_s[i], "sales_amount": amt_s[i]}
            overall = round(
                scores["sales_qty"] * w["sales_qty"] + scores["sales_amount"] * w["sales_amount"], 2)

        rows.append({
            "id": c.get("id"),
            "name": c["name"],
            "category": c.get("category"),
            "abc_class": c.get("abc_class"),
            "scores": {k: round(v, 2) for k, v in scores.items()},
            "overall_score": overall,
            "raw": {
                "sales_qty": c.get("sales_qty"),
                "sales_amount": c.get("sales_amount"),
                "avg_price": c.get("avg_price"),
                "transaction_count": c.get("transaction_count"),
                "qty_per_transaction": c.get("qty_per_transaction"),
                "association_count": c.get("association_count"),
                "max_lift": c.get("max_lift"),
                "top_partner": c.get("top_partner"),
                "gross_profit": c.get("gross_profit"),
                "turnover_days": c.get("turnover_days"),
                "sales_per_sqm": c.get("sales_per_sqm"),
            },
        })

    rows.sort(key=lambda r: -r["overall_score"])
    for idx, r in enumerate(rows):
        r["rank"] = idx + 1
        r["priority"] = chr(ord("A") + idx)
        r["recommendation"] = _recommend(r, idx, len(rows))

    return {
        "success": True,
        "mode": "subcategory",
        "model": model,
        "weights": w,
        "dimensions": dims,
        "items": rows,
        "best": rows[0]["name"],
        "worst": rows[-1]["name"],
        "conclusion": _conclusion(rows, model),
        "ai_judgement": _judgement(rows, model),
        "disclaimer": "AI建议，仅供辅助决策，最终选品由采购人员确认。",
    }


def _recommend(row: Dict, idx: int, total: int) -> Dict:
    s = row["overall_score"]
    abc = row.get("abc_class")
    if idx == 0:
        action = "推荐保留"
        reason = f"综合得分 {s}，在本次比较中排名第一。"
    elif idx == total - 1:
        action = "建议精简" if s >= 50 else "建议退出"
        reason = f"综合得分 {s}，排名末位。"
    elif s >= 70:
        action = "推荐保留"
        reason = f"综合得分 {s}，处于中上水平。"
    else:
        action = "建议观察"
        reason = f"综合得分 {s}，表现中等，建议观察一个周期。"

    strengths, risks = [], []
    sc = row["scores"]
    for k, v in sc.items():
        label = SUB_DIMENSION_LABELS.get(k, k)
        if v >= 80:
            strengths.append(f"{label}得分 {v}")
        if v <= 30:
            risks.append(f"{label}得分仅 {v}")
    if (row["raw"].get("max_lift") or 0) >= 3:
        strengths.append(f"关联强度高（最高提升度 {row['raw']['max_lift']}）")
    if not strengths:
        strengths.append("无突出优势维度")
    if not risks:
        risks.append("无显著风险维度")

    if abc:
        risks.append(f"ABC 分类为 {abc} 类")

    return {
        "action": action,
        "reason": reason,
        "strengths": strengths[:3],
        "risks": risks[:3],
        "change_condition": (
            f"该商品当前销量 {row['raw']['sales_qty']} 件、销售额 {row['raw']['sales_amount']} 元。"
            "若销量提升 20% 或能通过关联陈列带动连带率，综合排名将明显上升；"
            "若销量继续下滑且无提升空间，结论可能反转。"
        ),
    }


def _conclusion(rows: List[Dict], model: Dict) -> str:
    top, bottom = rows[0], rows[-1]
    note = "" if model["mode"] == "full" else "（基于两维模型，小类层无毛利与周转数据）"
    return (
        f"小类比较结果{note}：{top['name']} 综合得分 {top['overall_score']} 排名第一；"
        f"{bottom['name']} 得分 {bottom['overall_score']} 排名末位。"
    )


def _judgement(rows: List[Dict], model: Dict) -> Dict:
    top, bottom = rows[0], rows[-1]
    return {
        "ranking": [{"priority": r["priority"], "name": r["name"], "score": r["overall_score"]} for r in rows],
        "recommend_keep": [r["name"] for r in rows if r["recommendation"]["action"] == "推荐保留"],
        "suggest_watch": [r["name"] for r in rows if r["recommendation"]["action"] == "建议观察"],
        "suggest_simplify": [r["name"] for r in rows if r["recommendation"]["action"] == "建议精简"],
        "suggest_exit": [r["name"] for r in rows if r["recommendation"]["action"] == "建议退出"],
        "why": top["recommendation"]["reason"],
        "key_metrics": top["recommendation"]["strengths"],
        "max_risk": bottom["recommendation"]["risks"],
        "change_condition": top["recommendation"]["change_condition"],
        "model_note": model["reason"],
        "disclaimer": "AI建议，仅供辅助决策，最终选品由采购人员确认。",
    }
