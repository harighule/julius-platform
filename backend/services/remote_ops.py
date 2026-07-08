"""
JULIUS Remote Operations — Execute commands and file operations on LAN machines.
Supports SMB (Windows admin shares), WinRM/PowerShell Remoting, SSH, and PsExec.

Fixed to handle non-domain Windows machines properly:
  - WinRM uses Negotiate auth + TrustedHosts
  - SMB tries multiple credential formats
  - Fallback to PowerShell direct session with explicit credentials
"""

import os
import uuid
import logging
import socket
import subprocess
import platform
import asyncio
import winrm
from typing import Dict, Any, Optional, AsyncGenerator
from ..utils import safe_strip

logger = logging.getLogger(__name__)

# ── Stored Credentials for Remote Targets ────────────────────────────────
import json
_CREDS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database", "remote_creds.json")


def get_stored_credentials(target: str) -> tuple:
    """Get stored username/password for a target IP. Returns (username, password) or (None, None)."""
    try:
        if os.path.exists(_CREDS_FILE):
            with open(_CREDS_FILE, "r") as f:
                creds = json.load(f)
            if target in creds:
                return creds[target].get("username"), creds[target].get("password")
            # Check wildcard/default
            if "*" in creds:
                return creds["*"].get("username"), creds["*"].get("password")
    except Exception:
        pass
    return None, None


def store_credentials(target: str, username: str, password: str):
    """Store credentials for a target IP (or '*' for default)."""
    try:
        creds: Dict[str, Any] = {}
        if os.path.exists(_CREDS_FILE):
            with open(_CREDS_FILE, "r") as f:
                creds = json.load(f)
        # Add to in-memory cache
        creds.update({target: {"username": username, "password": password}})
        with open(_CREDS_FILE, "w") as f:
            json.dump(creds, f, indent=2)
        logger.info(f"Stored credentials for {target}")
    except Exception as e:
        logger.warning(f"Failed to store credentials: {e}")


def _resolve_credentials(target: str, username: Optional[str] = None, password: Optional[str] = None) -> tuple:
    """Resolve credentials: use provided ones, fall back to stored, then to None."""
    if username and password:
        return username, password
    stored_user, stored_pass = get_stored_credentials(target)
    return (username or stored_user, password or stored_pass)


# ── Local WinRM setup (run once) ─────────────────────────────────────────
_winrm_setup_done = False


def _ensure_local_winrm():
    """Ensure WinRM is configured on THIS machine to allow outbound connections."""
    global _winrm_setup_done
    if _winrm_setup_done:
        return
    try:
        # Check if WinRM service is running
        svc_check = subprocess.run(
            ["sc", "query", "WinRM"], capture_output=True, text=True, timeout=5
        )
        if "RUNNING" not in svc_check.stdout:
            # Try to start WinRM service
            subprocess.run(["sc", "start", "WinRM"], capture_output=True, text=True, timeout=10)
            logger.info("WinRM service started")

        # Set TrustedHosts using winrm.cmd (works even without WSMan provider loaded)
        subprocess.run(
            ["winrm", "set", "winrm/config/client", "@{TrustedHosts=\"*\"}"],
            capture_output=True, text=True, timeout=10
        )
        logger.info("Local WinRM TrustedHosts configured to '*'")
        _winrm_setup_done = True
    except Exception as e:
        logger.debug(f"WinRM local setup skipped: {e}")
        _winrm_setup_done = True  # Don't retry


