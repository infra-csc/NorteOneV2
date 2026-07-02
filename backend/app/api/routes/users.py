import io
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response as RawResponse
from sqlalchemy import or_, func
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from ...core.database import get_db
from ...core.security import get_password_hash, require_permission, invalidate_user_sessions
from ...models.user import Usuario
from ...models.perfil_acesso import PerfilAcesso
from ...models.dimensoes import DimCentroCusto
from ...schemas.auth import UserCreate, UserUpdate, UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Usuários"])


def _user_to_response(user: Usuario) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "nome": user.nome,
        "perfil_acesso_id": user.perfil_acesso_id,
        "perfil_acesso_nome": user.perfil_acesso_rel.nome if user.perfil_acesso_rel else None,
        "is_admin": user.perfil_acesso_rel.is_admin if user.perfil_acesso_rel else False,
        "centro_custo_id": user.centro_custo_id,
        "ativo": user.ativo,
        "auth_provider": user.auth_provider or "local",
        "recebe_alertas_corte": user.recebe_alertas_corte or False,
        "recebe_insights_nori": user.recebe_insights_nori or False,
        "permite_login_local": user.permite_login_local or False,
    }


@router.get("/", response_model=List[UserResponse])
def list_users(
    skip: int = 0,
    limit: int = 100,
    q: Optional[str] = None,
    ativo: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_usuarios", "pode_visualizar")),
):
    query = db.query(Usuario).options(joinedload(Usuario.perfil_acesso_rel))
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(or_(Usuario.nome.ilike(term), Usuario.email.ilike(term)))
    if ativo is not None:
        query = query.filter(Usuario.ativo == ativo)
    users = query.order_by(func.lower(Usuario.nome)).offset(skip).limit(limit).all()
    return [_user_to_response(u) for u in users]


