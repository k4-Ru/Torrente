import socket
import threading
import hashlib
import time
import logging
import os
import uuid

from protocol import encode, recv_message, MSG_BITFIELD, MSG_REQUEST, MSG_PIECE, MSG_HAVE
from piece_manager import PieceManager
from tracker import tracker_client_request, TRACKER_PORT

log = logging.getLogger("peer")

PEER_SERVER_PORT = 6882


class PeerNode:
    def __init__(
        self,
        host: str,
        peer_port: int,
        tracker_ip: str,
        tracker_port: int = TRACKER_PORT,
        log_callback=None,
        progress_callback=None,
        done_callback=None,
    ):
        self.host = host
        self.peer_port = peer_port
        self.tracker_ip = tracker_ip
        self.tracker_port = tracker_port
        self.log_callback = log_callback
        self.progress_callback = progress_callback
        self.done_callback = done_callback

        self.piece_manager = PieceManager()
        self.torrent_id = None
        self.instance_id = uuid.uuid4().hex
        self.known_peers = []   # [{"ip": ..., "peer_port": ...}] 
        self.peer_bitfields = {}  # { (ip, port): set of piece indices }
        self._running = False
        self._server_sock = None
        self._heartbeat_thread = None
        self.lock = threading.Lock()
        # Transfer stats
        self.uploaded_bytes = 0
        self.downloaded_bytes = 0
        self.uploaded_pieces = 0
        self.downloaded_pieces = 0














    #  Seeder: Share a file
    
    def share_file(self, filepath: str) -> str:
        """Load file, register with tracker, start serving. Returns torrent_id."""
        torrent_info = self.piece_manager.load_file(filepath)
        self.torrent_id = hashlib.sha1(
            (torrent_info["filename"] + str(torrent_info["filesize"])).encode()
        ).hexdigest()[:16]

        self._log(f"Sharing '{torrent_info['filename']}' as torrent {self.torrent_id}")
        self._log(f"Split into {torrent_info['num_pieces']} pieces")

        # Announce to tracker
        resp = tracker_client_request(self.tracker_ip, self.tracker_port, self._tracker_payload("announce", include_torrent_info=True))
        if resp.get("status") != "ok":
            raise RuntimeError(f"Tracker error: {resp}")

        self._start_server()
        self._start_heartbeat_loop()
        return self.torrent_id

    
    
    
    
    
    
    
    
    
    
    
    
    
    #  LeecherDownload a file

    def download_torrent(self, torrent_id: str, save_dir: str):
        """Join swarm and start downloading. Runs in background thread."""
        self.torrent_id = torrent_id

        # Get torrent info + peers from tracker
        resp = tracker_client_request(self.tracker_ip, self.tracker_port, self._tracker_payload("announce"))

        if resp.get("status") != "ok":
            self._log(f"Failed to join swarm: {resp.get('error')}")
            return

        torrent_info = resp["torrent_info"]
        self.piece_manager.prepare_download(torrent_info, save_dir)
        self._update_peers(resp.get("peers", []))

        self._log(f"Downloading '{torrent_info['filename']}' ({torrent_info['num_pieces']} pieces)")
        self._log(f"Found {len(self.known_peers)} peers in swarm")

        self._start_server()
        self._start_heartbeat_loop()

        # Start download loop in background
        threading.Thread(target=self._download_loop, daemon=True).start()

    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    #  Piece server (seeder role)

    def _start_server(self):
        # Avoid starting the server twice
        if self._running and self._server_sock:
            self._log("Peer server already running")
            return

        self._running = True
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            sock.bind((self.host, self.peer_port))
        except OSError as e:
            # Address already in use: try nearby ports before failing
            if getattr(e, 'errno', None) == 48 or 'Address already in use' in str(e):
                orig = self.peer_port
                found = False
                for p in range(self.peer_port + 1, self.peer_port + 21):
                    try:
                        sock.bind((self.host, p))
                        self.peer_port = p
                        found = True
                        break
                    except Exception:
                        continue
                if not found:
                    sock.close()
                    raise
                self._log(f"Port {orig} busy, bound peer server to alternate port {self.peer_port}")
                # If already announced, tell tracker about new port
                try:
                    if self.torrent_id:
                        tracker_client_request(self.tracker_ip, self.tracker_port, self._tracker_payload("announce"))
                except Exception:
                    pass
            else:
                sock.close()
                raise

        sock.listen(20)
        sock.settimeout(1.0)
        self._server_sock = sock
        self._log(f"Peer server listening on port {self.peer_port}")
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self):
        while self._running:
            try:
                conn, addr = self._server_sock.accept()
                threading.Thread(
                    target=self._serve_peer,
                    args=(conn, addr),
                    daemon=True
                ).start()
            except socket.timeout:
                continue
            except OSError:
                break
            
            
            
            
            

    def _serve_peer(self, conn: socket.socket, addr):
        """Handle incoming requests from another peer."""
        try:
            conn.settimeout(30.0)
            msg_type, payload = recv_message(conn)

            if msg_type == MSG_BITFIELD:
                # Peer wants to know what we have
                bitfield = self.piece_manager.have_bitfield()
                conn.sendall(encode(MSG_BITFIELD, {"pieces": bitfield}))

            elif msg_type == MSG_HAVE:
                # Peer notifies they obtained a piece; update our view of their bitfield
                index = payload.get("index")
                if index is not None:
                    # find peer_port for this ip from known_peers
                    with self.lock:
                        matches = [p for p in self.known_peers if p.get("ip") == addr[0]]
                    for p in matches:
                        key = (p.get("ip"), p.get("peer_port"))
                        self.peer_bitfields.setdefault(key, set()).add(index)

            elif msg_type == MSG_REQUEST:
                index = payload["index"]
                data = self.piece_manager.get_piece(index)
                if data is not None:
                    conn.sendall(encode(MSG_PIECE, {
                        "index": index,
                        "data": data.hex(),
                    }))
                    with self.lock:
                        try:
                            self.uploaded_bytes += len(data)
                            self.uploaded_pieces += 1
                        except Exception:
                            pass
                else:
                    conn.sendall(encode(MSG_PIECE, {"index": index, "data": None}))

        except Exception as e:
            pass  # Peer disconnected, that's fine
        finally:
            conn.close()














    #  Download loop (for leecher role)


    def _download_loop(self):
        """Main download logic: find missing pieces, request from peers."""
        stall_count = 0

        while not self.piece_manager.is_complete() and self._running:
            # Refresh peer list from tracker periodically
            self._refresh_peers()
            peers_snapshot = self._get_known_peers_snapshot()

            if not peers_snapshot:
                self._log("No peers available, waiting...")
                time.sleep(3)
                stall_count += 1
                if stall_count > 10:
                    self._log("No peers found after retries. Giving up.")
                    return
                continue

            stall_count = 0
            missing = self.piece_manager.missing_pieces()

            if not missing:
                time.sleep(0.1)
                continue

            # Try to download next missing piece from any available peer
            downloaded_any = False
            for piece_idx in missing[:5]:  # Try up to 5 at a time
                for peer in peers_snapshot:
                    success = self._request_piece(peer["ip"], peer["peer_port"], piece_idx)
                    if success:
                        downloaded_any = True
                        if self.progress_callback:
                            self.progress_callback(
                                len(self.piece_manager.pieces),
                                self.piece_manager.total_pieces,
                                self.piece_manager.filename,
                            )
                        break

            if not downloaded_any:
                time.sleep(0.5)

        if self.piece_manager.is_complete():
            self._log(f"Download complete! Saving '{self.piece_manager.filename}'...")
            self.piece_manager.reconstruct()
            self._log(f"File saved to: {self.piece_manager.filepath}")
            # Re-announce to tracker so it can reflect that this peer may now be a full seeder
            try:
                tracker_client_request(self.tracker_ip, self.tracker_port, self._tracker_payload("announce", include_torrent_info=True))
                self._log("Re-announced to tracker as seeder")
            except Exception:
                self._log("Failed to re-announce to tracker")
            if self.done_callback:
                self.done_callback(self.piece_manager.filepath)

    def _request_piece(self, peer_ip: str, peer_port: int, index: int) -> bool:
        """Request a specific piece from a peer. Returns True on success."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(10.0)
                s.connect((peer_ip, peer_port))
                s.sendall(encode(MSG_REQUEST, {"index": index}))
                msg_type, payload = recv_message(s)

                if msg_type == MSG_PIECE and payload.get("data"):
                    data = bytes.fromhex(payload["data"])
                    self.piece_manager.pending.add(index)
                    saved = self.piece_manager.save_piece(index, data)
                    if saved:
                        with self.lock:
                            try:
                                self.downloaded_bytes += len(data)
                                self.downloaded_pieces += 1
                            except Exception:
                                pass
                        # Notify other peers we now have this piece (non-blocking)
                        try:
                            threading.Thread(target=self._broadcast_have, args=(index,), daemon=True).start()
                        except Exception:
                            pass
                        return True
                    else:
                        self._log(f"Piece {index} failed hash check!")
                        return False
        except Exception:
            return False
        return False

    def _send_have_to_peer(self, peer_ip: str, peer_port: int, index: int):
        """Send a MSG_HAVE to a single peer (used by _broadcast_have)."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(3.0)
                s.connect((peer_ip, peer_port))
                s.sendall(encode(MSG_HAVE, {"index": index}))
        except Exception:
            pass

    def _broadcast_have(self, index: int):
        """Notify all known peers that we now have `index`.

        Runs in a background thread and ignores failures to keep behavior robust.
        """
        peers = self._get_known_peers_snapshot()
        for p in peers:
            # don't send to ourselves
            if p.get("instance_id") == self.instance_id:
                continue
            try:
                threading.Thread(target=self._send_have_to_peer, args=(p.get("ip"), p.get("peer_port"), index), daemon=True).start()
            except Exception:
                continue

    def _tracker_payload(self, action: str, include_torrent_info: bool = False) -> dict:
        payload = {
            "action": action,
            "torrent_id": self.torrent_id,
            "peer_port": self.peer_port,
            "instance_id": self.instance_id,
            "uploaded_bytes": self.uploaded_bytes,
            "downloaded_bytes": self.downloaded_bytes,
            "uploaded_pieces": self.uploaded_pieces,
            "downloaded_pieces": self.downloaded_pieces,
            "is_seeder": self.piece_manager.is_complete(),
        }
        if include_torrent_info:
            payload["torrent_info"] = self.piece_manager.get_torrent_info()
        return payload

    def _get_peer_bitfield(self, peer_ip: str, peer_port: int) -> set:
        """Ask a peer which pieces it has."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5.0)
                s.connect((peer_ip, peer_port))
                s.sendall(encode(MSG_BITFIELD, {}))
                msg_type, payload = recv_message(s)
                if msg_type == MSG_BITFIELD:
                    pieces = set(payload.get("pieces", []))
                    # store for quick lookup
                    with self.lock:
                        self.peer_bitfields[(peer_ip, peer_port)] = pieces
                    return pieces
        except Exception:
            pass
        return set()

    def _start_heartbeat_loop(self):
        """Periodically tell the tracker that this peer is still online."""
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return

        def run():
            while self._running:
                try:
                    tracker_client_request(self.tracker_ip, self.tracker_port, self._tracker_payload("heartbeat"))
                except Exception:
                    pass
                time.sleep(10)

        self._heartbeat_thread = threading.Thread(target=run, daemon=True)
        self._heartbeat_thread.start()
    
    
    
    
    

    def _refresh_peers(self):
        """Re-check tracker for updated peer list."""
        try:
            resp = tracker_client_request(self.tracker_ip, self.tracker_port, {
                "action": "get_peers",
                "torrent_id": self.torrent_id,
            })
            if resp.get("status") == "ok":
                self._update_peers(resp.get("peers", []))
        except Exception:
            pass

    def _update_peers(self, peers: list):
        with self.lock:
            # Filter out ourselves (same running instance)
            self.known_peers = [
                p for p in peers
                if p.get("instance_id") != self.instance_id
            ]

    def _get_known_peers_snapshot(self) -> list:
        """Thread-safe snapshot for iteration in download loop."""
        with self.lock:
            return list(self.known_peers)

    def stop(self):
        self._running = False
        try:
            if self.torrent_id:
                tracker_client_request(self.tracker_ip, self.tracker_port, self._tracker_payload("leave"))
        except Exception:
            pass
        if self._server_sock:
            try:
                self._server_sock.close()
            finally:
                self._server_sock = None

    def _log(self, msg: str):
        log.info(msg)
        if self.log_callback:
            self.log_callback(msg)
