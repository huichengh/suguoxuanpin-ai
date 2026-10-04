"""选品比较引擎

对 2-6 个候选对象（品类或 SKU）做多维标准化打分与排序。
周转天数逆向标准化在这里同样适用。
"""
from typing import Dict, List, Optional

from .common import MissingFieldError, minmax_normalize, validate_weights

DEFAULT_WEIGHTS = {"sales": 0.30, "margin": 0.30, "turnover": 0.20, "space": 0.20}

SKU_REQUIRED_FIELDS = [
    "sales_qty", "sales_amount", "gross_profit", "turnover_days", "sales_per_sqm"
]

DIMENSION_LABELS = {
    "sales": "销量",
    "margin": "毛利",
    "turnover": "库存周转",
    "space": "坪效",
}


def sku_data_sufficient(candidates: List[Dict]) -> bool:
    """SKU 级评价必须有真实经营指标，缺任一关键字段即判为不足。"""
    if not candidates:
        return False
    for c in candidates:
        for f in SKU_REQUIRED_FIELDS:
            if c.get(f) is None:
                return False
    return True


def missing_sku_fields(candidates: List[Dict]) -> List[str]:
    missing = set()
    for c in candidates:
        for f in SKU_REQUIRED_FIELDS:
            if c.get(f) is None:
                missing.add(f)
    return sorted(missing)


def compare_candidates(
    candidates: List[Dict],
    weights: Optional[Dict[str, float]] = None,
    mode: str = "category",
) -> Dict:
    """mode: category | sku

    candidates 每项需包含：id, name, sales_qty, sales_amount, gross_profit,
    turnover_days, sales_per_sqm；缺失则抛 MissingFieldError。
    """
    if len(candidates) < 2:
        raise ValueError("至少需要 2 个比较对象")
    if len(candidates) > 6:
        raise ValueError("最多支持 6 个比较对象")

    for c in candidates:
        miss = [f for f in SKU_REQUIRED_FIELDS if c.get(f) is None]
        if miss:
            raise MissingFieldError(miss, f"比较对象「{c.get('name', c.get('id'))}」")

    w = validate_weights(weights or DEFAULT_WEIGHTS)
    items = list(candidates)

    sales_scores = minmax_normalize([c["sales_qty"] for c in items], True)
    margin_scores = minmax_normalize([c["gross_profit"] for c in items], True)
    # 周转天数逆向：越低越好
    turnover_scores = minmax_normalize([c["turnover_days"] for c in items], False)
    space_scores = minmax_normalize([c["sales_per_sqm"] for c in items], True)

    rows = []
    for i, c in enumerate(items):
        scores = {
            "sales": sales_scores[i],
            "margin": margin_scores[i],
            "turnover": turnover_scores[i],
            "space": space_scores[i],
        }
        overall = round(sum(scores[k] * w[k] for k in w), 2)
        amount = c["sales_amount"] or 0
        profit = c["gross_profit"] or 0
        rows.append({
            "id": c.get("id"),
            "name": c.get("name"),
            "scores": scores,
            "overall_score": overall,
            "raw": {
                "sales_qty": c["sales_qty"],
                "sales_amount": amount,
                "gross_profit": profit,
                "gross_margin_rate": round(profit / amount * 100, 2) if amount else None,
                "turnover_days": c["turnover_days"],
                "sales_per_sqm": c["sales_per_sqm"],
                "stockout_count": c.get("stockout_count"),
                "sku_count": c.get("sku_count"),
                "category_health_score": c.get("category_health_score"),
                "association_power": c.get("association_power"),
                "demand_trend": c.get("demand_trend"),
            },
            "extra": {k: v for k, v in c.items() if k not in SKU_REQUIRED_FIELDS and k not in ("id", "name")},
        })

    rows.sort(key=lambda x: x["overall_score"], reverse=True)
    for idx, r in enumerate(rows):
        r["rank"] = idx + 1
        r["priority"] = chr(ord("A") + idx)
        r["recommendation"] = recommend_action(r, idx, len(rows))

    return {
        "mode": mode,
        "weights": w,
        "items": rows,
        "dimensions": [
            {"key": k, "label": DIMENSION_LABELS[k], "weight": w[k]} for k in w
        ],
        "best": rows[0]["name"],
        "worst": rows[-1]["name"],
        "conclusion": build_conclusion(rows, mode),
    }


