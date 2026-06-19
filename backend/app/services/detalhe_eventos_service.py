"""
Serviço de consolidação de inscrições em grão fino (Detalhamento de Eventos).

Fluxo:
1. Busca em sku_mappings os IDs de Ativo e Magento para o evento_grupo pedido.
2. Executa as duas queries em paralelo (ThreadPoolExecutor).
3. Concatena e agrega por dimensões comuns + canonical event key.
4. Recalcula ticket_medio = SUM(receita_liquida) / SUM(inscritos).
5. Mantém os result sets brutos por banco para auditoria/cross-validation.

Snapshot noturno:
- get_detalhe() lê do snapshot PostgreSQL (< 1s) se atualizado há < 26h.
- force_refresh=True ou snapshot ausente disparam query ao vivo e regravação.
- save_snapshot() persiste o payload após query ao vivo.

Chave canônica de consolidação:
- Cada linha raw é enriquecida com `canonical_grupo` = evento_grupo resolvido via
  mapa reverso sku_mappings: (fonte.upper(), id_externo) → evento_grupo.
- A consolidação sempre agrega por (canonical_grupo, DIM_KEYS), o que garante:
  * Linhas Ativo e Magento do MESMO evento canônico se fundem por dimensão.
  * Eventos distintos que coincidam em dimensões NUNCA são fundidos.
- Isso funciona tanto para query de evento único quanto para query global sem filtro.

Cache: dict em memória por chave (evento_grupo or "__all__"), TTL 15 min.
"""
from __future__ import annotations

import json
import logging
import time
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any

from sqlalchemy import text
from sqlalchemy.orm import Session

import app.core.database as db_module
from app.models.dimensoes import SkuMapping
from app.queries.detalhe_eventos import build_ativo_detalhe, build_magento_detalhe

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 900  # 15 minutos
SNAPSHOT_MAX_AGE_HOURS = 26  # snapshot válido por 26h

_cache: Dict[str, Tuple[float, Any]] = {}
_cache_lock = threading.Lock()

# Single-flight guard para force_refresh ao vivo.
# Impede que dois usuários simultâneos disparem queries pesadas ao Ativo/Magento
# para o mesmo evento_grupo ao mesmo tempo. O segundo recebe HTTP 429.
_inflight: set = set()
_inflight_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Contrato de colunas
# ---------------------------------------------------------------------------

COLUMNS = [
    "banco", "id_evento", "evento", "canal", "kit", "distancia",
    "modalidade", "pelotao", "produtos", "tamanho_camiseta",
    "inscritos", "receita_bruta", "receita_liquida", "ticket_medio",
]

DIM_KEYS = ["canal", "kit", "distancia", "modalidade", "pelotao", "produtos", "tamanho_camiseta"]


def _row_to_dict(row) -> Dict:
    d = {}
    for i, col in enumerate(COLUMNS):
        val = row[i]
        if col == "inscritos":
            val = int(val) if val is not None else 0
        elif col in ("receita_bruta", "receita_liquida", "ticket_medio"):
            val = float(val) if val is not None else 0.0
        elif val is not None:
            val = str(val)
        d[col] = val
    return d


# ---------------------------------------------------------------------------
# Resolução de IDs via sku_mappings
# ---------------------------------------------------------------------------

def get_evento_ids(db: Session, evento_grupo: str) -> Tuple[List[int], List[int]]:
    """Retorna (ativo_ids, magento_ids) para o evento_grupo."""
    mappings = (
        db.query(SkuMapping)
        .filter(SkuMapping.evento_grupo == evento_grupo, SkuMapping.ativo == True)
        .all()
    )
    ativo_ids = [m.id_externo for m in mappings if m.fonte == "ATIVO" and m.id_externo]
    magento_ids = [m.id_externo for m in mappings if m.fonte == "MAGENTO" and m.id_externo]
    return ativo_ids, magento_ids


