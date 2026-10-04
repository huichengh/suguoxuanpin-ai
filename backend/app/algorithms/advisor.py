"""AI 经营建议生成器

输入：数据库中的真实计算结果（健康度、关联规则、预测、缺货、周转）。
输出：结构化建议清单，每条都带数据依据，不输出泛泛空话。
"""
from typing import Dict, List, Optional

DEMO_NOTE = "以下分析基于模拟演示数据，不代表华润苏果真实经营数据。"


def _pct(v: Optional[float]) -> str:
    return f"{v:+.1f}%" if v is not None else "—"


def generate_daily_suggestions(
    health_rows: List[Dict],
    forecasts: List[Dict],
    rules_summary: Dict,
    pending_approvals: int = 0,
) -> List[Dict]:
    """生成首页「AI 今日建议」。"""
    out: List[Dict] = []

    # 1. 高风险品类
    risky = [r for r in health_rows if r["below_three_star"]]
    for r in sorted(risky, key=lambda x: x["overall_score"])[:2]:
        out.append({
            "title": f"{r['category']}健康度仅 {r['overall_score']} 分，建议重点优化商品结构",
            "suggestion": r["suggestion"],
            "data_basis": (
                f"近{health_rows[0].get('months', 12)}个月聚合：销售额 {r['total_amount']:,.0f} 元、"
                f"毛利额 {r['total_profit']:,.0f} 元、毛利率 {r['gross_margin_rate']}%、"
                f"平均周转 {r['avg_turnover_days']} 天、坪效 {r['avg_sales_per_sqm']} 元/㎡/月、"
                f"缺货 {r['stockout_count']} 次、SKU 均值 {r['avg_sku_count']} 个"
            ),
            "affected": r["category"],
            "priority": "高",
            "risk_level": "Level 3",
            "requires_approval": True,
            "code": f"SUG-HLTH-{r['category']}",
        })

    # 2. 需求上行品类
    up = [f for f in forecasts if f.get("trend_level") in ("明显上涨", "温和上涨")]
    for f in sorted(up, key=lambda x: (x.get("change_pct") or 0), reverse=True)[:2]:
        out.append({
            "title": f"{f['category']}需求{f['trend_level']}，未来4期均量 {f['future_avg']:,.0f} 件",
            "suggestion": (
                f"建议按{f['trend_level']}趋势调整备货量，"
                + ("优先保障货源，避免热销缺货。" if f["trend_level"] == "明显上涨"
                   else "适度增加安全库存，同时监控预测区间宽度。")
            ),
            "data_basis": (
                f"最近4期实际均量 {f['recent_avg']:,.0f} 件，未来4期预测均量 {f['future_avg']:,.0f} 件，"
                f"环比 {_pct(f.get('change_pct'))}；平均预测区间宽度 {f['avg_interval_width_pct']}%，"
                f"历史期数 {f['history_periods']} 期"
            ),
            "affected": f["category"],
            "priority": "高" if f["trend_level"] == "明显上涨" else "中",
            "risk_level": "Level 2",
            "requires_approval": False,
            "code": f"SUG-FCST-{f['category']}",
        })

    # 3. 需求下行品类（积压风险）
    down = [f for f in forecasts if f.get("trend_level") in ("明显下降", "温和下降")]
    for f in sorted(down, key=lambda x: (x.get("change_pct") or 0))[:1]:
        out.append({
            "title": f"{f['category']}需求{f['trend_level']}，建议控制备货避免积压",
            "suggestion": "建议下调该品类订货量，优先消化库存，长尾 SKU 逐步退出。",
            "data_basis": (
                f"未来4期预测均量 {f['future_avg']:,.0f} 件，较最近4期实际 {_pct(f.get('change_pct'))}；"
                f"预测数据为模拟结果，仅供趋势参考"
            ),
            "affected": f["category"],
            "priority": "中",
            "risk_level": "Level 2",
            "requires_approval": False,
            "code": f"SUG-FCSTDOWN-{f['category']}",
        })

    # 4. 缺货频繁品类
    stockout_bad = sorted(health_rows, key=lambda x: -x["stockout_count"])[:2]
    for r in stockout_bad:
        if r["stockout_count"] < 8:
            continue
        out.append({
            "title": f"{r['category']}近12个月缺货 {r['stockout_count']} 次，供货稳定性不足",
            "suggestion": "建议核查该品类主供应商履约情况，对高频次缺 SKU 建立安全库存或引入备选供应商。",
            "data_basis": (
                f"月均缺货 {r['stockout_count'] / max(1, r['months']):.1f} 次，"
                f"SKU 均值 {r['avg_sku_count']} 个，平均周转 {r['avg_turnover_days']} 天"
            ),
            "affected": r["category"],
            "priority": "高" if r["stockout_count"] >= 15 else "中",
            "risk_level": "Level 2",
            "requires_approval": False,
            "code": f"SUG-STKOUT-{r['category']}",
        })

    # 5. 关联陈列机会
    top_rules = rules_summary.get("rules", [])[:3]
    if top_rules:
        pairs = "、".join(f"{r['antecedent']}+{r['consequent']}(提升度{r['lift']})" for r in top_rules)
        out.append({
            "title": f"发现 {len(top_rules)} 条高强度关联规则，建议调整关联陈列",
            "suggestion": "建议在社区门店动线节点设置关联陈列区，并配套组合促销提升连带率。",
            "data_basis": (
                f"基于 {rules_summary.get('basket_count', 0):,} 笔交易篮、"
                f"{rules_summary.get('item_count', 0)} 个商品项实时计算，"
                f"参数 support≥{rules_summary['params']['min_support']}、"
                f"confidence≥{rules_summary['params']['min_confidence']}、lift≥{rules_summary['params']['min_lift']}；"
                f"Top 规则：{pairs}"
            ),
            "affected": "全店",
            "priority": "中",
            "risk_level": "Level 1",
            "requires_approval": False,
            "code": "SUG-ASSOC-TOP",
        })

    # 6. 高周转资金占用
    slow = sorted(health_rows, key=lambda x: -x["avg_turnover_days"])[:1]
    if slow and slow[0]["avg_turnover_days"] > 45:
        r = slow[0]
        out.append({
            "title": f"{r['category']}平均周转 {r['avg_turnover_days']} 天，资金占用偏重",
            "suggestion": "建议缩减该品类 SKU 数量与陈列面积，把货架资源让给坪效更高的品类。",
            "data_basis": (
                f"平均周转 {r['avg_turnover_days']} 天，坪效 {r['avg_sales_per_sqm']} 元/㎡/月，"
                f"SKU 均值 {r['avg_sku_count']} 个，健康度 {r['overall_score']} 分"
            ),
            "affected": r["category"],
            "priority": "中",
            "risk_level": "Level 3",
            "requires_approval": True,
            "code": f"SUG-TURN-{r['category']}",
        })

    if pending_approvals:
        out.append({
            "title": f"当前有 {pending_approvals} 条 AI 建议待人工审批",
            "suggestion": "建议及时处理审批队列，避免高影响建议积压影响门店调整节奏。",
            "data_basis": f"审批中心待审批记录 {pending_approvals} 条",
            "affected": "全店",
            "priority": "中",
            "risk_level": "Level 1",
            "requires_approval": False,
            "code": "SUG-APPROVAL",
        })

    out.sort(key=lambda x: {"高": 0, "中": 1, "低": 2}[x["priority"]])
    return out[:5]


