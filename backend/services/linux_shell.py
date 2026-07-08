"""
JULIUS Linux Shell — Built-in Linux terminal capabilities.
On Windows: routes commands through WSL (Windows Subsystem for Linux).
On Linux/macOS: executes natively via /bin/bash.

Features:
- Persistent session with working directory tracking
- Command history with output capture
- Package management (apt, yum, pacman detection)
- Safety guardrails for destructive commands
- Full autonomous control by the AI chatbot
"""

import os
import re
import logging
import subprocess
import platform
import time
import uuid
import shlex
from typing import Dict, Any, List, Optional
from datetime import datetime
from ..utils import safe_strip

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Shell Environment Detection
# ═══════════════════════════════════════════════════════════════════════════

_system = platform.system()
_is_windows = _system == "Windows"
_shell_backend = None  # "wsl", "git-bash", "powershell", "bash", "sh"


def _find_git_bash() -> Optional[str]:
    """Find Git Bash executable on Windows."""
    paths = [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\bin\bash.exe"),
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None


# Common Linux → PowerShell command translations
_PS_TRANSLATIONS = {
    "ls": "Get-ChildItem",
    "pwd": "Get-Location",
    "whoami": "$env:USERNAME",
    "hostname": "$env:COMPUTERNAME",
    "cat": "Get-Content",
    "echo": "Write-Output",
    "mkdir": "New-Item -ItemType Directory -Force -Path",
    "rmdir": "Remove-Item -Recurse -Force -Path",
    "cp": "Copy-Item",
    "mv": "Move-Item",
    "rm": "Remove-Item -Force",
    "touch": "New-Item -ItemType File -Force -Path",
    "clear": "Clear-Host",
    "date": "Get-Date",
    "ps": "Get-Process",
    "kill": "Stop-Process -Id",
    "curl": "Invoke-WebRequest -Uri",
    "wget": "Invoke-WebRequest -OutFile",
    "ping": "Test-Connection",
    "ipconfig": "Get-NetIPAddress",
    "ifconfig": "Get-NetIPAddress",
    "netstat": "Get-NetTCPConnection",
    "df": "Get-PSDrive -PSProvider FileSystem",
    "free": "Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize,FreePhysicalMemory",
    "uname": "Write-Output \"Windows $([System.Environment]::OSVersion.Version)\"",
    "uname -a": "[System.Environment]::OSVersion | Format-List",
    "uptime": "(Get-Date) - (Get-CimInstance Win32_OperatingSystem).LastBootUpTime | Format-Table Days,Hours,Minutes",
}


def _translate_to_powershell(command: str) -> str:
    """Translate basic Linux commands to PowerShell equivalents."""
    cmd = safe_strip(command)

    # Exact match first
    if cmd in _PS_TRANSLATIONS:
        return _PS_TRANSLATIONS[cmd]

    # Check if the first word has a translation
    parts = cmd.split(None, 1)
    if parts and parts[0] in _PS_TRANSLATIONS:
        ps_cmd = _PS_TRANSLATIONS[parts[0]]
        args = parts[1] if len(parts) > 1 else ""
        # Clean up Linux flags for PowerShell
        args = re.sub(r'\s*-[a-z]+', '', args)  # Strip single-char flags like -l, -a
        return f"{ps_cmd} {args}".strip()

    # If no translation found, try running as-is (many tools like python, git, node work)
    return cmd


def _detect_shell() -> str:
    """Detect the best available Linux shell backend.

    Priority on Windows:
      1. WSL with a real distro (Ubuntu, Debian, etc.) — NOT docker-desktop
      2. Git Bash (ships with Git for Windows)
      3. PowerShell (always available, limited Linux compat but works)

    Priority on Linux/macOS:
      1. /bin/bash
      2. /bin/sh
    """
    global _shell_backend

    if _is_windows:
        # ── 1. Check WSL with a REAL Linux distro ──────────────────────
        try:
            # List installed WSL distros
            list_result = subprocess.run(
                ["wsl", "--list", "--quiet"],
                capture_output=True, text=True, timeout=5
            )
            raw = safe_strip(list_result.stdout.replace("\x00", ""))
            distros = [safe_strip(d) for d in raw.splitlines() if safe_strip(d)]
            # Filter out docker-desktop distros — they don't have bash
            real_distros = [d for d in distros
                           if "docker" not in d.lower()]

            if real_distros:
                # We have a real distro — verify it actually works
                try:
                    test = subprocess.run(
                        ["wsl", "-d", real_distros[0], "--", "echo", "julius_ok"],
                        capture_output=True, text=True, timeout=8
                    )
                    if "julius_ok" in test.stdout:
                        _shell_backend = "wsl"
                        # Store the working distro name for later use
                        global _wsl_distro
                        _wsl_distro = real_distros[0]
                        logger.info(f"Linux shell: WSL distro '{_wsl_distro}' detected")
                        return "wsl"
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    pass
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # ── 2. Check Git Bash ──────────────────────────────────────────
        git_bash_paths = [
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\bash.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\bin\bash.exe"),
        ]
        for git_bash in git_bash_paths:
            if os.path.exists(git_bash):
                _shell_backend = "git-bash"
                logger.info(f"Linux shell: Git Bash detected at {git_bash}")
                return "git-bash"

        # ── 3. PowerShell fallback (always available on Windows) ───────
        _shell_backend = "powershell"
        logger.info("Linux shell: No WSL/Git Bash found, using PowerShell fallback")
        return "powershell"
    else:
        # Linux/macOS — native
        if os.path.exists("/bin/bash"):
            _shell_backend = "bash"
        elif os.path.exists("/bin/sh"):
            _shell_backend = "sh"
        else:
            _shell_backend = "sh"
        return _shell_backend

# Track which WSL distro to use (set during detection)
_wsl_distro: Optional[str] = None


# Auto-detect on import
_detect_shell()


# ═══════════════════════════════════════════════════════════════════════════
# Session Management
# ═══════════════════════════════════════════════════════════════════════════

class ShellSession:
    """Tracks a persistent shell session with working directory and history."""

    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self.cwd = "~"  # Current working directory in Linux context
        self.history: List[Dict[str, Any]] = []
        self.env: Dict[str, str] = {}
        self.created_at = datetime.utcnow().isoformat()
        self.last_used = self.created_at

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "cwd": self.cwd,
            "history_count": len(self.history),
            "created_at": self.created_at,
            "last_used": self.last_used,
            "backend": _shell_backend,
        }


