"""
Serviço de consolidação de inscrições em grão fino (Detalhamento de Eventos).

Fluxo:
1. Busca em sku_mappings os IDs de Ativo e Magento para o evento_grupo pedido.
2. Executa as duas queries em paralelo (ThreadPoolExecutor).
3. Concatena e agrega por dimensões comuns + canonical event key.
4. Recalcula ticket_medio = SUM(receita_liquida) / SUM(inscritos).
5. Mantém os result sets brutos por banco para auditoria/cross-validation.

Chave canônica de consolidação:
- Para consulta de evento único (evento_grupo fornecido): agrega por DIM_KEYS apenas,
  permitindo que linhas Ativo e Magento do mesmo evento se fundam por dimensão.
- Para consulta sem filtro (evento_grupo=None): inclui (banco, id_evento) na chave
  para evitar fusão entre eventos diferentes que coincidam em dimensões.

Cache: dict em memória por chave (evento_grupo or "__all__"), TTL 15 min.
"""
from __future__ import annotations

import logging
import time
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple, Any

from sqlalchemy import text
from sqlalchemy.orm import Session

import app.core.database as db_module
from app.models.dimensoes import SkuMapping
from app.queries.detalhe_eventos import build_ativo_detalhe, build_magento_detalhe

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 900  # 15 minutos

_cache: Dict[str, Tuple[float, Any]] = {}
_cache_lock = threading.Lock()

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


def _fetch_magento(ids: Optional[List[int]]) -> Tuple[Optional[List[Dict]], Optional[str]]:
    if db_module.engine_magento is None:
        return None, "Magento não configurado"
    try:
        from app.core.db_retry import magento_run
        sql, params = build_magento_detalhe(ids)
        logger.info(f"[DetalheEventos] Magento query ids={ids}")

        def _work(conn):
            return conn.execute(text(sql), params).fetchall()

        rows = magento_run(_work, label="detalhe-eventos:fetch-magento", profile="request")
        logger.info(f"[DetalheEventos] Magento: {len(rows)} linhas")
        return [_row_to_dict(r) for r in rows], None
    except Exception as e:
        logger.error(f"[DetalheEventos] Magento error: {e}")
        return None, str(e)


# ---------------------------------------------------------------------------
# Consolidação
# ---------------------------------------------------------------------------

def _consolidar(
    rows_ativo: List[Dict],
    rows_magento: List[Dict],
    evento_grupo: Optional[str],
) -> List[Dict]:
    """
    Agrega todas as linhas por DIM_KEYS (+ event identity quando multi-evento).

    Quando evento_grupo é fornecido (query de evento único), agrega apenas por
    DIM_KEYS — isso permite fusão de linhas Ativo+Magento para o mesmo evento.

    Quando evento_grupo é None (consulta global sem filtro), inclui (banco, id_evento)
    na chave para prevenir merge cross-event (eventos distintos que coincidam em
    dimensões devem permanecer separados).
    """
    multi_event_mode = evento_grupo is None

    agg: Dict[tuple, Dict] = {}

    for row in (rows_ativo or []) + (rows_magento or []):
        dim_key = tuple(row.get(k) for k in DIM_KEYS)
        if multi_event_mode:
            # Inclui identidade canônica do evento para evitar cross-event merge
            event_key = (row.get("banco"), row.get("id_evento"))
            key = event_key + dim_key
        else:
            key = dim_key

        if key not in agg:
            agg[key] = {k: row.get(k) for k in DIM_KEYS}
            if multi_event_mode:
                # Preserva informações de evento para o modo global
                agg[key]["evento"] = row.get("evento")
                agg[key]["id_evento"] = row.get("id_evento")
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
    Para cada combinação de DIM_KEYS, verifica se a soma por banco
    coincide com o total consolidado. Retorna lista de divergências.
    """
    by_key_banco: Dict[tuple, Dict[str, Dict]] = defaultdict(dict)

    for row in (rows_ativo or []) + (rows_magento or []):
        key = tuple(row.get(k) for k in DIM_KEYS)
        banco = row.get("banco", "?")
        by_key_banco[key][banco] = row

    divergencias = []
    for rec in consolidado:
        key = tuple(rec.get(k) for k in DIM_KEYS)
        banco_rows = by_key_banco.get(key, {})
        soma_ins = sum(r.get("inscritos", 0) for r in banco_rows.values())
        soma_liq = sum(r.get("receita_liquida", 0.0) for r in banco_rows.values())

        diff_ins = abs(soma_ins - (rec.get("inscritos") or 0))
        diff_liq = abs(soma_liq - (rec.get("receita_liquida") or 0.0))

        if diff_ins > 0 or diff_liq > 0.01:
            divergencias.append({
                "dimensoes": {k: rec.get(k) for k in DIM_KEYS},
                "consolidado_inscritos": rec.get("inscritos"),
                "soma_bancos_inscritos": soma_ins,
                "diff_inscritos": diff_ins,
                "consolidado_receita_liquida": rec.get("receita_liquida"),
                "soma_bancos_receita_liquida": round(soma_liq, 2),
                "diff_receita_liquida": round(diff_liq, 2),
            })
    return divergencias


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
    Usa cache em memória por 15 min.
    """
    cache_key = evento_grupo or "__all__"

    if not force_refresh:
        with _cache_lock:
            entry = _cache.get(cache_key)
        if entry:
            ts, data = entry
            if time.time() - ts < CACHE_TTL_SECONDS:
                logger.debug(f"[DetalheEventos] cache HIT key={cache_key}")
                return data

    ativo_ids: Optional[List[int]] = None
    magento_ids: Optional[List[int]] = None
    evento_nome: Optional[str] = None
    skus: List[str] = []

    if evento_grupo:
        ativo_ids_list, magento_ids_list = get_evento_ids(db, evento_grupo)
        ativo_ids = ativo_ids_list or None
        magento_ids = magento_ids_list or None

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

    with ThreadPoolExecutor(max_workers=2) as executor:
        fut_ativo = executor.submit(_fetch_ativo, ativo_ids)
        fut_magento = executor.submit(_fetch_magento, magento_ids)

        rows_ativo, error_ativo = fut_ativo.result()
        rows_magento, error_magento = fut_magento.result()

    consolidado = _consolidar(rows_ativo or [], rows_magento or [], evento_grupo)
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
    }

    with _cache_lock:
        _cache[cache_key] = (time.time(), payload)

    return payload


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
