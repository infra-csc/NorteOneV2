from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response as RawResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from ...core.database import get_db
from ...core.security import get_current_user, verify_password, get_password_hash
from ...models.user import Usuario
from ...models.user_pref import UserUiPref
import json
import os
import re
import uuid

router = APIRouter(prefix="/profile", tags=["Perfil"])

# Chaves de preferência: slug simples, evita lixo arbitrário na tabela
PREF_KEY_RE = re.compile(r"^[a-z0-9_\-]{1,100}$")
MAX_PREF_VALUE_LEN = 10_000


def _validate_pref_key(chave: str) -> str:
    if not PREF_KEY_RE.match(chave):
        raise HTTPException(status_code=400, detail="Chave de preferência inválida")
    return chave

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MIME_MAP = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class PrefUpsertRequest(BaseModel):
    # Valor JSON arbitrário (lista, objeto, etc.) — serializado ao gravar
    valor: object


@router.get("/prefs")
def list_prefs(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Todas as preferências de UI do usuário logado: { chave: valor }."""
    rows = db.query(UserUiPref).filter(UserUiPref.usuario_id == current_user.id).all()
    out = {}
    for r in rows:
        try:
            out[r.chave] = json.loads(r.valor)
        except (ValueError, TypeError):
            continue  # valor corrompido — ignora em vez de quebrar a tela
    return out


@router.put("/prefs/{chave}")
def upsert_pref(
    chave: str,
    data: PrefUpsertRequest,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    _validate_pref_key(chave)
    valor = json.dumps(data.valor, ensure_ascii=False)
    if len(valor) > MAX_PREF_VALUE_LEN:
        raise HTTPException(status_code=400, detail="Valor de preferência muito grande")
    row = (
        db.query(UserUiPref)
        .filter(UserUiPref.usuario_id == current_user.id, UserUiPref.chave == chave)
        .first()
    )
    if row is None:
        row = UserUiPref(usuario_id=current_user.id, chave=chave, valor=valor)
        db.add(row)
    else:
        row.valor = valor
    db.commit()
    return {"chave": chave, "valor": data.valor}


@router.delete("/prefs/{chave}")
def delete_pref(
    chave: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    _validate_pref_key(chave)
    db.query(UserUiPref).filter(
        UserUiPref.usuario_id == current_user.id, UserUiPref.chave == chave
    ).delete()
    db.commit()
    return {"message": "Preferência removida"}


@router.get("/me")
def get_profile(current_user: Usuario = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "nome": current_user.nome,
        "perfil_acesso_nome": current_user.perfil_acesso_rel.nome if current_user.perfil_acesso_rel else None,
        "foto_perfil": current_user.foto_perfil,
    }


@router.put("/password")
def change_password(
    data: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    if not verify_password(data.current_password, current_user.senha_hash):
        raise HTTPException(status_code=400, detail="Senha atual incorreta")
    if len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="A nova senha deve ter pelo menos 6 caracteres")
    # current_user é detached (pool de auth); grava no usuário DESTA sessão
    user = db.get(Usuario, current_user.id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    user.senha_hash = get_password_hash(data.new_password)
    db.commit()
    return {"message": "Senha alterada com sucesso"}


@router.post("/photo")
async def upload_photo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Formato não suportado. Use JPG, PNG ou WebP.")

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Arquivo muito grande. Máximo 5MB.")

    mime_type = MIME_MAP.get(ext, "image/jpeg")
    filename = f"{current_user.id}_{uuid.uuid4().hex[:8]}{ext}"

    user = db.get(Usuario, current_user.id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    user.foto_perfil = f"/api/profile/photo/{filename}"
    user.foto_perfil_data = contents
    user.foto_perfil_mime = mime_type
    db.commit()
    return {"foto_perfil": user.foto_perfil}


@router.delete("/photo")
def delete_photo(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    user = db.get(Usuario, current_user.id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    user.foto_perfil = None
    user.foto_perfil_data = None
    user.foto_perfil_mime = None
    db.commit()
    return {"message": "Foto removida"}


@router.get("/photo/{filename}")
def get_photo(
    filename: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    safe_name = os.path.basename(filename)
    expected_path = f"/api/profile/photo/{safe_name}"
    user = db.query(Usuario).filter(
        Usuario.foto_perfil == expected_path
    ).first()

    if not user or not user.foto_perfil_data:
        raise HTTPException(status_code=404, detail="Foto não encontrada")

    return RawResponse(
        content=user.foto_perfil_data,
        media_type=user.foto_perfil_mime or "image/jpeg",
        headers={"Cache-Control": "private, max-age=86400"},
    )
