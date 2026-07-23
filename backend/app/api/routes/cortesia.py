"""Rotas proxy autenticadas para o app externo de Cortesias.

O token da integração vive apenas no backend (secret CORTESIA_API_TOKEN).
As rotas exigem a mesma permissão de visualização do módulo Projeção de
Inscritos, já que o painel de Cortesias é exibido dentro dessa tela.
"""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.security import require_permission
from ...models.cadastro_evento import CadastroEvento
from ...models.user import Usuario
from ...services import cortesia_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cortesia", tags=["Cortesias"])

PROJECAO_PERMISSION = "projecao_inscritos"

# Concorrência limitada para não martelar a API externa nem esgotar o
# threadpool do próprio worker (o endpoint em lote ocupa UM slot do anyio
# threadpool e roda suas chamadas em threads privadas).
_BATCH_MAX_WORKERS = 10

# Cache negativo curto para SKUs "não encontrados" no app de Cortesias.
# O cache positivo (60s) já vive no service; sem este espelho negativo,
# cada recarga da tela refaria ~dezenas de consultas 404 na API externa.
_NAO_ENCONTRADO_TTL_SECONDS = 60.0
_nao_encontrado_cache: dict = {}  # sku -> (ts, detail)
_nao_encontrado_lock = threading.Lock()

# Single-flight do lote /eventos: enquanto um fan-out externo está em
# andamento, requisições concorrentes AGUARDAM e reutilizam o mesmo
# resultado (sucesso OU erro explícito), em vez de disparar lotes
# paralelos que martelam a API externa (~116 consultas por lote frio).
_LOTE_WAIT_TIMEOUT_SECONDS = 120.0
_lote_cond = threading.Condition()
_lote_inflight = False
_lote_seq = 0  # incrementa a cada lote concluído
_lote_outcome = None  # ("ok", payload) | ("http_error", status, detail)

# Cache curto do payload COMPLETO do lote: dentro da janela, requisições
# reusam o último resultado bem-sucedido sem novo fan-out (~116 consultas
# externas). Apenas sucesso é cacheado — erros continuam explícitos e
# nunca são servidos como se fossem dados válidos. O payload já carrega
# "atualizado_em" para transparência da idade do dado.
_LOTE_CACHE_TTL_SECONDS = 45.0
_lote_cache_payload = None  # último payload "ok"
_lote_cache_ts = 0.0  # time.monotonic() da gravação


def _lote_cache_get():
    """Retorna o payload cacheado se ainda estiver dentro da janela."""
    with _lote_cond:
        if (
            _lote_cache_payload is not None
            and (time.monotonic() - _lote_cache_ts) < _LOTE_CACHE_TTL_SECONDS
        ):
            return _lote_cache_payload
    return None


def _nao_encontrado_get(sku: str) -> Optional[str]:
    now = time.time()
    with _nao_encontrado_lock:
        entry = _nao_encontrado_cache.get(sku)
        if entry and (now - entry[0]) < _NAO_ENCONTRADO_TTL_SECONDS:
            return entry[1]
    return None


def _nao_encontrado_put(sku: str, detail: str):
    now = time.time()
    with _nao_encontrado_lock:
        expired = [k for k, (ts, _d) in _nao_encontrado_cache.items() if now - ts >= _NAO_ENCONTRADO_TTL_SECONDS]
        for k in expired:
            _nao_encontrado_cache.pop(k, None)
        _nao_encontrado_cache[sku] = (now, detail)


@router.get("/metrics")
def get_cortesia_metrics(
    sku: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None, alias="userId"),
    area: Optional[str] = Query(None),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_visualizar")),
):
    filtros = [("sku", sku), ("userId", user_id), ("area", area)]
    informados = [(t, v) for t, v in filtros if v is not None and v.strip()]
    if len(informados) != 1:
        raise HTTPException(
            status_code=400,
            detail="Informe exatamente um filtro: sku, userId ou area.",
        )
    tipo, valor = informados[0]
    return cortesia_service.get_metrics(tipo, valor)


@router.get("/users")
def get_cortesia_users(
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_visualizar")),
):
    return cortesia_service.get_users()


