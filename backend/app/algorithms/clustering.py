"""商品聚类（C 方案）

对 70 个小类按「销量、销售额、均价、连带率、关联强度」做 K-means 聚类，
自动划分明星品 / 金牛品 / 长尾品 / 问题品四类，每类给出差异化经营建议。

实现说明：
- 自实现 K-means，不依赖 sklearn。特征先做 Min-Max 标准化，避免量纲差异主导距离。
- 聚类数 k 可配置（默认 4），用「轮廓系数简化版」评估 k 的合理性：
  对每个 k 计算类内平均平方和下降的边际收益，收益趋缓时提示更优 k。
"""
import math
from typing import Dict, List, Optional, Tuple

# 特征字段：名称、是否越高越好
FEATURES = [
    ("sales_qty", "销量", True),
    ("sales_amount", "销售额", True),
    ("avg_price", "均价", False),          # 低价高频 vs 高价低频，是不同的经营策略
    ("qty_per_transaction", "连带率", True),
    ("max_lift", "关联强度", True),
]

CLUSTER_PROFILES = {
    "明星品": {
        "color": "#257354",
        "desc": "高销量、高销售额、高连带，是门店的核心利润来源",
        "advice": "保障货源稳定，优先给予最好的陈列位置，可适度扩充品种",
    },
    "金牛品": {
        "color": "#4a7fb5",
        "desc": "销量与销售额均衡，经营稳健",
        "advice": "维持现有投入，通过关联陈列提升连带率，挖掘利润空间",
    },
    "长尾品": {
        "color": "#d9a520",
        "desc": "销量低但保持一定销售额，周转慢占用资金",
        "advice": "缩减陈列面积与订货量，将资源让给明星品，评估是否转线上专供",
    },
    "问题品": {
        "color": "#d94a4a",
        "desc": "销量、关联度均低，经营贡献最小",
        "advice": "建议评估退出或转为定制商品，避免占用门店资源",
    },
}


