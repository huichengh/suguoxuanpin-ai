"""Agent 回答组装：按标准模板生成结构化答案"""
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from . import agent as A
from . import tools as T
from ..algorithms import advisor
from ..config import DEMO_DISCLAIMER
from ..models import Transaction
from ..services import analytics as SA


def _f(v, suffix="", nd=0):
    if v is None:
        return "—"
    try:
        return f"{v:,.{nd}f}{suffix}"
    except (TypeError, ValueError):
        return f"{v}{suffix}"


def envelope(conclusion: str, basis: List[str], analysis: str, advice: str,
             risk: str, status: str, tools_used: List[str],
             extra: Optional[Dict] = None, demo_note: bool = True) -> Dict:
    return {
        "conclusion": conclusion,
        "key_basis": basis[:5],
        "analysis": analysis,
        "advice": advice,
        "risk_limit": risk,
        "decision_status": status,
        "tools_used": tools_used,
        "disclaimer": "AI建议，仅供辅助决策，最终选品由采购人员确认。",
        "demo_note": DEMO_DISCLAIMER if demo_note else "",
        "extra": extra or {},
    }


def answer(db: Session, user: str, question: str) -> Dict:
    intent = A.detect_intent(question)
    category = A.extract_category(db, question)
    targets = A.extract_compare_targets(db, question)

    handler = HANDLERS.get(intent, handle_dashboard)
    result = handler(db, user, question, category, targets)
    result["intent"] = intent
    return result


# ---------- 各意图处理器 ----------

def handle_greeting(db, user, q, category, targets):
    d = T.dashboard_summary(db)
    k = d["kpi"]
    return envelope(
        "您好，我是苏果智选AI，可以帮您做品类诊断、商品比较、关联陈列分析和需求预测判断。",
        [
            f"当前门店：{d['store']}",
            f"在售品类 {k['category_total']} 个，其中健康品类 {k['healthy_category']} 个、风险品类 {k['risk_category']} 个",
            f"本月累计缺货 {k['stockout_this_month']} 次，平均库存周转 {k['avg_turnover_days']} 天",
            f"待人工审批建议 {k['pending_approvals']} 条",
        ],
        f"平台已接入品类销售 {d['data_status']['category_sales_rows']} 行、"
        f"交易明细 {d['data_status']['transaction_rows']} 条（{d['data_status']['transaction_count']} 笔交易）、"
        f"需求数据 {d['data_status']['demand_rows']} 行。所有结论都从这些数据实时计算。",
        "您可以问我：「哪些品类需要精简」「生鲜蔬果的健康度怎么样」"
        "「牛奶和面包的关联度如何」「未来4期哪些品类需求上涨」「生成综合选品方案」。",
        f"{DEMO_DISCLAIMER}。SKU 级商品数据当前未接入，SKU 量化评价暂不可用。",
        "AI建议，仅供辅助决策",
        ["get_dashboard_summary"],
    )


def handle_dashboard(db, user, q, category, targets):
    d = T.dashboard_summary(db)
    k = d["kpi"]
    health = d["health_overview"]
    top = health[0] if health else None
    bottom = health[-1] if health else None

    return envelope(
        f"门店当前 {k['category_total']} 个品类中 {k['healthy_category']} 个健康、{k['risk_category']} 个需重点优化，"
        f"整体结构存在调整空间。",
        [
            f"品类总数 {k['category_total']} 个，健康（≥70分）{k['healthy_category']} 个，风险（<55分）{k['risk_category']} 个",
            f"近12个月累计缺货 {k['stockout_this_month']} 次，平均库存周转 {k['avg_turnover_days']} 天",
            f"高价值关联组合（提升度≥2）{k['high_value_associations']} 条",
            f"需求上涨品类 {k['demand_rising_categories']} 个，待审批建议 {k['pending_approvals']} 条",
        ],
        (f"表现最好的是{top['category']}（{top['score']} 分，{top['stars']}）；"
         f"最弱的是{bottom['category']}（{bottom['score']} 分，{bottom['stars']}）。"
         if top and bottom else "暂无品类健康度数据。"),
        "建议先处理健康度低于 55 分的品类，同时关注缺货次数高的品类供货稳定性。",
        f"{DEMO_DISCLAIMER}。",
        "AI建议，仅供辅助决策",
        ["get_dashboard_summary"],
    )


