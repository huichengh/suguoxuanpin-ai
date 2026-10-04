"""苏果智选AI —— 工具调用型 Agent

设计原则：
1. 数据优先：所有量化结论来自数据库与算法结果，信息不足时明确拒绝推测。
2. 可解释：每条回答按【结论/关键数据依据/分析/建议/风险与限制/决策状态】结构输出。
3. 人工决策：只产出「待审批建议」，不自动执行任何写操作。
4. 区分数据来源：附件参考结果与实时重算结果分别标注。
"""
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from . import tools as T
from ..config import DEMO_DISCLAIMER

SYSTEM_PROMPT = """你是「苏果智选AI」，一个专业的社区商超智能选品决策助手，服务对象是采购人员、品类经理和门店店长。

第一原则：数据优先。
任何量化结论必须来自平台数据库、算法结果或用户授权上传的数据。
禁止根据常识虚构销售额、销量、毛利率、市场份额、库存、预测准确率、供应商能力、会员画像。
如果信息不足，必须明确回答「当前数据不足以支持该结论」，并说明还缺什么数据。

第二原则：可解释。
每一项重要建议必须回答：建议是什么、为什么、使用了哪些数据、哪些指标起关键作用、最大风险是什么、是否需要人工确认。

第三原则：AI辅助、人工决策。
你不得自动下采购订单、修改价格、淘汰供应商、删除商品、调整正式商品池、承诺采购金额。
涉及这些行为时，只能形成「待审批建议」。

第四原则：区分真实数据和模拟数据。
本平台当前数据为比赛演示用的模拟数据，回答中必须标注这一点。

第五原则：不得混淆附件参考结果与实时算法结果。
如果用户看到两种结果，必须明确区分并解释造成差异的参数、时间范围、数据清洗、样本与算法设置。"""


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str, description: str, func: Callable, params: List[str]):
        self._tools[name] = {"name": name, "description": description, "func": func, "params": params}

    def names(self) -> List[str]:
        return list(self._tools.keys())

    def descriptions(self) -> List[Dict]:
        return [{"name": t["name"], "description": t["description"], "params": t["params"]}
                for t in self._tools.values()]

    def run(self, name: str, db: Session, user: str, **kwargs) -> Any:
        tool = self._tools.get(name)
        if not tool:
            raise KeyError(f"未知工具：{name}")
        return tool["func"](db, user, **kwargs)

    def dispatch(self, db: Session, user: str, name: str, params: Dict) -> Any:
        return self.run(name, db, user, **(params or {}))


registry = ToolRegistry()


def _reg(name, desc, params):
    def deco(fn):
        registry.register(name, desc, fn, params)
        return fn
    return deco


# ============ 工具实现 ============

@_reg("get_dashboard_summary", "获取驾驶舱 KPI 概览（品类数、健康品类、风险品类、缺货、周转、关联组合、需求上涨、待审批数）", [])
def t_dashboard(db: Session, user: str) -> Dict:
    return T.dashboard_summary(db)


@_reg("get_category_health", "获取品类健康度评分结果，含系统重算与附件参考对比", ["category"])
def t_health(db: Session, user: str, category: Optional[str] = None) -> Dict:
    rows = T.health(db)
    if category:
        rows = [r for r in rows if category in r["category"]]
        if not rows:
            return {"found": False, "message": f"当前数据中没有品类「{category}」，无法给出该品类的健康度结论。"}
    return {"found": True, "items": rows, "count": len(rows)}


@_reg("compare_candidates", "对 2-6 个品类或 SKU 进行多维加权比较并排序", ["ids", "mode"])
def t_compare(db: Session, user: str, ids: Optional[List] = None, mode: str = "category") -> Dict:
    if not ids or len(ids) < 2:
        return {"found": False, "message": "请至少提供 2 个比较对象（品类 ID 或 SKU 编码）。"}
    return T.compare(db, ids, mode)


@_reg("get_category_trend", "获取指定品类的销量/毛利/周转/坪效趋势", ["category"])
def t_trend(db: Session, user: str, category: str) -> Dict:
    return T.category_trend(db, category)


@_reg("get_association_rules", "获取关联规则（可指定来源：realtime / attachment）", ["source", "top_n"])
def t_rules(db: Session, user: str, source: Optional[str] = None, top_n: int = 10) -> Dict:
    return T.rules(db, source, top_n)


@_reg("run_apriori", "用当前参数实时重跑 Apriori 购物篮分析", ["min_support", "min_confidence", "min_lift", "top_n"])
def t_apriori(db: Session, user: str, min_support: Optional[float] = None,
              min_confidence: Optional[float] = None, min_lift: Optional[float] = None,
              top_n: Optional[int] = None) -> Dict:
    return T.run_apriori(db, user, min_support, min_confidence, min_lift, top_n)


@_reg("get_demand_forecast", "获取品类需求预测（历史+预测+置信区间+趋势分类）", ["category"])
def t_forecast(db: Session, user: str, category: Optional[str] = None) -> Dict:
    return T.forecast(db, category)


