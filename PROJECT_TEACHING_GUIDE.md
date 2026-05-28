# Torrente Teaching Guide

This document explains how the current project works, file-by-file, including imports, definitions, call flow, and purpose.

## 1) Big Picture Architecture

Torrente has 3 runtime roles:
- Tracker: central directory of torrents and peers (`tracker.py`) over TCP port `6881`.
- Peer: each user can seed and/or download pieces (`peer.py`) over TCP port `6882` (or custom).
- GUI app: controls tracker + peer actions (`mainn.py`, Tkinter desktop UI).

Data flow:
1. Seeder chooses a file in GUI.
2. Seeder peer splits file into pieces, hashes each piece, computes `torrent_id`.
3. Seeder announces to tracker: "I host torrent X on peer port Y".
4. Leecher enters tracker IP + torrent ID in GUI.
5. Leecher asks tracker for torrent metadata + peer list.
6. Leecher requests missing pieces directly from peers.
7. Piece hashes are verified, then file is reconstructed.

## 2) File-by-File Breakdown

## `protocol.py`

Purpose:
- Defines wire protocol for peer-to-peer messages (framing + message types).

Imports:
- `json`: serialize/deserialize payloads.
- `struct`: pack/unpack fixed-size headers.

Constants:
- `MSG_HANDSHAKE = 0`
- `MSG_BITFIELD = 1`
- `MSG_REQUEST = 2`
- `MSG_PIECE = 3`
- `MSG_HAVE = 4`
- `MSG_INTERESTED = 5`
- `MSG_CHOKE = 6`
- `HEADER_SIZE = 5` (1 byte type + 4 byte payload length)

Definitions:
- `encode(msg_type: int, payload: dict) -> bytes`
  - Called by: `PeerNode._serve_peer`, `PeerNode._request_piece`, `PeerNode._get_peer_bitfield`.
  - Does: builds `[type][len][json_body]` binary message.

- `recv_message(sock) -> tuple`
  - Called by: `PeerNode._serve_peer`, `PeerNode._request_piece`, `PeerNode._get_peer_bitfield`.
  - Does: reads one full framed message and returns `(msg_type, payload_dict)`.

- `_recv_exact(sock, n: int) -> bytes`
  - Called by: `recv_message` only.
  - Does: loops socket receives until exactly `n` bytes are read.

Why it matters:
- This is the contract peers use to understand each other.

---

## `piece_manager.py`

Purpose:
- Owns all file-piece logic: split, hash, track missing pieces, verify and rebuild.

Imports:
- `hashlib`: SHA-1 checksums.
- `os`: filenames/paths/sizes.
- `math`: ceiling piece count.
- `json`: currently imported but not used.

Constant:
- `PIECE_SIZE = 256 * 1024` (256 KB)

Class:
- `PieceManager`

State fields:
- `filepath`, `filename`, `filesize`
- `num_pieces`, `total_pieces`
- `piece_hashes` (ordered expected hashes)
- `pieces` (`{index: bytes}` of owned pieces)
- `pending` (`set` of currently-downloading piece indices)

Methods:
- `load_file(filepath)`
  - Called by: `PeerNode.share_file`.
  - Does: seeder-side file split + hash generation, fills `pieces` and metadata.

- `prepare_download(torrent_info, save_dir)`
  - Called by: `PeerNode.download_torrent`.
  - Does: leecher-side initialization from tracker-provided torrent metadata.

- `save_piece(index, data)`
  - Called by: `PeerNode._request_piece`.
  - Does: hash-checks piece before storing; rejects corrupted/wrong data.

- `get_piece(index)`
  - Called by: `PeerNode._serve_peer`.
  - Does: returns piece data to upload to another peer.

- `have_piece(index)`
  - Called by: currently unused.

- `missing_pieces()`
  - Called by: `PeerNode._download_loop`.

- `have_bitfield()`
  - Called by: `PeerNode._serve_peer` for `MSG_BITFIELD` response.

- `is_complete()`
  - Called by: `PeerNode._download_loop`, `reconstruct`.

- `progress()`
  - Called by: currently unused.

- `reconstruct()`
  - Called by: `PeerNode._download_loop` after complete download.
  - Does: writes ordered pieces to disk.

- `get_torrent_info()`
  - Called by: `load_file`; returned up to tracker/other peers.
  - Contains: filename, filesize, num_pieces, piece_hashes.

Why it matters:
- All integrity and assembly correctness is centralized here.