def create_remote_folder(target: str, remote_path: str, username: Optional[str] = None, password: Optional[str] = None) -> Dict[str, Any]:
    """Create a folder on a remote machine. Tries multiple methods."""
    # Auto-resolve stored credentials
    username, password = _resolve_credentials(target, username, password)
    results = {"target": target, "path": remote_path, "success": False, "method": None, "error": None}
    errors = {}

    # Method 1: PowerShell Remoting (WinRM) — most reliable for Windows
    _ensure_local_winrm()
    winrm_result = _try_winrm_mkdir(target, remote_path, username, password)
    if winrm_result["success"]:
        results.update(winrm_result)
        return results
    errors["WinRM"] = winrm_result.get("error", "N/A")

    # Method 2: PowerShell New-PSDrive + SMB (explicit credential mapping)
    psdrive_result = _try_psdrive_mkdir(target, remote_path, username, password)
    if psdrive_result["success"]:
        results.update(psdrive_result)
        return results
    errors["PSDrive"] = psdrive_result.get("error", "N/A")

    # Method 3: SMB admin share (C$)
    smb_result = _try_smb_mkdir(target, remote_path, username, password)
    if smb_result["success"]:
        results.update(smb_result)
        return results
    errors["SMB(C$)"] = smb_result.get("error", "N/A")

    # Method 4: SMB Users share
    smb_users = _try_smb_users_share(target, remote_path, username, password)
    if smb_users["success"]:
        results.update(smb_users)
        return results
    errors["SMB(Users)"] = smb_users.get("error", "N/A")

    # Method 5: WMI remote process creation
    wmi_result = _try_wmi_mkdir(target, remote_path, username, password)
    if wmi_result["success"]:
        results.update(wmi_result)
        return results
    errors["WMI"] = wmi_result.get("error", "N/A")

    # Method 6: SSH
    ssh_result = _try_ssh_mkdir(target, remote_path, username, password)
    if ssh_result["success"]:
        results.update(ssh_result)
        return results
    errors["SSH"] = ssh_result.get("error", "N/A")

    error_lines = "\n".join([f"  {k}: {v}" for k, v in errors.items()])
    results["error"] = (
        f"Tried {len(errors)} methods, all failed:\n{error_lines}\n\n"
        f"To fix this, run ONE of these on the TARGET machine ({target}):\n\n"
        f"Option 1 — Enable WinRM (PowerShell as Admin on target):\n"
        f"  Enable-PSRemoting -Force -SkipNetworkProfileCheck\n"
        f"  Set-Item WSMan:\\localhost\\Client\\TrustedHosts -Value '*' -Force\n"
        f"  Set-NetFirewallRule -Name 'WINRM-HTTP-In-TCP' -Enabled True\n\n"
        f"Option 2 — Enable Admin Shares (run on target as Admin):\n"
        f"  reg add HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System "
        f"/v LocalAccountTokenFilterPolicy /t REG_DWORD /d 1 /f\n"
        f"  Then restart the target machine\n\n"
        f"Option 3 — Share a folder (GUI):\n"
        f"  Right-click folder → Properties → Sharing → Share → Add 'Everyone' with Read/Write"
    )
    return results


def execute_remote_command(target: str, command: str, username: Optional[str] = None, password: Optional[str] = None) -> Dict[str, Any]:
    """Execute a command on a remote machine using the robust V2 logic."""
    # Auto-resolve stored credentials
    username, password = _resolve_credentials(target, username, password)
    return execute_on_remote(target, username, password, command)


async def execute_remote_command_stream(target: str, command: str, username: Optional[str] = None, password: Optional[str] = None) -> AsyncGenerator[str, None]:
    """Execute a command on a remote machine and stream the output in real-time."""
    username, password = _resolve_credentials(target, username, password)
    _ensure_local_winrm()

    if username and password:
        ps_script = (
            f'$ErrorActionPreference = "Stop"; '
            f'$pw = ConvertTo-SecureString "{password}" -AsPlainText -Force; '
            f'$cred = New-Object System.Management.Automation.PSCredential("{username}", $pw); '
            f'Invoke-Command -ComputerName {target} -Credential $cred '
            f'-Authentication Negotiate -ScriptBlock {{ {command} }} | Out-String -Stream'
        )
    else:
        ps_script = (
            f'$ErrorActionPreference = "Stop"; '
            f'Invoke-Command -ComputerName {target} -ScriptBlock {{ {command} }} | Out-String -Stream'
        )

    try:
        process = await asyncio.create_subprocess_exec(
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        if process.stdout:
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                yield line.decode('utf-8', errors='replace')

        if process.stderr:
            err = await process.stderr.read()
            if err:
                yield err.decode('utf-8', errors='replace')

        await process.wait()
    except Exception as e:
        yield f"Stream Execution Error: {str(e)}\n"


def verify_remote_path(target: str, remote_path: str, username: Optional[str] = None, password: Optional[str] = None) -> Dict[str, Any]:
    """Check if a file or folder exists on a remote machine. Returns {'exists': bool}."""
    username, password = _resolve_credentials(target, username, password)
    result = {"target": target, "path": remote_path, "exists": False, "error": None}

    # Method 1: WinRM Test-Path
    _ensure_local_winrm()
    if username and password:
        ps_cmd = f'Test-Path "{remote_path}"'
        winrm = _try_winrm_exec(target, ps_cmd, username, password)
        if winrm["success"]:
            output = winrm.get("output", "").strip().lower()
            result["exists"] = output == "true"
            result["method"] = "WinRM"
            return result

    # Method 2: PSDrive UNC check
    unc = _to_unc_path(target, remote_path)
    if unc:
        # Authenticate first
        if username and password:
            parts = unc.split("\\")
            share_root = f"\\\\{target}\\{parts[3]}" if len(parts) >= 4 else f"\\\\{target}\\C$"
            subprocess.run(["net", "use", share_root, "/delete", "/y"],
                           capture_output=True, text=True, timeout=5)
            for user_fmt in [username, f"{target}\\{username}", f".\\{username}"]:
                auth = subprocess.run(
                    ["net", "use", share_root, f"/user:{user_fmt}", password],
                    capture_output=True, text=True, timeout=10
                )
                if auth.returncode == 0 or "already" in (auth.stderr + auth.stdout).lower():
                    break

        ps_script = f'Test-Path "{unc}"'
        check = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, text=True, timeout=10
        )
        result["exists"] = safe_strip(check.stdout).lower() == "true"
        result["method"] = "UNC"
        return result

    result["error"] = "Cannot verify — unable to convert path to UNC"
    return result