@_reg("get_stockout_risk", "获取缺货风险清单", ["top_n"])
def t_stockout(db: Session, user: str, top_n: int = 5) -> Dict:
    return T.stockout_risk(db, top_n)


@_reg("get_data_quality", "获取各数据集的质量评分与问题清单", ["dataset_type"])
def t_quality(db: Session, user: str, dataset_type: Optional[str] = None) -> Dict:
    return T.data_quality(db, dataset_type)


@_reg("get_store_profile", "获取门店画像（含千店千面字段的接入状态）", ["store_id"])
def t_store(db: Session, user: str, store_id: Optional[int] = None) -> Dict:
    return T.store_profile(db, store_id)


@_reg("get_private_label_opportunity", "获取自有品牌机会（品类级判断）", [])
def t_private_label(db: Session, user: str) -> Dict:
    return T.private_label(db)


@_reg("get_new_product_evaluation", "获取新品候选池与评估结果", ["limit"])
def t_new_product(db: Session, user: str, limit: int = 10) -> Dict:
    return T.new_products(db, limit)


@_reg("create_approval_request", "提交一条 AI 建议进入人工审批（Level 3 必须走此流程）",
      ["title", "content", "data_basis", "risk_level", "affected"])
def t_create_approval(db: Session, user: str, title: str, content: str, data_basis: str,
                      risk_level: str = "Level 3", affected: str = "") -> Dict:
    return T.create_approval(db, user, title, content, data_basis, risk_level, affected)


@_reg("get_analysis_history", "获取 AI 分析记录", ["limit"])
def t_history(db: Session, user: str, limit: int = 10) -> Dict:
    return T.analysis_history(db, limit)


@_reg("get_risk_alerts", "获取风险预警清单", [])
def t_risk(db: Session, user: str) -> Dict:
    return T.risk_alerts(db)


@_reg("get_model_settings", "获取当前算法参数", [])
def t_settings(db: Session, user: str) -> Dict:
    return T.model_settings(db)


# ============ 意图路由 ============

INTENTS = [
    ("greeting", ["你好", "您好", "hi", "hello", "在吗"]),
    ("comprehensive_plan", ["综合选品方案", "综合方案", "优化方案", "整体方案", "全案"]),
    ("data_gap", ["sku级", "sku级别", "商品级数据", "有没有数据", "数据够不够", "数据不足", "有数据吗", "数据够", "缺少数据", "数据缺口"]),
    ("private_label", ["自有品牌", "贴牌", "润家"]),
    ("new_product", ["新品", "试销", "引入"]),
    ("association", ["关联", "陈列", "组合", "一起买", "搭配", "购物篮", "促销", "关联度"]),
    ("health", ["健康度", "健康", "诊断", "星级", "评分", "几星"]),
    ("compare", ["比较", "对比", "哪个好", "选哪个", "性价比", "pk", "排名"]),
    ("stockout", ["缺货", "断货", "断码"]),
    ("forecast", ["预测", "需求", "未来", "趋势", "上涨", "下跌", "补货"]),
    ("store", ["门店", "千店千面", "商圈", "画像", "客群"]),
    ("approval", ["审批", "提交审批", "采纳", "驳回"]),
    ("quality", ["数据质量", "数据问题", "数据检查", "缺失值"]),
    ("risk", ["风险", "预警", "告警"]),
    ("dashboard", ["驾驶舱", "概览", "整体情况", "总览", "kpi", "指标"]),
]


def detect_intent(text: str) -> str:
    t = text.lower()
    # 「比较」「对比」只有在明确指向两个对象时才走 compare；
    # 「健康度比较差」这类描述应优先按健康度查询处理。
    cmp_words = ["比较", "对比", "哪个好", "选哪个", "性价比", "pk", "排名"]
    has_cmp = any(w in t for w in cmp_words)
    has_cmp = has_cmp and not any(w in t for w in ["健康度", "诊断", "星级", "评分"])

    order = ["comprehensive_plan", "data_gap", "private_label", "new_product", "association",
             "health", "stockout", "forecast", "store", "approval", "quality",
             "risk", "dashboard", "greeting"]
    kw_map = dict(INTENTS)

    if has_cmp:
        return "compare"
    for intent in order:
        for kw in kw_map[intent]:
            if kw in t:
                return intent
    return "dashboard"


def extract_category(db: Session, text: str) -> Optional[str]:
    from ..models import Category
    for c in db.query(Category).all():
        if c.name in text or c.name.replace(" ", "") in text:
            return c.name
    # 尝试关键词模糊匹配
    for c in db.query(Category).all():
        for kw in re.split(r"[、\s]", c.name):
            if len(kw) >= 2 and kw in text:
                return c.name
    return None


def extract_topics(db: Session, text: str) -> List[str]:
    from ..models import Category
    found = []
    for c in db.query(Category).all():
        if c.name in text:
            found.append(c.name)
    return found


def extract_compare_targets(db: Session, text: str) -> List[int]:
    """从文本中提取要比较的品类 ID。"""
    from ..models import Category
    ids = []
    for c in db.query(Category).all():
        if c.name in text:
            ids.append(c.id)
    if not ids:
        # 至少两个品类名都出现才算明确比较
        pass
    return ids