---

## `tracker.py`

Purpose:
- Implements central tracker server and tracker client helper.

Imports:
- `socket`: TCP server/client.
- `threading`: per-client concurrency + lock.
- `json`: request/response payload.
- `time`: imported but not used.
- `logging`: tracker logs.

Constants:
- `TRACKER_PORT = 6881`
- `BUFFER_SIZE = 65536`

Class:
- `TrackerServer(host="0.0.0.0", port=TRACKER_PORT, log_callback=None)`

State:
- `torrents`: in-memory map
  - `{torrent_id: {"info": torrent_info, "peers": [{"ip","peer_port"}]}}`
- `lock`: protects shared `torrents`.
- `_running`, `_server_sock`

Methods:
- `start()`
  - Called by: `TorrenteApp._start_tracker` (on background thread).
  - Does: bind/listen/accept loop; spins each client on `_handle_client` thread.

- `stop()`
  - Called by: `TorrenteApp._stop_tracker`.

- `_handle_client(conn, addr)`
  - Called by: `start()` per accepted connection.
  - Routes actions: `announce`, `get_peers`, `list_torrents`.

- `_handle_announce(msg, addr)`
  - Called by: `_handle_client`.
  - Seeder path: creates swarm if unknown and `torrent_info` provided.
  - Leecher path: joins existing swarm and gets metadata + peers.

- `_handle_get_peers(msg)`
  - Called by: `_handle_client`.
  - Returns latest peer list + torrent info.

- `_handle_list_torrents()`
  - Called by: `_handle_client`.
  - Returns summary list for GUI picker.

- `_recv_all(conn)`
  - Called by: `_handle_client`.
  - Reads until connection closes or JSON parse succeeds.

- `_log(msg)`
  - Called by: multiple tracker methods.
  - Forwards to logger and optional GUI callback.

- `swarm_info` property
  - Called by: `TorrenteApp._refresh_swarm_display`.
  - Returns GUI-friendly snapshot.

Module-level function:
- `tracker_client_request(tracker_ip, tracker_port, msg) -> dict`
  - Called by:
    - `PeerNode.share_file`
    - `PeerNode.download_torrent`
    - `PeerNode._refresh_peers`
    - `TorrenteApp._list_torrents`
  - Does: one request/one response TCP interaction with tracker.

Why it matters:
- Tracker is the coordination point; peer-to-peer file traffic does not pass through it.

---

## `peer.py`

Purpose:
- Implements peer behavior for both seeding and downloading.

Imports:
- `socket`, `threading`, `hashlib`, `time`, `logging`, `os`
- From `protocol`: `encode`, `recv_message`, `MSG_BITFIELD`, `MSG_REQUEST`, `MSG_PIECE`, `MSG_HAVE`
- From `piece_manager`: `PieceManager`
- From `tracker`: `tracker_client_request`, `TRACKER_PORT`

Constants:
- `PEER_SERVER_PORT = 6882`

Class:
- `PeerNode(host, peer_port, tracker_ip, tracker_port=TRACKER_PORT, log_callback=None, progress_callback=None, done_callback=None)`

Main methods and call graph:
- `share_file(filepath)`
  - Called by: `TorrenteApp._start_seeding` worker thread.
  - Flow: `PieceManager.load_file` -> compute `torrent_id` -> announce to tracker -> start peer server.

- `download_torrent(torrent_id, save_dir)`
  - Called by: `TorrenteApp._start_download` thread.
  - Flow: announce/join tracker -> `prepare_download` -> `_update_peers` -> start peer server -> start `_download_loop` thread.

- `_start_server()` -> `_accept_loop()` -> `_serve_peer(conn, addr)`
  - Called by: both `share_file` and `download_torrent`.
  - Handles incoming peer requests:
    - `MSG_BITFIELD`: replies with owned piece indexes.
    - `MSG_REQUEST`: replies with requested piece bytes (hex in JSON).

- `_download_loop()`
  - Called by: `download_torrent` (background thread).
  - Repeats until complete:
    - `_refresh_peers()` from tracker
    - `missing_pieces()`
    - for each missing piece, try peers via `_request_piece(...)`
    - fire `progress_callback` when piece saved.
  - On completion: `reconstruct()` + `done_callback`.

- `_request_piece(peer_ip, peer_port, index)`
  - Called by: `_download_loop`.
  - Sends `MSG_REQUEST`, reads `MSG_PIECE`, verifies/saves via `save_piece`.

