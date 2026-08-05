"""Tests for the bulk .txt coupon import endpoint (task #244).

``importar_cupons`` parses a plain-text file of ``EVENTO;AREA;CODIGO`` lines
and applies each one to the matching *pending* cupom solicitação, reusing the
same validation/save helper as the single-paste flow (``_aplicar_codigos_cupom``,
task #242) so the two paths can never drift apart.

Design properties under test:

* Exactly one matching pending solicitação for a (evento, área) group → applied.
* Zero matches → that group's lines are rejected ("não encontrada"); other
  groups in the same file are unaffected (each group commits independently).
* 2+ matches (ambiguous) → rejected outright, never auto-distributed; the
  rejection message points back at the single-paste "Colar código" flow.
* The same code appearing on 2+ lines anywhere in the file is rejected on
  exactly those lines (naming the colliding line numbers), before any
  group-matching happens — this is stricter/more precise than relying on the
  downstream "código já em uso" check alone.
* Header line, comment lines (`#`), blank lines, and template rows with an
  empty CODIGO are all silently skipped and counted in `ignorados`, never
  `rejeitados`.
* A validation failure inside `_aplicar_codigos_cupom` for one group (e.g.
  wrong quantity) becomes a rejection line for that group's lines, not an
  unhandled exception that would abort the whole request.
* Wrong file extension / empty file / no usable data lines are all rejected
  clearly (never silently accepted as "0 applied" with no explanation).

Uses the same in-memory SQLite + StaticPool pattern as
``test_coupon_concurrency.py`` (see that file's module docstring for why this
is safe despite SQLite not implementing row locking): each test here is
single-threaded, so ``with_for_update()`` just becomes a normal read.
"""

import asyncio
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Register ALL mappers so relationship targets resolve across modules.
import app.models  # noqa: F401
from app.core.database import Base
from app.models.cadastro_evento import CadastroEvento
from app.models.cortesia_solicitacao import (
    STATUS_GERADO,
    STATUS_SOLICITADO,
    TIPO_CUPOM,
    CortesiaCupomCodigo,
    CortesiaSolicitacao,
)
from app.models.projecao import AreaProjecao
from app.models.user import Usuario

from app.api.routes.cortesia_solicitacao import (
    _e_cabecalho_importacao,
    baixar_modelo_importacao_cupons,
    importar_cupons,
)


# ---------------------------------------------------------------------------
# Shared in-memory engine (all tests in this module reuse it)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    with eng.connect() as conn:
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_cortesia_cupom_codigo_codigo "
                "ON cortesia_cupom_codigo (UPPER(codigo))"
            )
        )
        conn.commit()
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def SessionFactory(engine):
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture(scope="module")
def seed_base(SessionFactory):
    """One admin user shared by all tests in this module."""
    session = SessionFactory()
    try:
        user = Usuario(
            id=9101,
            nome="Importador Tester",
            email="importador@test.local",
            auth_provider="local",
            ativo=True,
        )
        session.add(user)
        session.commit()
    finally:
        session.close()
    return {"user_id": 9101}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeUploadFile:
    """Minimal stand-in for FastAPI's UploadFile (only `.filename` and async
    `.read()` are required by `importar_cupons`)."""

    def __init__(self, filename: str = "cupons.txt", content: bytes = b""):
        self.filename = filename
        self._content = content

    async def read(self) -> bytes:
        return self._content


def _make_fake_admin(user_id: int = 9101):
    from types import SimpleNamespace
    return SimpleNamespace(id=user_id, nome="Importador Tester")


def _call_importar(db, texto: str, *, filename: str = "cupons.txt", fake_user=None):
    fake_user = fake_user or _make_fake_admin()
    fake_upload = _FakeUploadFile(filename=filename, content=texto.encode("utf-8"))
    with patch(
        "app.api.routes.cortesia_solicitacao.is_user_admin",
        return_value=True,
    ):
        return asyncio.run(importar_cupons(arquivo=fake_upload, db=db, current_user=fake_user))


