from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
import asyncio
from app.services.nori_service import chat_with_nori, analyze_marketing_data, get_greeting, OpenAIQuotaError, OpenAIConfigError
from app.core.security import get_current_user
from app.core.database import get_db
from app.models.user import Usuario
from app.models.nori_insights import NoriInsight
from sqlalchemy.orm import Session
from datetime import datetime

router = APIRouter(prefix="/nori", tags=["Assistente Nori"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    context: Optional[List[ChatMessage]] = None
    events_data: Optional[List[dict]] = None


class ChatResponse(BaseModel):
    response: str
    success: bool


class AnalysisRequest(BaseModel):
    events_data: List[dict]


class InsightResponse(BaseModel):
    id: int
    evento_id: Optional[str]
    evento_nome: str
    tipo: str
    titulo: str
    conteudo: str
    acao_sugerida: Optional[str]
    impacto_estimado_reais: Optional[float]
    impacto_estimado_percentual: Optional[float]
    status: str
    gerado_em: str

    class Config:
        from_attributes = True


@router.get("/greeting")
def nori_greeting(current_user: Usuario = Depends(get_current_user)):
    return {"greeting": get_greeting(), "success": True}


@router.post("/chat", response_model=ChatResponse)
def nori_chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    try:
        context_list = None
        if request.context:
            context_list = [{"role": m.role, "content": m.content} for m in request.context]

        insights_context = None
        try:
            from app.services.nori_insights_service import get_active_insights_summary
            insights_context = get_active_insights_summary(db, limit=5)
        except Exception:
            pass

        response = asyncio.run(chat_with_nori(
            message=request.message,
            context=context_list,
            events_data=request.events_data,
            insights_context=insights_context,
        ))

        return ChatResponse(response=response, success=True)
    except OpenAIQuotaError as e:
        raise HTTPException(status_code=402, detail=str(e))
    except OpenAIConfigError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar mensagem: {str(e)}")


@router.post("/analyze", response_model=ChatResponse)
def nori_analyze(
    request: AnalysisRequest,
    current_user: Usuario = Depends(get_current_user)
):
    try:
        response = asyncio.run(analyze_marketing_data(request.events_data))
        return ChatResponse(response=response, success=True)
    except OpenAIQuotaError as e:
        raise HTTPException(status_code=402, detail=str(e))
    except OpenAIConfigError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao analisar dados: {str(e)}")


@router.get("/insights", response_model=List[InsightResponse])
def list_insights(
    status: Optional[str] = Query(None, description="Filtrar por status: novo, visto, descartado"),
    tipo: Optional[str] = Query(None, description="Filtrar por tipo"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    query = db.query(NoriInsight)
    if status:
        query = query.filter(NoriInsight.status == status)
    else:
        query = query.filter(NoriInsight.status.in_(["novo", "visto"]))
    if tipo:
        query = query.filter(NoriInsight.tipo == tipo)
    query = query.order_by(
        NoriInsight.impacto_estimado_reais.desc().nullslast(),
        NoriInsight.gerado_em.desc()
    )
    insights = query.limit(50).all()
    return [
        InsightResponse(
            id=ins.id,
            evento_id=ins.evento_id,
            evento_nome=ins.evento_nome,
            tipo=ins.tipo,
            titulo=ins.titulo,
            conteudo=ins.conteudo,
            acao_sugerida=ins.acao_sugerida,
            impacto_estimado_reais=ins.impacto_estimado_reais,
            impacto_estimado_percentual=ins.impacto_estimado_percentual,
            status=ins.status,
            gerado_em=ins.gerado_em.isoformat() if ins.gerado_em else "",
        )
        for ins in insights
    ]


@router.patch("/insights/{insight_id}")
def update_insight_status(
    insight_id: int,
    status: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    if status not in ("novo", "visto", "descartado"):
        raise HTTPException(status_code=400, detail="Status inválido. Use: novo, visto, descartado")
    insight = db.query(NoriInsight).filter(NoriInsight.id == insight_id).first()
    if not insight:
        raise HTTPException(status_code=404, detail="Insight não encontrado")
    insight.status = status
    insight.atualizado_em = datetime.now()
    db.commit()
    return {"success": True, "id": insight_id, "status": status}


@router.delete("/insights/{insight_id}")
def delete_insight(
    insight_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    insight = db.query(NoriInsight).filter(NoriInsight.id == insight_id).first()
    if not insight:
        raise HTTPException(status_code=404, detail="Insight não encontrado")
    db.delete(insight)
    db.commit()
    return {"success": True}


@router.post("/insights/gerar")
def trigger_insights_generation(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    try:
        from app.services.nori_insights_service import run_proactive_insights_job
        result = asyncio.run(run_proactive_insights_job(db))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar insights: {str(e)}")
