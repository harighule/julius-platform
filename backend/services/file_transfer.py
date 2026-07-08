"""
JULIUS — Remote File Download Module
Handles file transfer from remote targets to the local machine via WinRM (Base64) or SMB.
"""

import winrm
import base64
import os
import subprocess
import logging
from typing import Dict, Any, Optional
from .utils import safe_strip

logger = logging.getLogger(__name__)

# ============================================================
# LOCAL DOWNLOAD FOLDER
# ============================================================
LOCAL_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "JULIUS_Downloads")


def ensure_download_dir():
    """Create the local download directory if it doesn't exist."""
    os.makedirs(LOCAL_DOWNLOAD_DIR, exist_ok=True)
    return LOCAL_DOWNLOAD_DIR


def download_file_from_remote(target_ip, username, password, remote_file_path, local_save_dir=None):
    """
    Download a file from a remote machine to local machine.
    
    Flow:
    1. Connect via WinRM
    2. Read file as Base64 on remote machine
    3. Transfer Base64 string back
    4. Decode and save locally
    
    Args:
        target_ip: Remote machine IP
        username: Remote admin username
        password: Remote admin password
        remote_file_path: Full path to file on remote machine (or just filename to search)
        local_save_dir: Local directory to save file (defaults to Desktop/JULIUS_Downloads)
    
    Returns:
        dict with success status, local file path, and file size
    """
    result = {
        "success": False,
        "local_path": "",
        "file_size": 0,
        "error": "",
        "method": ""
    }

    if not local_save_dir:
        local_save_dir = ensure_download_dir()
    else:
        os.makedirs(local_save_dir, exist_ok=True)

    # Try Method 1: WinRM Base64 Transfer
    try:
        res = _download_via_winrm(target_ip, username, password, remote_file_path, local_save_dir)
        if res["success"]:
            return res
        result["error"] = res.get("error", "WinRM failed")
    except Exception as e:
        result["error"] = f"WinRM transfer error: {str(e)}"

    # Try Method 2: SMB Copy
    try:
        res = _download_via_smb(target_ip, username, password, remote_file_path, local_save_dir)
        if res["success"]:
            return res
        result["error"] += f" | SMB copy failed: {res.get('error', 'Unknown error')}"
    except Exception as e:
        result["error"] += f" | SMB transfer error: {str(e)}"

    return result


def _download_via_winrm(target_ip, username, password, remote_file_path, local_save_dir):
    """Download file via WinRM by reading as Base64 chunks."""
    result = {
        "success": False,
        "local_path": "",
        "file_size": 0,
        "error": "",
        "method": "WinRM-Base64"
    }

    try:
        session = winrm.Session(
            f"http://{target_ip}:5985/wsman",
            auth=(username, password),
            transport="ntlm",
            read_timeout_sec=120,
            operation_timeout_sec=100
        )

        # Step 1: Find the file if only filename is given
        find_command = f'''
$searchPath = "{remote_file_path}"

# Check if it's a full path that exists
if (Test-Path $searchPath) {{
    Write-Output $searchPath
}} else {{
    # Search common directories for the filename
    $filename = Split-Path $searchPath -Leaf
    if (-not $filename) {{ $filename = $searchPath }}
    
    $searchDirs = @(
        "$env:USERPROFILE\\Desktop",
        "$env:USERPROFILE\\Documents",
        "$env:USERPROFILE\\Downloads",
        "$env:PUBLIC\\Desktop",
        "C:\\Users"
    )
    
    $found = $null
    foreach ($dir in $searchDirs) {{
        if (Test-Path $dir) {{
            $res = Get-ChildItem -Path $dir -Filter "*$filename*" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($res) {{
                $found = $res.FullName
                break
            }}
        }}
    }}
    
    if ($found) {{
        Write-Output $found
    }} else {{
        Write-Error "FILE_NOT_FOUND: $filename"
        exit 1
    }}
}}
'''

        response = session.run_ps(find_command)
        stdout = safe_strip(response.std_out)
        stderr = safe_strip(response.std_err)

        if response.status_code != 0 or not stdout:
            result["error"] = f"File not found on remote: {stderr or 'No output'}"
            return result

        actual_remote_path = stdout.strip().split("\n")[0].strip()

        # Step 2: Get file size first
        size_cmd = f'(Get-Item "{actual_remote_path}").Length'
        size_response = session.run_ps(size_cmd)
        size_str = safe_strip(size_response.std_out)
        file_size = int(size_str) if size_str.isdigit() else 0

        # Step 3: Read file as Base64
        CHUNK_SIZE = 10 * 1024 * 1024  # 10MB chunks

        if file_size <= CHUNK_SIZE:
            # Single read
            read_cmd = f'[Convert]::ToBase64String([System.IO.File]::ReadAllBytes("{actual_remote_path}"))'
            read_response = session.run_ps(read_cmd)
            b64_data = safe_strip(read_response.std_out)

            if read_response.status_code != 0 or not b64_data:
                result["error"] = f"Failed to read file: {safe_strip(read_response.std_err)}"
                return result

            # Decode and save
            file_bytes = base64.b64decode(b64_data)
        else:
            # Chunked read for large files
            total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
            all_bytes = b""

            for i in range(total_chunks):
                offset = i * CHUNK_SIZE
                length = min(CHUNK_SIZE, file_size - offset)

                chunk_cmd = f'''
$stream = [System.IO.File]::OpenRead("{actual_remote_path}")
$buffer = New-Object byte[] {length}
$stream.Position = {offset}
$stream.Read($buffer, 0, {length}) | Out-Null
$stream.Close()
[Convert]::ToBase64String($buffer)
'''
                chunk_response = session.run_ps(chunk_cmd)
                chunk_b64 = safe_strip(chunk_response.std_out)

                if chunk_response.status_code != 0 or not chunk_b64:
                    result["error"] = f"Failed at chunk {i+1}/{total_chunks}"
                    return result

                all_bytes += base64.b64decode(chunk_b64)

            file_bytes = all_bytes

        # Step 4: Save locally
        filename = os.path.basename(actual_remote_path)
        local_path = os.path.join(local_save_dir, filename)

        # Handle duplicate filenames
        if os.path.exists(local_path):
            name, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(local_path):
                local_path = os.path.join(local_save_dir, f"{name}_{counter}{ext}")
                counter += 1

        with open(local_path, "wb") as f:
            f.write(file_bytes)

        result["success"] = True
        result["local_path"] = local_path
        result["file_size"] = len(file_bytes)
        result["remote_path"] = actual_remote_path
        return result

    except Exception as e:
        result["error"] = str(e)
        return result