def handle_health(db, user, q, category, targets):
    all_rows = SA.health_rows(db)
    rows = all_rows
    if category:
        rows = [x for x in all_rows if x["category"] == category]
        if not rows:
            return envelope(
                f"当前数据中没有品类「{category}」，无法给出该品类的健康度结论。",
                [f"数据库中现有品类：{', '.join(x['category'] for x in all_rows)}"],
                "缺少该品类的销售数据。",
                f"请先在「数据中心」上传包含「{category}」的品类销售数据。",
                "当前数据不足以支持该结论。",
                "数据不足",
                ["get_category_health"],
            )

    single = bool(category)
    rows = rows[:1] if single else rows[:5]
    lines = []
    for x in rows:
        lines.append(
            f"第{x['rank']}名 {x['category']}：{x['overall_score']}分（{x['stars']} {x['grade']}），"
            f"销量贡献{x['sales_contribution']}%、毛利贡献{x['margin_contribution']}%、"
            f"周转{x['avg_turnover_days']}天、坪效{x['avg_sales_per_sqm']}元/㎡/月、缺货{x.get('stockout_count', x['total_stockout'])}次"
        )
    target = rows[0] if rows else None
    weakest = all_rows[-1] if all_rows else None

    if single:
        conclusion = (
            f"{target['category']} 综合健康度 {target['overall_score']} 分（{target['stars']} {target['grade']}），"
            f"在 {len(all_rows)} 个品类中排名第 {target['rank']}。"
        )
        suggestion = f"建议：{target['suggestion']}"
    else:
        conclusion = (
            f"共 {len(all_rows)} 个品类，"
            + (f"其中 {weakest['category']} 健康度最低（{weakest['overall_score']} 分），最需优化。" if weakest else "")
        )
        suggestion = f"建议对{weakest['category']}执行「{weakest['suggestion']}」" if weakest else ""

    return envelope(
        conclusion, lines,
        "评分模型 = 销量贡献×0.30 + 毛利贡献×0.30 + 库存周转×0.20 + 坪效×0.20，"
        "各指标标准化到 0-100，其中库存周转天数越低越好，采用逆向标准化。"
        + ("系统重算结果与附件预置参考结果存在差异，差异来源是聚合口径与标准化方式，平台会同时展示两者，不修改任何一方。"
           if rows and rows[0].get("attachment_reference") else ""),
        suggestion,
        f"{DEMO_DISCLAIMER}。SKU 级健康度需 SKU 数据，当前不支持。",
        "AI建议，需人工确认后执行",
        ["get_category_health"],
        {"items": rows},
    )