- `_get_peer_bitfield(peer_ip, peer_port)`
  - Currently not used in download strategy.

- `_refresh_peers()`
  - Called by: `_download_loop`.

- `_update_peers(peers)` and `_get_known_peers_snapshot()`
  - Thread-safe peer list management.

- `stop()`
  - Called by GUI before replacing an existing node.

- `_log(msg)`
  - Logger + GUI callback.

Important note:
- `MSG_HAVE` is imported but not used; protocol has room for richer bittorrent-like behavior but current logic is simpler.

Important updates (recent changes):
- Downloaders now broadcast `MSG_HAVE` to known peers when they successfully save a piece; peers handle `MSG_HAVE` and update their local `peer_bitfields` so they have a more current view of which pieces other peers hold.
- When a downloader completes and reconstructs the file, it now re-announces to the tracker with `torrent_info` so the tracker can reflect that this peer is now a full seeder.
- These additions are designed to be minimal and non-blocking (background threads, best-effort notifications) to avoid impacting the existing download loop.

## Threading & Locks (Concurrency)

Where threads are used:
- `TrackerServer.start()` runs an accept loop and spawns one thread per client connection (`_handle_client`).
- `PeerNode` uses background threads for the peer server (`_start_server` -> `_accept_loop` -> per-connection `_serve_peer`) and for the download loop (`_download_loop`) and small background notifications (broadcasting `MSG_HAVE`, re-announce on complete).

Locks in the code:
- `TrackerServer.lock`: protects the shared `torrents` map when handlers create swarms, add peers, or read peer lists. This prevents two concurrent `announce` requests from corrupting the in-memory structure or losing updates.
- `PeerNode.lock`: used when updating or reading `known_peers` and when storing peer bitfields (`peer_bitfields`). It ensures the download loop can iterate over a consistent snapshot while other threads may be adding/removing peers.

Why this prevents race conditions:
- Without locks, two threads could concurrently modify a shared list or dict (for example, adding a peer while another thread reads the peer list). That can lead to lost updates, corrupted internal state, or exceptions from iterating mutated containers.
- The locks make the read-modify-write sequences atomic: a thread acquires the lock, performs updates or reads, then releases the lock so other threads see a consistent view.
- Using `self.lock` around small critical sections keeps contention low while providing safety for the shared state.

Remaining concurrency notes and suggestions:
- `PieceManager.pieces` is accessed by both the download thread (writes via `save_piece`) and the per-connection server threads (reads via `get_piece`). Currently there is no fine-grained lock inside `PieceManager`. This has worked in practice for small tests, but for production or heavy concurrency you should guard access to `pieces` (for example, by adding a `threading.Lock` inside `PieceManager` or by using `PeerNode.lock` when accessing pieces) to avoid subtle read/write races.
- All background notifications (broadcasts and re-announces) are done best-effort in separate daemon threads so they don't block the critical download path; their failures are logged but ignored to keep the system robust.
- If you later add more complex scheduling (choking/unchoking, rarest-first), consider using stronger synchronization patterns or a single-threaded event loop for the peer state machine to simplify reasoning about concurrency.

---

## `mainn.py` (Tkinter GUI entry point)

Purpose:
- Desktop app that controls tracker and peer functions and visualizes progress/logs.

Imports:
- UI: `tkinter`, `ttk`, `filedialog`, `messagebox`, `scrolledtext`
- Runtime: `threading`, `socket`, `os`, `sys`, `time`
- Local modules:
  - `TrackerServer`, `tracker_client_request`, `TRACKER_PORT`
  - `PeerNode`, `PEER_SERVER_PORT`

Top-level utility:
- `get_local_ip()`
  - Called by: `TorrenteApp.__init__`.
  - Uses UDP connect trick to determine LAN IP.

Class:
- `TorrenteApp(root)`

UI construction methods:
- `_apply_theme()`
- `_show_intro_splash()`
- `_build_ui()`
- `_tab_tracker(nb)`
- `_tab_share(nb)`
- `_tab_download(nb)`
- `_tab_log(nb)`

Tracker actions:
- `_start_tracker()`
  - Creates `TrackerServer`, starts it in daemon thread.
- `_stop_tracker()`

Share (Seeder) actions:
- `_pick_file()`
- `_start_seeding()`
  - Creates `PeerNode`, runs `share_file()` in thread.
- `_show_torrent_id(torrent_id)`

