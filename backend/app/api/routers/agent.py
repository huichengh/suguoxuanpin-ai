"""AI 选品助手接口 + 新品评估"""
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...agents import agent as A
from ...agents import responder
from ...agents import tools as T
from ...config import DEMO_DISCLAIMER
from ...database import get_db
from ...models import AgentConversation, AuditLog, User
from ..deps import get_current_user, require_permission

router = APIRouter(prefix="/api/agent", tags=["AI选品助手"])


class ChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    question: str
    answer: dict
    suggestions: List[str]


SUGGESTIONS = [
    "现在门店的商品结构有哪些问题？",
    "生鲜蔬果的健康度怎么样？",
    "比较生鲜蔬果和纺织服装",
    "哪些品类建议精简？",
    "牛奶和面包的关联度有多高？",
    "火锅底料和丸子适合一起陈列吗？",
    "未来4期哪些品类需求上涨？",
    "哪些品类缺货比较频繁？",
    "纺织服装的需求趋势如何？",
    "哪个品类适合做自有品牌？",
    "生成综合选品方案",
    "当前有哪些数据质量问题？",
    "查看风险预警",
]


@router.get("/tools")
def list_tools(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return {
        "tools": A.registry.descriptions(),
        "system_prompt": A.SYSTEM_PROMPT,
        "principles": [
            "数据优先：量化结论必须来自数据库与算法结果，信息不足时明确拒绝推测",
            "可解释：每条建议说明依据、关键指标、最大风险与是否需人工确认",
            "AI辅助、人工决策：不自动执行下单、改价、淘汰供应商等不可逆操作",
            "区分真实与模拟数据：演示数据必须标注来源",
            "区分附件参考结果与实时算法结果，并解释差异来源",
        ],
        "answer_template": ["【结论】", "【关键数据依据】", "【分析】", "【建议】", "【风险与限制】", "【决策状态】"],
        "sensitive_data_policy": (
            "会员姓名、手机号、身份证号等个人身份信息不得发送给外部大模型；"
            "AI 只读取匿名化数据、聚合数据与算法结果。"
        ),
    }


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, db: Session = Depends(get_db),
         user: User = Depends(get_current_user)):
    q = body.question.strip()
    if not q:
        raise HTTPException(400, detail="问题不能为空")

    session_id = body.session_id or uuid.uuid4().hex[:16]

    db.add(AgentConversation(session_id=session_id, user=user.username,
                             role="user", content=q))
    db.commit()

    try:
        answer = responder.answer(db, user.username, q)
    except Exception as e:
        raise HTTPException(500, detail=f"分析过程出错：{e}")

    text = format_answer(answer)
    db.add(AgentConversation(session_id=session_id, user=user.username,
                             role="assistant", content=text,
                             tools_used=answer.get("tools_used", [])))
    db.add(AuditLog(user=user.username, action="agent_chat", target=session_id,
                    detail=f"意图 {answer.get('intent')}，工具 {answer.get('tools_used')}",
                    ip="127.0.0.1"))
    db.commit()

    return {"session_id": session_id, "question": q, "answer": answer,
            "suggestions": SUGGESTIONS}


def format_answer(a: dict) -> str:
    """把结构化回答渲染为标准回答模板文本。"""
    lines = [
        "【结论】", a["conclusion"], "",
        "【关键数据依据】",
    ]
    lines += [f"  {i+1}. {b}" for i, b in enumerate(a["key_basis"])] or ["  -"]
    lines += ["", "【分析】", a["analysis"], "", "【建议】", a["advice"], "",
              "【风险与限制】", a["risk_limit"], "", "【决策状态】", a["decision_status"]]
    if a.get("demo_note"):
        lines += ["", f"数据说明：{a['demo_note']}"]
    lines += ["", a["disclaimer"]]
    return "\n".join(lines)