def _make_evento(db, evento_id: int, nome: str, sku: str):
    if not db.query(CadastroEvento).filter_by(id=evento_id).first():
        db.add(CadastroEvento(id=evento_id, nome=nome, sku=sku))
        db.commit()


def _make_area(db, area_id: int, nome: str, sigla: str):
    if not db.query(AreaProjecao).filter_by(id=area_id).first():
        db.add(AreaProjecao(id=area_id, nome=nome, sigla=sigla, ativo=True))
        db.commit()


def _make_pendente(db, sol_id: int, evento_id: int, area_id: int, quantidade: int, user_id: int = 9101):
    db.add(CortesiaSolicitacao(
        id=sol_id, evento_id=evento_id, area_projecao_id=area_id,
        tipo=TIPO_CUPOM, quantidade=quantidade, status=STATUS_SOLICITADO,
        solicitado_por=user_id,
    ))
    db.commit()


def _resultado_por_linha(resumo, linha: int):
    return next(r for r in resumo.resultados if r.linha == linha)


# ---------------------------------------------------------------------------
# Happy path: exact single match applies and persists
# ---------------------------------------------------------------------------

def test_import_exact_match_applies_and_persists(SessionFactory, seed_base):
    db_setup = SessionFactory()
    try:
        _make_evento(db_setup, 6101, "Evento Importação Feliz", "IMP2026")
        _make_area(db_setup, 5101, "Área Importação", "IA")
        _make_pendente(db_setup, 8101, 6101, 5101, quantidade=2)
    finally:
        db_setup.close()

    db = SessionFactory()
    try:
        texto = (
            "EVENTO;AREA;CODIGO\n"
            "evento importação feliz;área importação;MAGCODE-A\n"
            "Evento Importação Feliz;Área Importação;MAGCODE-B\n"
        )
        resumo = _call_importar(db, texto)
    finally:
        db.close()

    assert resumo.aplicados == 2, resumo
    assert resumo.rejeitados == 0, resumo
    assert resumo.ignorados == 1, "header line must be counted as ignorado"
    assert all(r.aplicado for r in resumo.resultados)

    db_check = SessionFactory()
    try:
        sol = db_check.query(CortesiaSolicitacao).filter_by(id=8101).first()
        assert sol.status == STATUS_GERADO
        codigos = sorted(
            c.codigo for c in db_check.query(CortesiaCupomCodigo).filter_by(solicitacao_id=8101).all()
        )
        assert codigos == ["MAGCODE-A", "MAGCODE-B"]
    finally:
        db_check.close()


# ---------------------------------------------------------------------------
# Zero match: rejected, other groups in the same file unaffected
# ---------------------------------------------------------------------------

def test_import_not_found_group_rejected_others_unaffected(SessionFactory, seed_base):
    db_setup = SessionFactory()
    try:
        _make_evento(db_setup, 6102, "Evento Import Parcial", "IMPPARC")
        _make_area(db_setup, 5102, "Área Parcial", "AP")
        _make_pendente(db_setup, 8102, 6102, 5102, quantidade=1)
    finally:
        db_setup.close()

    db = SessionFactory()
    try:
        texto = (
            "Evento Import Parcial;Área Parcial;MAGGOODCODE\n"
            "Evento Que Nao Existe;Área Fantasma;MAGBADCODE\n"
        )
        resumo = _call_importar(db, texto)
    finally:
        db.close()

    assert resumo.aplicados == 1
    assert resumo.rejeitados == 1
    linha1 = _resultado_por_linha(resumo, 1)
    linha2 = _resultado_por_linha(resumo, 2)
    assert linha1.aplicado is True
    assert linha2.aplicado is False
    assert "não encontrada" in linha2.mensagem.lower() or "nenhuma solicitação pendente" in linha2.mensagem.lower()

    db_check = SessionFactory()
    try:
        sol = db_check.query(CortesiaSolicitacao).filter_by(id=8102).first()
        assert sol.status == STATUS_GERADO, "matching group must still apply despite the other group failing"
    finally:
        db_check.close()