def list_eventos_disponiveis(db: Session) -> List[Dict]:
    """
    Lista todos os evento_grupos com pelo menos um mapeamento ativo.
    Retorna nome canônico, evento_grupo (chave SKU), IDs por banco e anos.
    """
    mappings = (
        db.query(SkuMapping)
        .filter(SkuMapping.ativo == True, SkuMapping.evento_grupo != None)
        .order_by(SkuMapping.evento_grupo, SkuMapping.ano.desc())
        .all()
    )

    grupos: Dict[str, Dict] = {}
    for m in mappings:
        eg = m.evento_grupo
        if not eg:
            continue
        if eg not in grupos:
            grupos[eg] = {
                "evento_grupo": eg,
                "nome_evento": m.nome_evento or eg,
                "ativo_ids": [],
                "magento_ids": [],
                "skus": [],
                "anos": set(),
            }
        g = grupos[eg]
        if m.nome_evento and len(m.nome_evento) > len(g["nome_evento"]):
            g["nome_evento"] = m.nome_evento
        if m.fonte == "ATIVO" and m.id_externo and m.id_externo not in g["ativo_ids"]:
            g["ativo_ids"].append(m.id_externo)
        elif m.fonte == "MAGENTO" and m.id_externo and m.id_externo not in g["magento_ids"]:
            g["magento_ids"].append(m.id_externo)
        if m.sku and m.sku not in g["skus"]:
            g["skus"].append(m.sku)
        if m.ano:
            g["anos"].add(m.ano)

    result = []
    for g in grupos.values():
        g["anos"] = sorted(g["anos"], reverse=True)
        result.append(g)
    result.sort(key=lambda x: x["nome_evento"] or "")
    return result


# ---------------------------------------------------------------------------
# Fetch individual por banco (usa bind params via SQLAlchemy text())
# ---------------------------------------------------------------------------

def _fetch_ativo(ids: Optional[List[int]]) -> Tuple[Optional[List[Dict]], Optional[str]]:
    """
    ids=None  → query sem filtro (modo global sem evento_grupo selecionado)
    ids=[]    → evento selecionado mas sem IDs Ativo → retorna vazio, NÃO executa query
    ids=[...] → filtra pelos IDs fornecidos
    """
    if isinstance(ids, list) and len(ids) == 0:
        logger.info("[DetalheEventos] Ativo: nenhum ID para este evento_grupo, retornando vazio")
        return [], None
    if db_module.engine_ssh is None:
        return None, "SSH tunnel não configurado"
    try:
        sql, params = build_ativo_detalhe(ids)
        logger.info(f"[DetalheEventos] Ativo query ids={ids}")
        with db_module.engine_ssh.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        logger.info(f"[DetalheEventos] Ativo: {len(rows)} linhas")
        return [_row_to_dict(r) for r in rows], None
    except Exception as e:
        logger.error(f"[DetalheEventos] Ativo error: {e}")
        return None, str(e)


def _fetch_magento(
    ids: Optional[List[int]],
    profile: str = "request",
) -> Tuple[Optional[List[Dict]], Optional[str]]:
    """
    ids=None  → query sem filtro (modo global sem evento_grupo selecionado)
    ids=[]    → evento selecionado mas sem IDs Magento → retorna vazio, NÃO executa query
    ids=[...] → filtra pelos IDs fornecidos

    profile: "request" (padrão, para clicks de usuário — 2 tentativas, backoff curto)
             "background" (para batch noturno — 3 tentativas, backoff maior)
    """
    if isinstance(ids, list) and len(ids) == 0:
        logger.info("[DetalheEventos] Magento: nenhum ID para este evento_grupo, retornando vazio")
        return [], None
    if db_module.engine_magento is None:
        return None, "Magento não configurado"
    try:
        from app.core.db_retry import magento_run
        sql, params = build_magento_detalhe(ids)
        logger.info(f"[DetalheEventos] Magento query ids={ids} profile={profile}")

        def _work(conn):
            return conn.execute(text(sql), params).fetchall()

        rows = magento_run(_work, label="detalhe-eventos:fetch-magento", profile=profile)
        logger.info(f"[DetalheEventos] Magento: {len(rows)} linhas")
        return [_row_to_dict(r) for r in rows], None
    except Exception as e:
        logger.error(f"[DetalheEventos] Magento error: {e}")
        return None, str(e)


# ---------------------------------------------------------------------------
# Consolidação
# ---------------------------------------------------------------------------