@router.get("/history")
def chat_history(session_id: Optional[str] = None, limit: int = 50,
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(AgentConversation)
    if session_id:
        q = q.filter(AgentConversation.session_id == session_id)
    rows = q.order_by(AgentConversation.created_at.desc()).limit(limit).all()
    return {
        "items": [
            {"role": r.role, "content": r.content, "tools_used": r.tools_used,
             "created_at": r.created_at.isoformat() if r.created_at else None,
             "session_id": r.session_id}
            for r in reversed(rows)
        ]
    }


# ---------------- 新品评估 ----------------
new_router = APIRouter(prefix="/api/new-products", tags=["新品评估"])


class NewProductRequest(BaseModel):
    name: str
    category_id: Optional[int] = None
    brand: Optional[str] = None
    purchase_price: Optional[float] = None
    suggested_retail_price: Optional[float] = None
    expected_margin_rate: Optional[float] = None
    supplier: Optional[str] = None
    target_consumer: Optional[str] = None
    spec: Optional[str] = None
    packaging: Optional[str] = None
    season: Optional[str] = None
    selling_point: Optional[str] = None
    is_private_label: Optional[bool] = None
    reference_sku: Optional[str] = None


@new_router.post("/evaluate")
def evaluate(body: NewProductRequest, db: Session = Depends(get_db),
             user: User = Depends(require_permission("new_product"))):
    from ...models import CandidateProduct
    from ...services import analytics as SA

    payload = body.model_dump()
    result = SA.evaluate_new_product(db, payload)

    rec = CandidateProduct(
        name=body.name, category_id=body.category_id, brand=body.brand,
        purchase_price=body.purchase_price, suggested_retail_price=body.suggested_retail_price,
        expected_margin_rate=body.expected_margin_rate, supplier=body.supplier,
        target_consumer=body.target_consumer, spec=body.spec, packaging=body.packaging,
        season=body.season, selling_point=body.selling_point,
        is_private_label=bool(body.is_private_label), reference_sku=body.reference_sku,
        completeness_score=result["completeness_score"],
        potential_level=result["potential_level"], evaluation=result,
        created_by=user.username, created_at=datetime.utcnow(),
    )
    db.add(rec)
    db.add(AuditLog(user=user.username, action="evaluate_new_product", target=body.name,
                    detail=f"潜力等级 {result['potential_level']}", ip="127.0.0.1"))
    db.commit()
    result["candidate_id"] = rec.id
    result["demo_label"] = DEMO_DISCLAIMER
    return result


def require_new_product():
    from ..deps import require_permission
    return require_permission("new_product")


@new_router.get("/candidates")
def list_candidates(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ...models import CandidateProduct

    rows = db.query(CandidateProduct).order_by(CandidateProduct.created_at.desc()).all()
    return {
        "items": [
            {"id": r.id, "name": r.name, "category": r.category.name if r.category else "",
             "brand": r.brand, "supplier": r.supplier, "purchase_price": r.purchase_price,
             "suggested_retail_price": r.suggested_retail_price,
             "expected_margin_rate": r.expected_margin_rate,
             "potential_level": r.potential_level, "completeness_score": r.completeness_score,
             "is_private_label": r.is_private_label, "target_consumer": r.target_consumer,
             "selling_point": r.selling_point,
             "created_by": r.created_by,
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows
        ],
        "count": len(rows),
        "note": "新品评估使用解释型等级，不输出成功概率等精确数值。",
    }


@new_router.delete("/candidates/{cid}")
def delete_candidate(cid: int, db: Session = Depends(get_db),
                     user: User = Depends(require_permission("new_product"))):
    from ...models import CandidateProduct
    r = db.query(CandidateProduct).filter_by(id=cid).first()
    if not r:
        raise HTTPException(404, detail="候选商品不存在")
    db.delete(r)
    db.add(AuditLog(user=user.username, action="delete_candidate", target=str(cid),
                    detail="删除新品候选", ip="127.0.0.1"))
    db.commit()
    return {"success": True}