# ---------------------------------------------------------------------------
# Ambiguous match (2+ pending for same evento+área): rejected, not distributed
# ---------------------------------------------------------------------------

def test_import_ambiguous_group_rejected(SessionFactory, seed_base):
    db_setup = SessionFactory()
    try:
        _make_evento(db_setup, 6103, "Evento Ambíguo", "IMPAMB")
        _make_area(db_setup, 5103, "Área Ambígua", "AA")
        # Recurring-event names are not unique (see memory: id_evento_magento
        # canonical source) — two pending requests can legitimately share the
        # same (evento, área) text.
        _make_pendente(db_setup, 8103, 6103, 5103, quantidade=1)
        _make_pendente(db_setup, 8104, 6103, 5103, quantidade=1)
    finally:
        db_setup.close()

    db = SessionFactory()
    try:
        texto = "Evento Ambíguo;Área Ambígua;MAGAMBCODE\n"
        resumo = _call_importar(db, texto)
    finally:
        db.close()

    assert resumo.aplicados == 0
    assert resumo.rejeitados == 1
    linha = _resultado_por_linha(resumo, 1)
    assert "ambíguo" in linha.mensagem.lower() or "ambiguo" in linha.mensagem.lower()
    assert "colar código" in linha.mensagem.lower(), "must point to the fallback single-paste flow"

    db_check = SessionFactory()
    try:
        for sid in (8103, 8104):
            sol = db_check.query(CortesiaSolicitacao).filter_by(id=sid).first()
            assert sol.status == STATUS_SOLICITADO, f"sol {sid} must stay untouched on ambiguous match"
    finally:
        db_check.close()


# ---------------------------------------------------------------------------
# Cross-file duplicate code: only the colliding lines are rejected
# ---------------------------------------------------------------------------

def test_import_cross_file_duplicate_code_rejects_only_those_lines(SessionFactory, seed_base):
    db_setup = SessionFactory()
    try:
        _make_evento(db_setup, 6104, "Evento Dup A", "IMPDUPA")
        _make_area(db_setup, 5104, "Área Dup A", "ADA")
        _make_pendente(db_setup, 8105, 6104, 5104, quantidade=1)

        _make_evento(db_setup, 6105, "Evento Dup B", "IMPDUPB")
        _make_area(db_setup, 5105, "Área Dup B", "ADB")
        _make_pendente(db_setup, 8106, 6105, 5105, quantidade=1)

        _make_evento(db_setup, 6106, "Evento Solo", "IMPSOLO")
        _make_area(db_setup, 5106, "Área Solo", "ASO")
        _make_pendente(db_setup, 8107, 6106, 5106, quantidade=1)
    finally:
        db_setup.close()

    db = SessionFactory()
    try:
        # Lines 1 and 2 share the same code across two *different* groups;
        # line 3 has a distinct code targeting an unrelated, valid group.
        texto = (
            "Evento Dup A;Área Dup A;MAGSAMECODE\n"
            "Evento Dup B;Área Dup B;magsamecode\n"
            "Evento Solo;Área Solo;MAGUNIQUECODE\n"
        )
        resumo = _call_importar(db, texto)
    finally:
        db.close()

    assert resumo.aplicados == 1
    assert resumo.rejeitados == 2
    linha1, linha2, linha3 = (_resultado_por_linha(resumo, i) for i in (1, 2, 3))
    assert linha1.aplicado is False and "repetido" in linha1.mensagem.lower()
    assert linha2.aplicado is False and "repetido" in linha2.mensagem.lower()
    # Message names both colliding line numbers so the admin can find them.
    assert "1" in linha1.mensagem and "2" in linha1.mensagem
    assert linha3.aplicado is True

    db_check = SessionFactory()
    try:
        assert db_check.query(CortesiaSolicitacao).filter_by(id=8105).first().status == STATUS_SOLICITADO
        assert db_check.query(CortesiaSolicitacao).filter_by(id=8106).first().status == STATUS_SOLICITADO
        assert db_check.query(CortesiaSolicitacao).filter_by(id=8107).first().status == STATUS_GERADO
    finally:
        db_check.close()


