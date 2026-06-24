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
import re
import time
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any

from sqlalchemy import text
from sqlalchemy.orm import Session

import app.core.database as db_module
from app.models.dimensoes import SkuMapping, ModalidadeAlias
from app.models.kit_config import KitConfig
from app.models.kit_mapping_snapshot import KitMappingSnapshot
from app.queries.detalhe_eventos import build_ativo_detalhe, build_magento_detalhe

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 900  # 15 minutos
SNAPSHOT_MAX_AGE_HOURS = 26  # snapshot válido por 26h

_cache: Dict[str, Tuple[float, Any]] = {}
_cache_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Cache de aliases de modalidade
# ---------------------------------------------------------------------------

_alias_map: Dict[str, str] = {}
_alias_map_lock = threading.Lock()
_alias_map_loaded: bool = False


def _load_alias_map(db: Session) -> Dict[str, str]:
    global _alias_map, _alias_map_loaded
    rows = db.query(ModalidadeAlias).all()
    result = {r.raw_value: r.canonical_value for r in rows}
    with _alias_map_lock:
        _alias_map = result
        _alias_map_loaded = True
    return result


def _get_alias_map(db: Session) -> Dict[str, str]:
    with _alias_map_lock:
        if _alias_map_loaded:
            return dict(_alias_map)
    return _load_alias_map(db)


def invalidate_alias_cache() -> None:
    global _alias_map_loaded
    with _alias_map_lock:
        _alias_map.clear()
        _alias_map_loaded = False


def _normalize_modalidade(val: Optional[str], alias_map: Dict[str, str]) -> Optional[str]:
    """Normaliza o valor bruto de modalidade em 5 passos:
    1. Strip + colapsar espaços internos.
    2. Lookup no alias_map pelo valor bruto (override manual).
    3. Regex: padrões numérico+k/km → '<N>km' (ex: '5K', '5 km', '5Km' → '5km').
    4. Lowercase.
    5. Segundo lookup no alias_map pelo valor já normalizado.
    """
    if not val:
        return val
    v = " ".join(val.strip().split())
    if v in alias_map:
        return alias_map[v]
    v = re.sub(r"(\d+)\s*[Kk][Mm]?", lambda m: f"{m.group(1)}km", v)
    v = v.lower()
    if v in alias_map:
        return alias_map[v]
    return v


# Single-flight guard para force_refresh ao vivo.
# Impede que dois usuários simultâneos disparem queries pesadas ao Ativo/Magento
# para o mesmo evento_grupo ao mesmo tempo. O segundo recebe HTTP 429.
_inflight: set = set()
_inflight_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Contrato de colunas
# ---------------------------------------------------------------------------

COLUMNS = [
    "banco", "id_evento", "evento", "canal", "kit", "modalidade",
    "pelotao", "produtos", "tamanho_camiseta",
    "inscritos", "receita_bruta", "receita_liquida", "ticket_medio",
]

DIM_KEYS = ["canal", "kit", "modalidade", "pelotao", "produtos", "tamanho_camiseta"]


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
    """
    Retorna (ativo_ids, magento_ids) para o evento_grupo, filtrando pelo ano-competência corrente.

    O campo SkuMapping.ano representa o ano da edição do evento.
    Filtrar por YEAR(CURDATE()) evita somar pedidos de edições anteriores que
    compartilham o mesmo evento_grupo (ex.: Troféu Brasil 2025 + 2026).
    Mapeamentos sem ano (nullable historicamente) são conservados via OR IS NULL.
    """
    from datetime import date as _date
    current_year = _date.today().year
    mappings = (
        db.query(SkuMapping)
        .filter(
            SkuMapping.evento_grupo == evento_grupo,
            SkuMapping.ativo == True,
            (SkuMapping.ano == current_year) | (SkuMapping.ano == None),
        )
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

    from datetime import date as _date
    _current_year = _date.today().year

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
        # Exibe apenas IDs do ano corrente (ou sem ano cadastrado) no header.
        # O campo "anos" acumula todos os anos para o label do dropdown.
        _is_current = (m.ano is None or m.ano == _current_year)
        if _is_current and m.fonte == "ATIVO" and m.id_externo and m.id_externo not in g["ativo_ids"]:
            g["ativo_ids"].append(m.id_externo)
        elif _is_current and m.fonte == "MAGENTO" and m.id_externo and m.id_externo not in g["magento_ids"]:
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

        t0 = time.time()

        def _work(conn):
            return conn.execute(text(sql), params).fetchall()

        rows = magento_run(_work, label="detalhe-eventos:fetch-magento", profile=profile)
        elapsed_ms = int((time.time() - t0) * 1000)
        dicts = [_row_to_dict(r) for r in rows]
        logger.info(
            f"[DetalheEventos] Magento: {len(dicts)} linhas em {elapsed_ms}ms "
            f"(limit=90000ms ids={ids})"
        )
        # Validation helper: log presence of shirt/produto columns in first row
        if dicts:
            first = dicts[0]
            shirt_val = first.get("tamanho_camiseta")
            prod_val = first.get("produtos")
            logger.info(
                f"[DetalheEventos] Magento colunas spot-check — "
                f"tamanho_camiseta={'presente' if shirt_val is not None else 'null/ausente'} "
                f"produtos={'presente' if prod_val is not None else 'null/ausente'}"
            )
        return dicts, None
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
        r.get("modalidade") or "",
        -(r.get("inscritos") or 0),
    ))
    return consolidated