Download (Leecher) actions:
- `_pick_save_dir()`
- `_list_torrents()`
  - Calls `tracker_client_request(..., {"action": "list_torrents"})` in thread.
- `_populate_torrent_list(resp)`
- `_on_torrent_select(event)`
- `_start_download()`
  - Creates `PeerNode`, starts `download_torrent(...)` thread.

Progress + completion callbacks:
- `_on_progress(done, total, filename)`
- `_update_progress_ui(...)`
- `_on_download_done(filepath)`
- `_show_download_done(filepath)`

Tracker monitoring + logs:
- `_refresh_swarm_display()` (poll every 2s)
- `_log(msg)`
- `_append_log(text)`
- `_clear_log()`

Entrypoint:
- `if __name__ == "__main__":` creates `Tk`, instantiates `TorrenteApp`, runs `mainloop()`.

Why it matters:
- It is the orchestrator that wires tracker and peer classes to human actions.

---

## `README.md`

Purpose:
- Run instructions and operator workflow (which machine starts tracker, who seeds, who downloads).

---

## 3) End-to-End Runtime Sequence (Concrete)

Seeder side:
1. User clicks `Start Seeding` in GUI.
2. `mainn.py::_start_seeding` creates `PeerNode`.
3. `peer.py::share_file` calls `piece_manager.py::load_file`.
4. Peer announces to tracker via `tracker.py::tracker_client_request` (`action=announce` + `torrent_info`).
5. Tracker stores swarm and peer entry.
6. Peer starts piece server (`_start_server`).

Leecher side:
1. User enters tracker IP + torrent ID and clicks `Start Download`.
2. `mainn.py::_start_download` creates `PeerNode` and calls `download_torrent` in thread.
3. `download_torrent` announces to tracker (`action=announce`, no torrent_info).
4. Tracker returns torrent metadata + peers.
5. Leecher enters `_download_loop`, keeps refreshing peers (`get_peers`) and requesting pieces.
6. Each received piece is hash-verified (`save_piece`).
7. When all pieces are complete, `reconstruct` writes final file.

## 4) Key Engineering Limitations (Current Version)

- Tracker memory is in-process only; restart loses all swarm state.
- No authentication, encryption, or peer trust model.
- Simple scheduling strategy (no rarest-first, no choking/unchoking logic).
- No retry queues beyond simple loop; limited failure diagnostics.
- Some unused imports/constants (`json` in `piece_manager.py`, `MSG_HAVE` in `peer.py`, `time` in `tracker.py`).

## 5) If You Want to Present This Clearly

Say it as three layers:
1. Coordination layer (`tracker.py`) tells peers where others are.
2. Data layer (`peer.py` + `protocol.py`) moves and verifies file pieces.
3. UX layer (`mainn.py`) triggers actions and visualizes progress.

That framing is usually enough for both technical and non-technical panel questions.

## 6) `mainn.py` Actions Map (Controller Layer)

These are the user-triggered action methods and what each one does.

- `_start_tracker` ([mainn.py:426](/Users/carlnicolas/dev/Torrente/mainn.py:426))
  - Trigger: `Start Tracker` button.
  - Calls: `TrackerServer(...)` then `threading.Thread(target=self.tracker_server.start, daemon=True).start()`.
  - State updates: tracker status label, button enable/disable state, log.

- `_stop_tracker` ([mainn.py:436](/Users/carlnicolas/dev/Torrente/mainn.py:436))
  - Trigger: `Stop Tracker` button.
  - Calls: `self.tracker_server.stop()`.
  - State updates: clears tracker instance, status label, button state, log.

- `_pick_file` ([mainn.py:447](/Users/carlnicolas/dev/Torrente/mainn.py:447))
  - Trigger: `Browse` button in Share tab.
  - Calls: file dialog only.
  - State updates: `self.share_filepath`, selected filename/size label.

- `_pick_save_dir` ([mainn.py:456](/Users/carlnicolas/dev/Torrente/mainn.py:456))
  - Trigger: `Browse` button in Download tab.
  - Calls: directory dialog only.
  - State updates: `self.dl_save_dir`, save path label.

- `_start_seeding` ([mainn.py:468](/Users/carlnicolas/dev/Torrente/mainn.py:468))
  - Trigger: `Start Seeding` button.
  - Calls:
    - creates `PeerNode`
    - background `self.peer_node.share_file(self.share_filepath)`
    - on success: `_show_torrent_id(...)`
  - State updates: stops previous `peer_node` if any, starts new seed session.