# ---------------------------------------------------------------------------
# Header / comment / blank lines and empty-código template rows are ignored
# ---------------------------------------------------------------------------

def test_import_header_and_comments_and_blank_lines_ignored(SessionFactory, seed_base):
    db_setup = SessionFactory()
    try:
        _make_evento(db_setup, 6107, "Evento Cabecalho", "IMPCAB")
        _make_area(db_setup, 5107, "Área Cabecalho", "AC")
        _make_pendente(db_setup, 8108, 6107, 5107, quantidade=1)
    finally:
        db_setup.close()

    db = SessionFactory()
    try:
        texto = (
            "# comentário explicativo\n"
            "\n"
            "EVENTO;AREA;CODIGO\n"
            "   \n"
            "Evento Cabecalho;Área Cabecalho;MAGREALCODE\n"
        )
        resumo = _call_importar(db, texto)
    finally:
        db.close()

    assert resumo.aplicados == 1
    assert resumo.rejeitados == 0
    # Only the real data line should ever show up in `resultados`; comment/
    # blank/header lines are never even parsed as entries.
    assert len(resumo.resultados) == 1
    assert resumo.ignorados == 1  # the header line


def test_import_blank_codigo_template_row_ignored_when_mixed_with_real_data(SessionFactory, seed_base):
    """A template row downloaded via /importar-cupons/modelo but not yet
    filled in (empty CODIGO) must be silently skipped — not reported as a
    parsing failure — when the file also has at least one real data line
    (the realistic case: admin filled in only some of the template rows)."""
    db_setup = SessionFactory()
    try:
        _make_evento(db_setup, 6108, "Evento Template", "IMPTPL")
        _make_area(db_setup, 5108, "Área Template", "AT2")
        _make_pendente(db_setup, 8109, 6108, 5108, quantidade=1)

        _make_evento(db_setup, 6112, "Evento Template Preenchido", "IMPTPL2")
        _make_area(db_setup, 5112, "Área Template Preenchido", "AT3")
        _make_pendente(db_setup, 8113, 6112, 5112, quantidade=1)
    finally:
        db_setup.close()

    db = SessionFactory()
    try:
        texto = (
            "Evento Template;Área Template;\n"  # ainda não preenchida
            "Evento Template Preenchido;Área Template Preenchido;MAGFILLEDCODE\n"
        )
        resumo = _call_importar(db, texto)
    finally:
        db.close()

    assert resumo.aplicados == 1
    assert resumo.rejeitados == 0
    assert resumo.ignorados == 1
    assert len(resumo.resultados) == 1, "the still-blank template row must never appear in resultados"


def test_import_all_blank_template_rows_raises_clear_error(SessionFactory, seed_base):
    """Re-uploading the template without filling in any code must raise a
    clear, actionable error — not silently 'succeed' with 0 applied and no
    explanation of why."""
    from fastapi import HTTPException

    db = SessionFactory()
    try:
        texto = "Evento Não Preenchido;Área Não Preenchida;\n"
        with pytest.raises(HTTPException) as exc_info:
            _call_importar(db, texto)
        assert exc_info.value.status_code == 400
        assert "nenhum código" in exc_info.value.detail.lower()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# A group-level validation failure becomes a rejection line, not a crash
# ---------------------------------------------------------------------------

