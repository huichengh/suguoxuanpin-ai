"""审批中心 + 系统管理接口"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...config import DEMO_DISCLAIMER, DEMO_SOURCE
from ...database import get_db
from ...models import (
    AiRecommendation, AnalysisJob, ApprovalRequest, AuditLog, KnowledgeDoc,
    ModelRunLog, ModelSetting, Role, Store, User,
)
from ...services import analytics as A
from ..deps import get_current_user, require_admin, require_permission

router = APIRouter(prefix="/api", tags=["审批与管理"])


# ---------------- 审批中心 ----------------
approval_router = APIRouter(prefix="/api/approvals", tags=["审批中心"])


class ApprovalCreate(BaseModel):
    title: str
    content: str
    data_basis: str
    risk_level: str = "Level 3"
    source_module: str = "AI选品助手"
    affected_categories: Optional[str] = None


class ApprovalDecision(BaseModel):
    action: str        # approve / reject / withdraw / adopt / defer
    comment: Optional[str] = None


@approval_router.get("")
def list_approvals(status: Optional[str] = None,
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(ApprovalRequest)
    if status:
        q = q.filter(ApprovalRequest.status == status)
    rows = q.order_by(ApprovalRequest.submitted_at.desc()).all()
    return {
        "items": [
            {
                "id": r.id, "code": r.code, "source_module": r.source_module,
                "ai_suggestion": r.ai_suggestion, "data_basis": r.data_basis,
                "risk_level": r.risk_level, "applicant": r.applicant, "approver": r.approver,
                "status": r.status, "approval_comment": r.approval_comment,
                "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
                "decided_at": r.decided_at.isoformat() if r.decided_at else None,
                "recommendation_id": r.recommendation_id,
            }
            for r in rows
        ],
        "count": len(rows),
        "stats": {
            "待审批": db.query(ApprovalRequest).filter_by(status="待审批").count(),
            "已通过": db.query(ApprovalRequest).filter_by(status="已通过").count(),
            "已驳回": db.query(ApprovalRequest).filter_by(status="已驳回").count(),
            "已撤回": db.query(ApprovalRequest).filter_by(status="已撤回").count(),
        },
        "levels": [
            {"level": "Level 1", "name": "信息提示", "need_approval": False,
             "desc": "AI 仅提供信息参考，无需审批流程"},
            {"level": "Level 2", "name": "经营建议", "need_approval": False,
             "desc": "可由业务人员直接采纳或驳回"},
            {"level": "Level 3", "name": "高影响建议", "need_approval": True,
             "desc": "SKU退出、大规模精简、供应商调整、重大补货、价格调整，必须人工审批"},
        ],
    }


@approval_router.post("")
def create_approval(body: ApprovalCreate, db: Session = Depends(get_db),
                    user: User = Depends(require_permission("approval_submit"))):
    now = datetime.utcnow()
    seq = db.query(ApprovalRequest).count() + 1
    code = f"AR-{now.strftime('%Y%m%d')}-{seq:04d}"

    rec = AiRecommendation(
        code=f"REC-{seq:04d}", source_module=body.source_module, title=body.title,
        content=body.content, data_basis=body.data_basis,
        affected_categories=body.affected_categories, priority="高",
        risk_level=body.risk_level, requires_approval=(body.risk_level == "Level 3"),
        decision_status="待审", created_by=user.username, created_at=now,
    )
    db.add(rec)
    db.flush()

    ar = ApprovalRequest(
        code=code, recommendation_id=rec.id, source_module=body.source_module,
        ai_suggestion=f"{body.title}\n\n{body.content}", data_basis=body.data_basis,
        risk_level=body.risk_level, applicant=user.username, status="待审批",
        submitted_at=now,
    )
    db.add(ar)
    db.add(AuditLog(user=user.username, action="create_approval", target=code,
                    detail=f"{body.risk_level}｜{body.title}", ip="127.0.0.1"))
    db.commit()
    return {"success": True, "code": code, "id": ar.id,
            "message": f"已提交人工审批（{code}）。AI 不能自动执行该操作。"}


@approval_router.patch("/{aid}")
def decide_approval(aid: int, body: ApprovalDecision, db: Session = Depends(get_db),
                    user: User = Depends(require_permission("approval_submit"))):
    ar = db.query(ApprovalRequest).filter(ApprovalRequest.id == aid).first()
    if not ar:
        raise HTTPException(404, detail="审批记录不存在")
    if ar.status != "待审批":
        raise HTTPException(400, detail=f"该记录已处于「{ar.status}」状态，不能重复处理")

    mapping = {"approve": "已通过", "reject": "已驳回", "withdraw": "已撤回",
               "adopt": "已通过", "defer": "待审批"}
    if body.action not in mapping:
        raise HTTPException(400, detail="action 需为 approve / reject / withdraw / adopt / defer")

    new_status = mapping[body.action]
    if new_status != "待审批":
        ar.status = new_status
        ar.approver = user.username
        ar.decided_at = datetime.utcnow()
        ar.approval_comment = body.comment

    if ar.recommendation_id:
        rec = db.query(AiRecommendation).filter_by(id=ar.recommendation_id).first()
        if rec:
            rec.decision_status = "已采纳" if new_status == "已通过" else (
                "已驳回" if new_status == "已驳回" else rec.decision_status)

    db.add(AuditLog(user=user.username, action=f"approval_{body.action}", target=ar.code,
                    detail=body.comment or "", ip="127.0.0.1"))
    db.commit()
    return {"success": True, "code": ar.code, "status": ar.status}


@approval_router.get("/recommendations")
def list_recommendations(db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)):
    rows = db.query(AiRecommendation).order_by(AiRecommendation.created_at.desc()).limit(100).all()
    return {
        "items": [
            {"id": r.id, "code": r.code, "source_module": r.source_module, "title": r.title,
             "content": r.content, "data_basis": r.data_basis,
             "affected_categories": r.affected_categories, "priority": r.priority,
             "risk_level": r.risk_level, "requires_approval": r.requires_approval,
             "decision_status": r.decision_status, "created_by": r.created_by,
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows
        ],
        "count": len(rows),
    }


# ---------------- 系统管理 ----------------
admin_router = APIRouter(prefix="/api/admin", tags=["系统管理"])


@admin_router.get("/model-settings")
def get_model_settings(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    rows = db.query(ModelSetting).order_by(ModelSetting.category, ModelSetting.key).all()
    return {
        "items": [
            {"id": r.id, "key": r.key, "value": r.value, "category": r.category,
             "description": r.description, "updated_by": r.updated_by,
             "updated_at": r.updated_at.isoformat() if r.updated_at else None,
             "previous_value": r.previous_value, "change_reason": r.change_reason}
            for r in rows
        ],
        "editable": [r.key for r in rows if r.category == "algorithm"],
        "note": "修改算法参数会记录修改前后值、修改人员、时间与原因，确保结果可追溯。",
    }


class SettingUpdate(BaseModel):
    key: str
    value: object
    reason: Optional[str] = None


@admin_router.put("/model-settings")
def update_model_settings(body: SettingUpdate, db: Session = Depends(get_db),
                          user: User = Depends(require_admin)):
    s = db.query(ModelSetting).filter(ModelSetting.key == body.key).first()
    if not s:
        raise HTTPException(404, detail=f"参数 {body.key} 不存在")

    old = s.value
    reason = body.reason or "管理员调整算法参数"

    if body.key.endswith("_weights") and isinstance(body.value, dict):
        total = sum(float(v) for v in body.value.values())
        if abs(total - 1.0) > 1e-6:
            raise HTTPException(400, detail=f"权重之和必须为 1，当前为 {total:.4f}")
    if "min_support" in body.key or "min_confidence" in body.key:
        v = float(body.value)
        if not 0 < v < 1:
            raise HTTPException(400, detail="支持度与置信度必须介于 0 与 1 之间")
    if "min_lift" in body.key:
        if float(body.value) <= 0:
            raise HTTPException(400, detail="最小提升度必须大于 0")
    if body.key == "apriori_top_n":
        if not 1 <= int(body.value) <= 200:
            raise HTTPException(400, detail="TopN 必须介于 1 与 200 之间")

    A.set_setting(db, body.key, body.value, user.username, reason)
    db.add(AuditLog(user=user.username, action="update_setting", target=body.key,
                    detail=f"{old} → {body.value}；原因：{reason}", ip="127.0.0.1"))
    db.commit()

    note = ""
    if body.key in ("category_health_weights", "compare_weights"):
        note = " 权重已更新，建议重新计算品类健康度或比较结果以应用新权重。"
    elif body.key.startswith("apriori_"):
        note = " Apriori 参数已更新，建议点击「重新计算」使新参数生效。"
    return {"success": True, "key": body.key, "value": body.value, "previous_value": old,
            "note": note.strip(),
            "message": f"参数 {body.key} 已从 {old} 更新为 {body.value}。{note.strip()}"}


@admin_router.get("/users")
def list_users(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    rows = db.query(User).all()
    return {
        "items": [
            {"id": u.id, "username": u.username, "full_name": u.full_name,
             "role": u.role.name if u.role else "", "role_code": u.role.code if u.role else "",
             "permissions": u.role.permissions if u.role else [],
             "store": u.store.name if u.store else None,
             "is_active": u.is_active,
             "created_at": u.created_at.isoformat() if u.created_at else None,
             "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None}
            for u in rows
        ]
    }


@admin_router.get("/roles")
def list_roles(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    rows = db.query(Role).all()
    return {
        "items": [
            {"id": r.id, "code": r.code, "name": r.name, "description": r.description,
             "permissions": r.permissions,
             "user_count": db.query(User).filter_by(role_id=r.id).count()}
            for r in rows
        ],
        "permission_catalog": [
            {"code": "compare", "name": "商品比较"},
            {"code": "recommendation", "name": "选品建议"},
            {"code": "new_product", "name": "新品管理"},
            {"code": "category_health", "name": "品类诊断"},
            {"code": "association", "name": "关联规则"},
            {"code": "forecast", "name": "需求预测"},
            {"code": "approval_submit", "name": "审批申请"},
            {"code": "data_read", "name": "查看数据中心"},
            {"code": "feedback", "name": "提交反馈"},
        ],
    }


@admin_router.get("/stores")
def list_stores_admin(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    rows = db.query(Store).all()
    return {
        "items": [
            {"id": s.id, "code": s.code, "name": s.name, "city": s.city,
             "district": s.district, "business_district": s.business_district,
             "area_sqm": s.area_sqm, "is_default": s.is_default, "is_demo": s.is_demo,
             "pop_3km": s.pop_3km, "consumption_power": s.consumption_power}
            for s in rows
        ]
    }


class StoreUpdate(BaseModel):
    pop_3km: Optional[int] = None
    resident_ratio: Optional[float] = None
    office_ratio: Optional[float] = None
    student_ratio: Optional[float] = None
    senior_ratio: Optional[float] = None
    consumption_power: Optional[str] = None
    poi_residential: Optional[int] = None
    poi_office: Optional[int] = None
    poi_school: Optional[int] = None
    main_competitors: Optional[str] = None
    delivery_capability: Optional[str] = None


@admin_router.patch("/stores/{store_id}")
def update_store(store_id: int, body: StoreUpdate, db: Session = Depends(get_db),
                 user: User = Depends(require_admin)):
    s = db.query(Store).filter(Store.id == store_id).first()
    if not s:
        raise HTTPException(404, detail="门店不存在")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(s, k, v)
    db.add(AuditLog(user=user.username, action="update_store", target=s.name,
                    detail=str(body.model_dump(exclude_none=True)), ip="127.0.0.1"))
    db.commit()
    return {"success": True, "store": s.name,
            "note": "门店画像数据为人工录入，平台不会自行编造人口或 POI 数量。"}


@admin_router.get("/knowledge")
def list_knowledge(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    rows = db.query(KnowledgeDoc).all()
    return {
        "items": [
            {"id": r.id, "title": r.title, "category": r.category, "content": r.content,
             "tags": r.tags, "is_active": r.is_active,
             "updated_by": r.updated_by,
             "updated_at": r.updated_at.isoformat() if r.updated_at else None}
            for r in rows
        ]
    }


class KnowledgeCreate(BaseModel):
    title: str
    category: str
    content: str
    tags: Optional[str] = None


@admin_router.post("/knowledge")
def create_knowledge(body: KnowledgeCreate, db: Session = Depends(get_db),
                     user: User = Depends(require_admin)):
    doc = KnowledgeDoc(title=body.title, category=body.category, content=body.content,
                       tags=body.tags, is_active=True, updated_by=user.username,
                       updated_at=datetime.utcnow())
    db.add(doc)
    db.add(AuditLog(user=user.username, action="create_knowledge", target=body.title,
                    detail=body.category, ip="127.0.0.1"))
    db.commit()
    return {"success": True, "id": doc.id}


@admin_router.get("/audit-logs")
def audit_logs(limit: int = 200, action: Optional[str] = None,
               db: Session = Depends(get_db), user: User = Depends(require_admin)):
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action == action)
    rows = q.order_by(AuditLog.created_at.desc()).limit(limit).all()
    return {
        "items": [
            {"id": r.id, "user": r.user, "action": r.action, "target": r.target,
             "detail": r.detail, "ip": r.ip,
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows
        ],
        "count": len(rows),
    }


@admin_router.get("/model-logs")
def model_logs(limit: int = 100, db: Session = Depends(get_db),
               user: User = Depends(require_admin)):
    rows = db.query(ModelRunLog).order_by(ModelRunLog.created_at.desc()).limit(limit).all()
    return {
        "items": [
            {"id": r.id, "algorithm": r.algorithm, "parameters": r.parameters,
             "dataset": r.dataset, "status": r.status, "output": r.output,
             "duration_ms": r.duration_ms,
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows
        ]
    }


@admin_router.get("/analysis-history")
def analysis_history(limit: int = 100, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    jobs = db.query(AnalysisJob).order_by(AnalysisJob.created_at.desc()).limit(limit).all()
    runs = db.query(ModelRunLog).order_by(ModelRunLog.created_at.desc()).limit(limit).all()
    return {
        "jobs": [
            {"id": j.id, "job_type": j.job_type, "status": j.status, "algorithm": j.algorithm,
             "parameters": j.parameters, "source_dataset_id": j.source_dataset_id,
             "result_summary": j.result_summary, "duration_ms": j.duration_ms,
             "triggered_by": j.triggered_by,
             "created_at": j.created_at.isoformat() if j.created_at else None}
            for j in jobs
        ],
        "runs": [
            {"id": r.id, "algorithm": r.algorithm, "parameters": r.parameters,
             "dataset": r.dataset, "status": r.status, "output": r.output,
             "duration_ms": r.duration_ms,
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in runs
        ],
        "note": "每个算法结果都记录 source_dataset_id、algorithm、parameters、created_at，保证可追溯。",
    }


@router.get("/analysis-history")
def analysis_history_public(limit: int = 50, db: Session = Depends(get_db),
                            user: User = Depends(get_current_user)):
    return analysis_history(limit, db, user)


# ---------------- 报告导出 ----------------
report_router = APIRouter(prefix="/api/report", tags=["报告导出"])


@report_router.get("/diagnosis", response_class=PlainTextResponse)
def export_report(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """生成《门店AI选品诊断报告》纯文本版本，前端可另存为 PDF。"""
    from ...agents import tools as T
    from ...algorithms import advisor

    d = T.dashboard_summary(db)
    health = A.health_rows(db)
    fcs = A.forecast_views(db)
    rules = A.rule_summary_for_advisor(db)
    store = db.query(Store).filter_by(is_default=True).first()
    params = A.risk_params(db)
    w = A.get_setting(db, "category_health_weights", {"sales": 0.3, "margin": 0.3, "turnover": 0.2, "space": 0.2})
    alerts = advisor.risk_alerts(health, fcs, **params)
    plan = advisor.generate_comprehensive_plan(health, fcs, rules)
    pending = db.query(ApprovalRequest).filter_by(status="待审批").all()

    L = []
    L.append("门店AI选品诊断报告")
    L.append("=" * 56)
    L.append(f"门店：{store.name if store else '-'}")
    L.append(f"报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    L.append(f"数据来源：{DEMO_SOURCE}")
    L.append(f"免责声明：{DEMO_DISCLAIMER}")
    L.append("")

    L.append("一、门店概况")
    L.append("-" * 56)
    if store:
        L.append(f"门店编码：{store.code}")
        L.append(f"所在区域：{store.city}{store.district} {store.business_district}")
        L.append(f"门店类型：{store.store_type}　营业面积：{store.area_sqm} ㎡")
    L.append(f"数据规模：品类销售 {d['data_status']['category_sales_rows']} 行，"
             f"交易明细 {d['data_status']['transaction_rows']} 条（{d['data_status']['transaction_count']} 笔交易），"
             f"需求数据 {d['data_status']['demand_rows']} 行")
    L.append("")

    L.append("二、核心指标")
    L.append("-" * 56)
    k = d["kpi"]
    L.append(f"品类总数：{k['category_total']} 个")
    L.append(f"健康品类（≥70分）：{k['healthy_category']} 个")
    L.append(f"风险品类（<55分）：{k['risk_category']} 个")
    L.append(f"近12个月累计缺货：{k['stockout_this_month']} 次")
    L.append(f"平均库存周转：{k['avg_turnover_days']} 天")
    L.append(f"高价值关联组合（lift≥2）：{k['high_value_associations']} 条")
    L.append(f"需求上涨品类：{k['demand_rising_categories']} 个")
    L.append(f"待审批建议：{k['pending_approvals']} 条")
    L.append("")

    L.append("三、品类健康度")
    L.append("-" * 56)
    L.append(f"{'排名':<4}{'品类':<12}{'综合分':<8}{'等级':<8}{'销量贡献':<10}{'毛利贡献':<10}{'周转(天)':<10}{'坪效':<10}{'缺货':<6}")
    for h in health:
        L.append(f"{h['rank']:<4}{h['category']:<12}{h['overall_score']:<8}{h['grade']:<8}"
                 f"{str(h['sales_contribution'])+'%':<10}{str(h['margin_contribution'])+'%':<10}"
                 f"{str(h['avg_turnover_days']):<10}{str(h['avg_sales_per_sqm']):<10}{str(h.get('stockout_count')):<6}")
    L.append("")
    L.append("附件参考结果与系统重算结果差异：")
    for h in health:
        if h.get("attachment_reference"):
            L.append(f"  {h['category']}：系统重算 {h['overall_score']} 分 / "
                     f"附件参考 {h['attachment_reference']['overall_score']} 分"
                     f"（差异 {h.get('diff_vs_attachment')}）")
    L.append("")

    L.append("四、需求预测（模拟预测结果）")
    L.append("-" * 56)
    for f in fcs:
        cp = f"{f['change_pct']:+.1f}%" if f.get("change_pct") is not None else "—"
        L.append(f"{f['category']}：{f['trend_level']}，未来4期均量 {f['future_avg']} 件，环比 {cp}，"
                 f"风险 {f['risk']['risk_level']}")
        L.append(f"  {f['sample_note']}")
    L.append("")

    L.append("五、关联陈列机会（实时重算）")
    L.append("-" * 56)
    L.append(f"购物篮构建方式：交易号 + 商品名称（演示数据商品编码离散）")
    L.append(f"参数：support≥{rules['params']['min_support']}、confidence≥{rules['params']['min_confidence']}、lift≥{rules['params']['min_lift']}")
    for r in rules["rules"][:8]:
        L.append(f"  {r['display_rule']}：support={r['support']:.4f} conf={r['confidence']:.4f} "
                 f"lift={r['lift']:.2f}　{r['display_suggestion']}")
    L.append("")

    L.append("六、风险预警")
    L.append("-" * 56)
    if alerts:
        for a in alerts:
            L.append(f"[{a['level']}] {a['type']} — {a['target']}：{a['value']}。{a['detail']}")
    else:
        L.append("当前无触发预警。")
    L.append("")

    L.append("七、AI优化建议")
    L.append("-" * 56)
    for g in ["优先扩充", "建议保持", "重点观察", "建议精简", "建议退出"]:
        items = plan[g]
        L.append(f"【{g}】")
        if not items:
            L.append("  无")
        for it in items:
            L.append(f"  · {it['category']}：{it['action']}")
            L.append(f"    数据依据：{it['data_basis']}")
    L.append("")

    L.append("八、待审批事项")
    L.append("-" * 56)
    if pending:
        for p in pending:
            L.append(f"{p.code}｜{p.risk_level}｜申请人 {p.applicant}｜{p.ai_suggestion.splitlines()[0]}")
    else:
        L.append("当前无待审批事项。")
    L.append("")

    L.append("九、数据来源与模型参数")
    L.append("-" * 56)
    L.append("数据集：dataset_category_sales / transactions_sample / demand_forecast / "
             "association_rules / category_health")
    L.append(f"品类健康度权重：销量 {w.get('sales')}、毛利 {w.get('margin')}、"
             f"周转 {w.get('turnover')}、坪效 {w.get('space')}")
    ap = rules["params"]
    L.append(f"Apriori 参数：min_support={ap['min_support']}、min_confidence={ap['min_confidence']}、"
             f"min_lift={ap['min_lift']}、TopN={ap['top_n']}")
    L.append(f"风险阈值：周转>{params['turnover_threshold']}天、坪效<{params['space_threshold']}、"
             f"缺货≥{params['stockout_threshold']}次、健康度<{params['score_threshold']}分")
    L.append("")
    L.append("十、免责声明")
    L.append("-" * 56)
    L.append(f"本报告全部数据为{DEMO_SOURCE}，{DEMO_DISCLAIMER}。")
    L.append("报告由 AI 辅助生成，结论仅供门店采购人员与品类经理参考，")
    L.append("最终选品决策由采购人员确认，涉及 SKU 退出、供应商调整、价格调整的建议须经人工审批。")
    return "\n".join(L)