_sessions: Dict[str, ShellSession] = {}


def get_session(session_id: str = "default") -> ShellSession:
    if session_id not in _sessions:
        _sessions[session_id] = ShellSession(session_id)
    return _sessions[session_id]


# ═══════════════════════════════════════════════════════════════════════════
# Command Execution
# ═══════════════════════════════════════════════════════════════════════════

# Commands that need confirmation (destructive)
DANGEROUS_PATTERNS = [
    r"rm\s+-rf\s+/(?!\S)",       # rm -rf / (root wipe)
    r"mkfs\.",                    # format filesystem
    r"dd\s+if=.*of=/dev/",       # overwrite disk
    r":\(\)\{\s*:\|:\s*&\s*\};:",  # fork bomb
    r"chmod\s+-R\s+777\s+/",     # recursive 777 on root
    r"shutdown",                  # shutdown system
    r"reboot",                    # reboot system
    r"init\s+0",                  # halt
]

# Commands that open interactive shells and will hang forever
INTERACTIVE_COMMANDS = {
    "su", "sudo su", "sudo -i", "sudo -s", "bash", "sh", "zsh",
    "fish", "csh", "tcsh", "ksh", "dash", "python", "python3",
    "node", "irb", "mysql", "psql", "mongo", "redis-cli",
    "ssh", "telnet", "ftp", "ncat", "nc",
    "katoolin3", "sudo katoolin3", "msfconsole", "sqlmap",
}