def list_remote_folder(target: str, remote_path: str, username: Optional[str] = None, password: Optional[str] = None) -> Dict[str, Any]:
    """List contents of a folder on a remote machine."""
    username, password = _resolve_credentials(target, username, password)

    # Method 1: WinRM Get-ChildItem
    _ensure_local_winrm()
    ps_cmd = f'Get-ChildItem -Path "{remote_path}" -Force | Select-Object Name, Mode, Length, LastWriteTime | Format-Table -AutoSize | Out-String -Width 200'
    winrm = _try_winrm_exec(target, ps_cmd, username, password)
    if winrm["success"]:
        return {"target": target, "path": remote_path, "success": True,
                "method": "WinRM", "contents": winrm.get("output", "(empty)")}

    # Method 2: UNC dir listing
    unc = _to_unc_path(target, remote_path)
    if unc:
        if username and password:
            parts = unc.split("\\")
            share_root = f"\\\\{target}\\{parts[3]}" if len(parts) >= 4 else f"\\\\{target}\\C$"
            subprocess.run(["net", "use", share_root, "/delete", "/y"],
                           capture_output=True, text=True, timeout=5)
            for user_fmt in [username, f"{target}\\{username}", f".\\{username}"]:
                auth = subprocess.run(
                    ["net", "use", share_root, f"/user:{user_fmt}", password],
                    capture_output=True, text=True, timeout=10
                )
                if auth.returncode == 0 or "already" in (auth.stderr + auth.stdout).lower():
                    break

        dir_result = subprocess.run(
            ["cmd", "/c", "dir", unc],
            capture_output=True, text=True, timeout=10
        )
        if dir_result.returncode == 0:
            return {"target": target, "path": remote_path, "success": True,
                    "method": "UNC/dir", "contents": safe_strip(dir_result.stdout)[:1000]}

    return {"target": target, "path": remote_path, "success": False,
            "error": f"Cannot list remote folder. WinRM: {winrm.get('error', 'N/A')}"}