def recommend_action(row: Dict, idx: int, total: int) -> Dict:
    s = row["overall_score"]
    raw = row["raw"]
    if idx == 0:
        action = "推荐保留"
        reason = f"综合得分 {s}，在本次比较中排名第一。"
    elif idx == total - 1:
        action = "建议精简" if s >= 40 else "建议退出"
        reason = f"综合得分 {s}，在本次比较中排名末位。"
    elif s >= 70:
        action = "建议保留"
        reason = f"综合得分 {s}，处于可比对象中上水平。"
    else:
        action = "建议观察"
        reason = f"综合得分 {s}，表现中等，建议观察一个周期。"

    strengths, risks = [], []
    sc = row["scores"]
    for k in ("sales", "margin", "turnover", "space"):
        if sc[k] >= 80:
            strengths.append(f"{DIMENSION_LABELS[k]}得分 {sc[k]}")
        if sc[k] <= 30:
            risks.append(f"{DIMENSION_LABELS[k]}得分仅 {sc[k]}")
    if raw.get("stockout_count") and raw["stockout_count"] >= 15:
        risks.append(f"缺货 {raw['stockout_count']} 次，供货稳定性不足")
    if not strengths:
        strengths.append("无突出优势维度")
    if not risks:
        risks.append("无显著风险维度")

    return {
        "action": action,
        "reason": reason,
        "strengths": strengths[:3],
        "risks": risks[:3],
        "change_condition": change_condition(row),
    }


def change_condition(row: Dict) -> str:
    t = row["raw"].get("turnover_days") or 10
    return (
        f"若该对象周转天数降至 {max(1, round(t * 0.7))} 天以内，"
        f"或坪效提升 20%，综合得分将明显上升；若缺货次数继续增加且销量下滑，结论可能反转。"
    )


def build_conclusion(rows: List[Dict], mode: str) -> str:
    top = rows[0]
    bottom = rows[-1]
    top_dims = [DIMENSION_LABELS[k] for k, v in top["scores"].items() if v >= 80]
    label = "品类" if mode == "category" else "商品"
    return (
        f"综合{label}比较，{top['name']} 综合得分 {top['overall_score']} 排名第一，"
        f"优势维度为{'、'.join(top_dims) if top_dims else '综合表现'}；"
        f"{bottom['name']} 得分 {bottom['overall_score']} 排名末位。"
    )


def build_ai_judgement(result: Dict) -> Dict:
    """生成「AI 综合判断」结构化输出。"""
    rows = result["items"]
    top = rows[0]
    bottom = rows[-1]
    # 建议扩充：评分高且需求趋势上行
    expand = [
        r["name"] for r in rows
        if r["scores"]["sales"] >= 60 and (r["raw"].get("demand_trend") or "").find("上涨") >= 0
    ]
    return {
        "ranking": [{"priority": r["priority"], "name": r["name"], "score": r["overall_score"]} for r in rows],
        "recommend_keep": [r["name"] for r in rows if r["recommendation"]["action"] == "推荐保留"],
        "suggest_expand": expand,
        "suggest_watch": [r["name"] for r in rows if r["recommendation"]["action"] == "建议观察"],
        "suggest_simplify": [r["name"] for r in rows if r["recommendation"]["action"] == "建议精简"],
        "suggest_exit": [r["name"] for r in rows if r["recommendation"]["action"] == "建议退出"],
        "why": top["recommendation"]["reason"],
        "key_metrics": top["recommendation"]["strengths"],
        "max_risk": bottom["recommendation"]["risks"],
        "change_condition": top["recommendation"]["change_condition"],
        "disclaimer": "AI建议，仅供辅助决策，最终选品由采购人员确认。",
    }