- `_show_torrent_id` ([mainn.py:503](/Users/carlnicolas/dev/Torrente/mainn.py:503))
  - Trigger: callback after seeding starts.
  - Calls: UI pack/config only.
  - State updates: torrent ID panel shown, log entry.

- `_list_torrents` ([mainn.py:509](/Users/carlnicolas/dev/Torrente/mainn.py:509))
  - Trigger: `List Available Torrents` button.
  - Calls: `tracker_client_request(..., {"action": "list_torrents"})` in background thread.
  - State updates: passes response to `_populate_torrent_list`.

- `_populate_torrent_list` ([mainn.py:524](/Users/carlnicolas/dev/Torrente/mainn.py:524))
  - Trigger: callback from `_list_torrents`.
  - Calls: listbox writes only.
  - State updates: `self._torrent_list_data`, listbox rows.

- `_on_torrent_select` ([mainn.py:537](/Users/carlnicolas/dev/Torrente/mainn.py:537))
  - Trigger: selecting an item in listbox.
  - Calls: none external.
  - State updates: writes selected `torrent_id` into input field.

- `_start_download` ([mainn.py:546](/Users/carlnicolas/dev/Torrente/mainn.py:546))
  - Trigger: `Start Download` button.
  - Calls:
    - creates `PeerNode` with progress/done callbacks
    - background thread `self.peer_node.download_torrent(torrent_id, self.dl_save_dir)`
  - State updates: resets progress bar/status, starts leecher session.

- `_clear_log` ([mainn.py:685](/Users/carlnicolas/dev/Torrente/mainn.py:685))
  - Trigger: `Clear` button in Log tab.
  - Calls: none external.
  - State updates: clears log widget contents.

## 7) Example Payloads (Updated)

These payloads are what flow between modules.

### A) Tracker TCP payloads (`tracker_client_request`)

Seeder announce request:
```json
{
  "action": "announce",
  "torrent_id": "1a2b3c4d5e6f7890",
  "peer_port": 6882,
  "torrent_info": {
    "filename": "demo.pdf",
    "filesize": 7340032,
    "num_pieces": 28,
    "piece_hashes": ["sha1_piece_0", "sha1_piece_1"]
  }
}
```

Seeder announce response:
```json
{
  "status": "ok",
  "torrent_info": {
    "filename": "demo.pdf",
    "filesize": 7340032,
    "num_pieces": 28,
    "piece_hashes": ["sha1_piece_0", "sha1_piece_1"]
  },
  "peers": []
}
```

Leecher join request (same action, no `torrent_info`):
```json
{
  "action": "announce",
  "torrent_id": "1a2b3c4d5e6f7890",
  "peer_port": 6882
}
```

Get peers request:
```json
{
  "action": "get_peers",
  "torrent_id": "1a2b3c4d5e6f7890"
}
```

Get peers response:
```json
{
  "status": "ok",
  "torrent_info": {
    "filename": "demo.pdf",
    "filesize": 7340032,
    "num_pieces": 28,
    "piece_hashes": ["sha1_piece_0", "sha1_piece_1"]
  },
  "peers": [
    {"ip": "100.64.0.10", "peer_port": 6882},
    {"ip": "100.64.0.11", "peer_port": 6883}
  ]
}
```

List torrents request:
```json
{
  "action": "list_torrents"
}
```

List torrents response:
```json
{
  "status": "ok",
  "torrents": [
    {
      "torrent_id": "1a2b3c4d5e6f7890",
      "filename": "demo.pdf",
      "filesize": 7340032,
      "num_peers": 2
    }
  ]
}
```

### B) Peer-to-peer framed protocol payloads (`protocol.py`)

`MSG_REQUEST` payload:
```json
{"index": 7}
```

`MSG_PIECE` success payload:
```json
{
  "index": 7,
  "data": "<hex-encoded-bytes>"
}
```

`MSG_PIECE` missing/unavailable payload:
```json
{
  "index": 7,
  "data": null
}
```

`MSG_BITFIELD` response payload:
```json
{
  "pieces": [0, 1, 2, 7, 8]
}
```

Notes:
- Peer messages are framed as `[type(1 byte)][length(4 bytes)][json bytes]`.
- `MSG_HAVE`, `MSG_INTERESTED`, and `MSG_CHOKE` are defined constants but not active in current download logic.