def generate_comprehensive_plan(
    health_rows: List[Dict],
    forecasts: List[Dict],
    rules_summary: Dict,
) -> Dict:
    """AI 综合选品方案：优先扩充 / 建议保持 / 重点观察 / 建议精简 / 建议退出。

    每项都必须有多维数据依据，禁止仅凭单一健康分给结论。
    """
    fmap = {f["category"]: f for f in forecasts}
    plan = {"优先扩充": [], "建议保持": [], "重点观察": [], "建议精简": [], "建议退出": []}

    for r in health_rows:
        f = fmap.get(r["category"], {})
        trend = f.get("trend_level", "无预测数据")
        trend_pct = f.get("change_pct")
        dims = []
        dims.append(f"健康度 {r['overall_score']} 分（{r['grade']}）")
        dims.append(f"销量贡献 {r['sales_contribution']}%")
        dims.append(f"毛利贡献 {r['margin_contribution']}%")
        dims.append(f"周转 {r['avg_turnover_days']} 天")
        dims.append(f"坪效 {r['avg_sales_per_sqm']} 元/㎡/月")
        dims.append(f"缺货 {r['stockout_count']} 次")
        dims.append(f"需求趋势 {trend}" + (f"（{_pct(trend_pct)}）" if trend_pct is not None else ""))
        basis = "；".join(dims)

        strong = r["overall_score"] >= 70
        weak = r["overall_score"] < 45
        mid = 45 <= r["overall_score"] < 70
        up = trend in ("明显上涨", "温和上涨")
        down = trend in ("明显下降", "温和下降")

        if strong and up:
            plan["优先扩充"].append({
                "category": r["category"], "data_basis": basis,
                "action": "扩大货架面积与订货量，同步补充高毛利子品类",
                "multi_dimension": "健康度达标且需求上行，销量/毛利/坪效三项均支撑扩充决策",
            })
        elif strong:
            plan["建议保持"].append({
                "category": r["category"], "data_basis": basis,
                "action": "维持现有商品结构与陈列，重点保障货源稳定",
                "multi_dimension": "健康度优秀但需求未明显上行，扩充需谨慎，先巩固基本盘",
            })
        elif weak and down:
            plan["建议退出"].append({
                "category": r["category"], "data_basis": basis,
                "action": "评估退出或转线上专供，释放货架与资金",
                "multi_dimension": "健康度低、周转慢、坪效低且需求下行，四项指标一致指向收缩",
            })
        elif weak or (mid and down):
            plan["建议精简"].append({
                "category": r["category"], "data_basis": basis,
                "action": "大幅精简 SKU 数量，缩减陈列面积，保留核心刚需品",
                "multi_dimension": f"健康度偏低叠加需求{'下行' if down else '平稳'}，需腾出资源给高价值品类",
            })
        else:
            plan["重点观察"].append({
                "category": r["category"], "data_basis": basis,
                "action": "维持现状并设置监控指标，下个周期复评",
                "multi_dimension": "各项指标处于中间区间，暂无明确优化方向，需持续观察",
            })

    top_rules = rules_summary.get("rules", [])[:8]
    if top_rules:
        detail = "; ".join(
            "{} + {} lift={}".format(r["antecedent"], r["consequent"], r["lift"]) for r in top_rules[:5]
        )
        plan["重点观察"].append({
            "category": "关联陈列机会",
            "data_basis": (
                f"实时计算得到 {len(rules_summary.get('rules', []))} 条通过阈值的关联规则，"
                f"Top：{detail}"
            ),
            "action": "在生鲜区、食品区、日化区设置关联陈列位，配套组合促销",
            "multi_dimension": "关联规则来自真实交易明细重算，可直接支撑陈列调整",
        })

    plan["免责声明"] = DEMO_NOTE
    plan["决策状态"] = "以上为 AI 建议，涉及 SKU 退出、供应商调整、价格调整的建议需提交人工审批。"
    return plan


