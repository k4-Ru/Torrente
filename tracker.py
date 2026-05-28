import socket
import threading
import json
import time
import logging

logging.basicConfig(level=logging.INFO, format="[TRACKER] %(message)s")
log = logging.getLogger("tracker")

TRACKER_PORT = 6881
BUFFER_SIZE  = 65536
PEER_TIMEOUT_SECONDS = 30


class TrackerServer:
    def __init__(self, host="0.0.0.0", port=TRACKER_PORT, log_callback=None):
        self.host = host
        self.port = port
        self.log_callback = log_callback  # GUI callback for status updates

        # { torrent_id: { "info": <torrent_info_dict>, "peers": [{"ip","port","peer_port"}, ...] } }
        self.torrents: dict = {}
        self.lock = threading.Lock()
        self._running = False
        self._server_sock = None
        self._cleanup_thread = None








    
    
    
    
    #  Start / Stop the tracker server which is running on port 6881 
    def start(self):
        self._running = True
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((self.host, self.port))
        self._server_sock.listen(20)
        self._server_sock.settimeout(1.0)
        self._log(f"Tracker listening on port {self.port}")
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

        while self._running:
            try:
                conn, addr = self._server_sock.accept()
                threading.Thread(
                    target=self._handle_client,
                    args=(conn, addr),
                    daemon=True
                ).start()
            except socket.timeout:
                continue
            except OSError:
                break

    def stop(self):
        self._running = False
        if self._server_sock:
            self._server_sock.close()

    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    #  Client handler                                                      #

    def _handle_client(self, conn: socket.socket, addr):
        try:
            conn.settimeout(10.0)
            raw = self._recv_all(conn)
            if not raw:
                return
            msg = json.loads(raw.decode("utf-8"))
            action = msg.get("action")

            if action == "announce":
                response = self._handle_announce(msg, addr)
            elif action == "get_peers":
                response = self._handle_get_peers(msg)
            elif action == "list_torrents":
                response = self._handle_list_torrents()
            elif action == "heartbeat":
                response = self._handle_heartbeat(msg, addr)
            elif action == "leave":
                response = self._handle_leave(msg, addr)
            else:
                response = {"error": "unknown action"}

            conn.sendall(json.dumps(response).encode("utf-8"))

        except Exception as e:
            self._log(f"Error handling {addr}: {e}")
        finally:
            conn.close()

    
    
    
    
    
    
    
    
    
    
    #  Actions                                                             #

    def _handle_announce(self, msg: dict, addr) -> dict:
        """Peer announces itself as having a torrent."""
        torrent_id = msg["torrent_id"]
        peer_port  = msg["peer_port"]   # the port this peer listens on for piece requests
        instance_id = msg.get("instance_id")
        torrent_info = msg.get("torrent_info")  # only seeders send this

        with self.lock:
            if torrent_id not in self.torrents:
                if not torrent_info:
                    return {"error": "torrent not known, send torrent_info"}
                self.torrents[torrent_id] = {"info": torrent_info, "peers": []}

            swarm = self.torrents[torrent_id]

            # Update or add this peer
            peer_entry = {"ip": addr[0], "peer_port": peer_port, "instance_id": instance_id, "last_seen": time.time()}
            existing = [
                p for p in swarm["peers"]
                if p["ip"] == addr[0] and p["peer_port"] == peer_port and p.get("instance_id") == instance_id
            ]
            if not existing:
                swarm["peers"].append(peer_entry)
                self._log(f"Peer {addr[0]}:{peer_port} joined swarm for '{swarm['info']['filename']}'")
            else:
                existing[0]["last_seen"] = time.time()

            # Return torrent info + all other peers
            other_peers = [p for p in swarm["peers"] if not (p["ip"] == addr[0] and p["peer_port"] == peer_port)]
            return {
                "status": "ok",
                "torrent_info": swarm["info"],
                "peers": [
                    {"ip": p["ip"], "peer_port": p["peer_port"], "instance_id": p.get("instance_id")}
                    for p in other_peers
                ],
            }

    def _handle_heartbeat(self, msg: dict, addr) -> dict:
        """Refresh last_seen for a peer so tracker knows it is still online."""
        torrent_id = msg.get("torrent_id")
        peer_port = msg.get("peer_port")
        instance_id = msg.get("instance_id")
        if not torrent_id or not peer_port:
            return {"error": "missing torrent_id or peer_port"}

        with self.lock:
            if torrent_id not in self.torrents:
                return {"error": "torrent not found"}
            swarm = self.torrents[torrent_id]
            for peer in swarm["peers"]:
                if peer["ip"] == addr[0] and peer["peer_port"] == peer_port and peer.get("instance_id") == instance_id:
                    peer["last_seen"] = time.time()
                    return {"status": "ok"}
        return {"error": "peer not found"}

    def _handle_leave(self, msg: dict, addr) -> dict:
        """Remove a peer immediately when it shuts down.

        This makes the peer disappear from counts right away instead of waiting
        for the heartbeat timeout.
        """
        torrent_id = msg.get("torrent_id")
        peer_port = msg.get("peer_port")
        instance_id = msg.get("instance_id")
        if not torrent_id or not peer_port:
            return {"error": "missing torrent_id or peer_port"}

        with self.lock:
            if torrent_id not in self.torrents:
                return {"error": "torrent not found"}
            swarm = self.torrents[torrent_id]
            before = len(swarm["peers"])
            swarm["peers"] = [
                p for p in swarm["peers"]
                if not (p["ip"] == addr[0] and p["peer_port"] == peer_port and p.get("instance_id") == instance_id)
            ]
            removed = before - len(swarm["peers"])
            if removed:
                self._log(f"Peer {addr[0]}:{peer_port} left torrent '{swarm['info']['filename']}'")
                return {"status": "ok"}
        return {"error": "peer not found"}
            
            
            
            
            
            
            
            

    def _handle_get_peers(self, msg: dict) -> dict:
        """Return current peer list for a torrent."""
        torrent_id = msg["torrent_id"]
        with self.lock:
            if torrent_id not in self.torrents:
                return {"error": "torrent not found"}
            swarm = self.torrents[torrent_id]
            self._prune_stale_peers_locked(swarm)
            return {
                "status": "ok",
                "torrent_info": swarm["info"],
                "peers": [
                    {"ip": p["ip"], "peer_port": p["peer_port"], "instance_id": p.get("instance_id")}
                    for p in swarm["peers"]
                ],
            }
            
            
            
            
            
            
            

    def _handle_list_torrents(self) -> dict:
        """Return all available torrents."""
        with self.lock:
            result = []
            for tid, data in self.torrents.items():
                self._prune_stale_peers_locked(data)
                result.append({
                    "torrent_id": tid,
                    "filename": data["info"]["filename"],
                    "filesize": data["info"]["filesize"],
                    "num_peers": len(data["peers"]),
                })
            return {"status": "ok", "torrents": result}

    
    
    
    
    
    
    
    
    
    
    
    
    
    #  Helpers                                                             #
    def _recv_all(self, conn: socket.socket) -> bytes:
        chunks = []
        while True:
            try:
                chunk = conn.recv(BUFFER_SIZE)
                if not chunk:
                    break
                chunks.append(chunk)
                # Simple framing: try to parse; if it works, we're done
                try:
                    json.loads(b"".join(chunks))
                    break
                except json.JSONDecodeError:
                    continue
            except socket.timeout:
                break
        return b"".join(chunks)

    def _log(self, msg: str):
        log.info(msg)
        if self.log_callback:
            self.log_callback(msg)

    def _prune_stale_peers_locked(self, swarm: dict):
        """Remove peers whose heartbeat/announce is too old.

        Caller must hold self.lock.
        """
        now = time.time()
        before = len(swarm["peers"])
        swarm["peers"] = [p for p in swarm["peers"] if now - p.get("last_seen", 0) <= PEER_TIMEOUT_SECONDS]
        removed = before - len(swarm["peers"])
        if removed:
            self._log(f"Pruned {removed} stale peer(s)")

    def _cleanup_loop(self):
        while self._running:
            time.sleep(PEER_TIMEOUT_SECONDS)
            with self.lock:
                for swarm in self.torrents.values():
                    self._prune_stale_peers_locked(swarm)

    @property
    def swarm_info(self) -> dict:
        """Snapshot of current swarms for GUI display."""
        with self.lock:
            for data in self.torrents.values():
                self._prune_stale_peers_locked(data)
            return {
                tid: {
                    "filename": data["info"]["filename"],
                    "peers": len(data["peers"]),
                }
                for tid, data in self.torrents.items()
            }


def tracker_client_request(tracker_ip: str, tracker_port: int, msg: dict) -> dict:
    """Helper: send one request to tracker, return response."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(10.0)
        s.connect((tracker_ip, tracker_port))
        s.sendall(json.dumps(msg).encode("utf-8"))
        s.shutdown(socket.SHUT_WR)
        data = b""
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            data += chunk
    return json.loads(data.decode("utf-8"))
