"""商品 ABC 分类（C 方案）

替代 K-means 聚类。原因：当前演示数据的小类销量极差仅 3.2 倍、
均价极差 1.13 倍，K-means 分出的簇内部差异极小（明星品 1338 件 vs 长尾品 1273 件），
聚类效果说服力不足。ABC 分类基于累计销售额占比，
不依赖细粒度区分度，在数据分布均匀时依然能给出可解释的经营结论。

ABC 分类原理：
    按销售额降序排列，逐个累加占比：
      A 类：累计占比 ≤ 70%   —— 核心商品，销售额贡献主力
      B 类：70% < 累计 ≤ 90% —— 次要商品
      C 类：累计占比 > 90%   —— 长尾商品，数量多但贡献低

每类给出差异化的库存、陈列与策略建议。
"""
from typing import Dict, List, Optional

CLASS_PROFILES = {
    "A": {
        "name": "A类 核心商品",
        "color": "#257354",
        "ratio": "累计销售额 0-70%",
        "desc": "销售额贡献主力，商品数少但金额集中",
        "advice": "重点保障货源，设置安全库存，给予最佳陈列位置，避免缺货",
        "inventory": "高库存深度，按销量波动灵活补货",
    },
    "B": {
        "name": "B类 次要商品",
        "color": "#4a7fb5",
        "ratio": "累计销售额 70-90%",
        "desc": "销售贡献中等，是A类与长尾之间的过渡层",
        "advice": "维持现有陈列，通过关联陈列提升连带率，挖掘利润空间",
        "inventory": "中等库存深度，周转异常时及时调整订货量",
    },
    "C": {
        "name": "C类 长尾商品",
        "color": "#d9a520",
        "ratio": "累计销售额 90-100%",
        "desc": "商品数量多但销售额贡献低，占用货架与资金",
        "advice": "缩减陈列面积与订货量，评估转线上专供或精简，为A类腾出空间",
        "inventory": "低库存深度，按需订货，滞销即淘汰",
    },
}

# 数据区分度诊断阈值：极差比低于该值时提示数据区分度不足
LOW_DISCRIMINATION_RATIO = 2.0


def diagnose_discrimination(items: List[Dict]) -> Dict:
    """诊断小类数据的区分度，用于诚实展示算法效果边界。"""
    out = {}
    for f, label in [("sales_qty", "销量"), ("sales_amount", "销售额"), ("avg_price", "均价")]:
        vals = sorted(float(i[f]) for i in items if i.get(f) is not None)
        if not vals:
            continue
        lo, hi = vals[0], vals[-1]
        ratio = hi / lo if lo > 0 else 0
        out[f] = {
            "label": label,
            "min": round(lo, 1),
            "median": round(vals[len(vals) // 2], 1),
            "max": round(hi, 1),
            "ratio": round(ratio, 2),
            "low": ratio < LOW_DISCRIMINATION_RATIO,
        }
    return out


def abc_classify(items: List[Dict], a_thresh: float = 0.70, b_thresh: float = 0.90) -> Dict:
    """ABC 分类主函数。

    items 每项需含 name、sales_amount。
    """
    valid = [i for i in items if i.get("sales_amount") is not None and i["sales_amount"] > 0]
    if not valid:
        return {
            "success": False,
            "message": "当前没有可用于 ABC 分类的数据（需要小类销售额字段）。",
            "missing_data": ["小类销售额"],
        }

    ranked = sorted(valid, key=lambda x: -x["sales_amount"])
    total = sum(i["sales_amount"] for i in ranked)
    n = len(ranked)

    rows = []
    cum = 0.0
    for item in ranked:
        share = item["sales_amount"] / total
        cum += share
        if cum <= a_thresh:
            cls = "A"
        elif cum <= b_thresh:
            cls = "B"
        else:
            cls = "C"
        rows.append({
            "name": item.get("name"),
            "category": item.get("category"),
            "sales_amount": round(item["sales_amount"], 1),
            "sales_qty": item.get("sales_qty"),
            "share_pct": round(share * 100, 2),
            "cumulative_pct": round(cum * 100, 2),
            "abc_class": cls,
        })

    # 分类统计
    groups: Dict[str, List[Dict]] = {"A": [], "B": [], "C": []}
    for r in rows:
        groups[r["abc_class"]].append(r)

    class_stats = []
    for c in ("A", "B", "C"):
        g = groups[c]
        prof = CLASS_PROFILES[c]
        amount = sum(r["sales_amount"] for r in g)
        class_stats.append({
            "class": c,
            "name": prof["name"],
            "color": prof["color"],
            "ratio_desc": prof["ratio"],
            "description": prof["desc"],
            "advice": prof["advice"],
            "inventory_policy": prof["inventory"],
            "count": len(g),
            "count_pct": round(len(g) / n * 100, 1),
            "sales_amount": round(amount, 1),
            "sales_pct": round(amount / total * 100, 2),
            "avg_amount_per_item": round(amount / len(g), 1) if g else 0,
            "items": g,
        })

    diag = diagnose_discrimination(valid)
    low_items = [v for v in diag.values() if v.get("low")]

    if low_items:
        parts = "、".join(
            f"{v['label']}极差 {v['ratio']} 倍（{v['min']:g} ~ {v['max']:g}）" for v in low_items
        )
        limitation = (
            f"数据区分度提示：{parts}，低于 {LOW_DISCRIMINATION_RATIO} 倍的判定线。"
            "这意味着本演示数据中各小类表现较为接近，ABC 三档的绝对差异不明显。"
            "真实商超中明星品与长尾品的销量差距可达数十倍，届时分类区分度会显著提升。"
            "平台如实展示计算结果，不对数据做任何修饰。"
        )
    else:
        limitation = None

    return {
        "success": True,
        "total_sales": round(total, 1),
        "total_items": n,
        "thresholds": {"A": a_thresh, "B": b_thresh},
        "classes": class_stats,
        "rows": rows,
        "items": rows,
        "summary": (
            f"共 {n} 个小类。A类 {class_stats[0]['count']} 个（占商品数 {class_stats[0]['count_pct']}%）"
            f"贡献销售额 {class_stats[0]['sales_pct']}%；"
            f"B类 {class_stats[1]['count']} 个贡献 {class_stats[1]['sales_pct']}%；"
            f"C类 {class_stats[2]['count']} 个（占商品数 {class_stats[2]['count_pct']}%）"
            f"贡献 {class_stats[2]['sales_pct']}%。"
        ),
        "data_discrimination": diag,
        "data_limitation": limitation,
        "method": "ABC 分类法（按累计销售额占比 70/20/10 划分）",
        "method_note": (
            "选择 ABC 分类而非 K-means 聚类：当前数据区分度有限，"
            "聚类分组的簇内差异过小；ABC 分类基于累计贡献，结论更稳定也更可解释。"
        ),
    }


def abc_by_category(items: List[Dict], a_thresh: float = 0.70, b_thresh: float = 0.90) -> List[Dict]:
    """按大类分别做 ABC 分类，供二级分析。"""
    by_cat: Dict[str, List[Dict]] = {}
    for i in items:
        by_cat.setdefault(i.get("category") or "未分类", []).append(i)
    out = []
    for cat, group in by_cat.items():
        r = abc_classify(group, a_thresh, b_thresh)
        if r.get("success"):
            out.append({"category": cat, **r})
    return out