# ---------------------------------------------------------------------------
# Canonicalização de nomes de kit via KitConfig.tipo_kit
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Regras de normalização de nomes brutos de kit (aplicadas como fallback
# quando o kit NÃO tem tipo_kit configurado no kit_config).
#
# Formato: lista de tuplas (regex_pattern, substituição).
# - A primeira regra que casar é aplicada; as demais são ignoradas.
# - Use grupos de captura (\1, \2…) na substituição quando precisar
#   preservar parte do nome original.
# - Para adicionar um novo padrão: inclua uma nova tupla ANTES do
#   comentário "# ── fim das regras ──" abaixo.
# ---------------------------------------------------------------------------
_KIT_NAME_PATTERNS: list = [
    # "DESCONTO PARA GRUPOS - 159,99" / "- 169.99" etc. → "Desconto Grupo"
    (r"(?i)^desconto\s+para\s+grupos?\s*[-–]\s*[\d.,]+\s*$", "Desconto Grupo"),
    # "DESCONTO PARA GRUPOS - CORTESIA" → "Desconto Grupo - Cortesia"
    (r"(?i)^desconto\s+para\s+grupos?\s*[-–]\s*cortesia\s*$", "Desconto Grupo - Cortesia"),
    # "DESCONTO PARA GRUPOS - PARTICIPAÇÃO" / "- PARTICIPACAO" → "Desconto Grupo - Participação"
    (r"(?i)^desconto\s+para\s+grupos?\s*[-–]\s*participa[cç][aã]o\s*$", "Desconto Grupo - Participação"),
    # "DESCONTO PARA GRUPOS - <outro sufixo>" → "Desconto Grupo - <sufixo capitalizado>"
    (r"(?i)^desconto\s+para\s+grupos?\s*[-–]\s*(.+)$", r"Desconto Grupo - \1"),
    # ── fim das regras ──
]
# Pré-compila os padrões uma única vez no import do módulo.
_KIT_NAME_PATTERNS_COMPILED: list = [
    (re.compile(pat), repl) for pat, repl in _KIT_NAME_PATTERNS
]


def _normalize_kit_raw(name: Optional[str]) -> str:
    """Trim + colapso de espaços internos com padrões de normalização.

    Aplicado como fallback para kits sem tipo_kit em kit_config.
    Os padrões em _KIT_NAME_PATTERNS são testados em ordem; o primeiro
    que casar substitui o nome inteiro. Se nenhum casar, devolve o nome
    com apenas trim + colapso de espaços.
    """
    if not name:
        return ""
    cleaned = re.sub(r"\s+", " ", name.strip())
    for pattern, repl in _KIT_NAME_PATTERNS_COMPILED:
        result = pattern.sub(repl, cleaned)
        if result != cleaned:
            return re.sub(r"\s+", " ", result).strip()
    return cleaned


def _build_kit_canonical_maps(
    db: Session,
    magento_event_ids: List[int],
) -> Tuple[Dict[Tuple, str], Dict[str, str]]:
    """
    Retorna dois dicionários de resolução canônica a partir de KitConfig:

    magento_map: {(id_evento_magento: int, kit_nome_raw: str) → tipo_kit}
        Chave baseia-se em KitConfig.id_evento (== Magento event ID) e
        KitConfig.kit_nome (== soi_parent.name nas linhas Magento).

    ativo_map: {ativo_categoria_raw: str → tipo_kit}
        Global (sem escopo de evento) porque linhas Ativo usam IDs do Ativo
        que não coincidem com KitConfig.id_evento (Magento).
        ativo_categoria pode conter múltiplas categorias separadas por vírgula.

    Entradas com tipo_kit NULL ou vazio são ignoradas.
    """
    magento_map: Dict[Tuple, str] = {}
    ativo_map: Dict[str, str] = {}

    # Join KitMappingSnapshot to resolve nome_kit (raw Magento bundle name)
    # when KitConfig.kit_nome is null (common — UI never sends it).
    query = (
        db.query(KitConfig, KitMappingSnapshot.nome_kit)
        .outerjoin(
            KitMappingSnapshot,
            KitMappingSnapshot.bundle_entity_id == KitConfig.bundle_entity_id,
        )
        .filter(
            KitConfig.tipo_kit.isnot(None),
            KitConfig.tipo_kit != "",
        )
    )
    if magento_event_ids:
        query = query.filter(KitConfig.id_evento.in_(magento_event_ids))

    for cfg, snap_nome_kit in query.all():
        tipo = cfg.tipo_kit.strip()
        if not tipo:
            continue
        # Mapa Magento: prefer KitConfig.kit_nome; fall back to KitMappingSnapshot.nome_kit
        bundle_name = (cfg.kit_nome or snap_nome_kit or "").strip()
        if cfg.id_evento is not None and bundle_name:
            magento_map[(int(cfg.id_evento), bundle_name)] = tipo
        # Mapa Ativo: ativo_categoria → tipo_kit (pode ter múltiplos separados por vírgula)
        if cfg.ativo_categoria:
            for cat in cfg.ativo_categoria.replace("\n", ",").split(","):
                cat = cat.strip()
                if cat and cat not in ativo_map:
                    ativo_map[cat] = tipo

    return magento_map, ativo_map


def _apply_canonical_kit(
    rows: List[Dict],
    magento_map: Dict[Tuple, str],
    ativo_map: Dict[str, str],
) -> None:
    """
    Resolve o nome canônico de kit para cada linha, *in-place*.

    Linhas Magento: lookup via (id_evento, kit.strip()) no magento_map.
    Linhas Ativo:   lookup via kit.strip() no ativo_map.
    Fallback: _normalize_kit_raw (trim + colapso de espaços).
    """
    for row in rows:
        raw = row.get("kit") or ""
        banco = row.get("banco") or ""
        canonical: Optional[str] = None

        if banco == "Magento" and magento_map:
            try:
                ev_id = int(row.get("id_evento") or 0)
            except (ValueError, TypeError):
                ev_id = 0
            canonical = magento_map.get((ev_id, raw.strip()))
        elif banco == "Ativo" and ativo_map:
            canonical = ativo_map.get(raw.strip())

        row["kit"] = canonical if canonical else _normalize_kit_raw(raw)


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

def _read_snapshot_raw(db: Session, evento_grupo: str) -> Optional[Tuple[Dict, datetime, float]]:
    """
    Lê o snapshot do PostgreSQL independente da idade.
    Retorna (payload_dict, updated_at, age_hours) se existir, None se não existir.
    O chamador decide se o snapshot é fresco ou stale.
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
        now_utc = datetime.now(timezone.utc)
        updated = row.updated_at
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        age_h = (now_utc - updated).total_seconds() / 3600
        payload_dict = json.loads(row.payload)
        return payload_dict, updated, age_h
    except Exception as e:
        logger.warning(f"[DetalheSnap] Erro ao ler snapshot de '{evento_grupo}': {e}")
        return None


def _read_snapshot(db: Session, evento_grupo: str) -> Optional[Tuple[Dict, datetime]]:
    """
    Lê o snapshot do PostgreSQL para o evento_grupo.
    Retorna (payload_dict, updated_at) se válido (< SNAPSHOT_MAX_AGE_HOURS), None caso contrário.
    """
    result = _read_snapshot_raw(db, evento_grupo)
    if result is None:
        return None
    payload_dict, updated, age_h = result
    if age_h > SNAPSHOT_MAX_AGE_HOURS:
        logger.debug(f"[DetalheSnap] snapshot de '{evento_grupo}' tem {age_h:.1f}h — ignorando (>{SNAPSHOT_MAX_AGE_HOURS}h)")
        return None
    return payload_dict, updated


def _trigger_background_refresh(evento_grupo: str) -> None:
    """
    Dispara um refresh ao vivo para evento_grupo em background (thread daemon).
    Não faz nada se já houver um refresh em andamento para o mesmo evento.
    Cria sua própria sessão de banco — não bloqueia o request atual.
    """
    cache_key = evento_grupo
    with _inflight_lock:
        if cache_key in _inflight:
            logger.debug(
                f"[DetalheSnap SWR] Refresh background ignorado para '{evento_grupo}' "
                "— outro já está em andamento"
            )
            return

    def _bg() -> None:
        from app.core.database import SessionLocal
        db_bg = SessionLocal()
        try:
            logger.info(f"[DetalheSnap SWR] Iniciando refresh background para '{evento_grupo}'")
            get_detalhe(db_bg, evento_grupo, force_refresh=True)
            logger.info(f"[DetalheSnap SWR] Refresh background concluído para '{evento_grupo}'")
        except Exception as _e:
            logger.warning(
                f"[DetalheSnap SWR] Refresh background falhou para '{evento_grupo}': {_e}"
            )
        finally:
            try:
                db_bg.close()
            except Exception:
                pass

    t = threading.Thread(
        target=_bg,
        name=f"detalhe-swr-{evento_grupo}",
        daemon=True,
    )
    t.start()


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

    Ordem de leitura (padrão SWR — stale-while-revalidate):
    1. Cache em memória (TTL 15min) — bypass se force_refresh.
    2. Snapshot PostgreSQL (qualquer idade):
       - Fresco (< SNAPSHOT_MAX_AGE_HOURS): retorna imediatamente.
       - Stale (>= SNAPSHOT_MAX_AGE_HOURS): retorna imediatamente com
         snapshot_stale=True e dispara refresh em background (sem bloquear
         o usuário). O cache em memória é populado com o dado stale por 15min;
         após esse tempo, a próxima leitura pega o snapshot já atualizado.
       - Ausente: cai na query ao vivo.
       - Bypass completo se force_refresh=True.
    3. Query ao vivo (Ativo + Magento) — salva no snapshot e no cache.
       Single-flight guard via _inflight: segundo force_refresh simultâneo
       para o mesmo evento recebe HTTP 429.

    Campos adicionais no retorno:
    - source: "cache" | "snapshot" | "live"
    - snapshot_updated_at: ISO string com data/hora do snapshot
    - snapshot_stale: True se o snapshot estava expirado ao ser servido
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

        # 2. Snapshot PostgreSQL com padrão SWR (stale-while-revalidate).
        #    Apenas para evento único — "__all__" não tem snapshot por chave.
        if evento_grupo:
            snap_raw = _read_snapshot_raw(db, evento_grupo)
            if snap_raw is not None:
                payload_dict, updated_at, age_h = snap_raw

                # Re-apply canonical kit names so alias changes in KitConfig
                # are reflected immediately without waiting for the next live refresh.
                try:
                    por_banco = payload_dict.get("por_banco") or {}
                    rows_ativo_snap = por_banco.get("Ativo") or []
                    rows_magento_snap = por_banco.get("Magento") or []
                    magento_ids_snap = list({
                        int(r["id_evento"])
                        for r in rows_magento_snap
                        if r.get("id_evento")
                    })
                    km_snap, ka_snap = _build_kit_canonical_maps(db, magento_ids_snap)
                    _apply_canonical_kit(rows_ativo_snap, km_snap, ka_snap)
                    _apply_canonical_kit(rows_magento_snap, km_snap, ka_snap)
                    payload_dict["consolidado"] = _consolidar(rows_ativo_snap, rows_magento_snap)
                    payload_dict["totais"] = _calc_totais(payload_dict["consolidado"])
                except Exception as _kit_err:
                    logger.warning(f"[DetalheSnap] Erro ao re-aplicar kit names no snapshot: {_kit_err}")

                payload_dict["source"] = "snapshot"
                payload_dict["snapshot_updated_at"] = updated_at.isoformat()

                if age_h <= SNAPSHOT_MAX_AGE_HOURS:
                    # Snapshot fresco: retorna imediatamente
                    payload_dict["snapshot_stale"] = False
                    with _cache_lock:
                        _cache[cache_key] = (time.time(), payload_dict)
                    logger.info(
                        f"[DetalheSnap] Fresh snapshot para '{evento_grupo}' "
                        f"({age_h:.1f}h, atualizado {updated_at.isoformat()})"
                    )
                    return payload_dict
                else:
                    # Snapshot stale: retorna imediatamente + dispara refresh em background.
                    # O usuário vê o dado anterior sem esperar; o refresh atualiza o cache.
                    payload_dict["snapshot_stale"] = True
                    with _cache_lock:
                        _cache[cache_key] = (time.time(), payload_dict)
                    logger.info(
                        f"[DetalheSnap SWR] Stale snapshot para '{evento_grupo}' "
                        f"({age_h:.1f}h > {SNAPSHOT_MAX_AGE_HOURS}h) — "
                        "servindo dado anterior + refresh em background"
                    )
                    _trigger_background_refresh(evento_grupo)
                    return payload_dict

    # 3. Query ao vivo — single-flight guard.
    # Quando force_refresh=True e outro request já está executando as queries
    # pesadas para o mesmo evento_grupo, serve o dado em cache/snapshot com
    # refresh_in_progress=True (sem levantar 429), para que o frontend possa
    # mostrar dados e re-poll automático quando o refresh terminar.
    if force_refresh and evento_grupo:
        with _inflight_lock:
            if cache_key in _inflight:
                logger.info(
                    f"[DetalheEventos] force_refresh bloqueado para '{evento_grupo}' — "
                    "já há uma consulta ao vivo em andamento; servindo dado em cache (single-flight)"
                )
                # Tenta cache em memória primeiro
                with _cache_lock:
                    entry = _cache.get(cache_key)
                if entry:
                    _, cached_data = entry
                    return {**cached_data, "refresh_in_progress": True}
                # Tenta snapshot PostgreSQL usando sessão independente —
                # a `db` do request pode estar em estado inválido quando há
                # stress no pool, e uma sessão limpa garante que o snapshot
                # seja encontrado mesmo nesse cenário.
                from app.core.database import SessionLocal
                db_snap = SessionLocal()
                try:
                    snap_raw = _read_snapshot_raw(db_snap, evento_grupo)
                finally:
                    db_snap.close()
                if snap_raw is not None:
                    payload_dict, updated_at, age_h = snap_raw
                    payload_dict["source"] = "snapshot"
                    payload_dict["snapshot_updated_at"] = updated_at.isoformat()
                    payload_dict["snapshot_stale"] = True
                    payload_dict["refresh_in_progress"] = True
                    return payload_dict
                # Último recurso: sem dado nenhum disponível — retorna 202
                # para que o frontend faça re-poll automático.
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=202,
                    detail=(
                        "Atualização em andamento — aguarde alguns instantes."
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

        # Normaliza modalidade em todas as rows (regex + alias table)
        alias_map = _get_alias_map(db)
        for row in (rows_ativo or []):
            if row.get("modalidade"):
                row["modalidade"] = _normalize_modalidade(row["modalidade"], alias_map)
        for row in (rows_magento or []):
            if row.get("modalidade"):
                row["modalidade"] = _normalize_modalidade(row["modalidade"], alias_map)

        # Resolve canonical kit names via KitConfig.tipo_kit (lightweight PG query).
        # Magento rows look up by (id_evento, kit_nome); Ativo rows by ativo_categoria.
        # Falls back to normalized raw name when tipo_kit is not configured.
        kit_mapa_magento, kit_mapa_ativo = _build_kit_canonical_maps(db, magento_ids)
        _apply_canonical_kit(rows_ativo or [], kit_mapa_magento, kit_mapa_ativo)
        _apply_canonical_kit(rows_magento or [], kit_mapa_magento, kit_mapa_ativo)

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
        snap_saved = False
        if evento_grupo and not (error_ativo and error_magento):
            snap_saved = save_snapshot(db, evento_grupo, payload)
            if snap_saved:
                payload["snapshot_updated_at"] = datetime.now(timezone.utc).isoformat()

        # Validation summary log — searchable in production to confirm all criteria:
        # • rows from Magento (confirms query ran and returned data)
        # • elapsed visible in the per-bank log above (< 90000ms)
        # • snapshot created (confirms badge will show "Snapshot" on next load)
        magento_rows = len(rows_magento) if rows_magento else 0
        logger.info(
            f"[DetalheEventos] live query concluída — evento_grupo={evento_grupo!r} "
            f"consolidado={len(consolidado)} linhas "
            f"magento_rows={magento_rows} "
            f"erros={list(payload['erros'].keys()) or 'nenhum'} "
            f"snapshot={'salvo' if snap_saved else 'não salvo'}"
        )

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