def list_remote_shares(target: str) -> Dict[str, Any]:
    """List SMB shares on a remote machine."""
    try:
        result = subprocess.run(
            ["net", "view", f"\\\\{target}"],
            capture_output=True, text=True, timeout=10
        )
        return {"target": target, "output": result.stdout, "success": result.returncode == 0}
    except Exception as e:
        return {"target": target, "success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# Robust Remote Execution Logic (V2)
# ═══════════════════════════════════════════════════════════════════════════

def execute_winrm(target_ip, username, password, command, timeout=60):
    """
    Execute a command on a remote machine via WinRM with full error handling.
    Returns: dict with 'success', 'output', 'error', 'method'
    """
    result = {
        "success": False,
        "output": "",
        "error": "",
        "method": "WinRM",
        "target": target_ip
    }

    # Validate inputs — null-check everything
    if not target_ip or not safe_strip(target_ip):
        result["error"] = "Target IP is empty or None"
        return result

    if not username or not safe_strip(username):
        result["error"] = "Username is empty or None"
        return result

    if not password:
        result["error"] = "Password is empty or None"
        return result

    if not command or not safe_strip(command):
        result["error"] = "Command is empty or None"
        return result

    # Clean inputs
    target_ip = safe_strip(target_ip)
    username = safe_strip(username)
    command = safe_strip(command)

    # Try multiple WinRM connection methods
    methods = [
        ("pywinrm_ntlm", lambda: _try_pywinrm_library(target_ip, username, password, command, "ntlm")),
        ("pywinrm_basic", lambda: _try_pywinrm_library(target_ip, username, password, command, "basic")),
        ("powershell_invoke", lambda: _try_powershell_invoke(target_ip, username, password, command)),
        ("psexec_fallback", lambda: _try_psexec_fallback(target_ip, username, password, command)),
    ]

    errors = []
    for method_name, method_func in methods:
        try:
            logger.info(f"Trying {method_name} on {target_ip}")
            output = method_func()
            if output is not None:
                result["success"] = True
                result["output"] = safe_strip(output)
                result["method"] = method_name
                logger.info(f"{method_name} succeeded on {target_ip}")
                return result
        except Exception as e:
            error_msg = f"{method_name}: {str(e)}"
            errors.append(error_msg)
            logger.warning(error_msg)
            continue

    result["error"] = " | ".join(errors)
    return result


def _try_pywinrm_library(target_ip, username, password, command, auth_transport):
    """Execute via pywinrm library."""
    try:
        session = winrm.Session(
            f"http://{target_ip}:5985/wsman",
            auth=(username, password),
            transport=auth_transport,
            read_timeout_sec=60,
            operation_timeout_sec=50
        )
        # Use run_ps to handle PowerShell commands better
        response = session.run_ps(command)

        # Null-check everything before .strip()
        stdout = safe_strip(response.std_out) if response else ""
        stderr = safe_strip(response.std_err) if response else ""

        if response and response.status_code == 0:
            return stdout
        else:
            raise Exception(f"Exit code {response.status_code if response else 'None'}: {stderr}")
    except Exception as e:
        raise Exception(f"pywinrm ({auth_transport}): {str(e)}")


def _try_powershell_invoke(target_ip, username, password, command):
    """Execute via PowerShell Invoke-Command subprocess."""
    ps_script = f'''
$password = ConvertTo-SecureString '{password}' -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential('{username}', $password)
try {{
    $result = Invoke-Command -ComputerName {target_ip} -Credential $cred -ScriptBlock {{
        {command}
    }} -ErrorAction Stop
    Write-Output $result
}} catch {{
    Write-Error $_.Exception.Message
    exit 1
}}
'''
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
        capture_output=True,
        timeout=60
    )

    stdout = safe_strip(proc.stdout)
    stderr = safe_strip(proc.stderr)

    if proc.returncode == 0 and stdout:
        return stdout
    else:
        raise Exception(f"PowerShell Invoke: {stderr or 'No output'}")


def _try_psexec_fallback(target_ip, username, password, command):
    """Execute via PsExec as last resort."""
    try:
        proc = subprocess.run(
            [
                "PsExec.exe", f"\\\\{target_ip}",
                "-u", username, "-p", password,
                "-s", "-accepteula",
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-Command", command
            ],
            capture_output=True,
            timeout=60
        )

        stdout = safe_strip(proc.stdout)
        stderr = safe_strip(proc.stderr)

        if proc.returncode == 0:
            return stdout
        else:
            raise Exception(f"PsExec: {stderr or 'Unknown error'}")
    except FileNotFoundError:
        raise Exception("PsExec not found in PATH")


def execute_ssh(target_ip, username, password, command, port=22):
    """Execute command via SSH with proper null handling."""
    try:
        import paramiko
    except ImportError:
        return {"success": False, "error": "Paramiko not installed"}

    result = {
        "success": False,
        "output": "",
        "error": "",
        "method": "SSH",
        "target": target_ip
    }

    if not all([target_ip, username, password, command]):
        result["error"] = "Missing required parameter (target_ip, username, password, or command is None)"
        return result

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=safe_strip(target_ip),
            port=port,
            username=safe_strip(username),
            password=password,
            timeout=30
        )

        stdin, stdout, stderr = client.exec_command(safe_strip(command), timeout=60)

        output = safe_strip(stdout.read())
        error = safe_strip(stderr.read())
        exit_code = stdout.channel.recv_exit_status()

        client.close()

        if exit_code == 0:
            result["success"] = True
            result["output"] = output
        else:
            result["error"] = error or f"Exit code: {exit_code}"

    except Exception as e:
        result["error"] = f"SSH: {str(e)}"

    return result