def handle_data_gap(db, user, q, category, targets):
    """回答数据不足类问题：明确说明缺什么，不编造。"""
    from ..models import CandidateProduct, DemandRecord, SkuProduct, Store, TransactionItem

    status = SA.sku_data_status(db)
    items = []
    items.append({
        "name": "SKU 级商品数据",
        "state": "已接入" if status["sufficient"] else "未接入",
        "count": f"{status['sku_count']} 个 SKU",
        "detail": status["message"],
    })
    items.append({
        "name": "会员 RFM 数据",
        "state": "未接入",
        "count": "0 条",
        "detail": "当前无法完成 RFM 客群分层。",
    })
    items.append({
        "name": "门店周边 POI 与人口数据",
        "state": "未接入",
        "count": "0 条",
        "detail": "千店千面模块待接入门店周边数据。",
    })
    store = db.query(Store).filter_by(is_default=True).first()
    items.append({
        "name": "需求预测历史数据",
        "state": "部分接入",
        "count": f"{db.query(DemandRecord).count()} 行 / {len({r.category_id for r in db.query(DemandRecord).all()})} 个品类",
        "detail": "仅 5 个品类有预测数据，历史期数 12 期，低于推荐的 24-36 期。",
    })
    items.append({
        "name": "交易明细数据",
        "state": "已接入",
        "count": f"{db.query(TransactionItem).count()} 条明细",
        "detail": "支撑 Apriori 关联规则计算。",
    })

    gaps = [i for i in items if i["state"] != "已接入"]
    return envelope(
        f"当前有 {len(gaps)} 类数据尚未接入，这些维度无法给出量化结论。",
        [f"{i['name']}：{i['state']}（{i['count']}）—— {i['detail']}" for i in items],
        "平台遵循「数据优先」原则：缺少的数据不做推测、不生成看似精确的数值，"
        "只在 UI 中明确标注「数据不足」与所需字段。",
        ("SKU 级评价：请在「数据中心」上传 SKU 候选商品数据模板后，选品比较中心会自动启用完整量化模式。"
         if not status["sufficient"] else
         "如需进一步分析，可上传 SKU 级数据以支持单商品维度的量化评价。"),
        f"{DEMO_DISCLAIMER}。当前数据不足以支持的结论一律不做输出。",
        "数据不足",
        ["get_data_quality", "get_store_profile"],
        {"data_status": items},
    )


def handle_compare(db, user, q, category, targets):
    if len(targets) < 2:
        from ..models import Category
        avail = ", ".join(c.name for c in db.query(Category).all())
        return envelope(
            "当前数据不足以支持该结论：您提到的比较对象不足 2 个。",
            [f"可比较的品类：{avail}"],
            "比较功能需要至少 2 个候选对象。",
            "请明确指出要比较的品类，例如「比较生鲜蔬果和日化清洁」。",
            "对象不足，无法计算。",
            "数据不足",
            ["compare_candidates"],
        )

    payload = SA.compare_payload(db, [], "category", category_ids=targets)
    if not payload.get("sufficient", True):
        return envelope("当前数据不足以支持该结论。", [], "", "", "数据不足", "数据不足", ["compare_candidates"])

    items = payload["items"]
    best, worst = items[0], items[-1]
    basis = [
        f"{it['name']}：综合 {it['overall_score']} 分（优先级 {it['priority']}），"
        f"销量分 {it['scores']['sales']}、毛利分 {it['scores']['margin']}、"
        f"周转分 {it['scores']['turnover']}、坪效分 {it['scores']['space']}"
        for it in items
    ]
    return envelope(
        f"{best['name']} 综合得分 {best['overall_score']} 排名第一，{worst['name']} 得分 {worst['overall_score']} 排名末位。",
        basis,
        f"排名依据的权重为 销量{payload['weights']['sales']:.0%} / 毛利{payload['weights']['margin']:.0%} / "
        f"周转{payload['weights']['turnover']:.0%} / 坪效{payload['weights']['space']:.0%}。"
        f"{best['name']} 的最大优势是{'、'.join(best['recommendation']['strengths'])}；"
        f"{worst['name']} 的主要风险是{'、'.join(worst['recommendation']['risks'])}。",
        f"建议：{best['name']} → {best['recommendation']['action']}；"
        f"{worst['name']} → {worst['recommendation']['action']}。"
        + (f"建议扩充：{'、'.join(payload['ai_judgement']['suggest_expand'])}" if payload["ai_judgement"]["suggest_expand"] else ""),
        f"结论会改变的条件：{best['recommendation']['change_condition']} "
        f"{DEMO_DISCLAIMER}。",
        "需人工确认",
        ["compare_candidates"],
        {"comparison": payload},
    )


