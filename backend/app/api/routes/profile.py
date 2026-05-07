from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response as RawResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from ...core.database import get_db
from ...core.security import get_current_user, verify_password, get_password_hash
from ...models.user import Usuario
import os
import uuid

router = APIRouter(prefix="/profile", tags=["Perfil"])

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MIME_MAP = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


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
    current_user.senha_hash = get_password_hash(data.new_password)
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

    current_user.foto_perfil = f"/api/profile/photo/{filename}"
    current_user.foto_perfil_data = contents
    current_user.foto_perfil_mime = mime_type
    db.commit()
    return {"foto_perfil": current_user.foto_perfil}


@router.delete("/photo")
def delete_photo(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    current_user.foto_perfil = None
    current_user.foto_perfil_data = None
    current_user.foto_perfil_mime = None
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
