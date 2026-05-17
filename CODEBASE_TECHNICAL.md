# Torrente Codebase Guide (Short + Technical)

## 1) Mental Model

Torrente has 3 runtime roles:
- Tracker: keeps swarm membership (`tracker.py`)
- Seeder/Leecher Peer: serves and downloads pieces (`peer.py`)
- UI Controller: starts/stops tracker/peer and updates UI (`mainn.py`)

Core support modules:
- Piece logic + hashing: `piece_manager.py`
- Peer wire format: `protocol.py`

## 2) How Files Work Together

### In-process calls (imports)
- UI imports tracker + peer classes (`mainn.py:11-12`)
- Peer imports tracker client helper, piece manager, and protocol (`peer.py:8-10`)

### Network calls (TCP)
- Peer <-> Tracker uses JSON request/response (`tracker.py:73-91`, `tracker.py:223-236`)
- Peer <-> Peer uses framed header + JSON body (`protocol.py:16-20`, `protocol.py:23-32`)

## 3) Fast Flow View

### A) Start Tracker
1. UI builds `TrackerServer` and starts it on a thread (`mainn.py:425-426`)
2. Tracker accepts clients and spawns handler threads (`tracker.py:40-47`)

### B) Start Seeding
1. `PeerNode.share_file()` splits file and hashes pieces (`peer.py:59-61`, `piece_manager.py:30-46`)
2. Peer computes `torrent_id` (`peer.py:62-64`)
3. Peer announces to tracker with torrent metadata (`peer.py:70-75`)
4. Peer starts piece server (`peer.py:79`, `peer.py:126-134`)

### C) Start Download
1. Peer announces with only `torrent_id` + `peer_port` (`peer.py:90-94`)
2. Tracker returns `torrent_info` + peers (`tracker.py:133-137`)
3. Peer download loop requests missing pieces (`peer.py:198-227`, `peer.py:247-254`)
4. Each piece is hash-verified before store (`piece_manager.py:80-88`)
5. On complete, file is reconstructed (`peer.py:240-243`, `piece_manager.py:118-125`)

## 4) Payloads by Role (Compact)

## 4.1 Peer -> Tracker: `announce`
Defined/sent:
- Seeder version (`peer.py:70-75`)
- Leecher version (`peer.py:90-94`)
Handled:
- Dispatch (`tracker.py:82-83`)
- Parse fields (`tracker.py:112-114`)

Seeder request example:
```json
{
  "action": "announce",
  "torrent_id": "a1b2c3d4e5f67890",
  "peer_port": 6882,
  "torrent_info": {
    "filename": "movie.mp4",
    "filesize": 734003200,
    "num_pieces": 2800,
    "piece_hashes": ["..."]
  }
}
```

Success response shape (`tracker.py:133-137`):
```json
{
  "status": "ok",
  "torrent_info": {"filename": "...", "filesize": 0, "num_pieces": 0, "piece_hashes": ["..."]},
  "peers": [{"ip": "192.168.1.10", "peer_port": 6882}]
}
```

Error shape (`tracker.py:119`):
```json
{"error": "torrent not known, send torrent_info"}
```

## 4.2 Peer -> Tracker: `get_peers`
Defined/sent: `peer.py:286-289`
Returned: `tracker.py:154-158`

Request:
```json
{"action": "get_peers", "torrent_id": "a1b2c3d4e5f67890"}
```

## 4.3 UI -> Tracker: `list_torrents`
Defined/sent: `mainn.py:511-513`
Returned: `tracker.py:165-171`

Request:
```json
{"action": "list_torrents"}
```

Response item shape:
```json
{"torrent_id": "...", "filename": "...", "filesize": 123, "num_peers": 2}
```

## 4.4 Peer <-> Peer messages
Message constants:
- `MSG_BITFIELD=1`, `MSG_REQUEST=2`, `MSG_PIECE=3` (`protocol.py:6-8`)

Payload examples:
- Bitfield request body: `{}` (`peer.py:275`)
- Bitfield response body: `{"pieces":[0,1,2]}` (`peer.py:164`)
- Piece request body: `{"index":42}` (`peer.py:253`)
- Piece response body: `{"index":42,"data":"<hex>"}` (`peer.py:170-173`)
- Missing piece response: `{"index":42,"data":null}` (`peer.py:175`)

## 5) Threading and Safety

- Tracker: accept loop + per-client threads (`tracker.py:40-47`, `tracker.py:73-96`)
- Peer server: accept loop + per-peer threads (`peer.py:136-145`, `peer.py:155-180`)
- Download: background loop thread (`peer.py:110`, `peer.py:198-245`)
- UI updates marshaled to Tk thread via `root.after(...)` (`mainn.py:486`, `mainn.py:588`, `mainn.py:598`)

Locks:
- Tracker swarm map lock (`tracker.py:22`, `tracker.py:116`, `tracker.py:150`, `tracker.py:162`, `tracker.py:213`)
- Peer known-peer list lock (`peer.py:296`)

## 6) Current Limits (Important)

- Tracker state is memory-only; restart loses swarms (`tracker.py:21`)
- Scheduler is simple first-fit; not rarest-first (`peer.py:224-226`)
- `MSG_HAVE` and `peer_bitfields` are currently unused in active flow (`peer.py:8`, `peer.py:39`)
