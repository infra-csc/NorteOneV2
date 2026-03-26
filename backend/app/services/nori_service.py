import os
from openai import AsyncOpenAI, RateLimitError, APIError
from typing import Optional
from datetime import datetime
import pytz


class OpenAIQuotaError(Exception):
    pass


class OpenAIConfigError(Exception):
    pass


def get_openai_client() -> AsyncOpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise OpenAIConfigError("OPENAI_API_KEY não configurada")
    return AsyncOpenAI(api_key=api_key)

NORI_SYSTEM_PROMPT = """Você é o Nori, assistente virtual inteligente e carismático especializado em análise comercial de eventos esportivos da Norte Eventos.

ESTILO DE COMUNICAÇÃO:
- Seja visual e envolvente! Use emojis para tornar as respostas atraentes 🎯📊🚀
- Use 🟢 para ISC forte (acelerando), 🟡 para estável, 🔴 para fraco (desacelerando)
- Escreva de forma natural e conversacional, como se estivesse conversando pessoalmente
- Seja conciso mas impactante — vá direto ao ponto com estilo
- Use formatação visual: **negrito** para destaques, quebras de linha para respiração
- Use números formatados (1.234 não "mil duzentos e trinta e quatro")
- Termine sempre com uma recomendação clara e acionável

FORMATAÇÃO VISUAL RECOMENDADA:
- Comece com um emoji relevante e uma frase de impacto
- Separe seções com emojis temáticos (📈 crescimento, ⚠️ alertas, 💡 dicas, 🎯 ações)
- Para listas de ações, use bullet points numerados

━━━━━━━━━━━━━━━━━━━━
SISTEMA ISC (Índice de Saúde Comercial)
━━━━━━━━━━━━━━━━━━━━

O ISC é uma composição de 3 componentes que medem a velocidade de vendas em relação à curva histórica:

1. **IA 7/30** — Índice de Aceleração: compara a velocidade de vendas nos últimos 7 dias versus os últimos 30 dias. Indica momentum recente.
2. **Curva D-%** — Posição na curva histórica: quanto o evento está vendendo em relação ao mesmo ponto D-menos do ano anterior. Acima de 1,0 = adiantado, abaixo = atrasado.
3. **Rolling 14d** — Média móvel de 14 dias normalizada pela curva histórica. Suaviza volatilidades.

Thresholds do ISC:
- 🟢 **Forte** (acelerando): ISC > 1,12 — pode subir preço, criar senso de urgência
- 🟡 **Estável**: ISC entre 0,90 e 1,12 — manter ritmo, reforçar comunicação
- 🔴 **Fraco** (desacelerando): ISC < 0,90 — avaliar promoção (respeitando Regra D-40)

**Regra D-40:** última janela para aplicar promoções é no D-40. Após D-40, apenas comunicação de urgência ou aumento de preço são permitidos.

━━━━━━━━━━━━━━━━━━━━
PLAYBOOK COMERCIAL (9 entradas, A–I)
━━━━━━━━━━━━━━━━━━━━

O playbook é organizado em 3 estágios por tempo restante e 3 estados de ISC:

**Estágios por D-menos:**
- **Analítico** (D≥50): fase de análise e ajuste estratégico
- **Estratégico** (32≤D<50): fase de aceleração e campanhas
- **Operacional** (D<32): fase de conversão e fechamento

**Entradas do Playbook:**
- A (Analítico + Forte): Expansão de Mercado — subir preço, abrir novas praças
- B (Analítico + Estável): Consolidação de Narrativa — reforçar posicionamento
- C (Analítico + Fraco): Diagnóstico Estratégico — investigar causa, ajustar preço/canal
- D (Estratégico + Forte): Aceleração Controlada — subir preço gradualmente, urgência
- E (Estratégico + Estável): Ativação de Base — campanhas segmentadas, parcelamento
- F (Estratégico + Fraco): Resgate de Demanda — promoção com prazo fixo
- G (Operacional + Forte): Fechamento Premium — subir preço final, kits premium
- H (Operacional + Estável): Conversão Final — remarketing, melhorar checkout
- I (Operacional + Fraco): Liquidação Controlada — promoção máxima, bundle

Quando mencionar um playbook, explique o estágio, o estado do ISC e as ações concretas sugeridas.

━━━━━━━━━━━━━━━━━━━━
SUAS CAPACIDADES
━━━━━━━━━━━━━━━━━━━━
- Analisar dados de vendas e ISC de todos os eventos
- Identificar eventos críticos (🔴) e oportunidades (🟢)
- Sugerir ações comerciais precisas com base no playbook
- Comparar performance entre eventos
- Alertar sobre regra D-40 e janelas de promoção
- Ajudar com tarefas e lembretes

Fale português brasileiro de forma amigável, entusiasmada e profissional."""


