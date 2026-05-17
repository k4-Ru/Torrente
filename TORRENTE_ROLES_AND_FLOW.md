# Torrente Roles and Full Runtime Flow

## 1) Runtime Roles
- Tracker (`tracker.py`): registry for torrent metadata and swarm peers.
- Seeder peer (`peer.py`): owns full file, serves pieces.
- Leecher peer (`peer.py`): joins swarm, downloads/validates/reconstructs file.
- UI controller (`mainn.py`): starts tracker/peers and updates state in tabs.

Supporting modules:
- `piece_manager.py`: splitting, hashing, piece verification, reconstruction.
- `protocol.py`: peer-wire message framing (`type + length + JSON`).

## 2) Trigger Map (What starts what)

### 2.1 Start tracker
- Trigger file/function: `mainn.py:TorrenteApp._start_tracker()` (`mainn.py:423`)
- Creates `TrackerServer` (`mainn.py:425`)
- Runs `TrackerServer.start()` in a thread (`mainn.py:426`)

### 2.2 Start seeding
- Trigger file/function: `mainn.py:TorrenteApp._start_seeding()` (`mainn.py:463`)
- Creates `PeerNode` (`mainn.py:475`)
- Calls `PeerNode.share_file(filepath)` in a thread (`mainn.py:484`)

### 2.3 Start download
- Trigger file/function: `mainn.py:TorrenteApp._start_download()` (`mainn.py:546`)
- Creates `PeerNode` with progress/done callbacks (`mainn.py:560`)
- Calls `PeerNode.download_torrent(torrent_id, save_dir)` in a thread (`mainn.py:572`)

## 3) Tracker Role Flow

### 3.1 Server lifecycle
- `TrackerServer.start()` binds/listens on TCP (`tracker.py:31-38`)
- Accept loop spawns `_handle_client()` threads (`tracker.py:40-47`)
- Stop via `TrackerServer.stop()` (`tracker.py:53-56`)

### 3.2 Request routing
`_handle_client()` parses JSON and dispatches by `action` (`tracker.py:79-89`):
- `announce` -> `_handle_announce()` (`tracker.py:82-83`)
- `get_peers` -> `_handle_get_peers()` (`tracker.py:84-85`)
- `list_torrents` -> `_handle_list_torrents()` (`tracker.py:86-87`)

### 3.3 Swarm state model
- In-memory dictionary: `self.torrents` (`tracker.py:21`)
- Lock-protected mutation/read: `self.lock` (`tracker.py:22`)
- UI summary property: `swarm_info` (`tracker.py:210-220`)

## 4) Seeder Role Flow

Call path:
1. UI -> `_start_seeding()` (`mainn.py:463`)
2. Peer -> `share_file()` (`peer.py:59`)
3. Piece split/hash -> `PieceManager.load_file()` (`piece_manager.py:30`)
4. Announce to tracker -> `tracker_client_request(..., {"action":"announce", ...})` (`peer.py:70-75`)
5. Start peer piece server -> `_start_server()` (`peer.py:79`, `peer.py:126`)

Seeder specifics:
- `torrent_id` computed from filename+filesize SHA-1 truncated to 16 chars (`peer.py:62-64`)
- Seeder sends full `torrent_info` on announce (`peer.py:74`)

## 5) Leecher Role Flow

Call path:
1. UI -> `_start_download()` (`mainn.py:546`)
2. Peer -> `download_torrent()` (`peer.py:85`)
3. Join swarm announce (no `torrent_info`) (`peer.py:90-94`)
4. Tracker returns `torrent_info` + peers (`tracker.py:133-137`)
5. Initialize receiving state -> `prepare_download()` (`piece_manager.py:57`)
6. Start local peer server -> `_start_server()` (`peer.py:107`, `peer.py:126`)
7. Start engine -> `_download_loop()` thread (`peer.py:110`, `peer.py:198`)

## 6) Swarming Behavior (How peers cooperate)

### 6.1 Peer discovery and refresh
- Downloader periodically asks tracker for latest peers: `_refresh_peers()` (`peer.py:283-291`)
- Updates local peer list and removes self: `_update_peers()` (`peer.py:295-301`)

### 6.2 Piece scheduling and pulling
- Missing list from `missing_pieces()` (`piece_manager.py:97-102`)
- Loop tries up to first 5 missing pieces against known peers (`peer.py:224-226`)
- Piece pulled via `_request_piece(peer_ip, peer_port, index)` (`peer.py:247`)

### 6.3 Serving while leeching
- Leecher also runs `_serve_peer()` after `_start_server()` (`peer.py:155-175`)
- Any acquired pieces in `PieceManager.pieces` can be served to others
- This is actual swarm sharing beyond original seeder

## 7) Tracking Behavior and Actions

### 7.1 `announce`
- Seeder: includes `torrent_info` (`peer.py:70-75`)
- Leecher: only `torrent_id` + `peer_port` (`peer.py:90-94`)
- Handled in `_handle_announce()` (`tracker.py:110-137`)

### 7.2 `get_peers`
- Sent by downloader refresh loop (`peer.py:286-289`)
- Handled in `_handle_get_peers()` (`tracker.py:147-158`)

### 7.3 `list_torrents`
- Sent by UI list button path in `_list_torrents()` (`mainn.py:510-513`)
- Handled in `_handle_list_torrents()` (`tracker.py:160-171`)

## 8) Peer Wire Protocol

File: `protocol.py`
- Message types defined (`protocol.py:5-11`)
- Encoder: `encode()` (`protocol.py:16-20`)
- Decoder: `recv_message()` (`protocol.py:23-32`)
- Exact receive helper: `_recv_exact()` (`protocol.py:35-43`)

Used in peer flow:
- Request piece: send `MSG_REQUEST` (`peer.py:253`)
- Serve piece: respond `MSG_PIECE` (`peer.py:170-175`)
- Bitfield exchange path exists (`peer.py:161-164`, `peer.py:269-278`)

## 9) Integrity and Reconstruction

File: `piece_manager.py`
- Verify piece hash before save: `save_piece()` (`piece_manager.py:80-88`)
- Completion check: `is_complete()` (`piece_manager.py:108-109`)
- Rebuild output file in order: `reconstruct()` (`piece_manager.py:118-125`)

## 10) UI Update Paths

Progress updates:
- Peer triggers callback in `_download_loop()` (`peer.py:229-234`)
- UI receives at `_on_progress()` (`mainn.py:587`) -> `_update_progress_ui()` (`mainn.py:591`)

Completion updates:
- Peer triggers `done_callback` (`peer.py:244-245`)
- UI handles `_on_download_done()` (`mainn.py:597`) -> `_show_download_done()` (`mainn.py:600`)

Tracker swarm panel:
- Periodic refresh `_refresh_swarm_display()` (`mainn.py:614`)
- Reads `tracker_server.swarm_info` (`mainn.py:616`)

## 11) Ports and Transport
- Tracker TCP default: `6881` (`tracker.py:10`)
- Peer TCP default: `6882` (`peer.py:14`)
- Tracker socket read chunk: `BUFFER_SIZE=65536` (`tracker.py:11`, `tracker.py:191`)

## 12) Current Constraints
- Tracker state is memory-only; restart clears swarms (`tracker.py:21`)
- Piece scheduling is simple (not rarest-first) (`peer.py:224-226`)
- Some protocol constants are currently unused in active flow (`protocol.py:5`, `protocol.py:9-11`)
