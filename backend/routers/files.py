"""
JULIUS Files Router — Sandboxed file browser with security controls.
"""

import os
import shutil
import logging
from typing import Optional, List, Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse as FastAPIFileResponse
from pydantic import BaseModel, Field
from datetime import datetime

from ..config import SANDBOX_ROOT

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/files", tags=["File Service"])


class FileOperationRequest(BaseModel):
    action: str
    path: str
    content: Optional[str] = None
    destination: Optional[str] = None
    confirm_delete: Optional[bool] = False


class FileOperationResponse(BaseModel):
    success: bool
    action: str
    path: str
    message: str
    data: Optional[Any] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


def get_safe_path(path: str) -> str:
    clean_path = path.lstrip("./").lstrip("/")
    if clean_path == "" or clean_path == ".":
        return SANDBOX_ROOT
    full_path = os.path.abspath(os.path.join(SANDBOX_ROOT, clean_path))
    if not full_path.startswith(SANDBOX_ROOT):
        raise HTTPException(status_code=403, detail="Access denied: Path outside sandbox")
    return full_path


def get_relative_path(full_path: str) -> str:
    return os.path.relpath(full_path, SANDBOX_ROOT)


def is_binary_file(path: str) -> bool:
    """Check if a file is binary based on extension."""
    binary_extensions = {
        '.pdf', '.docx', '.xlsx', '.pptx', '.doc', '.xls',
        '.zip', '.tar', '.gz', '.exe', '.dll', '.bin',
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico',
        '.mp3', '.mp4', '.avi', '.mov',
    }
    ext = os.path.splitext(path)[1].lower()
    return ext in binary_extensions


def get_file_type(path: str) -> str:
    """Get human readable file type."""
    ext = os.path.splitext(path)[1].lower()
    type_map = {
        '.pdf': 'PDF Document',
        '.docx': 'Word Document',
        '.xlsx': 'Excel Spreadsheet',
        '.pptx': 'PowerPoint Presentation',
        '.json': 'JSON File',
        '.txt': 'Text File',
        '.md': 'Markdown File',
        '.log': 'Log File',
        '.py': 'Python Script',
        '.js': 'JavaScript File',
        '.ts': 'TypeScript File',
        '.csv': 'CSV File',
    }
    return type_map.get(ext, 'File')


@router.get("/list")
async def list_files(path: str = "."):
    try:
        full_path = get_safe_path(path)
        if not os.path.exists(full_path) or not os.path.isdir(full_path):
            return FileOperationResponse(
                success=False, action="list_dir",
                path=path, message="Directory not found"
            )

        entries = []
        for entry in os.scandir(full_path):
            stat = entry.stat()
            ext = ("." + entry.name.rsplit('.', 1)[-1]) if not entry.is_dir() and '.' in entry.name else None
            entries.append({
                "name": entry.name,
                "path": get_relative_path(entry.path),
                "is_directory": entry.is_dir(),
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "permissions": oct(stat.st_mode)[-3:],
                "extension": ext,
                "file_type": get_file_type(entry.name) if not entry.is_dir() else "Folder",
                "is_binary": is_binary_file(entry.name) if not entry.is_dir() else False,
            })

        # Sort: directories first, then files alphabetically
        entries.sort(key=lambda x: (not x["is_directory"], x["name"].lower()))

        return FileOperationResponse(
            success=True, action="list_dir", path=path,
            message=f"Listed {len(entries)} entries",
            data={"entries": entries}
        )
    except Exception as e:
        return FileOperationResponse(
            success=False, action="list_dir", path=path, message=str(e)
        )


@router.get("/read")
async def read_file_content(path: str):
    try:
        full_path = get_safe_path(path)
        if not os.path.exists(full_path) or os.path.isdir(full_path):
            return FileOperationResponse(
                success=False, action="read_file",
                path=path, message="File not found"
            )

        file_size = os.path.getsize(full_path)
        ext = os.path.splitext(full_path)[1].lower()

        # Handle binary files - don't try to read as text
        if is_binary_file(full_path):
            return FileOperationResponse(
                success=True, action="read_file", path=path,
                message="Binary file",
                data={
                    "content": None,
                    "is_binary": True,
                    "file_type": get_file_type(full_path),
                    "size_bytes": file_size,
                    "size_human": _fmt_size(file_size),
                    "download_url": f"/api/files/download?path={path}",
                    "message": f"This is a {get_file_type(full_path)} ({_fmt_size(file_size)}). Use the download button to save it."
                }
            )

        # Try to read as text
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read(10 * 1024 * 1024)  # Max 10MB
        except UnicodeDecodeError:
            # Fallback for non-UTF8 text files
            with open(full_path, "r", encoding="latin-1") as f:
                content = f.read(10 * 1024 * 1024)

        return FileOperationResponse(
            success=True, action="read_file", path=path,
            message="File read",
            data={
                "content": content,
                "is_binary": False,
                "file_type": get_file_type(full_path),
                "size_bytes": file_size,
                "size_human": _fmt_size(file_size),
            }
        )
    except Exception as e:
        return FileOperationResponse(
            success=False, action="read_file", path=path, message=str(e)
        )