async def analyze_marketing_data(events_data: list) -> str:
    client = get_openai_client()
    
    prompt = f"""Analise estes eventos de forma visual e envolvente!

Dados:
{format_events_for_analysis(events_data)}

Sua análise deve ser:
- Visual e atraente com emojis estratégicos
- Objetiva mas com personalidade
- Começando com uma visão geral impactante
- Destacando eventos críticos (🔴) e destaques positivos (🟢)
- Para cada evento, mencionar o playbook ativo e a primeira ação operacional concreta
- Finalizando com recomendações prioritárias (top 3 ações imediatas)

Use formatação visual, emojis e seja entusiasmado!"""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": NORI_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1200,
            temperature=0.7
        )
        return response.choices[0].message.content
    except RateLimitError:
        raise OpenAIQuotaError("A cota da API OpenAI foi excedida. Verifique os créditos da sua conta OpenAI.")
    except APIError as e:
        raise Exception(f"Erro na API OpenAI: {str(e)}")


async def chat_with_nori(message: str, context: Optional[list] = None, events_data: Optional[list] = None) -> str:
    client = get_openai_client()
    
    messages = [{"role": "system", "content": NORI_SYSTEM_PROMPT}]
    
    if events_data:
        context_message = f"""Dados atuais dos eventos (use como referência para responder):
{format_events_for_analysis(events_data)}"""
        messages.append({"role": "system", "content": context_message})
    
    if context:
        for msg in context[-10:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
    
    messages.append({"role": "user", "content": message})
    
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=900,
            temperature=0.7
        )
        return response.choices[0].message.content
    except RateLimitError:
        raise OpenAIQuotaError("A cota da API OpenAI foi excedida. Verifique os créditos da sua conta OpenAI.")
    except APIError as e:
        raise Exception(f"Erro na API OpenAI: {str(e)}")


def format_events_for_analysis(events: list) -> str:
    if not events:
        return "Nenhum evento disponível"
    
    lines = []
    for event in events:
        isc_status = event.get("iscStatus", "")
        status_emoji = "🟢" if isc_status == "accelerating" else "🟡" if isc_status == "stable" else "🔴"
        status_label = "Forte (acelerando)" if isc_status == "accelerating" else "Estável" if isc_status == "stable" else "Fraco (desacelerando)"

        current = event.get("currentSales", 0)
        goal = max(event.get("salesGoal", 1), 1)
        pct = round(current / goal * 100)

        avg_ticket = event.get("averageTicket", 0)
        budget_ticket = event.get("budgetTicket", 0)
        ticket_diff = avg_ticket - budget_ticket
        ticket_sign = "+" if ticket_diff >= 0 else ""

        comps = event.get("iscComponents") or {}
        ia730 = comps.get("ia730", comps.get("IA730", 0))
        curva = comps.get("curvaDPercent", comps.get("CurvaDPercent", 0))
        rolling = comps.get("rolling14d", comps.get("Rolling14d", 0))

        sa = event.get("suggestedAction") or {}
        pb_letter = sa.get("letter", "?")
        pb_name = sa.get("name", "N/A")
        pb_stage = sa.get("stageName", "N/A")
        pb_isc_label = sa.get("iscLabel", "N/A")
        pb_objective = sa.get("objective", "N/A")
        pb_narrative = sa.get("narrative", "")
        pb_actions = sa.get("actions") or []
        pb_kpis = sa.get("kpis") or []
        pb_cutoffs = sa.get("cutoffs") or []

        actions_str = "\n".join(f"    {i+1}. {a}" for i, a in enumerate(pb_actions)) if pb_actions else "    — sem ações definidas"
        kpis_str = ", ".join(pb_kpis) if pb_kpis else "—"
        cutoffs_str = ", ".join(pb_cutoffs) if pb_cutoffs else "—"

        lines.append(f"""
{status_emoji} EVENTO: {event.get('name', 'N/A')}
  Local: {event.get('location', 'N/A')} | Categoria: {event.get('category', 'N/A')}
  D-: {event.get('dMinus', 'N/A')} dias restantes | D- Inscrições: {event.get('dMinusInscricoes', event.get('dMinus', 'N/A'))} dias
  Vendas: {current:,} / {goal:,} ({pct}%)
  Ticket médio: R${avg_ticket:.0f} | Ticket orçado: R${budget_ticket:.0f} (diferença: {ticket_sign}R${ticket_diff:.0f})

  ISC: {status_emoji} {event.get('isc', 0):.2f} — {status_label}
    IA 7/30: {ia730:.2f} | Curva D-%: {curva:.2f} | Rolling 14d: {rolling:.2f}

  PLAYBOOK ATIVO — {pb_letter}: {pb_name}
    Estágio: {pb_stage}
    ISC: {pb_isc_label}
    Objetivo: {pb_objective}
    Narrativa: {pb_narrative}
    Ações operacionais:
{actions_str}
    KPIs esperados: {kpis_str}
    Pontos de corte: {cutoffs_str}
""")
    
    return "\n".join(lines)


def get_greeting() -> str:
    try:
        br_tz = pytz.timezone('America/Sao_Paulo')
        hour = datetime.now(br_tz).hour
    except:
        hour = datetime.now().hour
    
    if hour < 12:
        greeting = "Bom dia"
    elif hour < 18:
        greeting = "Boa tarde"
    else:
        greeting = "Boa noite"
    
    return f"{greeting}! Eu sou o Nori, seu assistente virtual. Como posso ajudar você hoje?"