def _auto_fix_command(command: str) -> str:
    """Auto-fix commands to be non-interactive (add -y flags, etc.)."""
    cmd = safe_strip(command)
    # add-apt-repository needs -y to avoid 'Press [ENTER] to continue'
    if 'add-apt-repository' in cmd and '-y' not in cmd:
        cmd = cmd.replace('add-apt-repository', 'add-apt-repository -y')
    # apt-get needs -y for non-interactive
    if 'apt-get' in cmd and '-y' not in cmd and 'install' in cmd:
        cmd = cmd.replace('apt-get install', 'apt-get install -y')
    if 'apt install' in cmd and '-y' not in cmd:
        cmd = cmd.replace('apt install', 'apt install -y')
    return cmd


def _is_dangerous(command: str) -> Optional[str]:
    """Check if a command is potentially destructive."""
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command):
            return f"Command matches dangerous pattern: {pattern}"
    return None


def execute_linux(command: str, session_id: str = "default",
                  timeout: int = 30, allow_dangerous: bool = False) -> Dict[str, Any]:
    """
    Execute a Linux command. Returns structured result with output, errors, exit code.

    On Windows: routes through WSL.
    On Linux/macOS: runs natively via bash.
    """
    session = get_session(session_id)
    session.last_used = datetime.utcnow().isoformat()
    start_time = time.time()

    result = {
        "command": command,
        "success": False,
        "output": "",
        "error": "",
        "exit_code": -1,
        "backend": _shell_backend,
        "cwd": session.cwd,
        "duration_ms": 0,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Safety check
    if not allow_dangerous:
        danger = _is_dangerous(command)
        if danger:
            result["error"] = f"⚠️ BLOCKED: {danger}. Use allow_dangerous=True to override."
            result["exit_code"] = -2
            session.history.append(result)
            return result

    # Block interactive commands that open shells and hang forever
    cmd_stripped = safe_strip(command).rstrip(";")
    if cmd_stripped in INTERACTIVE_COMMANDS:
        result["error"] = (
            f"⚠️ '{cmd_stripped}' opens an interactive shell and cannot run in this terminal.\n"
            f"You are already running as root. Just type your commands directly."
        )
        result["exit_code"] = -2
        session.history.append(result)
        return result

    # Strip sudo prefix — we already run as root via WSL -u root
    if _shell_backend == "wsl" and safe_strip(command).startswith("sudo "):
        command = safe_strip(command)[5:]  # remove 'sudo '

    # Auto-fix interactive prompts (add -y flags etc.)
    command = _auto_fix_command(command)

    # Check backend availability
    if _shell_backend is None:
        result["error"] = (
            "No Linux shell available.\n\n"
            "On Windows, install WSL:\n"
            "  1. Open PowerShell as Admin\n"
            "  2. Run: wsl --install\n"
            "  3. Restart your computer\n"
            "  4. Set up a Linux username/password\n\n"
            "Or install Git Bash from: https://git-scm.com/downloads"
        )
        return result

    try:
        # Build the full command with cd to session's working directory
        # Handle cd commands to update session cwd
        cd_match = re.match(r'^\s*cd\s+(.*)', safe_strip(command))

        # We save the real exit code BEFORE running cwd-tracking commands
        # so that pwd/echo don't mask a failed command's return code
        _cwd_trailer = '\n_JULIUS_RC=$?; echo "___JULIUS_CWD___"; pwd; exit $_JULIUS_RC'

        if _shell_backend == "wsl":
            # Use the specific distro we validated during detection
            full_cmd = f'cd {session.cwd} 2>/dev/null; {command}'
            # Also capture the final working directory
            full_cmd += _cwd_trailer
            wsl_cmd = ["wsl"]
            if _wsl_distro:
                wsl_cmd += ["-d", _wsl_distro]
            
            # WSL: RUN AS ROOT to prevent sudo prompts blocking and timing out
            wsl_cmd += ["-u", "root"]
            cmd_args = wsl_cmd + ["--", "bash", "-c", full_cmd]

        elif _shell_backend == "git-bash":
            git_bash = _find_git_bash()
            if not git_bash:
                raise FileNotFoundError("Git Bash not found")
            full_cmd = f'cd {session.cwd} 2>/dev/null; {command}'
            full_cmd += _cwd_trailer
            cmd_args = [git_bash, "-c", full_cmd]

        elif _shell_backend == "powershell":
            ps_cmd = _translate_to_powershell(command)
            cmd_args = ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd]

        elif _shell_backend in ("bash", "sh"):
            shell = f"/bin/{_shell_backend}"
            full_cmd = f'cd {session.cwd} 2>/dev/null; {command}'
            full_cmd += _cwd_trailer
            cmd_args = [shell, "-c", full_cmd]
        else:
            result["error"] = f"Unknown backend: {_shell_backend}"
            return result

        import threading

        proc = subprocess.Popen(
            cmd_args,
            stdin=subprocess.DEVNULL,  # Prevent commands from waiting for input
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env={**os.environ, **session.env}
        )

        # Pre-insert into history so the UI can poll live streams
        session.history.append(result)
        if len(session.history) > 100:
            session.history = session.history[-100:]
            
        _history_appended = True

        raw_output = []
        timeout_expired = False

        def read_output():
            try:
                for line in proc.stdout:
                    raw_output.append(line)
                    current_out = "".join(raw_output)
                    if "___JULIUS_CWD___" in current_out:
                        current_out = current_out.split("___JULIUS_CWD___")[0]
                    result["output"] = current_out.rstrip("\n")
            except Exception:
                pass

        t = threading.Thread(target=read_output)
        t.start()

        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timeout_expired = True
            proc.kill()
            
        t.join(timeout=1)

        raw_output_str = "".join(raw_output)
        output_parts = raw_output_str.rsplit("___JULIUS_CWD___\n", 1)
        
        if len(output_parts) == 2:
            result["output"] = output_parts[0].rstrip("\n")
            new_cwd = safe_strip(output_parts[1])
            if new_cwd:
                session.cwd = new_cwd
                result["cwd"] = new_cwd
        else:
            result["output"] = raw_output_str.rstrip("\n")

        if timeout_expired:
            result["error"] = f"Command timed out after {timeout}s"
            result["exit_code"] = -3
            result["success"] = False
        else:
            result["error"] = ""
            result["exit_code"] = proc.returncode
            result["success"] = proc.returncode == 0

    except FileNotFoundError:
        result["error"] = f"Shell backend '{_shell_backend}' not found. Reinstall WSL or Git Bash."
        result["exit_code"] = -4
    except Exception as e:
        result["error"] = str(e)
        result["exit_code"] = -5

    result["duration_ms"] = round((time.time() - start_time) * 1000)

    # History was already pre-inserted at line 342 for live streaming
    # Do NOT append again here — that caused every command to show twice

    return result