def _download_via_smb(target_ip, username, password, remote_file_path, local_save_dir):
    """Download file via SMB/UNC path copy."""
    result = {
        "success": False,
        "local_path": "",
        "file_size": 0,
        "error": "",
        "method": "SMB-Copy"
    }

    try:
        # Convert C:\path\to\file to C$\path\to\file for UNC
        if ":" in remote_file_path:
            unc_path = remote_file_path.replace(":", "$", 1)
        else:
            # Assume C$ if no drive specified
            unc_path = f"C$\\{remote_file_path.lstrip('\\/')}"

        full_unc = f"\\\\{target_ip}\\{unc_path}"
        filename = os.path.basename(remote_file_path)
        local_path = os.path.join(local_save_dir, filename)

        # Auth
        subprocess.run(f'net use "\\\\{target_ip}\\C$" /user:{username} {password}', shell=True, capture_output=True)

        # Copy
        proc = subprocess.run(f'copy "{full_unc}" "{local_path}"', shell=True, capture_output=True)

        if proc.returncode == 0 and os.path.exists(local_path):
            result["success"] = True
            result["local_path"] = local_path
            result["file_size"] = os.path.getsize(local_path)
        else:
            result["error"] = safe_strip(proc.stderr)

        # Cleanup
        subprocess.run(f'net use "\\\\{target_ip}\\C$" /delete /y', shell=True, capture_output=True)
        return result

    except Exception as e:
        result["error"] = str(e)
        return result


def handle_file_command(target_ip, username, password, command_text):
    """
    Parse and handle file-related commands (open, download, extract).
    """
    # Find filename and action
    action_keywords = ["open", "download", "extract", "read", "copy", "transfer", "get"]
    action = "download"
    filename = command_text.strip()
    
    for keyword in action_keywords:
        if command_text.strip().lower().endswith(keyword):
            action = keyword
            filename = command_text.strip()[:-(len(keyword))].strip()
            break

    # Download first
    res = download_file_from_remote(target_ip, username, password, filename)

    if res["success"]:
        local_path = res["local_path"]
        size_kb = res["file_size"] / 1024
        msg = (
            f"✓ File transferred successfully!\n"
            f"  Remote: {res.get('remote_path', filename)} @ {target_ip}\n"
            f"  Local:  {local_path} ({size_kb:.1f} KB)\n"
        )

        if action == "open":
            try:
                os.startfile(local_path)
                msg += "  Status: Opened locally"
            except Exception as e:
                msg += f"  Note: Could not auto-open: {e}"
        
        elif action == "extract":
            ext = os.path.splitext(local_path)[1].lower()
            if ext == ".pdf":
                msg += f"\n-- EXTRACTED TEXT --\n{extract_pdf_text(local_path)[:2000]}"
            else:
                try:
                    with open(local_path, "r", encoding="utf-8", errors="replace") as f:
                        msg += f"\n-- FILE CONTENT --\n{f.read()[:2000]}"
                except Exception as e:
                    msg += f"\n  Status: Failed to read content: {e}"
        
        return {"success": True, "message": msg, "local_path": local_path}
    
    return {"success": False, "message": f"✗ Transfer failed: {res.get('error')}"}


def extract_pdf_text(pdf_path):
    """Extract text from a PDF."""
    try:
        import pdfplumber
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t: text += t + "\n"
        return text
    except Exception:
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(pdf_path)
            text = ""
            for page in reader.pages:
                t = page.extract_text()
                if t: text += t + "\n"
            return text
        except Exception:
            return "[Install pdfplumber or PyPDF2 for PDF extraction]"