@router.post("/", response_model=UserResponse)
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_usuarios", "pode_criar")),
):
    existing = db.query(Usuario).filter(Usuario.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email já cadastrado")

    db_user = Usuario(
        email=user.email,
        nome=user.nome,
        senha_hash=get_password_hash(user.password),
        perfil_acesso_id=user.perfil_acesso_id,
        centro_custo_id=user.centro_custo_id,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    db_user = db.query(Usuario).options(joinedload(Usuario.perfil_acesso_rel)).filter(Usuario.id == db_user.id).first()
    return _user_to_response(db_user)


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_usuarios", "pode_visualizar")),
):
    user = db.query(Usuario).options(joinedload(Usuario.perfil_acesso_rel)).filter(Usuario.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return _user_to_response(user)


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    user_update: UserUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_usuarios", "pode_editar")),
):
    user = db.query(Usuario).filter(Usuario.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    update_data = user_update.model_dump(exclude_unset=True)

    prev_emergencia = bool(user.permite_login_local)
    nova_emergencia = update_data.get("permite_login_local", prev_emergencia)
    nova_senha = update_data.get("password") or None

    # Ao ativar o acesso de emergência, a conta precisa de uma senha local —
    # caso contrário o caminho de login por senha (break-glass) fica inutilizável,
    # especialmente em contas Microsoft cujo senha_hash foi zerado pela sincronização.
    if nova_emergencia and not prev_emergencia and not nova_senha and not user.senha_hash:
        raise HTTPException(
            status_code=400,
            detail="Defina uma senha de emergência ao ativar o acesso de emergência.",
        )

    if "password" in update_data and update_data["password"]:
        user.senha_hash = get_password_hash(update_data["password"])
    update_data.pop("password", None)

    was_active = user.ativo
    for field, value in update_data.items():
        setattr(user, field, value)

    if was_active and not user.ativo:
        invalidate_user_sessions(user_id, db)

    db.commit()
    db.refresh(user)

    # Auditoria (quem/quando): registra ativação/desativação do acesso de
    # emergência e a redefinição da senha de emergência feita por um admin.
    if nova_emergencia != prev_emergencia:
        logger.info(
            "[AUDITORIA] Acesso de emergência %s para usuário id=%s (%s) por admin id=%s (%s)",
            "ATIVADO" if nova_emergencia else "DESATIVADO",
            user.id,
            user.email,
            current_user.id,
            current_user.email,
        )
    if nova_emergencia and nova_senha:
        logger.info(
            "[AUDITORIA] Senha de emergência redefinida para usuário id=%s (%s) por admin id=%s (%s)",
            user.id,
            user.email,
            current_user.id,
            current_user.email,
        )

    user = db.query(Usuario).options(joinedload(Usuario.perfil_acesso_rel)).filter(Usuario.id == user.id).first()
    return _user_to_response(user)


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_usuarios", "pode_deletar")),
):
    user = db.query(Usuario).filter(Usuario.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    user.ativo = False
    invalidate_user_sessions(user_id, db)
    db.commit()
    return {"message": "Usuário desativado"}


_TEMPLATE_COLUMNS = [
    "nome",
    "email",
    "perfil_acesso",
    "centro_custo",
    "recebe_alertas_corte",
    "recebe_insights_nori",
]


def _parse_bool_cell(value) -> bool:
    if value is None:
        return False
    s = str(value).strip().lower()
    return s in {"sim", "s", "true", "1", "yes", "y", "verdadeiro", "x"}


def _is_blank(value) -> bool:
    if value is None:
        return True
    s = str(value).strip()
    return s == "" or s.lower() == "nan"


@router.get("/bulk-import/template")
def bulk_import_template(
    current_user: Usuario = Depends(require_permission("admin_usuarios", "pode_criar")),
):
    header = ",".join(_TEMPLATE_COLUMNS)
    example = "João da Silva,joao.silva@exemplo.com,Administrador,Marketing,não,sim"
    csv_content = "\ufeff" + header + "\n" + example + "\n"
    return RawResponse(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="modelo_importacao_usuarios.csv"'
        },
    )


@router.post("/bulk-import")
async def bulk_import_users(
    file: UploadFile = File(...),
    senha_padrao: str = Form(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_usuarios", "pode_criar")),
):
    import pandas as pd
    from email_validator import validate_email, EmailNotValidError

    if not senha_padrao or len(senha_padrao) < 6:
        raise HTTPException(status_code=400, detail="A senha padrão deve ter pelo menos 6 caracteres")

    filename = (file.filename or "").lower()
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Arquivo vazio")

    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(contents), dtype=str)
        elif filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(contents), dtype=str)
        else:
            raise HTTPException(status_code=400, detail="Formato não suportado. Use .csv ou .xlsx")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Não foi possível ler o arquivo. Verifique se está no formato correto (.csv ou .xlsx).")

    df.columns = [str(c).strip().lower() for c in df.columns]
    if "nome" not in df.columns or "email" not in df.columns:
        raise HTTPException(
            status_code=400,
            detail="A planilha precisa conter ao menos as colunas 'nome' e 'email'. Baixe o modelo para o formato correto.",
        )

    perfis = db.query(PerfilAcesso).all()
    perfil_by_nome = {p.nome.strip().lower(): p.id for p in perfis}
    centros = db.query(DimCentroCusto).all()
    centro_by_nome = {c.nome.strip().lower(): c.id for c in centros}

    existing_emails = {e[0].strip().lower() for e in db.query(Usuario.email).all() if e[0]}

    senha_hash = get_password_hash(senha_padrao)

    total = 0
    criados = 0
    pulados = []
    seen_emails = set()
    novos = []

    for idx, row in df.iterrows():
        linha = int(idx) + 2  # +1 cabeçalho, +1 índice base 0
        total += 1

        def _cell(col):
            return row[col] if col in df.columns else None

        nome_raw = _cell("nome")
        email_raw = _cell("email")

        if _is_blank(nome_raw):
            pulados.append({"linha": linha, "email": "" if _is_blank(email_raw) else str(email_raw).strip(), "motivo": "Nome vazio"})
            continue
        if _is_blank(email_raw):
            pulados.append({"linha": linha, "email": "", "motivo": "E-mail vazio"})
            continue

        nome = str(nome_raw).strip()
        email = str(email_raw).strip()

        try:
            validate_email(email, check_deliverability=False)
        except EmailNotValidError:
            pulados.append({"linha": linha, "email": email, "motivo": "E-mail inválido"})
            continue

        email_lower = email.lower()
        if email_lower in seen_emails:
            pulados.append({"linha": linha, "email": email, "motivo": "E-mail duplicado na planilha"})
            continue
        if email_lower in existing_emails:
            pulados.append({"linha": linha, "email": email, "motivo": "E-mail já cadastrado"})
            continue

        perfil_acesso_id = None
        perfil_raw = _cell("perfil_acesso")
        if not _is_blank(perfil_raw):
            perfil_acesso_id = perfil_by_nome.get(str(perfil_raw).strip().lower())
            if perfil_acesso_id is None:
                pulados.append({"linha": linha, "email": email, "motivo": f"Perfil de acesso '{str(perfil_raw).strip()}' não encontrado"})
                continue

        centro_custo_id = None
        centro_raw = _cell("centro_custo")
        if not _is_blank(centro_raw):
            centro_custo_id = centro_by_nome.get(str(centro_raw).strip().lower())
            if centro_custo_id is None:
                pulados.append({"linha": linha, "email": email, "motivo": f"Centro de custo '{str(centro_raw).strip()}' não encontrado"})
                continue

        db_user = Usuario(
            email=email,
            nome=nome,
            senha_hash=senha_hash,
            perfil_acesso_id=perfil_acesso_id,
            centro_custo_id=centro_custo_id,
            recebe_alertas_corte=_parse_bool_cell(_cell("recebe_alertas_corte")),
            recebe_insights_nori=_parse_bool_cell(_cell("recebe_insights_nori")),
        )
        db.add(db_user)
        novos.append(db_user)
        seen_emails.add(email_lower)
        existing_emails.add(email_lower)
        criados += 1

    if novos:
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(status_code=500, detail="Erro ao salvar os usuários importados.")

    return {
        "total": total,
        "criados": criados,
        "pulados": pulados,
    }