def execute_script(script: str, session_id: str = "default",
                   timeout: int = 60) -> Dict[str, Any]:
    """Execute a multi-line bash script."""
    # Preprocess: strip sudo, auto-fix commands, and block interactive commands
    lines = script.strip().splitlines()
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            cleaned_lines.append(line)
            continue
        # Block interactive commands inside scripts
        if stripped.rstrip(";") in INTERACTIVE_COMMANDS:
            return {
                "command": script, "success": False, "output": "",
                "error": f"⚠️ '{stripped}' opens an interactive shell and cannot run in scripts.\n"
                         f"You are already running as root. Just type your commands directly.",
                "exit_code": -2, "backend": _shell_backend, "cwd": "~",
                "duration_ms": 0, "timestamp": datetime.utcnow().isoformat(),
            }
        # Strip sudo prefix — we already run as root via WSL -u root
        if _shell_backend == "wsl" and stripped.startswith("sudo "):
            line = line.replace("sudo ", "", 1)
        # Auto-fix interactive prompts (add -y flags etc.)
        line = _auto_fix_command(line)
        cleaned_lines.append(line)
    script = "\n".join(cleaned_lines)

    # For simple single-line commands, just use execute_linux directly
    if len(cleaned_lines) == 1 and safe_strip(cleaned_lines[0]):
        return execute_linux(safe_strip(cleaned_lines[0]), session_id, timeout)

    # Write to temp file and execute
    script_id = uuid.uuid4().hex[:8]
    write_cmd = f'cat > /tmp/julius_script_{script_id}.sh << \'JULIUS_EOF\'\n{script}\nJULIUS_EOF'
    execute_linux(write_cmd, session_id, timeout=10)
    result = execute_linux(f"export DEBIAN_FRONTEND=noninteractive; bash /tmp/julius_script_{script_id}.sh", session_id, timeout=timeout)
    execute_linux(f"rm -f /tmp/julius_script_{script_id}.sh", session_id, timeout=5)
    return result


