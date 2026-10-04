"""品类健康度评分模型

模型：销量贡献 30% + 毛利贡献 30% + 库存周转 20% + 坪效 20%
关键点：库存周转天数越低越好，必须逆向标准化。
"""
from typing import Dict, List, Optional

import pandas as pd

from .common import MissingFieldError, grade_of, minmax_normalize, trend_pct, validate_weights

REQUIRED_COLUMNS = {
    "品类名称", "月份", "销量(件)", "销售额(元)", "毛利额(元)",
    "库存周转天数", "坪效(元/㎡/月)", "缺货次数", "SKU数量",
}

DEFAULT_WEIGHTS = {"sales": 0.30, "margin": 0.30, "turnover": 0.20, "space": 0.20}


def score_categories(
    df: pd.DataFrame,
    weights: Optional[Dict[str, float]] = None,
    months_window: int = 12,
) -> List[Dict]:
    """输入品类销售明细，输出每个品类的健康度评分明细。

    df 需包含 REQUIRED_COLUMNS 中的全部字段。
    months_window: 聚合最近 N 个月（默认 12）。
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise MissingFieldError(missing, "品类健康度评分")

    w = validate_weights(weights or DEFAULT_WEIGHTS)

    data = df.copy()
    data["月份"] = data["月份"].astype(str)
    # 取最近 N 个月
    all_months = sorted(data["月份"].unique())
    use_months = all_months[-months_window:] if len(all_months) > months_window else all_months
    data = data[data["月份"].isin(use_months)]

    rows: List[Dict] = []
    for cat, g in data.groupby("品类名称"):
        g = g.sort_values("月份")
        total_sales = float(g["销量(件)"].sum())
        total_amount = float(g["销售额(元)"].sum())
        total_profit = float(g["毛利额(元)"].sum())
        # 周转天数与坪效按月取均值（按销量加权更贴近实际，这里用简单均值避免字段缺失）
        avg_turnover = round(float(g["库存周转天数"].mean()), 2)
        avg_space = round(float(g["坪效(元/㎡/月)"].mean()), 2)
        total_stockout = int(g["缺货次数"].sum())
        avg_sku = round(float(g["SKU数量"].mean()), 1)

        rows.append({
            "category": cat,
            "months": len(g),
            "total_qty": total_sales,
            "total_amount": total_amount,
            "total_profit": total_profit,
            "gross_margin_rate": round(total_profit / total_amount * 100, 2) if total_amount else 0.0,
            "avg_turnover_days": avg_turnover,
            "avg_sales_per_sqm": avg_space,
            "stockout_count": total_stockout,
            "avg_sku_count": avg_sku,
            "_sales_series": g["销量(件)"].astype(float).tolist(),
            "_profit_series": g["毛利额(元)"].astype(float).tolist(),
            "_turnover_series": g["库存周转天数"].astype(float).tolist(),
            "_space_series": g["坪效(元/㎡/月)"].astype(float).tolist(),
        })

    if not rows:
        return []

    total_qty_all = sum(r["total_qty"] for r in rows) or 1.0
    total_profit_all = sum(r["total_profit"] for r in rows) or 1.0

    # 销量贡献 / 毛利贡献：份额型指标，本身已归一，无需再 Min-Max
    sales_contrib = [r["total_qty"] / total_qty_all * 100 for r in rows]
    margin_contrib = [r["total_profit"] / total_profit_all * 100 for r in rows]

    # 坪效：越高越好 → 正向 Min-Max
    space_scores = minmax_normalize([r["avg_sales_per_sqm"] for r in rows], higher_is_better=True)
    # 周转天数：越低越好 → 逆向 Min-Max（这是本模型最容易写错的地方）
    turnover_scores = minmax_normalize([r["avg_turnover_days"] for r in rows], higher_is_better=False)

    results = []
    for i, r in enumerate(rows):
        sales_score = round(sales_contrib[i] / max(sales_contrib) * 100, 2) if max(sales_contrib) else 0.0
        margin_score = round(margin_contrib[i] / max(margin_contrib) * 100, 2) if max(margin_contrib) else 0.0

        overall = round(
            sales_score * w["sales"]
            + margin_score * w["margin"]
            + turnover_scores[i] * w["turnover"]
            + space_scores[i] * w["space"], 2
        )
        grade, stars, below_three = grade_of(overall)

        r2 = {k: v for k, v in r.items() if not k.startswith("_")}
        r2.update({
            "sales_score": sales_score,
            "margin_score": margin_score,
            "turnover_score": turnover_scores[i],
            "space_score": space_scores[i],
            "overall_score": overall,
            "grade": grade,
            "stars": stars,
            "below_three_star": below_three,
            "sales_contribution": round(sales_contrib[i], 2),
            "margin_contribution": round(margin_contrib[i], 2),
            "sales_trend": trend_pct(r["_sales_series"]),
            "margin_trend": trend_pct(r["_profit_series"]),
            "turnover_trend": trend_pct(r["_turnover_series"]),
            "space_trend": trend_pct(r["_space_series"]),
            "alert_light": alert_light(overall, r["avg_turnover_days"], total_stockout),
        })
        results.append(r2)

    results.sort(key=lambda x: x["overall_score"], reverse=True)
    for idx, r in enumerate(results, 1):
        r["rank"] = idx
        r["diagnosis"] = build_diagnosis(r)
        r["suggestion"] = build_suggestion(r)
    return results


def alert_light(score: float, turnover: float, stockout: int) -> str:
    if score >= 75:
        return "绿灯"
    if score >= 55:
        return "黄灯"
    if score >= 40:
        return "橙灯"
    return "红灯"


def build_diagnosis(r: Dict) -> str:
    parts = []
    if r["stockout_count"] >= 15:
        parts.append(f"缺货 {r['stockout_count']} 次，供货稳定性偏弱")
    elif r["stockout_count"] >= 6:
        parts.append(f"缺货 {r['stockout_count']} 次，需关注高频次缺")
    else:
        parts.append(f"缺货 {r['stockout_count']} 次，供货基本稳定")

    if r["avg_turnover_days"] > 60:
        parts.append(f"平均周转 {r['avg_turnover_days']} 天，资金占用偏重")
    elif r["avg_turnover_days"] > 35:
        parts.append(f"平均周转 {r['avg_turnover_days']} 天，处于中等区间")
    else:
        parts.append(f"平均周转 {r['avg_turnover_days']} 天，流转效率良好")

    if r["margin_contribution"] > 25:
        parts.append(f"贡献毛利 {r['margin_contribution']}%，是门店主要利润来源")
    elif r["margin_contribution"] < 8:
        parts.append(f"毛利贡献仅 {r['margin_contribution']}%，对利润贡献偏低")

    return "；".join(parts) + "。"


def build_suggestion(r: Dict) -> str:
    s = r["overall_score"]
    if s >= 85:
        return "保持优势，优先保障货源稳定，可适度扩充高毛利子品类。"
    if s >= 70:
        return "整体良好，建议优化商品结构，聚焦核心 SKU，减少长尾低效品。"
    if s >= 55:
        return "建议重点优化：精简低效 SKU，提升连带率与坪效表现。"
    if s >= 40:
        return "建议大幅精简 SKU 数量，缩减陈列面积，保留核心刚需品。"
    return "建议评估退出或转为线上专供，避免占用门店资源。"