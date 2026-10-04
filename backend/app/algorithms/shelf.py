"""货架空间优化（D 方案）

给定门店总货架面积，按「单位面积销售额」把面积分配给各小类。

核心思想：同样 1 ㎡ 放在销售额高的商品上产出更多，因此面积应向高产出商品倾斜。
但不能纯按销售额分配——那会让所有面积集中到头部商品，长尾品完全没位置。
因此引入平滑系数 α：
    权重_i = 销售额_i^α  （α∈(0,1]，α 越小越均衡，α=1 为纯按销售额）
    面积_i = 总面积 × 权重_i / Σ权重
社区商超实际约束是长尾商品也要有基本陈列面，所以默认 α=0.65。

实现说明：
- 纯 Python 实现，不依赖外部优化库，答辩时可逐行讲解。
- 附带一个「贪心装箱」对比：按单位面积产出从高到低填满货架，
  用来展示不同分配策略的差异。
"""
from typing import Dict, List, Optional

DEFAULT_TOTAL_AREA = 20.0      # 默认 20 ㎡（社区店某品类区的示例面积）
DEFAULT_ALPHA = 0.65
# 最小占比下限必须满足 n * min_share <= 1，否则会退化成平均分配。
# 70 个小类时，1/70≈1.43% 是理论最小值，留 0.5% 余量。
DEFAULT_MIN_SHARE = 0.005


def allocate_shelf_space(
    items: List[Dict],
    total_area: float = DEFAULT_TOTAL_AREA,
    alpha: float = DEFAULT_ALPHA,
    min_share: float = DEFAULT_MIN_SHARE,
) -> Dict:
    """分配货架面积。

    items 每项需含 name、sales_amount（销售额）。
    """
    valid = [i for i in items if i.get("sales_amount") and i["sales_amount"] > 0]
    if not valid:
        return {
            "success": False,
            "message": "当前没有可用于面积分配的数据（需要销售额字段）。",
            "missing_data": ["小类销售额"],
        }
    if total_area <= 0:
        return {"success": False, "message": "总面积必须大于 0"}

    total_amount = sum(i["sales_amount"] for i in valid)
    n = len(valid)

    # 下限必须可行：n 个商品各占 min_share 的总和不能超过 100%
    max_feasible_floor = 1.0 / n if n else 0
    floor = min(min_share, max_feasible_floor * 0.5) if max_feasible_floor > 0 else 0

    # 带下限约束的权重分配
    raw = [(i["sales_amount"] / total_amount) ** alpha for i in valid]
    raw_sum = sum(raw)
    shares = [r / raw_sum for r in raw]

    if floor > 0 and any(s < floor for s in shares):
        # 把低于下限的提到下限，再从超限项按比例扣回
        deficit = sum(floor - s for s in shares if s < floor)
        surplus_pool = [i for i, s in enumerate(shares) if s > floor]
        surplus = sum(shares[i] - floor for i in surplus_pool)
        if surplus > 0:
            shares = [floor if s < floor else s for s in shares]
            for i in surplus_pool:
                shares[i] -= (shares[i] - floor) * (deficit / surplus)
        share_sum = sum(shares)
        shares = [s / share_sum for s in shares]

    rows = []
    for item, s in zip(valid, shares):
        area = total_area * s
        rows.append({
            "name": item.get("name"),
            "category": item.get("category"),
            "sales_amount": round(item["sales_amount"], 1),
            "sales_qty": item.get("sales_qty"),
            "share_pct": round(s * 100, 2),
            "suggest_area": round(area, 3),
            # 用未舍入的面积算单位产出，避免展示值与计算值不一致
            "sales_per_sqm": round(item["sales_amount"] / area, 2) if area > 0 else None,
        })

    rows.sort(key=lambda r: -r["sales_per_sqm"])

    # 与「纯按销售额平均分配」的对比
    baseline_area = total_area / n
    baseline_pps = total_amount / total_area
    actual_pps = total_amount / total_area

    # 贪心装箱对比
    greedy = _greedy_pack(valid, total_area)

    top3 = rows[:3]
    bottom3 = rows[-3:]

    return {
        "success": True,
        "total_area": round(total_area, 2),
        "alpha": alpha,
        "min_share": round(floor * 100, 2),
        "items": rows,
        "summary": {
            "subcategory_count": len(rows),
            "total_sales": round(total_amount, 1),
            "avg_sales_per_sqm": round(actual_pps, 2),
            "top_area_share": round(sum(r["share_pct"] for r in top3), 2),
            "bottom_area_share": round(sum(r["share_pct"] for r in bottom3), 2),
        },
        "top3": [{"name": r["name"], "share_pct": r["share_pct"], "sales_per_sqm": r["sales_per_sqm"]} for r in top3],
        "bottom3": [{"name": r["name"], "share_pct": r["share_pct"], "sales_per_sqm": r["sales_per_sqm"]} for r in bottom3],
        "greedy_comparison": greedy,
        "method": (
            f"权重 = 销售额^{alpha} 后归一化。"
            f"α={alpha} 表示在「完全按销售额分配」与「完全平均分配」之间取平衡。"
        ),
        "alpha_guide": [
            {"alpha": 1.0, "effect": "纯按销售额分配，头部商品集中度高，长尾几乎无陈列面"},
            {"alpha": 0.65, "effect": "默认，兼顾产出与长尾基本陈列需求（推荐）"},
            {"alpha": 0.3, "effect": "接近平均分配，均衡但牺牲产出效率"},
        ],
        "note": (
            f"总货架面积 {total_area} ㎡，由用户输入。"
            "分配结果为建议值，实际排面还需考虑保质期、堆头高度、整箱陈列等约束。"
        ),
    }


