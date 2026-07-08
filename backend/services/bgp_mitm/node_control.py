#!/usr/bin/env python3
import paramiko, time, threading, json, os, socket, subprocess
from datetime import datetime
from pathlib import Path
from .utils import setup_logging

logger = setup_logging("node_control")
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
NODES_FILE = BASE_DIR / "data" / "controlled_nodes.json"

class NodeController:
    def __init__(self):
        self.controlled_nodes = {}
        self.ssh_clients = {}
        self.load_nodes()
    
    def load_nodes(self):
        if NODES_FILE.exists():
            with open(NODES_FILE, "r") as f:
                self.controlled_nodes = json.load(f)
        else:
            self.controlled_nodes = {}
    
    def save_nodes(self):
        with open(NODES_FILE, "w") as f:
            json.dump(self.controlled_nodes, f, indent=2)
    
    def test_connection(self, host, port=22):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except:
            return False
    
    def connect_ssh(self, node_id, host, port=22, username=None, password=None, key_path=None):
        try:
            logger.info(f"[+] Attempting SSH to {host}:{port}")
            if not self.test_connection(host, port):
                logger.error(f"[!] SSH port {port} not open on {host}")
                return {"success": False, "error": "Port not open"}
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            if key_path:
                private_key = paramiko.RSAKey.from_private_key_file(key_path)
                client.connect(host, port, username, pkey=private_key, timeout=10)
            else:
                client.connect(host, port, username, password, timeout=10)
            self.ssh_clients[node_id] = client
            self.controlled_nodes[node_id] = {
                "node_id": node_id,
                "host": host,
                "port": port,
                "username": username,
                "connected_at": datetime.now().isoformat(),
                "status": "connected"
            }
            self.save_nodes()
            logger.info(f"[+] ✅ SSH connected to {node_id} at {host}")
            return {"success": True, "message": f"Connected to {host}"}
        except paramiko.AuthenticationException:
            logger.error(f"[!] Authentication failed for {host}")
            return {"success": False, "error": "Authentication failed"}
        except Exception as e:
            logger.error(f"[!] Connection failed: {e}")
            return {"success": False, "error": str(e)}
    
    def execute_command(self, node_id, command):
        if node_id not in self.ssh_clients:
            return {"success": False, "error": "Node not connected"}
        try:
            client = self.ssh_clients[node_id]
            stdin, stdout, stderr = client.exec_command(command, timeout=30)
            output = stdout.read().decode()
            error = stderr.read().decode()
            return {
                "success": True,
                "node_id": node_id,
                "command": command,
                "output": output,
                "error": error
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def discover_nodes(self, max_nodes=50):
        discovered = []
        try:
            result = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}"],
                capture_output=True, text=True
            )
            containers = result.stdout.strip().split('\n')
            for container in containers:
                if container:
                    discovered.append({
                        "node_id": container,
                        "host": "127.0.0.1",
                        "port": 22,
                        "nickname": container,
                        "type": "docker",
                        "status": "discovered"
                    })
        except Exception as e:
            logger.error(f"Docker discovery failed: {e}")
        for i in range(3):
            discovered.append({
                "node_id": f"test_node_{i+1}",
                "host": "127.0.0.1",
                "port": 2222 + i,
                "nickname": f"Test_{i+1}",
                "type": "simulated",
                "status": "discovered"
            })
        logger.info(f"[+] Discovered {len(discovered)} nodes")
        return discovered
    
    def attack_node(self, node_id, attack_type="mitm"):
        if node_id not in self.controlled_nodes:
            return {"success": False, "error": "Node not controlled"}
        logger.info(f"[+] Launching {attack_type} attack on {node_id}")
        return {
            "success": True,
            "node_id": node_id,
            "attack_type": attack_type,
            "status": "launched",
            "message": f"{attack_type} attack launched"
        }
    
    def get_controlled_nodes(self):
        return self.controlled_nodes
    
    def disconnect_node(self, node_id):
        if node_id in self.ssh_clients:
            self.ssh_clients[node_id].close()
            del self.ssh_clients[node_id]
        if node_id in self.controlled_nodes:
            self.controlled_nodes[node_id]['status'] = 'disconnected'
            self.save_nodes()
        return {"success": True, "message": f"Node {node_id} disconnected"}

_controller = None
def get_node_controller():
    global _controller
    if _controller is None:
        _controller = NodeController()
    return _controller

def discover_nodes(max_nodes=50):
    return get_node_controller().discover_nodes(max_nodes)
def control_node(node_id, host, port=22, username=None, password=None):
    return get_node_controller().connect_ssh(node_id, host, port, username, password)
def execute_on_node(node_id, command):
    return get_node_controller().execute_command(node_id, command)
def attack_node(node_id, attack_type="mitm"):
    return get_node_controller().attack_node(node_id, attack_type)
def get_controlled():
    return get_node_controller().get_controlled_nodes()