def execute_on_remote(target_ip, username, password, command):
    """
    Master function: Try all methods to execute a command on a remote machine.
    Order: WinRM → SSH → Report failure with details
    """
    if not target_ip:
        return {"success": False, "error": "Target IP is None or empty", "output": "", "method": "none"}

    # Try WinRM first
    winrm_result = execute_winrm(target_ip, username, password, command)
    if winrm_result["success"]:
        return winrm_result

    # Try SSH
    ssh_result = execute_ssh(target_ip, username, password, command)
    if ssh_result["success"]:
        return ssh_result

    # All methods failed
    return {
        "success": False,
        "output": "",
        "error": f"All methods failed on {target_ip}: WinRM: {winrm_result['error']} | SSH: {ssh_result['error']}",
        "method": "none",
        "target": target_ip,
        "remediation_hint": "Run the JULIUS Remote Access Remediation script on the target machine"
    }


def launch_interactive_app_on_remote(target_ip, username, password, app_command):
    """
    Launch a GUI application on a remote machine's interactive desktop.
    Bypasses Session 0 isolation by targeting the active console session.
    """
    if not app_command or not safe_strip(app_command):
        return {"success": False, "error": "App command is None or empty"}

    cmd = safe_strip(app_command)
    task_name = f"JuliusLaunch_{uuid.uuid4().hex[:8]}"

    # Use a robust PowerShell script to handle modern/legacy task creation
    # 1. Sends a message to the desktop to confirm reachability
    # 2. Creates an INTERACTIVE task (/it)
    # 3. Runs and verifies the process exists
    ps_command = f'''
$cmd = '{cmd}'
$tn = "{task_name}"
$user = "{username}"
$pass = "{password}"

# Robust browser path detection (case-insensitive)
if ($cmd -ilike "brave*") {{
    $paths = @(
        "C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe",
        "C:\\Program Files (x86)\\BraveSoftware\\Brave-Browser\\Application\\brave.exe",
        "$env:LOCALAPPDATA\\BraveSoftware\\Brave-Browser\\Application\\brave.exe"
    )
    foreach ($p in $paths) {{ if (Test-Path $p) {{ $cmd = $p; break }} }}
}}
elseif ($cmd -ilike "chrome*") {{
    $paths = @(
        "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
        "$env:LOCALAPPDATA\\Google\\Chrome\\Application\\chrome.exe"
    )
    foreach ($p in $paths) {{ if (Test-Path $p) {{ $cmd = $p; break }} }}
}}
elseif ($cmd -ilike "edge*") {{
    $paths = @(
        "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
        "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
        "$env:LOCALAPPDATA\\Microsoft\\Edge\\Application\\msedge.exe"
    )
    foreach ($p in $paths) {{ if (Test-Path $p) {{ $cmd = $p; break }} }}
}}

# Step 1: Session Reachability Test
msg * "JULIUS Security Platform is opening $cmd interactively..." 2>$null

# Step 2: Create an INTERACTIVE task (/it)
# This is most robust via schtasks.exe /it when targeting a specific user session.
# We use backtick escaped quotes for the path.
$trValue = "`"$cmd`""
$create = & schtasks /create /f /sc ONCE /st 00:00 /tn $tn /tr $trValue /ru $user /rp $pass /it
if ($LASTEXITCODE -ne 0) {{ 
    Write-Error "Failed to create interactive task for $cmd. Ensure user '$user' is logged in. Result: $create"
    exit 1 
}}

# Step 3: Run the task
$run = & schtasks /run /tn $tn
if ($LASTEXITCODE -ne 0) {{ 
    # Clean up before exit
    schtasks /delete /f /tn $tn | Out-Null
    Write-Error "Failed to run interactive task $tn. Result: $run"
    exit 1 
}}

# Step 4: Verify process existence (wait 3s)
Start-Sleep -s 3
$procName = [System.IO.Path]::GetFileNameWithoutExtension($cmd)
$proc = Get-Process $procName -ErrorAction SilentlyContinue | Select-Object -First 1

if ($proc) {{
    Write-Output "SUCCESS: $cmd is now running in $user's interactive session (PID: $($proc.Id))"
}} else {{
    Write-Output "WARNING: Task reported success, but process '$procName' was not found after 3s. It may be running under a different parent."
}}

# Cleanup
schtasks /delete /f /tn $tn | Out-Null
'''
    return execute_on_remote(target_ip, username, password, ps_command)