def _build_canonical_map(db: Session) -> Dict[Tuple[str, int], str]:
    """
    Constrói mapa reverso (fonte.upper(), id_externo) → evento_grupo
    a partir de sku_mappings ativos.

    Utilizado para resolver a identidade canônica de cada linha raw
    retornada pelo Ativo/Magento antes de consolidar — garantindo que
    linhas de bancos diferentes que representam o MESMO evento se fundam
    pela chave canônica, não pelo id_externo individual.
    """
    mappings = (
        db.query(SkuMapping)
        .filter(SkuMapping.ativo == True, SkuMapping.evento_grupo != None)
        .all()
    )
    result: Dict[Tuple[str, int], str] = {}
    for m in mappings:
        if m.id_externo and m.fonte and m.evento_grupo:
            key = (m.fonte.upper(), int(m.id_externo))
            result[key] = m.evento_grupo
    return result


def _tag_canonical_grupo(
    rows: List[Dict],
    canonical_map: Dict[Tuple[str, int], str],
    default_grupo: Optional[str],
) -> None:
    """
    Enriquece cada linha in-place com `canonical_grupo` resolvido a partir do
    mapa reverso de sku_mappings. Quando não encontrado, usa `default_grupo`
    (evento_grupo da query, se for query de evento único) ou fallback
    para 'banco:id_evento' garantindo isolamento mínimo.
    """
    for row in rows:
        banco = (row.get("banco") or "").upper()
        id_ev = row.get("id_evento")
        try:
            id_ev_int = int(id_ev) if id_ev is not None else None
        except (ValueError, TypeError):
            id_ev_int = None

        resolved: Optional[str] = None
        if id_ev_int is not None:
            resolved = canonical_map.get((banco, id_ev_int))
        if resolved is None:
            resolved = default_grupo
        if resolved is None:
            # Último fallback: isolamento por banco+id evita cross-event merge
            resolved = f"__raw__{banco}_{id_ev}"
        row["canonical_grupo"] = resolved


def _consolidar(
    rows_ativo: List[Dict],
    rows_magento: List[Dict],
) -> List[Dict]:
    """
    Agrega todas as linhas por (canonical_grupo, DIM_KEYS).

    canonical_grupo é resolvido previamente via _tag_canonical_grupo() usando
    o mapa reverso de sku_mappings. Isso garante:
    - Linhas Ativo e Magento do MESMO evento canônico se fundem por dimensão.
    - Eventos distintos que coincidam em dimensões nunca são fundidos,
      independentemente de a query ser de evento único ou global sem filtro.
    """
    agg: Dict[tuple, Dict] = {}

    for row in (rows_ativo or []) + (rows_magento or []):
        canonical = row.get("canonical_grupo") or "__unknown__"
        dim_key = tuple(row.get(k) for k in DIM_KEYS)
        key = (canonical,) + dim_key

        if key not in agg:
            agg[key] = {k: row.get(k) for k in DIM_KEYS}
            agg[key]["canonical_grupo"] = canonical
            agg[key]["evento"] = row.get("evento")
            agg[key]["inscritos"] = 0
            agg[key]["receita_bruta"] = 0.0
            agg[key]["receita_liquida"] = 0.0
            agg[key]["bancos"] = []

        agg[key]["inscritos"] += row.get("inscritos") or 0
        agg[key]["receita_bruta"] += row.get("receita_bruta") or 0.0
        agg[key]["receita_liquida"] += row.get("receita_liquida") or 0.0

        banco = row.get("banco")
        if banco and banco not in agg[key]["bancos"]:
            agg[key]["bancos"].append(banco)

    consolidated = []
    for rec in agg.values():
        ins = rec["inscritos"]
        rec_liq = rec["receita_liquida"]
        rec["ticket_medio"] = round(rec_liq / ins, 2) if ins else 0.0
        rec["receita_bruta"] = round(rec["receita_bruta"], 2)
        rec["receita_liquida"] = round(rec_liq, 2)
        consolidated.append(rec)

    consolidated.sort(key=lambda r: (
        r.get("canal") or "",
        r.get("kit") or "",
        r.get("distancia") or "",
        -(r.get("inscritos") or 0),
    ))
    return consolidated