def test_import_quantity_mismatch_becomes_rejection_not_crash(SessionFactory, seed_base):
    """The pending solicitação asks for 2 cortesias but the file only
    supplies 1 code for that group — `_aplicar_codigos_cupom` raises
    HTTPException(400); `importar_cupons` must turn that into a rejection
    line for the group, not propagate the exception and abort the request."""
    db_setup = SessionFactory()
    try:
        _make_evento(db_setup, 6109, "Evento Quantidade", "IMPQTD")
        _make_area(db_setup, 5109, "Área Quantidade", "AQ")
        _make_pendente(db_setup, 8110, 6109, 5109, quantidade=2)
    finally:
        db_setup.close()

    db = SessionFactory()
    try:
        texto = "Evento Quantidade;Área Quantidade;MAGONLYONE\n"
        resumo = _call_importar(db, texto)
    finally:
        db.close()

    assert resumo.aplicados == 0
    assert resumo.rejeitados == 1
    linha = _resultado_por_linha(resumo, 1)
    assert "2 cortesia" in linha.mensagem or "quantidade" in linha.mensagem.lower() or "1 código" in linha.mensagem

    db_check = SessionFactory()
    try:
        sol = db_check.query(CortesiaSolicitacao).filter_by(id=8110).first()
        assert sol.status == STATUS_SOLICITADO
        assert db_check.query(CortesiaCupomCodigo).filter_by(solicitacao_id=8110).count() == 0
    finally:
        db_check.close()


# ---------------------------------------------------------------------------
# Defensive re-check: solicitação changed status between the initial match
# and the per-group lock (stale in-memory snapshot).
# ---------------------------------------------------------------------------

def test_import_stale_pending_snapshot_defensive_recheck(SessionFactory, seed_base):
    """Simulates a solicitação that was already generated by the time its
    group is processed, even though the earlier pending-matching pass still
    saw it as pending (e.g. another admin acted on it mid-file-processing).

    ``importar_cupons`` re-reads the row with `with_for_update()` right
    before applying, and must catch this via `sol.status == STATUS_GERADO`
    rather than trusting the earlier snapshot."""
    db_setup = SessionFactory()
    try:
        _make_evento(db_setup, 6110, "Evento Corrida", "IMPRACE")
        _make_area(db_setup, 5110, "Área Corrida", "ACR")
        _make_pendente(db_setup, 8111, 6110, 5110, quantidade=1)
    finally:
        db_setup.close()

    # Build a fake "pending" snapshot object exposing the same evento/area
    # attributes the real matching pass reads, but pointing at the sol id
    # that is actually already GERADO in the DB by the time we apply.
    from types import SimpleNamespace as _SNS

    def _fake_pendentes(db):
        real = db.query(CortesiaSolicitacao).filter_by(id=8111).first()
        return [_SNS(id=8111, evento=real.evento, area_projecao=real.area_projecao)]

    db = SessionFactory()
    try:
        # Flip the row to already-gerado *after* building the fake snapshot
        # function (so the "pending" view is stale relative to the DB).
        sol = db.query(CortesiaSolicitacao).filter_by(id=8111).first()
        sol.status = STATUS_GERADO
        db.commit()

        texto = "Evento Corrida;Área Corrida;MAGSTALECODE\n"
        with patch(
            "app.api.routes.cortesia_solicitacao._pendentes_cupom_com_nomes",
            side_effect=_fake_pendentes,
        ):
            resumo = _call_importar(db, texto)
    finally:
        db.close()

    assert resumo.aplicados == 0
    assert resumo.rejeitados == 1
    linha = _resultado_por_linha(resumo, 1)
    assert "recebeu um código ou foi cancelada" in linha.mensagem.lower()


# ---------------------------------------------------------------------------
# File-level rejections
# ---------------------------------------------------------------------------

def test_import_wrong_extension_rejected(SessionFactory, seed_base):
    from fastapi import HTTPException

    db = SessionFactory()
    try:
        with pytest.raises(HTTPException) as exc_info:
            _call_importar(db, "Evento;Área;CODE", filename="cupons.csv")
        assert exc_info.value.status_code == 400
        assert ".txt" in exc_info.value.detail
    finally:
        db.close()


