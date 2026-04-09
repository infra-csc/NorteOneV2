import os
import json
import logging
from datetime import datetime, date
from zoneinfo import ZoneInfo
from typing import Optional
from openai import AsyncOpenAI, RateLimitError, APIError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

INSIGHTS_TIPOS = {
    "margem_oportunidade": "Oportunidade de Margem",
    "isc_alerta": "Alerta ISC Crítico",
    "preco_defasado": "Preço Defasado",
    "ticket_abaixo_orcado": "Ticket Abaixo do Orçado",
    "aceleracao_sem_reajuste": "Aceleração Sem Reajuste",
    "kit_custo_baixo": "Kit com Custo Baixo",
}

INSIGHTS_SYSTEM_PROMPT = """Você é um analista financeiro especialista em precificação e margem de eventos esportivos da Norte Eventos.

Seu objetivo é identificar oportunidades de aumento de margem que os gestores humanos frequentemente não percebem no dia a dia, analisando os dados de todos os eventos ativos.

DEFINIÇÕES DAS MÉTRICAS DE MARGEM (use corretamente em suas análises):
- **margem_bruta_pct** (ex: 70%): % de margem por ticket = (ticket_medio - custo_kit) / ticket_medio. Indica a eficiência de custo por inscrição.
- **margem_orcada_bruta_pct** (ex: 74%): % de margem por ticket no orçamento = (ticket_orcado - custo_kit) / ticket_orcado.
- **margem_realizacao_rate_pct** (ex: 45%): % da margem total orçada que já foi capturada = margem_realizada_R$ / margem_orcada_R$. É a métrica mais importante para avaliar o progresso financeiro real do evento.
- **pct_vendas_meta**: % de vendas realizadas sobre a meta (ex: 55% = vendeu 55% da meta). Serve de referência — o margem_realizacao_rate_pct deveria ser próximo ao pct_vendas_meta se o ticket estiver conforme planejado.

CRITÉRIOS DE ANÁLISE:

1. **ticket_abaixo_orcado**: Ticket realizado < ticket orçado. O evento está vendendo abaixo do planejado. Calcule o impacto: (ticket_orcado - ticket_atual) × vendas_atuais.

2. **aceleracao_sem_reajuste**: ISC > 1.12 (forte/acelerando) mas ticket_atual está próximo ou abaixo do ticket_orcado. Demanda alta e preço não foi ajustado — é o momento ideal para subir o preço.

3. **margem_oportunidade**: margem_realizacao_rate_pct está mais de 8 pontos percentuais abaixo de pct_vendas_meta. Isso significa que o evento está capturando menos margem do que deveria proporcionalmente às suas vendas — o ticket realizado está abaixo do orçado. Exemplo: se pct_vendas_meta = 55% mas margem_realizacao_rate_pct = 45%, há uma defasagem de 10 pontos. NÃO use margem_bruta_pct vs margem_orcada_bruta_pct para disparar esse insight.

4. **preco_defasado**: Evento no estágio Estratégico (D 32-50) ou Operacional (D<32) com ISC forte e preço não reajustado nos últimos 30 dias.

5. **kit_custo_baixo**: custo_kit < 20% do ticket médio mas margem_orcada é conservadora (< 50%). Há espaço para aumentar o preço sem comprometer vendas.

6. **isc_alerta**: ISC < 0.90 em evento com D < 50 dias. Janela de promoção pode estar se fechando (regra D-40).

IMPORTANTE: 
- Ao mencionar margem em seu texto, use SEMPRE o margem_realizacao_rate_pct (ex: "A margem realizada atingiu 45% do total orçado, com 55% das vendas concluídas"). Não mencione margem_bruta_pct como "margem realizada" para evitar confusão.
- Foque nos eventos com MAIOR IMPACTO FINANCEIRO potencial
- Calcule impactos realistas (não exagere)
- Seja específico nas ações sugeridas (ex: "Aumentar preço do kit básico de R$150 para R$170")
- Ignore eventos com D- negativo (já encerrados)
- Priorize eventos com mais vendas futuras potenciais

Retorne APENAS JSON válido, sem texto adicional."""