def risk_alerts(
    health_rows: List[Dict],
    forecasts: List[Dict],
    stockout_threshold: int = 8,
    turnover_threshold: float = 45.0,
    space_threshold: float = 600.0,
    score_threshold: float = 55.0,
) -> List[Dict]:
    """风险预警列表。"""
    alerts: List[Dict] = []
    for r in health_rows:
        if r["avg_turnover_days"] > turnover_threshold:
            alerts.append({
                "type": "高库存周转天数", "level": "高", "target": r["category"],
                "value": f"{r['avg_turnover_days']} 天",
                "detail": f"高于预警阈值 {turnover_threshold} 天，资金占用偏重。",
            })
        if r["avg_sales_per_sqm"] < space_threshold:
            alerts.append({
                "type": "低坪效", "level": "中", "target": r["category"],
                "value": f"{r['avg_sales_per_sqm']} 元/㎡/月",
                "detail": f"低于预警阈值 {space_threshold} 元/㎡/月。",
            })
        if r["stockout_count"] >= stockout_threshold:
            alerts.append({
                "type": "缺货频繁", "level": "高" if r["stockout_count"] >= 15 else "中",
                "target": r["category"], "value": f"{r['stockout_count']} 次",
                "detail": f"近12个月累计缺货 {r['stockout_count']} 次。",
            })
        if r["overall_score"] < score_threshold:
            alerts.append({
                "type": "健康度低于三星", "level": "高", "target": r["category"],
                "value": f"{r['overall_score']} 分（{r['stars']}）",
                "detail": "综合评分低于 55 分，需重点优化。",
            })

    for f in forecasts:
        if f.get("trend_level") == "明显上涨":
            alerts.append({
                "type": "预测需求快速上涨", "level": "中", "target": f["category"],
                "value": _pct(f.get("change_pct")),
                "detail": f"未来4期预测均量 {f['future_avg']:,.0f} 件，需关注补货。",
            })
        elif f.get("trend_level") == "明显下降":
            alerts.append({
                "type": "预测需求快速下跌", "level": "中", "target": f["category"],
                "value": _pct(f.get("change_pct")),
                "detail": f"未来4期预测均量 {f['future_avg']:,.0f} 件，需控制积压。",
            })
    return alerts


def private_label_opportunity(health_rows: List[Dict]) -> Dict:
    """自有品牌机会：当前只有品类级数据，明确说明不是 SKU 级预测。"""
    rows = []
    for r in health_rows:
        # 品类级判断：毛利贡献高 + 健康度中上 + 周转偏慢 = 有替代空间
        if r["margin_contribution"] >= 15 and r["overall_score"] >= 45:
            potential = "重点关注"
        elif r["margin_contribution"] >= 10:
            potential = "可评估"
        else:
            potential = "暂不建议"
        rows.append({
            "category": r["category"],
            "potential": potential,
            "margin_contribution": r["margin_contribution"],
            "sales_contribution": r["sales_contribution"],
            "overall_score": r["overall_score"],
            "turnover_days": r["avg_turnover_days"],
            "basis": (
                f"该品类毛利贡献 {r['margin_contribution']}%、销量贡献 {r['sales_contribution']}%、"
                f"健康度 {r['overall_score']} 分、平均周转 {r['avg_turnover_days']} 天。"
                "毛利贡献高说明该品类有利润承载空间，适合引入自有品牌承接部分需求。"
            ),
        })
    rows.sort(key=lambda x: -x["margin_contribution"])
    return {
        "level": "品类级建议",
        "level_note": "当前数据仅支持品类级判断。SKU 级自有品牌替代模型需要品牌级商品数据，平台不做 SKU 级替代预测。",
        "missing_data": [
            "SKU 级品牌标识（是否自有品牌）", "SKU 级毛利率", "竞品价格带分布",
            "SKU 级销量与周转", "供应商报价与自有品牌成本",
        ],
        "items": rows,
        "focus": [r["category"] for r in rows if r["potential"] == "重点关注"],
    }