def handle_association(db, user, q, category, targets):
    data = SA.association_rules(db)
    rt = data["realtime_rules"][:6]
    p = data["params"]
    basis = [
        f"实时重算：{data['summary']['realtime_count']} 条规则通过阈值（support≥{p['min_support']}、confidence≥{p['min_confidence']}、lift≥{p['min_lift']}）",
    ]
    for r in rt[:4]:
        basis.append(
            f"{r['display_rule']}：支持度 {r['support']:.4f}、置信度 {r['confidence']:.4f}、提升度 {r['lift']:.2f}（{r['strength']}）"
        )
    basis.append(
        f"附件参考规则 {data['summary']['attachment_count']} 条，其中 {data['summary']['attachment_passed']} 条通过当前默认阈值"
    )

    attach_only = [r for r in data["attachment_rules"] if not r["passes_threshold"]]
    basket_total = db.query(Transaction).count()
    analysis = (
        f"基于 {basket_total} 笔交易篮、按「交易号+商品名称」聚合实时计算得到的结果。"
        + (f"其中最强关联是 {rt[0]['display_rule']}，提升度 {rt[0]['lift']:.2f}。" if rt else "")
    )
    if attach_only:
        analysis += (
            f"注意：附件参考规则中有 {len(attach_only)} 条（如 {attach_only[0]['display_rule']}，"
            f"置信度 {attach_only[0]['confidence']}）低于当前 confidence 阈值 {p['min_confidence']}，"
            f"因此未出现在实时结果中。平台保留附件原始数据不修改，两者在 UI 中分别标注来源。"
        )

    return envelope(
        f"实时重算得到 {data['summary']['realtime_count']} 条通过阈值的关联规则，"
        + (f"最强的是 {rt[0]['antecedent']} + {rt[0]['consequent']}（提升度 {rt[0]['lift']:.2f}）。" if rt else ""),
        basis,
        analysis,
        (f"建议在社区门店动线设置关联陈列位：{rt[0]['antecedent']} 与 {rt[0]['consequent']} 相邻陈列，配套组合促销。" if rt else ""),
        f"{DEMO_DISCLAIMER}。当前演示数据商品编码高度离散，购物篮按「交易号+商品名称」构建；"
        f"真实企业数据接入后可切换为商品编码。",
        "AI建议，仅供参考",
        ["get_association_rules"],
        {"association": {k: v for k, v in data.items() if k in ("params", "realtime_rules", "attachment_rules", "network", "data_note")}},
    )


