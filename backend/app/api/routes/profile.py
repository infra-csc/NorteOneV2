from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel
from ...core.database import get_db
from ...core.security import get_current_user, verify_password, get_password_hash
from ...models.user import Usuario
import os
import uuid

router = APIRouter(prefix="/profile", tags=["Perfil"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "uploads", "profile_photos")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
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

    if current_user.foto_perfil:
        old_path = os.path.join(UPLOAD_DIR, os.path.basename(current_user.foto_perfil))
        if os.path.exists(old_path):
            os.remove(old_path)

    filename = f"{current_user.id}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(contents)

    current_user.foto_perfil = f"/api/profile/photo/{filename}"
    db.commit()
    return {"foto_perfil": current_user.foto_perfil}


@router.delete("/photo")
def delete_photo(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    if current_user.foto_perfil:
        old_path = os.path.join(UPLOAD_DIR, os.path.basename(current_user.foto_perfil))
        if os.path.exists(old_path):
            os.remove(old_path)
    current_user.foto_perfil = None
    db.commit()
    return {"message": "Foto removida"}


@router.get("/photo/{filename}")
def get_photo(filename: str):
    safe_name = os.path.basename(filename)
    filepath = os.path.join(UPLOAD_DIR, safe_name)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Foto não encontrada")
    from fastapi.responses import FileResponse
    return FileResponse(filepath)