def _check_divergencias(
    consolidado: List[Dict],
    rows_ativo: List[Dict],
    rows_magento: List[Dict],
) -> List[Dict]:
    """
    Para cada combinação (canonical_grupo + DIM_KEYS), verifica se a soma
    das linhas brutas por banco coincide com o total consolidado.

    Agrega por (canonical_grupo, DIM_KEYS, banco) via SUM para evitar
    false-divergence quando múltiplos IDs do mesmo banco compartilham
    as mesmas dimensões (ex: dois IDs Ativo no mesmo evento).
    """
    # Acumula totais por (canonical_grupo, *DIM_KEYS, banco)
    bank_sums: Dict[tuple, Dict[str, float]] = defaultdict(lambda: {"inscritos": 0.0, "receita_liquida": 0.0})

    for row in (rows_ativo or []) + (rows_magento or []):
        canonical = row.get("canonical_grupo") or "__unknown__"
        agg_key = (canonical,) + tuple(row.get(k) for k in DIM_KEYS)
        banco = row.get("banco", "?")
        slot_key = agg_key + (banco,)
        bank_sums[slot_key]["inscritos"] += row.get("inscritos") or 0
        bank_sums[slot_key]["receita_liquida"] += row.get("receita_liquida") or 0.0

    # Para cada linha consolidada, soma todos os bancos sob a mesma chave canônica
    divergencias = []
    for rec in consolidado:
        canonical = rec.get("canonical_grupo") or "__unknown__"
        agg_key = (canonical,) + tuple(rec.get(k) for k in DIM_KEYS)

        soma_ins = 0.0
        soma_liq = 0.0
        for slot_key, totals in bank_sums.items():
            # slot_key = (canonical, *DIM_KEYS, banco) — prefix must match agg_key
            if slot_key[:len(agg_key)] == agg_key:
                soma_ins += totals["inscritos"]
                soma_liq += totals["receita_liquida"]

        diff_ins = abs(soma_ins - (rec.get("inscritos") or 0))
        diff_liq = abs(soma_liq - (rec.get("receita_liquida") or 0.0))

        if diff_ins > 0.5 or diff_liq > 0.01:
            divergencias.append({
                "dimensoes": {k: rec.get(k) for k in DIM_KEYS},
                "consolidado_inscritos": rec.get("inscritos"),
                "soma_bancos_inscritos": int(soma_ins),
                "diff_inscritos": int(diff_ins),
                "consolidado_receita_liquida": rec.get("receita_liquida"),
                "soma_bancos_receita_liquida": round(soma_liq, 2),
                "diff_receita_liquida": round(diff_liq, 2),
            })
    return divergencias


# ---------------------------------------------------------------------------
# Snapshot PostgreSQL (leitura / escrita)
# ---------------------------------------------------------------------------

def _read_snapshot(db: Session, evento_grupo: str) -> Optional[Tuple[Dict, datetime]]:
    """
    Lê o snapshot do PostgreSQL para o evento_grupo.
    Retorna (payload_dict, updated_at) se válido (< SNAPSHOT_MAX_AGE_HOURS), None caso contrário.
    """
    try:
        from app.models.vendas_snapshot import DetalheEventosSnapshot
        row = (
            db.query(DetalheEventosSnapshot)
            .filter(DetalheEventosSnapshot.evento_grupo == evento_grupo)
            .first()
        )
        if row is None:
            return None
        # Verifica idade
        now_utc = datetime.now(timezone.utc)
        updated = row.updated_at
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        age_h = (now_utc - updated).total_seconds() / 3600
        if age_h > SNAPSHOT_MAX_AGE_HOURS:
            logger.debug(f"[DetalheSnap] snapshot de '{evento_grupo}' tem {age_h:.1f}h — ignorando (>{SNAPSHOT_MAX_AGE_HOURS}h)")
            return None
        payload_dict = json.loads(row.payload)
        return payload_dict, updated
    except Exception as e:
        logger.warning(f"[DetalheSnap] Erro ao ler snapshot de '{evento_grupo}': {e}")
        return None