def test_import_empty_file_rejected(SessionFactory, seed_base):
    from fastapi import HTTPException

    db = SessionFactory()
    try:
        with pytest.raises(HTTPException) as exc_info:
            _call_importar(db, "")
        assert exc_info.value.status_code == 400
        assert "vazio" in exc_info.value.detail.lower()
    finally:
        db.close()


def test_import_no_data_lines_rejected(SessionFactory, seed_base):
    """A file with only a header and comments (no real data rows) must be
    rejected with a clear message, not silently return "0 applied"."""
    from fastapi import HTTPException

    db = SessionFactory()
    try:
        texto = "# só comentário\nEVENTO;AREA;CODIGO\n"
        with pytest.raises(HTTPException) as exc_info:
            _call_importar(db, texto)
        assert exc_info.value.status_code == 400
        assert "nenhum código" in exc_info.value.detail.lower()
    finally:
        db.close()


def test_import_malformed_line_reported_not_silently_dropped(SessionFactory, seed_base):
    """A line that doesn't split into exactly 3 `;`-separated parts must
    surface as a rejection, not vanish silently."""
    db = SessionFactory()
    try:
        texto = "isso não tem os separadores certos\n"
        resumo = _call_importar(db, texto)
    finally:
        db.close()

    assert resumo.total == 1
    assert resumo.rejeitados == 1
    linha = _resultado_por_linha(resumo, 1)
    assert "formato inválido" in linha.mensagem.lower()


# ---------------------------------------------------------------------------
# Header-detection helper (unit)
# ---------------------------------------------------------------------------

def test_e_cabecalho_importacao_detects_case_and_accent_variants():
    assert _e_cabecalho_importacao("EVENTO", "AREA", "CODIGO")
    assert _e_cabecalho_importacao("evento", "área", "código")
    assert _e_cabecalho_importacao("Evento", "Área", "Código")
    assert _e_cabecalho_importacao(" evento ", " area ", " codigo ")
    # Real data must never be mistaken for the header, even if it happens to
    # contain similar-looking words.
    assert not _e_cabecalho_importacao("Corrida Evento Especial", "Área Norte", "MAGCODE123")
    assert not _e_cabecalho_importacao("Evento", "Área", "")


# ---------------------------------------------------------------------------
# Template download
# ---------------------------------------------------------------------------

def test_modelo_download_has_one_row_per_pending_unit_and_explanatory_header(SessionFactory, seed_base):
    db_setup = SessionFactory()
    try:
        _make_evento(db_setup, 6111, "Evento Modelo", "IMPMOD")
        _make_area(db_setup, 5111, "Área Modelo", "AM")
        _make_pendente(db_setup, 8112, 6111, 5111, quantidade=3)
    finally:
        db_setup.close()

    db = SessionFactory()
    try:
        with patch("app.api.routes.cortesia_solicitacao.is_user_admin", return_value=True):
            response = baixar_modelo_importacao_cupons(db=db, current_user=_make_fake_admin())

        async def _drain():
            chunks = []
            async for chunk in response.body_iterator:
                chunks.append(chunk)
            return b"".join(chunks)

        conteudo = asyncio.run(_drain())
    finally:
        db.close()

    texto = conteudo.decode("utf-8-sig")
    linhas_dados = [
        ln for ln in texto.splitlines()
        if ln and not ln.startswith("#") and ln != "EVENTO;AREA;CODIGO"
    ]
    linhas_evento_modelo = [ln for ln in linhas_dados if ln.startswith("Evento Modelo;Área Modelo;")]
    assert len(linhas_evento_modelo) == 3, "one template row per unit of quantidade"
    assert all(ln.endswith(";") for ln in linhas_evento_modelo), "código must be left blank in the template"
    assert "EVENTO;AREA;CODIGO" in texto