def handle_forecast(db, user, q, category, targets):
    f = T.forecast(db, category)
    if not f.get("found"):
        return envelope(
            f"当前数据中没有品类「{category}」的预测数据。",
            [f"当前有预测数据的品类：{', '.join(v['category'] for v in SA.forecast_views(db))}"],
            "缺少该品类的需求历史数据。",
            f"请上传包含「{category}」的需求历史数据（建议至少 12 期，24-36 期更佳）。",
            "当前数据不足以支持该结论。",
            "数据不足",
            ["get_demand_forecast"],
        )

    items = f["items"]
    if category:
        v = items[0]
        return envelope(
            f"{v['category']} 需求趋势为「{v['trend_level']}」，未来4期预测均量 {_f(v['future_avg'])} 件，"
            f"较最近4期实际 {_f(v['recent_avg'])} 件变化 {v['change_pct']:+.1f}%。" if v.get("change_pct") is not None else
            f"{v['category']} 需求趋势为「{v['trend_level']}」。",
            [
                f"历史期数 {v['history_periods']} 期，预测期数 {v['forecast_periods']} 期",
                f"未来4期预测均量 {_f(v['future_avg'])} 件",
                f"最近4期实际均量 {_f(v['recent_avg'])} 件",
                f"平均预测区间宽度 {v['avg_interval_width_pct']}%（区间越宽预测越不确定）",
                "；".join(v["risk"]["factors"]),
            ],
            f"风险等级判定为「{v['risk']['risk_level']}」。{v['sample_note']}",
            ("建议按上行趋势增加安全库存并优先保障货源。" if v["trend_level"] in ("明显上涨", "温和上涨")
             else "建议下调订货量，优先消化库存。" if v["trend_level"] in ("明显下降", "温和下降")
             else "建议维持当前订货策略。"),
            f"该预测为附件预置的模拟预测结果，{DEMO_DISCLAIMER}。{v['sample_note']}",
            "AI建议，需人工确认",
            ["get_demand_forecast"],
            {"forecast": v},
        )

    up = [v for v in items if v["trend_level"] in ("明显上涨", "温和上涨")]
    down = [v for v in items if v["trend_level"] in ("明显下降", "温和下降")]
    basis = [
        f"{v['category']}：{v['trend_level']}，未来4期均量 {_f(v['future_avg'])} 件，环比 {v['change_pct']:+.1f}%"
        for v in items
    ]
    return envelope(
        f"当前有预测数据的 {len(items)} 个品类中，"
        + (f"{len(up)} 个呈上涨趋势（{', '.join(v['category'] for v in up)}），" if up else "无明显上涨品类，")
        + (f"{len(down)} 个呈下降趋势（{', '.join(v['category'] for v in down)}）。" if down else "无明显下降品类。"),
        basis,
        "趋势判定方法：比较未来4期预测均量与最近4期实际均量，变化幅度超过 ±5% 为温和，±10% 为明显。"
        + "注意「纺织服装」等品类未包含在预测数据中，该品类趋势无法判断。",
        ("建议对上涨品类提前备货，对下降品类控制订货避免积压。" if up or down else "建议维持现有订货策略。"),
        f"全部预测值来自附件的模拟预测结果，{DEMO_DISCLAIMER}。仅 5 个品类有预测数据，"
        f"预测历史期数为 12 期，低于推荐的 24-36 期，结果仅供趋势参考。",
        "AI建议，需人工确认",
        ["get_demand_forecast"],
        {"forecasts": items},
    )


def handle_stockout(db, user, q, category, targets):
    r = T.stockout_risk(db, 5)
    items = r["items"]
    if not items or items[0]["stockout_count"] == 0:
        return envelope("当前数据中没有缺货记录。", [], "", "", "", "数据不足", ["get_stockout_risk"])

    return envelope(
        f"缺货最严重的是{items[0]['category']}，近12个月缺货 {items[0]['stockout_count']} 次。",
        [f"{it['category']}：缺货 {it['stockout_count']} 次 / {it['months']}个月，"
         f"月均 {it['stockout_count']/max(1,it['months']):.1f} 次，SKU 均值 {it['sku_count']} 个" for it in items],
        "缺货频次与 SKU 规模、周转天数共同反映供货稳定性。周转天数长同时缺货多的品类，"
        "通常意味着畅销品补货不及时、长尾品积压的结构性问题。",
        "建议对月均缺货 2 次以上的品类核查主供应商履约率，对高频缺货 SKU 建立安全库存或引入备选供应商。",
        f"{DEMO_DISCLAIMER}。缺货数据来自品类级汇总，无 SKU 级缺货明细。",
        "AI建议，仅供参考",
        ["get_stockout_risk"],
        {"stockout": items},
    )


def handle_private_label(db, user, q, category, targets):
    r = T.private_label(db)
    focus = r["focus"]
    return envelope(
        (f"从品类级数据看，{ '、'.join(focus) } 最值得关注自有品牌渗透机会。" if focus
         else "当前数据不足以识别明确的自有品牌机会品类。"),
        [f"{it['category']}：毛利贡献 {it['margin_contribution']}%、销量贡献 {it['sales_contribution']}%、"
         f"健康度 {it['overall_score']} 分、周转 {it['turnover_days']} 天 → {it['potential']}"
         for it in r["items"][:5]],
        "判断逻辑：毛利贡献高说明该品类有利润承载空间，健康度中上说明商品结构可承接自有品牌替换。"
        "这是品类级结论，不是 SKU 级替代预测。",
        ("建议对上述品类做自有品牌 SKU 级调研：核对竞品价格带、评估自有品牌毛利率与供应能力。" if focus else ""),
        f"{r['level_note']} 缺少的数据：{'、'.join(r['missing_data'])}。{DEMO_DISCLAIMER}。",
        "AI建议，需人工确认",
        ["get_private_label_opportunity"],
        {"private_label": r},
    )