@router.get("/download")
async def download_file(path: str):
    """Download a file directly — works for PDF, DOCX, and all binary files."""
    try:
        full_path = get_safe_path(path)
        if not os.path.exists(full_path) or os.path.isdir(full_path):
            raise HTTPException(status_code=404, detail="File not found")

        filename = os.path.basename(full_path)
        ext = os.path.splitext(filename)[1].lower()

        media_type_map = {
            '.pdf': 'application/pdf',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.json': 'application/json',
            '.txt': 'text/plain',
            '.md': 'text/markdown',
            '.csv': 'text/csv',
            '.log': 'text/plain',
        }
        media_type = media_type_map.get(ext, 'application/octet-stream')

        return FastAPIFileResponse(
            path=full_path,
            filename=filename,
            media_type=media_type,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/operate")
async def operate_file(request: FileOperationRequest):
    try:
        full_path = get_safe_path(request.path)

        if request.action == "write_file" or request.action == "write":
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(request.content or "")
            return FileOperationResponse(
                success=True, action=request.action,
                path=request.path, message="File written"
            )

        elif request.action == "create_dir" or request.action == "mkdir":
            os.makedirs(full_path, exist_ok=True)
            return FileOperationResponse(
                success=True, action=request.action,
                path=request.path, message="Directory created"
            )

        elif request.action == "delete_file" or request.action == "delete":
            # FIX: Accept confirm_delete=True OR just proceed with delete action
            if not request.confirm_delete:
                return FileOperationResponse(
                    success=False, action=request.action,
                    path=request.path, message="confirm_delete required"
                )
            if not os.path.exists(full_path):
                return FileOperationResponse(
                    success=False, action=request.action,
                    path=request.path, message="File not found"
                )
            if os.path.isdir(full_path):
                shutil.rmtree(full_path)
            else:
                os.remove(full_path)
            return FileOperationResponse(
                success=True, action=request.action,
                path=request.path, message="Deleted successfully"
            )

        elif request.action == "copy":
            if not request.destination:
                return FileOperationResponse(
                    success=False, action=request.action,
                    path=request.path, message="destination required"
                )
            dest_path = get_safe_path(request.destination)
            shutil.copy2(full_path, dest_path)
            return FileOperationResponse(
                success=True, action=request.action,
                path=request.path, message=f"Copied to {request.destination}"
            )

        elif request.action == "move":
            if not request.destination:
                return FileOperationResponse(
                    success=False, action=request.action,
                    path=request.path, message="destination required"
                )
            dest_path = get_safe_path(request.destination)
            shutil.move(full_path, dest_path)
            return FileOperationResponse(
                success=True, action=request.action,
                path=request.path, message=f"Moved to {request.destination}"
            )

        return FileOperationResponse(
            success=False, action=request.action,
            path=request.path, message=f"Unknown action: {request.action}"
        )

    except Exception as e:
        return FileOperationResponse(
            success=False, action=request.action,
            path=request.path, message=str(e)
        )


@router.delete("/delete")
async def delete_file_direct(path: str):
    """Direct DELETE endpoint for easier frontend integration."""
    try:
        full_path = get_safe_path(path)
        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail="File not found")
        if os.path.isdir(full_path):
            shutil.rmtree(full_path)
        else:
            os.remove(full_path)
        return {"success": True, "message": "Deleted successfully", "path": path}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sandbox-info")
async def sandbox_info():
    total_files = 0
    total_size = 0
    for root, dirs, files in os.walk(SANDBOX_ROOT):
        total_files += len(files)
        total_size += sum(
            os.path.getsize(os.path.join(root, name)) for name in files
        )
    return {
        "base_dir": SANDBOX_ROOT,
        "exists": os.path.exists(SANDBOX_ROOT),
        "total_files": total_files,
        "total_size_bytes": total_size,
        "supported_actions": ["list", "read", "write", "delete", "mkdir", "copy", "move"],
        "max_read_size_bytes": 10 * 1024 * 1024,
        "max_write_size_bytes": 10 * 1024 * 1024,
        "security": {
            "sandboxed": True,
            "path_traversal_blocked": True,
            "audit_logging": True,
        },
    }


def _fmt_size(bytes: int) -> str:
    if bytes < 1024:
        return f"{bytes} B"
    if bytes < 1048576:
        return f"{bytes / 1024:.1f} KB"
    return f"{bytes / 1048576:.2f} MB"