def _executar_lote_eventos(db: Session) -> dict:
    """Executa o lote completo (query PG + fan-out externo) e monta o payload.

    Levanta HTTPException em falha global — o chamador (single-flight)
    propaga o mesmo erro para todos os aguardantes.
    """
    hoje = date.today()
    eventos = (
        db.query(CadastroEvento)
        .filter(
            CadastroEvento.deleted_at.is_(None),
            CadastroEvento.data_evento.isnot(None),
            CadastroEvento.data_evento >= hoje,
            CadastroEvento.sku.isnot(None),
            func.trim(CadastroEvento.sku) != "",
        )
        .order_by(CadastroEvento.data_evento.asc(), CadastroEvento.nome.asc())
        .all()
    )

    # Materializa os dados e libera a conexão PG imediatamente: o fan-out
    # externo abaixo pode levar vários segundos e não precisa do banco —
    # segurar a sessão aqui contribuiria para esgotar o pool local.
    eventos_data = [
        {
            "id": ev.id,
            "nome": ev.nome,
            "data_evento": ev.data_evento,
            "sku": (ev.sku or "").strip(),
            "cidade": ev.cidade,
            "estado": ev.estado,
        }
        for ev in eventos
    ]
    db.close()

    # Dedup por SKU normalizado: eventos que compartilham SKU geram UMA consulta.
    skus_unicos: list[str] = []
    vistos: set = set()
    for ev in eventos_data:
        s = ev["sku"]
        if s and s not in vistos:
            vistos.add(s)
            skus_unicos.append(s)

    # resultado por sku: ("ok", data) | ("nao_encontrado", msg) | ("erro", status, msg) | ("abortado",)
    resultados: dict = {}
    abort = threading.Event()
    state_lock = threading.Lock()
    contagem = {"ok": 0, "nao_encontrado": 0, "falha": 0}
    primeira_falha: dict = {}

    def _consultar(sku: str):
        if abort.is_set():
            return sku, ("abortado",)
        neg = _nao_encontrado_get(sku.lower())
        if neg is not None:
            return sku, ("nao_encontrado", neg)
        try:
            data = cortesia_service.get_metrics("sku", sku)
            return sku, ("ok", data)
        except HTTPException as e:
            detail = e.detail if isinstance(e.detail, str) else "Falha na consulta ao app de Cortesias."
            if e.status_code == 404:
                _nao_encontrado_put(sku.lower(), detail)
                return sku, ("nao_encontrado", detail)
            return sku, ("erro", e.status_code, detail)
        except Exception as e:  # nunca zero silencioso
            logger.error("Cortesia lote: erro inesperado no SKU %s: %s", sku, e)
            return sku, ("erro", 502, "Erro inesperado na consulta ao app de Cortesias.")

    if skus_unicos:
        with ThreadPoolExecutor(max_workers=_BATCH_MAX_WORKERS, thread_name_prefix="cortesia-lote") as ex:
            futures = [ex.submit(_consultar, s) for s in skus_unicos]
            for fut in as_completed(futures):
                sku, res = fut.result()
                resultados[sku] = res
                with state_lock:
                    if res[0] == "ok":
                        contagem["ok"] += 1
                    elif res[0] == "nao_encontrado":
                        contagem["nao_encontrado"] += 1
                    elif res[0] == "erro":
                        contagem["falha"] += 1
                        if not primeira_falha:
                            primeira_falha = {"status": res[1], "detail": res[2]}
                        # Circuito: se as primeiras consultas falharam TODAS
                        # (sem nenhum ok/não-encontrado), a API está fora do ar
                        # ou o token foi recusado — aborta o restante do lote.
                        if (
                            contagem["ok"] == 0
                            and contagem["nao_encontrado"] == 0
                            and contagem["falha"] >= min(8, len(skus_unicos))
                        ):
                            abort.set()

        # Falha global: nenhuma resposta válida de nenhum SKU.
        if contagem["ok"] == 0 and contagem["nao_encontrado"] == 0 and contagem["falha"] > 0:
            raise HTTPException(
                status_code=primeira_falha.get("status", 502),
                detail=primeira_falha.get("detail", "Não foi possível consultar o app de Cortesias."),
            )

    linhas = []
    resumo = {"total": len(eventos_data), "ok": 0, "nao_encontrado": 0, "erro": 0}
    for ev in eventos_data:
        sku = ev["sku"]
        res = resultados.get(sku) or ("erro", 502, "Consulta não concluída. Tente novamente.")
        linha = {
            "evento_id": ev["id"],
            "nome": ev["nome"],
            "data_evento": ev["data_evento"].isoformat() if ev["data_evento"] else None,
            "sku": sku,
            "cidade": ev["cidade"],
            "estado": ev["estado"],
        }
        if res[0] == "ok":
            data = res[1]
            linha["status"] = "ok"
            linha["solicitados"] = data.get("solicitados")
            linha["aprovados"] = data.get("aprovados")
            linha["utilizados"] = data.get("utilizados")
            linha["disponiveis"] = data.get("disponiveis")
            # Infos extras da API externa (tolerantes a ausência — a resposta
            # já foi validada como métrica; label/source são complementares):
            #   nome_externo -> filter.label (nome do evento no app de Cortesias)
            #   fonte        -> source ("magento" | "local")
            filtro = data.get("filter")
            label = filtro.get("label") if isinstance(filtro, dict) else None
            linha["nome_externo"] = label.strip() if isinstance(label, str) and label.strip() else None
            fonte = data.get("source")
            linha["fonte"] = fonte.strip() if isinstance(fonte, str) and fonte.strip() else None
            resumo["ok"] += 1
        elif res[0] == "nao_encontrado":
            linha["status"] = "nao_encontrado"
            linha["mensagem"] = res[1] or "Evento não cadastrado no app de Cortesias."
            resumo["nao_encontrado"] += 1
        else:
            linha["status"] = "erro"
            linha["mensagem"] = (
                res[2] if len(res) >= 3 else "Consulta não concluída. Tente novamente."
            )
            resumo["erro"] += 1
        linhas.append(linha)

    return {
        "eventos": linhas,
        "resumo": resumo,
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/eventos")
def get_cortesia_eventos(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_visualizar")),
):
    """Lista eventos futuros com SKU e seus 4 números de cortesias (consulta por SKU).

    Uma linha por evento com status explícito:
      - ok             -> métricas presentes
      - nao_encontrado -> SKU ainda não cadastrado no app de Cortesias
      - erro           -> falha na consulta daquele SKU (mensagem na linha)

    Falha global (token recusado / API fora do ar): se NENHUM SKU responder
    (nem ok, nem nao_encontrado), o endpoint devolve o erro HTTP explícito
    em vez de linhas todas marcadas como erro — o frontend mostra banner.

    Single-flight por processo: se um lote já está em andamento, esta
    requisição AGUARDA e reutiliza o mesmo resultado (sucesso ou erro),
    em vez de disparar um fan-out externo paralelo.
    """
    global _lote_inflight, _lote_seq, _lote_outcome, _lote_cache_payload, _lote_cache_ts

    cortesia_service.ensure_configured()

    # Reuso rápido: se há um payload de sucesso recente, devolve direto
    # sem novo fan-out. "atualizado_em" no payload informa a idade do dado.
    cached = _lote_cache_get()
    if cached is not None:
        return cached

    with _lote_cond:
        if _lote_inflight:
            # Já há um lote em andamento: aguarda o resultado dele.
            seq_inicial = _lote_seq
            deadline = time.monotonic() + _LOTE_WAIT_TIMEOUT_SECONDS
            while _lote_inflight and _lote_seq == seq_inicial:
                restante = deadline - time.monotonic()
                if restante <= 0:
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            "Consulta ao app de Cortesias em andamento demorou demais. "
                            "Tente novamente em instantes."
                        ),
                    )
                _lote_cond.wait(timeout=restante)
            if _lote_seq != seq_inicial and _lote_outcome is not None:
                outcome = _lote_outcome
                if outcome[0] == "ok":
                    return outcome[1]
                # Erro explícito do lote compartilhado — nunca zeros silenciosos.
                raise HTTPException(status_code=outcome[1], detail=outcome[2])
            # Acordou sem resultado utilizável (caso raro): vira líder abaixo.
        _lote_inflight = True

    # Líder: executa o lote fora do lock.
    try:
        payload = _executar_lote_eventos(db)
        outcome = ("ok", payload)
    except HTTPException as e:
        detail = e.detail if isinstance(e.detail, str) else "Não foi possível consultar o app de Cortesias."
        outcome = ("http_error", e.status_code, detail)
    except Exception as e:
        logger.error("Cortesia lote: erro inesperado no fan-out: %s", e)
        outcome = ("http_error", 502, "Erro inesperado na consulta ao app de Cortesias.")
    finally:
        with _lote_cond:
            _lote_inflight = False
            _lote_seq += 1
            _lote_outcome = outcome if "outcome" in locals() else None
            if _lote_outcome is not None and _lote_outcome[0] == "ok":
                # Só sucesso entra no cache — erro nunca é servido como dado.
                _lote_cache_payload = _lote_outcome[1]
                _lote_cache_ts = time.monotonic()
            _lote_cond.notify_all()

    if outcome[0] == "ok":
        return outcome[1]
    raise HTTPException(status_code=outcome[1], detail=outcome[2])