def save_snapshot(db: Session, evento_grupo: str, payload: Dict) -> bool:
    """
    Persiste o payload no snapshot PostgreSQL via UPSERT.
    Retorna True em sucesso, False em falha (não lança).
    """
    try:
        from app.models.vendas_snapshot import DetalheEventosSnapshot
        payload_json = json.dumps(payload, ensure_ascii=False, default=str)
        now_utc = datetime.now(timezone.utc)

        existing = (
            db.query(DetalheEventosSnapshot)
            .filter(DetalheEventosSnapshot.evento_grupo == evento_grupo)
            .first()
        )
        if existing:
            existing.payload = payload_json
            existing.updated_at = now_utc
        else:
            db.add(DetalheEventosSnapshot(
                evento_grupo=evento_grupo,
                payload=payload_json,
                created_at=now_utc,
                updated_at=now_utc,
            ))
        db.commit()
        logger.info(f"[DetalheSnap] Snapshot salvo para '{evento_grupo}'")
        return True
    except Exception as e:
        logger.error(f"[DetalheSnap] Erro ao salvar snapshot de '{evento_grupo}': {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# API pública do serviço
# ---------------------------------------------------------------------------

def get_detalhe(
    db: Session,
    evento_grupo: Optional[str],
    force_refresh: bool = False,
) -> Dict:
    """
    Retorna o payload completo de detalhamento para o evento_grupo.

    Ordem de leitura:
    1. Cache em memória (TTL 15min) — bypass se force_refresh.
    2. Snapshot PostgreSQL (< SNAPSHOT_MAX_AGE_HOURS) — bypass se force_refresh.
    3. Query ao vivo (Ativo + Magento) — salva no snapshot e no cache.

    Campos adicionais no retorno:
    - source: "cache" | "snapshot" | "live"
    - snapshot_updated_at: ISO string com data/hora do snapshot (None se ao vivo sem snapshot prévio)
    """
    cache_key = evento_grupo or "__all__"

    if not force_refresh:
        # 1. Cache em memória
        with _cache_lock:
            entry = _cache.get(cache_key)
        if entry:
            ts, data = entry
            if time.time() - ts < CACHE_TTL_SECONDS:
                logger.debug(f"[DetalheEventos] cache HIT key={cache_key}")
                return data

        # 2. Snapshot PostgreSQL (apenas para evento único — não faz sentido para "__all__")
        if evento_grupo:
            snap = _read_snapshot(db, evento_grupo)
            if snap is not None:
                payload_dict, updated_at = snap
                payload_dict["source"] = "snapshot"
                payload_dict["snapshot_updated_at"] = updated_at.isoformat()
                with _cache_lock:
                    _cache[cache_key] = (time.time(), payload_dict)
                logger.info(f"[DetalheSnap] Servindo snapshot de '{evento_grupo}' (atualizado {updated_at.isoformat()})")
                return payload_dict

    # 3. Query ao vivo — single-flight guard.
    # Quando force_refresh=True e outro request já está executando as queries
    # pesadas para o mesmo evento_grupo, retorna 429 para evitar sobrecarga
    # simultânea no túnel SSH e no pool PostgreSQL local.
    if force_refresh and evento_grupo:
        from fastapi import HTTPException
        with _inflight_lock:
            if cache_key in _inflight:
                logger.info(
                    f"[DetalheEventos] force_refresh bloqueado para '{evento_grupo}' — "
                    "já há uma consulta ao vivo em andamento (single-flight)"
                )
                raise HTTPException(
                    status_code=429,
                    detail=(
                        "Outro usuário está atualizando este evento — "
                        "tente em alguns instantes."
                    ),
                )
            _inflight.add(cache_key)

    try:
        ativo_ids: Optional[List[int]] = None
        magento_ids: Optional[List[int]] = None
        evento_nome: Optional[str] = None
        skus: List[str] = []

        if evento_grupo:
            ativo_ids_list, magento_ids_list = get_evento_ids(db, evento_grupo)

            # IMPORTANT: keep empty list as [] — do NOT convert to None.
            # _fetch_ativo/magento(ids=[]) → returns empty rows immediately.
            # _fetch_ativo/magento(ids=None) → unfiltered full-year query (global mode only).
            # Converting [] to None would silently run full-year queries for an event
            # that simply has no IDs registered for one bank.
            ativo_ids = ativo_ids_list      # [] or [id, ...]
            magento_ids = magento_ids_list  # [] or [id, ...]

            # Reject unknown evento_grupo: if BOTH banks have zero IDs, the group
            # doesn't exist (or has no active mappings). Raise explicitly.
            if len(ativo_ids) == 0 and len(magento_ids) == 0:
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=404,
                    detail=f"evento_grupo '{evento_grupo}' não encontrado ou sem mapeamentos ativos em sku_mappings.",
                )

            mapping = (
                db.query(SkuMapping)
                .filter(SkuMapping.evento_grupo == evento_grupo, SkuMapping.ativo == True)
                .first()
            )
            if mapping:
                evento_nome = mapping.nome_evento
                skus_q = (
                    db.query(SkuMapping.sku)
                    .filter(SkuMapping.evento_grupo == evento_grupo, SkuMapping.ativo == True)
                    .all()
                )
                skus = [s[0] for s in skus_q if s[0]]

        rows_ativo: Optional[List[Dict]] = None
        rows_magento: Optional[List[Dict]] = None
        error_ativo: Optional[str] = None
        error_magento: Optional[str] = None

        # Build canonical map BEFORE fetching (lightweight PG query)
        canonical_map = _build_canonical_map(db)

        with ThreadPoolExecutor(max_workers=2) as executor:
            fut_ativo = executor.submit(_fetch_ativo, ativo_ids)
            fut_magento = executor.submit(_fetch_magento, magento_ids)

            rows_ativo, error_ativo = fut_ativo.result()
            rows_magento, error_magento = fut_magento.result()

        # Tag each row with its canonical_grupo before consolidating
        _tag_canonical_grupo(rows_ativo or [], canonical_map, evento_grupo)
        _tag_canonical_grupo(rows_magento or [], canonical_map, evento_grupo)

        consolidado = _consolidar(rows_ativo or [], rows_magento or [])
        divergencias = _check_divergencias(consolidado, rows_ativo or [], rows_magento or [])

        payload = {
            "evento_grupo": evento_grupo,
            "nome_evento": evento_nome,
            "skus": skus,
            "consolidado": consolidado,
            "por_banco": {
                "Ativo": rows_ativo or [],
                "Magento": rows_magento or [],
            },
            "divergencias": divergencias,
            "erros": {
                k: v for k, v in [("Ativo", error_ativo), ("Magento", error_magento)] if v
            },
            "totais": _calc_totais(consolidado),
            "source": "live",
            "snapshot_updated_at": None,
        }

        # Salva no snapshot PostgreSQL (apenas evento único, sem erros graves)
        if evento_grupo and not (error_ativo and error_magento):
            snap_saved = save_snapshot(db, evento_grupo, payload)
            if snap_saved:
                payload["snapshot_updated_at"] = datetime.now(timezone.utc).isoformat()

        with _cache_lock:
            _cache[cache_key] = (time.time(), payload)

        return payload

    finally:
        # Libera o slot de single-flight (se foi adquirido) independente de sucesso ou erro.
        if force_refresh and evento_grupo:
            with _inflight_lock:
                _inflight.discard(cache_key)


def _calc_totais(consolidado: List[Dict]) -> Dict:
    total_ins = sum(r.get("inscritos") or 0 for r in consolidado)
    total_bruta = sum(r.get("receita_bruta") or 0.0 for r in consolidado)
    total_liq = sum(r.get("receita_liquida") or 0.0 for r in consolidado)
    ticket = round(total_liq / total_ins, 2) if total_ins else 0.0

    por_canal: Dict[str, Dict] = {}
    for r in consolidado:
        canal = r.get("canal") or "—"
        if canal not in por_canal:
            por_canal[canal] = {"inscritos": 0, "receita_liquida": 0.0}
        por_canal[canal]["inscritos"] += r.get("inscritos") or 0
        por_canal[canal]["receita_liquida"] += r.get("receita_liquida") or 0.0

    return {
        "inscritos": total_ins,
        "receita_bruta": round(total_bruta, 2),
        "receita_liquida": round(total_liq, 2),
        "ticket_medio": ticket,
        "por_canal": por_canal,
    }


def invalidate_cache(evento_grupo: Optional[str] = None) -> None:
    with _cache_lock:
        if evento_grupo:
            _cache.pop(evento_grupo, None)
        else:
            _cache.clear()