INSIGHTS_USER_PROMPT_TEMPLATE = """Analise os seguintes eventos ativos e identifique oportunidades de melhoria de margem.

DADOS DOS EVENTOS:
{eventos_json}

Retorne um JSON com a seguinte estrutura:
{{
  "insights": [
    {{
      "evento_id": "string — ID do evento",
      "evento_nome": "string — nome do evento",
      "tipo": "string — um de: margem_oportunidade, isc_alerta, preco_defasado, ticket_abaixo_orcado, aceleracao_sem_reajuste, kit_custo_baixo",
      "titulo": "string — título impactante com até 80 caracteres",
      "conteudo": "string — análise detalhada em 2-3 parágrafos",
      "acao_sugerida": "string — ação específica e mensurável em até 200 caracteres",
      "impacto_estimado_reais": número — impacto financeiro estimado em R$ (pode ser null),
      "impacto_estimado_percentual": número — melhora percentual estimada na margem (pode ser null)
    }}
  ]
}}

Gere no máximo 8 insights, priorizando os de maior impacto. Se não houver oportunidades claras, retorne {{"insights": []}}."""


def _format_events_for_insights(events_data: list) -> str:
    simplified = []
    for evt in events_data:
        if not evt:
            continue
        isc = evt.get("isc", 0)
        isc_status = evt.get("iscStatus", "")
        d_minus = evt.get("dMinus", 999)

        if d_minus < 0:
            continue

        avg_ticket = evt.get("averageTicket", 0) or 0
        budget_ticket = evt.get("budgetTicket", 0) or 0
        ticket_atual = evt.get("ticketAtual", 0) or 0
        kit_cost = evt.get("kitCostPerUnit", 0) or 0
        margem_bruta_pct = evt.get("margemRealizadaPct", 0) or 0
        margem_orcada_bruta_pct = evt.get("margemOrcadaPct", 0) or 0
        margem_realizada_reais = evt.get("margemRealizadaTotal", 0) or 0
        margem_orcada_reais = evt.get("margemOrcadaTotal", 0) or 0
        margem_realizacao_rate = evt.get("margemRealizacaoRate", 0) or 0
        current_sales = evt.get("currentSales", 0) or 0
        sales_goal = evt.get("salesGoal", 1) or 1

        pct_vendas_meta = round(current_sales / sales_goal * 100, 1) if sales_goal > 0 else 0

        sa = evt.get("suggestedAction") or {}
        pb_letter = sa.get("letter", "?")
        pb_stage = sa.get("stageName", "N/A")

        simplified.append({
            "id": evt.get("id", ""),
            "nome": evt.get("name", ""),
            "d_minus": d_minus,
            "isc": round(isc, 2),
            "isc_status": isc_status,
            "playbook": f"{pb_letter} ({pb_stage})",
            "vendas_atuais": current_sales,
            "meta_vendas": sales_goal,
            "pct_vendas_meta": pct_vendas_meta,
            "ticket_medio_realizado": round(avg_ticket, 2),
            "ticket_orcado": round(budget_ticket, 2),
            "ticket_atual_magento": round(ticket_atual, 2),
            "custo_kit": round(kit_cost, 2),
            # Margem bruta % por ticket (eficiência de custo por inscrição)
            "margem_bruta_pct": round(margem_bruta_pct, 1),
            "margem_orcada_bruta_pct": round(margem_orcada_bruta_pct, 1),
            # Taxa de realização: quanto do total de margem orçada foi capturado
            # Esta é a métrica principal de progresso financeiro do evento
            "margem_realizacao_rate_pct": round(margem_realizacao_rate, 1),
            "margem_realizada_total_R$": round(margem_realizada_reais, 2),
            "margem_orcada_total_R$": round(margem_orcada_reais, 2),
        })

    return json.dumps(simplified, ensure_ascii=False, indent=2)