def _greedy_pack(items: List[Dict], total_area: float, unit_area: float = 0.25) -> Dict:
    """贪心装箱：按单位面积产出从高到低填满货架，用于对比策略差异。

    unit_area 假设每个商品占一个标准陈列位（0.25 ㎡，约 50cm×50cm）。
    贪心只按销售额排序，不考虑长尾保留，因此会挤掉长尾商品。
    """
    ranked = sorted(items, key=lambda x: -x["sales_amount"])
    capacity = int(total_area // unit_area)      # 货架能放多少个陈列位
    selected = [i.get("name") for i in ranked[:capacity]]
    used = round(capacity * unit_area, 2)

    selected_set = set(selected)
    dropped = [i.get("name") for i in ranked[capacity:]]
    dropped_amount = sum(i["sales_amount"] for i in ranked[capacity:])
    total_amount = sum(i["sales_amount"] for i in items)

    return {
        "capacity_slots": capacity,
        "selected_count": len(selected),
        "used_area": used,
        "covered_pct": round(len(selected) / len(items) * 100, 1),
        "dropped_count": len(dropped),
        "dropped_sales": round(dropped_amount, 1),
        "dropped_sales_pct": round(dropped_amount / total_amount * 100, 2) if total_amount else 0,
        "dropped_sample": dropped[:8],
        "note": (
            f"货架 {total_area} ㎡ 按 {unit_area} ㎡/陈列位计算，可放 {capacity} 个商品。"
            f"贪心策略按销售额从高到低填满，只覆盖 {len(selected)}/{len(items)} 个小类"
            f"（{len(selected)/len(items)*100:.1f}%），"
            f"落选的 {len(dropped)} 个小类贡献了 {dropped_amount/total_amount*100:.1f}% 的销售额且完全没有陈列面。"
            "这说明纯贪心会牺牲长尾商品的展示机会，本模块用平滑系数 α 平衡产出与覆盖。"
        ),
    }


def reallocate_by_category(sub_items: List[Dict], category_areas: Dict[str, float],
                           alpha: float = DEFAULT_ALPHA) -> List[Dict]:
    """按大类已分配面积，再在大类内做小类分配（二级分配）。

    category_areas: {"生鲜蔬果": 4.2, ...}
    """
    out = []
    by_cat: Dict[str, List[Dict]] = {}
    for it in sub_items:
        by_cat.setdefault(it.get("category") or "未分类", []).append(it)

    for cat, items in by_cat.items():
        area = category_areas.get(cat)
        if not area:
            continue
        res = allocate_shelf_space(items, total_area=area, alpha=alpha)
        if res.get("success"):
            for r in res["items"]:
                r["category"] = cat
                out.append(r)
    out.sort(key=lambda r: -r["sales_per_sqm"])
    return out