def minmax(values: List[float]) -> List[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return [0.5] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def kmeans(points: List[List[float]], k: int = 4, max_iter: int = 100, seed: int = 42):
    """自实现 K-means，返回 (labels, centroids, inertia)"""
    n = len(points)
    if n == 0:
        return [], [], 0.0
    k = min(k, n)

    # 确定性初始化：用等距取样，保证同一份数据每次结果一致（答辩可复现）
    centroids = [list(points[i * n // k]) for i in range(k)]

    labels = [0] * n
    for _ in range(max_iter):
        changed = False
        for i, p in enumerate(points):
            best, best_d = 0, float("inf")
            for ci, c in enumerate(centroids):
                d = sum((a - b) ** 2 for a, b in zip(p, c))
                if d < best_d:
                    best, best_d = ci, d
            if labels[i] != best:
                labels[i] = best
                changed = True
        # 重算质心
        sums = [[0.0] * len(points[0]) for _ in range(k)]
        counts = [0] * k
        for i, p in enumerate(points):
            counts[labels[i]] += 1
            for j, v in enumerate(p):
                sums[labels[i]][j] += v
        for ci in range(k):
            if counts[ci]:
                centroids[ci] = [s / counts[ci] for s in sums[ci]]
        if not changed:
            break

    inertia = sum(
        sum((a - b) ** 2 for a, b in zip(points[i], centroids[labels[i]])) for i in range(n)
    )
    return labels, centroids, inertia


def evaluate_k(points: List[List[float]], k_range=range(2, 7)) -> List[Dict]:
    """扫描不同 k 的 inertia，看边际收益，辅助判断聚类数是否合理。"""
    out = []
    prev = None
    for k in k_range:
        _, _, inertia = kmeans(points, k=k)
        gain = None if prev is None else round((prev - inertia) / prev * 100, 2)
        out.append({"k": k, "inertia": round(inertia, 4), "gain_pct": gain})
        prev = inertia
    return out


def name_clusters(clusters: List[Dict]) -> Dict[str, str]:
    """根据每个簇的销量/销售额均值，把簇映射到业务名称。

    规则（按簇内销量均值排序）：
    - 销量最高 + 销售额高 → 明星品
    - 销量次高 → 金牛品
    - 销量低 + 销售额低 → 问题品
    - 销量低 + 销售额中等 → 长尾品
    """
    ordered = sorted(clusters, key=lambda c: -c["avg_qty"])
    mapping = {}
    if len(ordered) >= 1:
        mapping[ordered[0]["cid"]] = "明星品"
    if len(ordered) >= 2:
        mapping[ordered[1]["cid"]] = "金牛品"
    if len(ordered) >= 3:
        mapping[ordered[-1]["cid"]] = "问题品"
    if len(ordered) >= 4:
        mapping[ordered[-2]["cid"]] = "长尾品"
    return mapping


def cluster_subcategories(items: List[Dict], k: int = 4) -> Dict:
    """对小类列表做聚类。

    items 每项需含 FEATURES 中定义的字段。
    返回各小类的簇标签、簇统计与经营建议。
    """
    valid = [i for i in items if all(i.get(f) is not None for f, _, _ in FEATURES)]
    valid_names = {id(i) for i in valid}
    skipped = [i for i in items if id(i) not in valid_names]

    if len(valid) < k:
        return {
            "success": False,
            "message": f"有效数据的小类只有 {len(valid)} 个，少于聚类数 {k}，无法聚类。",
            "missing_data": ["部分小类缺少聚类所需字段（销量/销售额/均价/连带率/关联强度）"],
            "skipped": [i.get("name") for i in skipped],
        }

    # 特征标准化
    cols = {f: minmax([float(i[f]) for i in valid]) for f, _, _ in FEATURES}
    points = [[cols[f][idx] for f, _, _ in FEATURES] for idx, _ in enumerate(valid)]

    labels, centroids, inertia = kmeans(points, k=k)
    k_scan = evaluate_k(points)

    # 簇统计
    clusters: Dict[int, Dict] = {}
    for idx, (item, lb) in enumerate(zip(valid, labels)):
        c = clusters.setdefault(lb, {
            "cid": lb, "items": [],
            "avg_qty": 0, "avg_amount": 0, "avg_price": 0, "total_amount": 0,
        })
        c["items"].append(item["name"])
        c["avg_qty"] += float(item["sales_qty"])
        c["avg_amount"] += float(item["sales_amount"])
        c["avg_price"] += float(item["avg_price"])
        c["total_amount"] += float(item["sales_amount"])

    clist = []
    for c in clusters.values():
        n = len(c["items"])
        clist.append({
            "cid": c["cid"],
            "count": n,
            "avg_qty": round(c["avg_qty"] / n, 1),
            "avg_amount": round(c["avg_amount"] / n, 1),
            "avg_price": round(c["avg_price"] / n, 2),
            "total_amount": round(c["total_amount"], 1),
            "items": c["items"],
        })

    mapping = name_clusters(clist)
    for c in clist:
        label = mapping.get(c["cid"], "长尾品")
        prof = CLUSTER_PROFILES[label]
        c["label"] = label
        c["color"] = prof["color"]
        c["description"] = prof["desc"]
        c["advice"] = prof["advice"]

    # 回填到每个小类
    for item, lb in zip(valid, labels):
        cid = item.get("category_id")
        item["cluster_label"] = mapping.get(lb, "长尾品")

    return {
        "success": True,
        "k": k,
        "features": [{"key": f, "label": lb, "higher_is_better": hib} for f, lb, hib in FEATURES],
        "clusters": sorted(clist, key=lambda c: -c["avg_amount"]),
        "k_scan": k_scan,
        "inertia": round(inertia, 4),
        "clustered_count": len(valid),
        "skipped": [i.get("name") for i in skipped],
        "method": "K-means（自实现，Min-Max 标准化，等距确定性初始化）",
        "note": (
            "聚类基于销量、销售额、均价、连带率、关联强度五个维度。"
            "均价为逆向特征：低价高频与高价低频属于不同经营策略，需区分看待。"
        ),
    }