def handle_new_product(db, user, q, category, targets):
    r = T.new_products(db)
    if not r["count"]:
        return envelope(
            "新品候选池为空，当前无法评估。",
            ["候选池中没有记录"],
            "需要先在「新品评估」页面录入新品候选信息。",
            "请录入商品名称、品类、采购价、建议零售价、供应商、目标消费者等字段，"
            "系统会基于品类健康度与需求趋势给出解释型潜力等级。",
            "候选池为空。",
            "数据不足",
            ["get_new_product_evaluation"],
        )
    return envelope(
        f"当前新品候选池中有 {r['count']} 个候选商品。",
        [f"{it['name']}（{it['category']}）：潜力等级 {it['potential_level']}，资料完整度 {it['completeness_score']}%"
         for it in r["items"][:5]],
        "评估结合所属品类健康度、需求趋势与新品资料完整度，输出「高潜力/中等潜力/谨慎试销」等级。",
        "建议按潜力等级排序，优先对高潜力新品安排小范围试销。",
        f"{r['note']} {DEMO_DISCLAIMER}。",
        "AI建议，需人工确认",
        ["get_new_product_evaluation"],
        {"new_products": r},
    )


def handle_store(db, user, q, category, targets):
    r = T.store_profile(db)
    if not r.get("found"):
        return envelope("没有找到门店记录。", [], "", "", "数据不足", "数据不足", ["get_store_profile"])

    s = r["store"]
    return envelope(
        f"当前门店为{s['name']}，位于{s['city']}{s['district']}{s['business_district']}，{s['store_type']}，营业面积 {s['area_sqm']} ㎡。",
        [f"门店编码与基础信息已完整" if not r["missing_fields"] else
         f"待接入字段：{'、'.join(r['missing_fields'])}"],
        "千店千面模块当前为「门店画像配置 + 数据待接入」状态。"
        "当前附件未包含门店周边 3 公里人口、客群结构与 POI 数据，平台不会自行编造人口数量。",
        "接入真实 POI 与人口数据后，可结合 STP 与 RFM 输出目标客群、重点品类、"
        "应扩充/压缩品类、建议价格带与场景组合。",
        f"{r['note']} {DEMO_DISCLAIMER}。",
        "数据待接入",
        ["get_store_profile"],
        {"store": r},
    )


def handle_approval(db, user, q, category, targets):
    from ..models import ApprovalRequest
    pend = db.query(ApprovalRequest).filter(ApprovalRequest.status == "待审批").count()
    return envelope(
        f"当前审批中心有 {pend} 条待审批记录。",
        [
            "Level 1 信息提示：无需审批，直接参考",
            "Level 2 经营建议：可采纳或驳回",
            "Level 3 高影响建议（SKU退出/大规模精简/供应商调整/重大补货/价格调整）：必须人工审批",
        ],
        "AI 不能自动下采购订单、修改价格、淘汰供应商或删除商品，只能形成「待审批建议」。",
        "可在「审批中心」查看每条建议的数据依据与风险等级并做出决策。",
        "审批动作需由具备相应权限的角色执行。",
        "需人工审批",
        ["get_dashboard_summary"],
    )