def open_file_on_remote(target_ip, username, password, file_path):
    """Open a file or application on a remote machine's desktop."""
    if not file_path or not safe_strip(file_path):
        return {"success": False, "error": "File path is None or empty"}

    file_path = safe_strip(file_path).lower()

    # Detect if it's an app that needs interactive launch
    if file_path.endswith(".exe") or file_path.endswith(".lnk") or file_path in ["brave", "chrome", "edge", "notepad", "calc"]:
        return launch_interactive_app_on_remote(target_ip, username, password, file_path)

    # Otherwise, fallback to standard Start-Process (good for background tasks or simple files)
    # ... but for a "Cyber Ops Terminal", we usually want everything interactive if it's an "open" request.
    
    # Standard search logic from before
    ps_command = f'''
$filePath = "{file_path}"
if (-not (Test-Path $filePath)) {{
    $searchPaths = @(
        "$env:USERPROFILE\\Desktop",
        "$env:USERPROFILE\\Documents",
        "$env:USERPROFILE\\Downloads",
        "$env:PUBLIC\\Desktop",
        "C:\\Users"
    )
    $found = $null
    foreach ($searchPath in $searchPaths) {{
        $result = Get-ChildItem -Path $searchPath -Filter (Split-Path $filePath -Leaf) -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($result) {{
            $found = $result.FullName
            break
        }}
    }}
    if ($found) {{ $filePath = $found }}
    else {{ Write-Error "File not found: $filePath"; exit 1 }}
}}
Start-Process -FilePath $filePath
Write-Output "Opened: $filePath"
'''
    return execute_on_remote(target_ip, username, password, ps_command)


# ═══════════════════════════════════════════════════════════════════════════
# Legacy Helpers (Internal)
# ═══════════════════════════════════════════════════════════════════════════

def _try_winrm_mkdir(target: str, remote_path: str, username: Optional[str] = None, password: Optional[str] = None) -> Dict:
    """Create a folder on a remote machine via WinRM, then verify it exists."""
    try:
        # Create the folder AND verify it exists in one remote call
        ps_cmd = (
            f'New-Item -Path "{remote_path}" -ItemType Directory -Force -ErrorAction Stop | Out-Null; '
            f'$exists = Test-Path "{remote_path}"; '
            f'if ($exists) {{ Write-Output "VERIFIED:{remote_path}" }} '
            f'else {{ Write-Error "Folder creation failed — path does not exist after New-Item" }}'
        )
        result = _try_winrm_exec(target, ps_cmd, username, password)
        if result["success"] and "VERIFIED:" in result.get("output", ""):
            result["output"] = f"Folder verified at {remote_path}"
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


def _try_winrm_exec(target: str, command: str, username: str = None, password: str = None) -> Dict:
    """Legacy wrapper for execute_winrm."""
    return execute_winrm(target, username, password, command)


# ═══════════════════════════════════════════════════════════════════════════
# PSDrive — Map network drive with explicit credentials, then operate
# ═══════════════════════════════════════════════════════════════════════════

