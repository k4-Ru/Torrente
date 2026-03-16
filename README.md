
---

## Requirements
python

## How to Run
```
python mainn.py 
python3 mainn.py
```


## Workflow

### Step 1 — Start the Tracker (ONE laptop only)
1. Open the **Tracker** tab
2. Click **Start Tracker**
3. Note the IP shown in the top-right corner — share this with everyone

### Step 2 — Share a File (any laptop)
1. Open the **Share** tab
2. Enter the Tracker IP (from Step 1)
3. Click **Browse** and pick any file
4. Click **Start Seeding**
5. A **Torrent ID** will appear — share this ID with whoever wants the file

### Step 3 — Download a File (any other laptop)
1. Open the **Download** tab
2. Enter the Tracker IP
3. Click **List Available Torrents** to see what's being shared (auto-fills Torrent ID)
   OR manually paste the Torrent ID
4. Choose a save folder
5. Click **Start Download**
6. Watch the progress bar fill up



## Ports Used

| Port | Purpose |
|------|---------|
| 6767 | Tracker server |
| 6882 | Peer file transfer |

Make sure firewalls allow these ports (or disable firewall for testing).

**Windows (run as admin):**
```
netsh advfirewall set allprofiles state off
```

**Linux:**
```
sudo ufw disable
```

**Mac:**
```
System Settings → Network → Firewall → Turn Off
```

---

## Files (madadagdagan pa maybe)

```
Torrente/
├── app.py           # GUI — run this
├── tracker.py       # Tracker server logic
├── peer.py          # Peer node (seeder + leecher)
├── piece_manager.py # File splitting, hashing, verification
└── protocol.py      # Message encoding/decoding
```

---

## for Troubleshooting

**"Cannot reach tracker"** → Check tracker laptop's IP, confirm firewall is off, confirm same WiFi
**Download stuck at 0%** → Make sure the seeder's app is still running and peer port (6882) is reachable
**Port already in use** → Change peer port in the Share/Download tab to any unused port (e.g. 6883, 6884...)
