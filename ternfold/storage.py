from __future__ import annotations
import hashlib, os
from pathlib import Path

class LocalStorage:
    def __init__(self,root:str|Path|None=None):
        default=Path(os.getenv("LOCALAPPDATA",str(Path.cwd()/".runtime")))/"Ternfold"/"storage"
        self.root=Path(root or os.getenv("TERNFOLD_STORAGE_ROOT",str(default))); self.root.mkdir(parents=True,exist_ok=True)
    def put(self,namespace:str,suffix:str,data:bytes)->tuple[str,str]:
        digest=hashlib.sha256(data).hexdigest(); clean="".join(ch for ch in suffix.lower() if ch.isalnum() or ch==".")[-12:] or ".bin"
        parts=Path(namespace).parts
        if Path(namespace).is_absolute() or not parts or any(part in {".",".."} or ":" in part for part in parts): raise ValueError("Unsafe storage key")
        key="/".join((*parts,f"{digest}{clean}")); path=self.root.joinpath(*parts,f"{digest}{clean}")
        path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists(): path.write_bytes(data)
        return key,digest
    def read(self,key:str)->bytes:
        parts=Path(key).parts
        if Path(key).is_absolute() or not parts or any(part in {".",".."} or ":" in part for part in parts): raise FileNotFoundError(key)
        path=self.root.joinpath(*parts)
        return path.read_bytes()
    def delete(self,key:str)->None:
        parts=Path(key).parts
        if Path(key).is_absolute() or not parts or any(part in {".",".."} or ":" in part for part in parts): raise FileNotFoundError(key)
        path=self.root.joinpath(*parts)
        path.unlink(missing_ok=True)
storage=LocalStorage()
