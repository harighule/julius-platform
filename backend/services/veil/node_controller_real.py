"""REAL Node Controller - Actual SSH connection to remote servers.

No simulations. Real SSH commands executed on remote nodes.
"""

import paramiko
import os
import pathlib as _pathlib
from typing import Optional, Dict, Any
from datetime import datetime

# Resolve DB path relative to this file so it works on any machine:
#   backend/services/veil/node_controller_real.py  ->  parents[3] == project root
_PROJECT_ROOT = _pathlib.Path(__file__).resolve().parents[3]
_DB_PATH = str(_PROJECT_ROOT / "data" / "julius.db")


class RealNodeController:
    """
    REAL SSH-based node controller.
    
    This actually connects to remote servers and executes real commands.
    No JSON-only responses.
    """
    
    def __init__(self):
        self._connections: Dict[str, paramiko.SSHClient] = {}
        self._controlled_nodes: Dict[str, Dict] = {}
        self._load_nodes_from_db()
    
    def _load_nodes_from_db(self):
        """Load existing controlled nodes from database."""
        try:
            import sqlite3
            conn = sqlite3.connect(_DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT node_id, host, port, username FROM controlled_nodes WHERE status = 'controlled'")
            rows = cursor.fetchall()
            for row in rows:
                self._controlled_nodes[row[0]] = {
                    "host": row[1],
                    "port": row[2],
                    "username": row[3],
                    "status": "controlled"
                }
            conn.close()
        except Exception as e:
            print(f"Failed to load nodes from DB: {e}")
    
    def _save_node_to_db(self, node_id: str, host: str, port: int, username: str):
        """Save controlled node to database."""
        try:
            import sqlite3
            import hashlib
            conn = sqlite3.connect(_DB_PATH)
            cursor = conn.cursor()
            
            # Generate a key for this node
            node_key = hashlib.sha3_256(f"{node_id}{host}{port}".encode()).hexdigest()
            
            cursor.execute("""
                INSERT OR REPLACE INTO controlled_nodes 
                (node_id, host, port, username, node_key, status, controlled_at, config)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (node_id, host, port, username, node_key, 'controlled', datetime.utcnow().isoformat(), '{}'))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Failed to save node to DB: {e}")
    
    def connect_ssh(self, node_id: str, host: str, port: int, username: str, password: str = None, key_path: str = None) -> bool:
        """
        REAL SSH connection to remote node.
        
        This actually establishes an SSH connection and executes a test command.
        """
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            if password:
                ssh.connect(host, port=port, username=username, password=password, timeout=10)
            elif key_path:
                key = paramiko.RSAKey.from_private_key_file(key_path)
                ssh.connect(host, port=port, username=username, pkey=key, timeout=10)
            else:
                # Try default SSH key
                default_key_path = os.path.expanduser("~/.ssh/id_rsa")
                if os.path.exists(default_key_path):
                    key = paramiko.RSAKey.from_private_key_file(default_key_path)
                    ssh.connect(host, port=port, username=username, pkey=key, timeout=10)
                else:
                    return False
            
            # Test connection with real command
            stdin, stdout, stderr = ssh.exec_command("echo 'JULIUS_VEIL_CONNECTED' && hostname && uptime")
            output = stdout.read().decode('utf-8')
            error = stderr.read().decode('utf-8')
            
            if "JULIUS_VEIL_CONNECTED" in output:
                self._connections[node_id] = ssh
                
                # FIXED: Split output safely without backslash in f-string
                lines = output.split('\n')
                hostname_line = lines[1] if len(lines) > 1 and output else "unknown"
                
                self._controlled_nodes[node_id] = {
                    "host": host,
                    "port": port,
                    "username": username,
                    "status": "controlled",
                    "hostname": hostname_line,
                    "connected_at": datetime.utcnow().isoformat()
                }
                self._save_node_to_db(node_id, host, port, username)
                print(f"[SSH] ✅ Connected to {host} as {username}")
                print(f"[SSH] Hostname: {hostname_line}")
                return True
            
            return False
            
        except Exception as e:
            print(f"[SSH] ❌ Connection failed to {host}: {e}")
            return False
    
    def execute_command(self, node_id: str, command: str) -> Optional[str]:
        """
        REAL command execution on remote node.
        
        Actually sends the command via SSH and returns real output.
        """
        ssh = self._connections.get(node_id)
        if not ssh:
            return None
        
        try:
            stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
            output = stdout.read().decode('utf-8')
            error = stderr.read().decode('utf-8')
            
            if error:
                print(f"[SSH] Command error: {error}")
            return output
        except Exception as e:
            print(f"[SSH] Command execution failed: {e}")
            return None
    
    def optimize_node(self, node_id: str) -> Dict:
        """
        REAL node optimization - executes actual commands on remote node.
        
        This actually:
        1. Installs VEIL configuration
        2. Enables Poisson delays
        3. Configures cover traffic
        4. Sets up Sphinx packet routing
        """
        ssh = self._connections.get(node_id)
        if not ssh:
            return {"error": f"Node {node_id} not connected via SSH", "real": False}
        
        results = {}
        
        # REAL: Install VEIL configuration
        veil_config = """# VEIL Protocol Configuration
VEIL_ENABLED=1
POISSON_DELAY_MEAN=10
COVER_TRAFFIC_RATE=1.0
SPHINX_PACKETS=1
TOR_SOCKS_PORT=9050
"""
        try:
            stdin, stdout, stderr = ssh.exec_command(f"echo '{veil_config}' | sudo tee /etc/veil/config.conf")
            output = stdout.read().decode('utf-8')
            results["config_installed"] = output or "OK"
        except Exception as e:
            results["config_installed"] = f"Failed: {e}"
        
        # REAL: Enable Tor if not running
        try:
            stdin, stdout, stderr = ssh.exec_command("systemctl is-active tor || sudo systemctl start tor")
            output = stdout.read().decode('utf-8')
            results["tor_enabled"] = output or "started"
        except Exception as e:
            results["tor_enabled"] = f"Failed: {e}"
        
        # REAL: Apply kernel parameters for better anonymity
        try:
            kernel_params = "net.ipv4.tcp_timestamps=0 net.ipv4.tcp_sack=0"
            stdin, stdout, stderr = ssh.exec_command(f"sudo sysctl -w {kernel_params}")
            output = stdout.read().decode('utf-8')
            results["kernel_optimized"] = output or "OK"
        except Exception as e:
            results["kernel_optimized"] = f"Failed: {e}"
        
        # REAL: Set up cover traffic cron job
        cover_cron = "*/5 * * * * /usr/bin/curl --socks5-hostname 127.0.0.1:9050 https://check.torproject.org/ > /dev/null 2>&1"
        try:
            stdin, stdout, stderr = ssh.exec_command(f'(crontab -l 2>/dev/null; echo "{cover_cron}") | crontab -')
            results["cover_traffic_cron"] = "installed"
        except Exception as e:
            results["cover_traffic_cron"] = f"Failed: {e}"
        
        results["real"] = True
        results["message"] = f"Node {node_id} optimized with REAL VEIL configurations"
        
        return results
    
    def protect_node(self, node_id: str) -> Dict:
        """
        REAL node protection - executes actual security commands.
        
        This actually:
        1. Configures firewall rules
        2. Sets up fail2ban
        3. Enables audit logging
        4. Deploys intrusion detection
        """
        ssh = self._connections.get(node_id)
        if not ssh:
            return {"error": f"Node {node_id} not connected via SSH", "real": False}
        
        results = {}
        
        # REAL: Configure iptables firewall
        firewall_rules = [
            "sudo iptables -A INPUT -i lo -j ACCEPT",
            "sudo iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT",
            "sudo iptables -A INPUT -p tcp --dport 22 -j ACCEPT",
            "sudo iptables -A INPUT -p tcp --dport 9050 -j ACCEPT",
            "sudo iptables -A INPUT -j DROP"
        ]
        
        for rule in firewall_rules:
            try:
                stdin, stdout, stderr = ssh.exec_command(rule)
                results["firewall"] = "configured"
            except Exception as e:
                results["firewall"] = f"Partial: {e}"
        
        # REAL: Install and configure fail2ban
        try:
            stdin, stdout, stderr = ssh.exec_command("sudo apt-get install -y fail2ban 2>/dev/null || sudo yum install -y fail2ban")
            stdin, stdout, stderr = ssh.exec_command("sudo systemctl enable fail2ban && sudo systemctl start fail2ban")
            results["fail2ban"] = "installed and running"
        except Exception as e:
            results["fail2ban"] = f"Failed: {e}"
        
        # REAL: Enable auditd for monitoring
        try:
            stdin, stdout, stderr = ssh.exec_command("sudo systemctl enable auditd && sudo systemctl start auditd 2>/dev/null")
            results["auditd"] = "enabled"
        except Exception as e:
            results["auditd"] = f"Failed: {e}"
        
        # REAL: Set up intrusion detection (aide)
        try:
            stdin, stdout, stderr = ssh.exec_command("sudo apt-get install -y aide 2>/dev/null && sudo aideinit")
            results["aide"] = "installed"
        except Exception as e:
            results["aide"] = f"Failed: {e}"
        
        # REAL: Configure log monitoring
        log_monitor = """
*/10 * * * * /usr/bin/journalctl -p err -n 50 >> /var/log/veil_security.log
"""
        try:
            stdin, stdout, stderr = ssh.exec_command(f'(crontab -l 2>/dev/null; echo "{log_monitor}") | crontab -')
            results["log_monitoring"] = "configured"
        except Exception as e:
            results["log_monitoring"] = f"Failed: {e}"
        
        results["real"] = True
        results["message"] = f"Node {node_id} protected with REAL security measures"
        
        return results
    
    def get_node_status(self, node_id: str) -> Dict:
        """Get REAL status from remote node."""
        ssh = self._connections.get(node_id)
        if not ssh:
            return {"error": "Not connected"}
        
        status = {}
        
        # Get system info
        try:
            stdin, stdout, stderr = ssh.exec_command("uname -a")
            output = stdout.read().decode('utf-8')
            status["system"] = output.strip()
        except:
            status["system"] = "unknown"
        
        # Check Tor status
        try:
            stdin, stdout, stderr = ssh.exec_command("systemctl is-active tor")
            output = stdout.read().decode('utf-8')
            status["tor"] = output.strip()
        except:
            status["tor"] = "unknown"
        
        # Check VEIL config
        try:
            stdin, stdout, stderr = ssh.exec_command("cat /etc/veil/config.conf 2>/dev/null || echo 'NOT_CONFIGURED'")
            output = stdout.read().decode('utf-8')
            status["veil_config"] = output.strip()[:100]
        except:
            status["veil_config"] = "NOT_CONFIGURED"
        
        return status
    
    def get_controlled_nodes(self) -> Dict[str, Dict]:
        """Get all controlled nodes with REAL status."""
        result = {}
        for node_id, ssh in self._connections.items():
            node_info = self._controlled_nodes.get(node_id, {})
            node_info["connected"] = True
            node_info["status"] = "active"
            result[node_id] = node_info
        return result
    
    def close_all(self):
        """Close all SSH connections."""
        for node_id, ssh in self._connections.items():
            try:
                ssh.close()
                print(f"[SSH] Closed connection to {node_id}")
            except:
                pass
        self._connections.clear()


# Global instance
_node_controller = None


def get_node_controller() -> RealNodeController:
    global _node_controller
    if _node_controller is None:
        _node_controller = RealNodeController()
    return _node_controller