def handle_quality(db, user, q, category, targets):
    r = T.data_quality(db)
    items = r.get("items", [])
    if not items:
        return envelope("尚未生成数据质量报告。", [], "", "请在「数据中心」上传数据集以触发质量检查。", "", "数据不足", ["get_data_quality"])

    return envelope(
        f"当前共 {len(items)} 份数据集已完成质量检查。",
        [f"{it['dataset_type']}：综合质量分 {it['overall_score']}，"
         f"完整性{it['completeness']}/一致性{it['consistency']}/有效性{it['validity']}/"
         f"唯一性{it['uniqueness']}/时效性{it['timeliness']}，发现 {len(it['issues'])} 类问题"
         for it in items],
        "质量检查覆盖完整性、一致性、有效性、唯一性、时效性五个维度。"
        "平台发现问题后不会静默修复，只展示问题字段、数量与处理建议，由用户选择自动清洗/人工确认/保留原始值。",
        "建议优先处理高严重度问题（字段缺失、主键重复、逻辑不一致）后再运行算法。",
        f"{DEMO_DISCLAIMER}。",
        "AI建议，仅供参考",
        ["get_data_quality"],
        {"quality": items},
    )


def handle_risk(db, user, q, category, targets):
    r = T.risk_alerts(db)
    items = r["items"]
    high = [i for i in items if i["level"] == "高"]
    return envelope(
        f"当前共触发 {len(items)} 条预警，其中高风险 {len(high)} 条。",
        [f"[{i['level']}] {i['type']} — {i['target']}：{i['value']}。{i['detail']}" for i in items[:5]],
        "预警规则由管理员在「系统管理 → 算法参数」中配置，包括周转天数、坪效、缺货次数、健康度分数线等阈值。",
        "建议优先处理高风险预警，涉及 SKU 退出的结论需提交人工审批。",
        f"{DEMO_DISCLAIMER}。",
        "AI建议，仅供参考",
        ["get_risk_alerts"],
        {"alerts": items},
    )


def handle_comprehensive_plan(db, user, q, category, targets):
    health = SA.health_rows(db)
    fcs = SA.forecast_views(db)
    rules = SA.rule_summary_for_advisor(db)
    plan = advisor.generate_comprehensive_plan(health, fcs, rules)

    groups = ["优先扩充", "建议保持", "重点观察", "建议精简", "建议退出"]
    basis = []
    for g in groups:
        for it in plan[g]:
            basis.append(f"{g}｜{it['category']}：{it['data_basis']}")
    basis = basis[:5]

    counts = "、".join(f"{g} {len(plan[g])} 个" for g in groups)
    conclusion = (
        f"综合健康度、销量毛利、周转坪效、缺货、关联规则与需求预测，"
        f"门店选品结构建议为：{counts}。"
    )
    analysis_parts = []
    for g in groups:
        if plan[g]:
            cats = "、".join(it["category"] for it in plan[g][:3])
            analysis_parts.append(f"{g}：{cats}")
    analysis = "；".join(analysis_parts) + "。每个结论都基于多维指标，不依据单一健康分。"

    return envelope(
        conclusion, basis, analysis,
        f"建议优先级：先执行「优先扩充」和「建议精简」（需人工审批 SKU 精简与退出），"
        f"同步落地关联陈列调整，最后按周期复评「重点观察」品类。",
        f"{plan['决策状态']} {DEMO_DISCLAIMER}。",
        "需人工审批",
        ["get_category_health", "get_demand_forecast", "get_association_rules"],
        {"plan": plan},
    )


HANDLERS = {
    "greeting": handle_greeting,
    "dashboard": handle_dashboard,
    "data_gap": handle_data_gap,
    "health": handle_health,
    "compare": handle_compare,
    "association": handle_association,
    "forecast": handle_forecast,
    "stockout": handle_stockout,
    "private_label": handle_private_label,
    "new_product": handle_new_product,
    "store": handle_store,
    "approval": handle_approval,
    "quality": handle_quality,
    "risk": handle_risk,
    "comprehensive_plan": handle_comprehensive_plan,
}