# ═══════════════════════════════════════════════════════════════════════════
# High-Level Linux Operations (AI-Friendly)
# ═══════════════════════════════════════════════════════════════════════════

def install_linux_package(packages: str) -> Dict[str, Any]:
    """Install packages using the detected package manager."""
    # Detect package manager
    pm_check = execute_linux("which apt-get yum dnf pacman 2>/dev/null | head -1")
    pm_path = safe_strip(pm_check.get("output", ""))

    if "apt-get" in pm_path or not pm_path:
        cmd = f"sudo apt-get update -qq && sudo apt-get install -y {packages}"
    elif "dnf" in pm_path:
        cmd = f"sudo dnf install -y {packages}"
    elif "yum" in pm_path:
        cmd = f"sudo yum install -y {packages}"
    elif "pacman" in pm_path:
        cmd = f"sudo pacman -S --noconfirm {packages}"
    else:
        cmd = f"sudo apt-get install -y {packages}"

    return execute_linux(cmd, timeout=120, session_id="system")


def get_linux_system_info() -> Dict[str, Any]:
    """Get comprehensive Linux system info."""
    commands = {
        "hostname": "hostname",
        "kernel": "uname -r",
        "distro": "cat /etc/os-release 2>/dev/null | head -5 || lsb_release -a 2>/dev/null",
        "uptime": "uptime",
        "cpu": "nproc",
        "memory": "free -h | head -2",
        "disk": "df -h / | tail -1",
        "ip": "hostname -I 2>/dev/null || ip addr show 2>/dev/null | grep 'inet ' | head -3",
        "user": "whoami",
        "shell": "echo $SHELL",
    }
    info = {}
    for key, cmd in commands.items():
        result = execute_linux(cmd, timeout=5, session_id="system")
        info[key] = result.get("output", "").strip() if result.get("success") else result.get("error", "N/A")
    return info


def get_shell_status() -> Dict[str, Any]:
    """Get the status of the Linux shell subsystem."""
    status = {
        "available": _shell_backend is not None,
        "backend": _shell_backend,
        "host_os": _system,
        "sessions": {sid: s.to_dict() for sid, s in _sessions.items()},
    }

    if _shell_backend:
        # Quick test
        test = execute_linux("echo 'JULIUS Linux Shell Active'", timeout=5, session_id="system")
        status["test_result"] = safe_strip(test.get("output", ""))
        status["operational"] = test.get("success", False)

        if test.get("success"):
            # Get basic info
            info = execute_linux("uname -a", timeout=5, session_id="system")
            status["kernel"] = safe_strip(info.get("output", ""))
            distro = execute_linux("cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'\"' -f2", timeout=5, session_id="system")
            status["distro"] = safe_strip(distro.get("output", ""))
    else:
        status["operational"] = False
        status["install_instructions"] = (
            "WSL not detected. Install it:\n"
            "1. Open PowerShell as Admin\n"
            "2. wsl --install\n"
            "3. Restart computer"
        )

    return status


def get_command_history(session_id: str = "default", limit: int = 20) -> List[Dict]:
    """Get recent command history."""
    session = get_session(session_id)
    return session.history[-limit:]