def _try_psdrive_mkdir(target: str, remote_path: str, username: Optional[str] = None, password: Optional[str] = None) -> Dict:
    """Create a folder using New-PSDrive to map a share with credentials, then mkdir.
    Includes post-creation verification via Test-Path on UNC."""
    try:
        path = remote_path.replace("/", "\\")
        # Determine the share and sub-path
        if len(path) >= 2 and path[1] == ":":
            drive = path[0].upper()
            rest = path[2:].lstrip("\\")
            share = f"\\\\{target}\\{drive}$"
            sub_path = rest
        else:
            share = f"\\\\{target}\\C$\\Users\\Public\\Desktop"
            sub_path = os.path.basename(path)

        unc_full = f"{share}\\{sub_path}"

        if username and password:
            # Build script: map drive, create folder, verify, cleanup
            ps_script = (
                f'$ErrorActionPreference = "Stop"; '
                f'$pw = ConvertTo-SecureString "{password}" -AsPlainText -Force; '
                f'$cred = New-Object System.Management.Automation.PSCredential("{username}", $pw); '
                # Remove any stale PSDrive
                f'Remove-PSDrive -Name "JuliusDrive" -Force -ErrorAction SilentlyContinue; '
                # Also disconnect stale net use for this share
                f'net use "{share}" /delete /y 2>$null; '
                # Map the drive with credentials
                f'New-PSDrive -Name "JuliusDrive" -PSProvider FileSystem -Root "{share}" -Credential $cred -ErrorAction Stop | Out-Null; '
                # Create the folder
                f'New-Item -Path "JuliusDrive:\\{sub_path}" -ItemType Directory -Force -ErrorAction Stop | Out-Null; '
                # Verify it exists on the mapped drive
                f'$exists = Test-Path "JuliusDrive:\\{sub_path}"; '
                f'Remove-PSDrive -Name "JuliusDrive" -Force -ErrorAction SilentlyContinue; '
                f'if ($exists) {{ Write-Output "VERIFIED:{unc_full}" }} '
                f'else {{ Write-Error "Folder was NOT created - verification failed" }}'
            )
        else:
            unc_path = f"{share}\\{sub_path}"
            ps_script = (
                f'New-Item -Path "{unc_path}" -ItemType Directory -Force -ErrorAction Stop | Out-Null; '
                f'$exists = Test-Path "{unc_path}"; '
                f'if ($exists) {{ Write-Output "VERIFIED:{unc_path}" }} '
                f'else {{ Write-Error "Folder was NOT created - verification failed" }}'
            )

        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True, text=True, timeout=20
        )

        stdout = result.stdout.strip()
        if result.returncode == 0 and "VERIFIED:" in stdout:
            verified_path = stdout.split("VERIFIED:", 1)[1].strip()
            return {"success": True, "method": "PSDrive+SMB", "output": f"Folder verified at {verified_path}"}
        elif result.returncode == 0:
            # Command succeeded but no VERIFIED tag — might be false positive
            return {"success": True, "method": "PSDrive+SMB (unverified)", "output": stdout[:200],
                    "warning": "Folder creation reported success but could not verify existence"}
        return {"success": False, "error": result.stderr.strip()[:300] or "PSDrive mkdir failed"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "PSDrive timed out (20s)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _try_psdrive_exec(target: str, command: str, username: Optional[str] = None, password: Optional[str] = None) -> Dict:
    """Execute a command by mapping a PSDrive to the remote machine, running CMD."""
    try:
        if not username or not password:
            return {"success": False, "error": "PSDrive exec requires credentials"}

        # For general command execution, PSDrive isn't ideal — skip
        return {"success": False, "error": "PSDrive only supports file operations"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# SMB Operations
# ═══════════════════════════════════════════════════════════════════════════

def _try_smb_mkdir(target: str, remote_path: str, username: Optional[str] = None, password: Optional[str] = None) -> Dict:
    """Create folder via SMB admin share (C$ share)."""
    try:
        unc_path = _to_unc_path(target, remote_path)
        if not unc_path:
            return {"success": False, "error": "Cannot convert path to UNC format"}

        # Determine the share root (e.g., \\target\C$)
        parts = unc_path.split("\\")
        share_root = "\\\\".join([""] + parts[2:4]) if len(parts) >= 4 else f"\\\\{target}\\C$"
        # Normalize: \\target\C$
        share_root = f"\\\\{target}\\{parts[3]}" if len(parts) >= 4 else f"\\\\{target}\\C$"

        # Disconnect any stale connections
        subprocess.run(["net", "use", share_root, "/delete", "/y"],
                       capture_output=True, text=True, timeout=5)

        # Authenticate with credentials — try multiple formats
        if username and password:
            auth_success = False
            # Formats to try: user, TARGET\user, .\user
            user_formats = [
                username,
                f"{target}\\{username}",
                f".\\{username}",
            ]
            last_err = ""
            for user_fmt in user_formats:
                auth_result = subprocess.run(
                    ["net", "use", share_root, f"/user:{user_fmt}", password],
                    capture_output=True, text=True, timeout=10
                )
                if auth_result.returncode == 0 or "already" in (auth_result.stderr + auth_result.stdout).lower():
                    auth_success = True
                    break
                last_err = auth_result.stderr.strip()[:200]

            if not auth_success:
                return {"success": False, "error": last_err or "SMB auth failed with all user formats"}

        result = subprocess.run(
            ["cmd", "/c", "mkdir", unc_path],
            capture_output=True, text=True, timeout=10
        )

        if result.returncode == 0 or "already exists" in (result.stderr + result.stdout).lower():
            return {"success": True, "method": "SMB", "unc_path": unc_path}
        return {"success": False, "error": result.stderr.strip() or result.stdout.strip() or "mkdir failed"}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "SMB connection timed out"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _try_smb_users_share(target: str, remote_path: str, username: Optional[str] = None, password: Optional[str] = None) -> Dict:
    """Try to create folder via the Users share."""
    try:
        share = f"\\\\{target}\\Users"

        # Disconnect stale
        subprocess.run(["net", "use", share, "/delete", "/y"],
                       capture_output=True, text=True, timeout=5)

        # Connect with credentials
        if username and password:
            auth_success = False
            for user_fmt in [username, f"{target}\\{username}", f".\\{username}"]:
                auth = subprocess.run(
                    ["net", "use", share, f"/user:{user_fmt}", password],
                    capture_output=True, text=True, timeout=10
                )
                if auth.returncode == 0 or "already" in (auth.stderr + auth.stdout).lower():
                    auth_success = True
                    break
            if not auth_success:
                return {"success": False, "error": f"Users share auth failed: {auth.stderr.strip()[:150]}"}

        # Convert local path to UNC via Users share
        path = remote_path.replace("/", "\\")
        if "\\Users\\" in path:
            after_users = path.split("\\Users\\", 1)[1]
            unc_path = f"\\\\{target}\\Users\\{after_users}"
        else:
            unc_path = f"\\\\{target}\\Users\\Public\\Desktop\\{os.path.basename(path)}"

        result = subprocess.run(["cmd", "/c", "mkdir", unc_path],
                               capture_output=True, text=True, timeout=10)

        if result.returncode == 0 or "already exists" in (result.stderr + result.stdout).lower():
            return {"success": True, "method": "SMB (Users share)", "unc_path": unc_path}
        return {"success": False, "error": result.stderr.strip() or result.stdout.strip() or "mkdir via Users share failed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _try_wmi_mkdir(target: str, remote_path: str, username: Optional[str] = None, password: Optional[str] = None) -> Dict:
    """Use WMIC to create folder remotely."""
    try:
        wmi_cmd = f'cmd /c "mkdir \\"{remote_path}\\""'
        args = ["wmic", f"/node:{target}"]
        if username and password:
            args += [f"/user:{username}", f"/password:{password}"]
        args += ["process", "call", "create", wmi_cmd]

        result = subprocess.run(args, capture_output=True, text=True, timeout=15)

        if "ReturnValue = 0" in result.stdout or result.returncode == 0:
            return {"success": True, "method": "WMI", "output": result.stdout.strip()[:200]}
        return {"success": False, "error": result.stderr.strip()[:200] or result.stdout.strip()[:200] or "WMI call failed"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "WMI timed out"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _to_unc_path(target: str, remote_path: str) -> Optional[str]:
    """Convert a local path like C:\\Users\\... to UNC: \\\\target\\C$\\Users\\..."""
    path = remote_path.replace("/", "\\")
    if len(path) >= 2 and path[1] == ":":
        drive = path[0].upper()
        rest = path[2:].lstrip("\\")
        return f"\\\\{target}\\{drive}$\\{rest}"
    if path.startswith("Desktop") or path.startswith("desktop"):
        path_without_desktop = path.replace('Desktop\\', '').replace('desktop\\', '')
        return f"\\\\{target}\\C$\\Users\\Public\\Desktop\\{path_without_desktop}"
    return None


# ═══════════════════════════════════════════════════════════════════════════
# SSH Operations
# ═══════════════════════════════════════════════════════════════════════════

def _try_ssh_mkdir(target: str, remote_path: str, username: Optional[str] = None, password: Optional[str] = None) -> Dict:
    # On Windows targets, use md/mkdir. On Linux, use mkdir -p
    cmd_win = f'cmd /c "mkdir \\"{remote_path}\\""'
    cmd_linux = f'mkdir -p "{remote_path}"'

    # Try paramiko first
    result = _try_ssh_exec(target, cmd_win, username, password)
    if result["success"]:
        return result

    # Try Linux command
    result2 = _try_ssh_exec(target, cmd_linux, username, password)
    if result2["success"]:
        return result2

    return result  # Return first error


def _try_ssh_exec(target: str, command: str, username: Optional[str] = None, password: Optional[str] = None) -> Dict:
    """Legacy wrapper for execute_ssh."""
    return execute_ssh(target, username, password, command)


def _try_openssh_exec(target: str, command: str, username: Optional[str] = None, password: Optional[str] = None) -> Dict:
    """Try Windows built-in OpenSSH client."""
    try:
        user = username or "admin"
        ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
                   f"{user}@{target}", command]
        result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            return {"success": True, "method": "OpenSSH", "output": result.stdout.strip()}
        return {"success": False, "error": result.stderr.strip()[:200] or "OpenSSH failed"}
    except Exception as e:
        return {"success": False, "error": f"OpenSSH: {e}"}