async def generate_insights_for_events(events_data: list) -> list:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.warning("[NoriInsights] OPENAI_API_KEY não configurada — pulando geração de insights")
        return []

    if not events_data:
        return []

    client = AsyncOpenAI(api_key=api_key)
    eventos_json = _format_events_for_insights(events_data)

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": INSIGHTS_SYSTEM_PROMPT},
                {"role": "user", "content": INSIGHTS_USER_PROMPT_TEMPLATE.format(eventos_json=eventos_json)},
            ],
            response_format={"type": "json_object"},
            max_tokens=2000,
            temperature=0.4,
        )
        raw = response.choices[0].message.content
        parsed = json.loads(raw)
        return parsed.get("insights", [])
    except RateLimitError:
        logger.error("[NoriInsights] RateLimitError na OpenAI")
        return []
    except APIError as e:
        logger.error(f"[NoriInsights] APIError: {e}")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"[NoriInsights] Erro ao parsear JSON da OpenAI: {e}")
        return []
    except Exception as e:
        logger.error(f"[NoriInsights] Erro inesperado: {e}")
        return []


def save_insights_to_db(db: Session, insights: list, events_context: Optional[dict] = None) -> int:
    """Persist generated insights, deduplicating by (evento_id, tipo, date) across ALL statuses."""
    from app.models.nori_insights import NoriInsight

    if not insights:
        return 0

    brasilia_tz = ZoneInfo('America/Sao_Paulo')
    today = datetime.now(brasilia_tz).date()
    day_start = datetime.combine(today, datetime.min.time())

    saved = 0
    for item in insights:
        evento_id = str(item.get("evento_id", "")) or None
        tipo = item.get("tipo", "margem_oportunidade")
        titulo = (item.get("titulo") or "")[:400]       # matches nori_insights.titulo VARCHAR(400)
        conteudo = item.get("conteudo") or ""
        acao_sugerida = (item.get("acao_sugerida") or "")[:500]
        evento_nome = (item.get("evento_nome") or "")[:300]  # matches nori_insights.evento_nome VARCHAR(300)

        if not titulo or not conteudo or not evento_nome:
            continue

        # Dedupe: one insight per (evento_id, tipo, day) regardless of status
        existing = db.query(NoriInsight).filter(
            NoriInsight.evento_id == evento_id,
            NoriInsight.tipo == tipo,
            NoriInsight.gerado_em >= day_start,
        ).first()

        if existing:
            continue

        # Capture the raw event metrics used to generate this insight
        ctx: Optional[dict] = None
        if events_context and evento_id and evento_id in events_context:
            ctx = events_context[evento_id]

        insight = NoriInsight(
            evento_id=evento_id,
            evento_nome=evento_nome,
            tipo=tipo,
            titulo=titulo,
            conteudo=conteudo,
            acao_sugerida=acao_sugerida if acao_sugerida else None,
            impacto_estimado_reais=item.get("impacto_estimado_reais"),
            impacto_estimado_percentual=item.get("impacto_estimado_percentual"),
            dados_contexto=ctx,
            status="novo",
        )
        db.add(insight)
        saved += 1

    if saved > 0:
        db.commit()

    return saved


async def run_proactive_insights_job(db: Session, force_refresh: bool = False) -> dict:
    logger.info(f"[NoriInsights] Iniciando job de insights proativos (force_refresh={force_refresh})...")
    _today_deleted = 0

    # On manual refresh: also wipe today's non-dismissed insights so we regenerate with fresh data.
    # On scheduled run: only remove stale insights from previous days.
    try:
        from app.models.nori_insights import NoriInsight as _NI
        brasilia_tz = ZoneInfo('America/Sao_Paulo')
        today_start = datetime.combine(datetime.now(brasilia_tz).date(), datetime.min.time())

        stale_q = (
            db.query(_NI)
            .filter(
                _NI.gerado_em < today_start,
                _NI.status.in_(["novo", "visto"]),
            )
        )
        stale_deleted = stale_q.delete(synchronize_session=False)

        if force_refresh:
            _today_deleted = (
                db.query(_NI)
                .filter(
                    _NI.gerado_em >= today_start,
                    _NI.status.in_(["novo", "visto"]),
                )
                .delete(synchronize_session=False)
            )

        if stale_deleted or _today_deleted:
            db.commit()
            if stale_deleted:
                logger.info(f"[NoriInsights] {stale_deleted} insights de dias anteriores removidos")
            if _today_deleted:
                logger.info(f"[NoriInsights] {_today_deleted} insights de hoje substituídos pela atualização forçada")
    except Exception as _cleanup_err:
        logger.warning(f"[NoriInsights] Erro ao limpar insights antigos: {_cleanup_err}")

    try:
        from datetime import datetime as _dt
        ano = _dt.now().year
        from app.api.routes.marketing import get_marketing_events
        result = get_marketing_events(
            ano=ano,
            status="active",
            categoria=None,
            busca=None,
            force_refresh=True,
            db=db,
            current_user=None,
            response=None,
        )
        if hasattr(result, "eventos"):
            events_raw = [e.model_dump() if hasattr(e, "model_dump") else dict(e) for e in result.eventos]
        elif isinstance(result, dict):
            events_raw = result.get("eventos", [])
            if events_raw and hasattr(events_raw[0], "model_dump"):
                events_raw = [e.model_dump() for e in events_raw]
        else:
            events_raw = []
    except Exception as e:
        logger.error(f"[NoriInsights] Erro ao buscar eventos: {e}")
        return {"status": "error", "message": str(e)}

    if not events_raw:
        logger.info("[NoriInsights] Nenhum evento ativo encontrado")
        return {"status": "ok", "insights_generated": 0}

    logger.info(f"[NoriInsights] Analisando {len(events_raw)} eventos ativos...")

    # Build a lookup of simplified event metrics keyed by event ID for dados_contexto
    events_context: dict = {}
    for evt in events_raw:
        if not evt:
            continue
        evt_id = str(evt.get("id", "") or evt.get("evento_id", "") or "")
        if not evt_id:
            continue
        # Store the same simplified view that was sent to the AI
        _sales = evt.get("currentSales") or 0
        _goal = evt.get("salesGoal") or 1
        _pct_vendas = round(_sales / _goal * 100, 1) if _goal > 0 else 0
        events_context[evt_id] = {
            "id": evt_id,
            "nome": evt.get("name", "") or evt.get("nome", ""),
            "d_minus": evt.get("dMinus"),
            "isc": evt.get("isc"),
            "isc_status": evt.get("iscStatus"),
            "vendas_atuais": _sales,
            "meta_vendas": _goal,
            "pct_vendas_meta": _pct_vendas,
            "ticket_medio_realizado": evt.get("averageTicket"),
            "ticket_orcado": evt.get("budgetTicket"),
            "ticket_atual_magento": evt.get("ticketAtual"),
            "custo_kit": evt.get("kitCostPerUnit"),
            "margem_bruta_pct": evt.get("margemRealizadaPct"),
            "margem_orcada_bruta_pct": evt.get("margemOrcadaPct"),
            "margem_realizacao_rate_pct": evt.get("margemRealizacaoRate"),
            "margem_realizada_total_R$": evt.get("margemRealizadaTotal"),
            "margem_orcada_total_R$": evt.get("margemOrcadaTotal"),
        }

    insights = await generate_insights_for_events(events_raw)
    logger.info(f"[NoriInsights] OpenAI retornou {len(insights)} insights")

    saved = save_insights_to_db(db, insights, events_context=events_context)
    logger.info(f"[NoriInsights] {saved} novos insights salvos no banco")

    return {
        "status": "ok",
        "events_analyzed": len(events_raw),
        "insights_generated": len(insights),
        "insights_saved": saved,
        "insights_replaced": _today_deleted,
    }


def get_active_insights_summary(db: Session, limit: int = 5) -> str:
    from app.models.nori_insights import NoriInsight

    try:
        insights = (
            db.query(NoriInsight)
            .filter(NoriInsight.status == "novo")
            .order_by(NoriInsight.impacto_estimado_reais.desc().nullslast())
            .limit(limit)
            .all()
        )

        if not insights:
            return ""

        lines = ["━━━ INSIGHTS PROATIVOS ATIVOS ━━━"]
        for ins in insights:
            impacto = ""
            if ins.impacto_estimado_reais:
                impacto = f" | Impacto: R${ins.impacto_estimado_reais:,.0f}"
            lines.append(f"• [{ins.tipo.upper()}] {ins.evento_nome}: {ins.titulo}{impacto}")
            if ins.acao_sugerida:
                lines.append(f"  → {ins.acao_sugerida}")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"[NoriInsights] Erro ao buscar resumo de insights: {e}")
        return ""
