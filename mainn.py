import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import socket
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tracker import TrackerServer, tracker_client_request, TRACKER_PORT
from peer import PeerNode, PEER_SERVER_PORT


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"



class TorrenteApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Torrente")
        self.root.geometry("860x640")

        self.local_ip = get_local_ip()
        self.tracker_server = None
        self.peer_node = None

        self._build_ui()

    def _build_ui(self):
        # Header
        header = tk.Frame(self.root)
        header.pack(fill="x", padx=10, pady=5)
        tk.Label(header, text="Torrente").pack(side="left")
        tk.Label(header, text=f"Your IP: {self.local_ip}").pack(side="right")

        ttk.Separator(self.root).pack(fill="x", padx=10)

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=10, pady=5)

        self._tab_tracker(nb)
        self._tab_share(nb)
        self._tab_download(nb)
        self._tab_log(nb)













    # Tab: Tracker 

    def _tab_tracker(self, nb):
        tab = tk.Frame(nb)
        nb.add(tab, text="Tracker")

        tk.Label(tab, text="Tracker Server", font=("TkDefaultFont", 11, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
        tk.Label(tab, text="One laptop runs the tracker. Others connect to it by IP.").pack(anchor="w", padx=10)

        # Status
        status_frame = tk.Frame(tab, relief="groove", bd=1)
        status_frame.pack(fill="x", padx=10, pady=8)
        self.tracker_status_text = tk.Label(status_frame, text="Tracker not running")
        self.tracker_status_text.pack(side="left", padx=8, pady=6)

        # Port config
        port_frame = tk.Frame(tab)
        port_frame.pack(anchor="w", padx=10, pady=4)
        tk.Label(port_frame, text="Tracker Port:").pack(side="left")
        self.tracker_port_var = tk.StringVar(value=str(TRACKER_PORT))
        tk.Entry(port_frame, textvariable=self.tracker_port_var, width=8).pack(side="left", padx=5)

        # Buttons
        btn_frame = tk.Frame(tab)
        btn_frame.pack(anchor="w", padx=10, pady=4)
        self.start_tracker_btn = tk.Button(btn_frame, text="Start Tracker", command=self._start_tracker)
        self.start_tracker_btn.pack(side="left", padx=(0, 5))
        self.stop_tracker_btn = tk.Button(btn_frame, text="Stop Tracker", command=self._stop_tracker, state="disabled")
        self.stop_tracker_btn.pack(side="left")

        ttk.Separator(tab).pack(fill="x", padx=10, pady=8)

        # Swarm info
        tk.Label(tab, text="Active Swarms", font=("TkDefaultFont", 10, "bold")).pack(anchor="w", padx=10)
        self.swarm_frame = tk.Frame(tab)
        self.swarm_frame.pack(fill="both", expand=True, padx=10, pady=4)
        self.swarm_label = tk.Label(self.swarm_frame, text="No active swarms")
        self.swarm_label.pack(anchor="w")

        self._refresh_swarm_display()














    #  Tab: Share 

    def _tab_share(self, nb):
        tab = tk.Frame(nb)
        nb.add(tab, text="Share")

        tk.Label(tab, text="Share a File", font=("TkDefaultFont", 11, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
        tk.Label(tab, text="Select a file to seed. Others can download it by entering the Torrent ID.").pack(anchor="w", padx=10)

        # Tracker IP
        row1 = tk.Frame(tab)
        row1.pack(anchor="w", padx=10, pady=4)
        tk.Label(row1, text="Tracker IP:", width=14, anchor="w").pack(side="left")
        self.share_tracker_ip = tk.Entry(row1, width=20)
        self.share_tracker_ip.insert(0, self.local_ip)
        self.share_tracker_ip.pack(side="left")

        # Peer port
        row2 = tk.Frame(tab)
        row2.pack(anchor="w", padx=10, pady=4)
        tk.Label(row2, text="My Peer Port:", width=14, anchor="w").pack(side="left")
        self.share_peer_port = tk.Entry(row2, width=8)
        self.share_peer_port.insert(0, str(PEER_SERVER_PORT))
        self.share_peer_port.pack(side="left")

        ttk.Separator(tab).pack(fill="x", padx=10, pady=8)

        # File picker
        file_row = tk.Frame(tab)
        file_row.pack(fill="x", padx=10, pady=4)
        tk.Label(file_row, text="File:", width=14, anchor="w").pack(side="left")
        self.share_file_label = tk.Label(file_row, text="No file selected", anchor="w")
        self.share_file_label.pack(side="left", fill="x", expand=True)
        tk.Button(file_row, text="Browse", command=self._pick_file).pack(side="left")

        self.share_filepath = None

        ttk.Separator(tab).pack(fill="x", padx=10, pady=8)

        tk.Button(tab, text="Start Seeding", command=self._start_seeding).pack(anchor="w", padx=10)

        # Torrent ID display (hidden until seeding starts)
        self.torrent_id_frame = tk.Frame(tab, relief="groove", bd=1)
        self.torrent_id_label = tk.Label(self.torrent_id_frame, text="", anchor="w", justify="left")













    # Tab: Download 

    def _tab_download(self, nb):
        tab = tk.Frame(nb)
        nb.add(tab, text="Download")

        tk.Label(tab, text="Download a File", font=("TkDefaultFont", 11, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
        tk.Label(tab, text="Enter the Tracker IP and Torrent ID to join a swarm and download.").pack(anchor="w", padx=10)

        # Tracker IP
        row1 = tk.Frame(tab)
        row1.pack(anchor="w", padx=10, pady=4)
        tk.Label(row1, text="Tracker IP:", width=14, anchor="w").pack(side="left")
        self.dl_tracker_ip = tk.Entry(row1, width=20)
        self.dl_tracker_ip.pack(side="left")

        # Peer port
        row2 = tk.Frame(tab)
        row2.pack(anchor="w", padx=10, pady=4)
        tk.Label(row2, text="My Peer Port:", width=14, anchor="w").pack(side="left")
        self.dl_peer_port = tk.Entry(row2, width=8)
        self.dl_peer_port.insert(0, str(PEER_SERVER_PORT))
        self.dl_peer_port.pack(side="left")

        # Torrent ID
        row3 = tk.Frame(tab)
        row3.pack(anchor="w", padx=10, pady=4)
        tk.Label(row3, text="Torrent ID:", width=14, anchor="w").pack(side="left")
        self.dl_torrent_id = tk.Entry(row3, width=20)
        self.dl_torrent_id.pack(side="left")

        # Save directory
        row4 = tk.Frame(tab)
        row4.pack(fill="x", padx=10, pady=4)
        tk.Label(row4, text="Save to:", width=14, anchor="w").pack(side="left")
        self.dl_save_label = tk.Label(row4, text=os.path.expanduser("~"), anchor="w")
        self.dl_save_label.pack(side="left", fill="x", expand=True)
        tk.Button(row4, text="Browse", command=self._pick_save_dir).pack(side="left")
        self.dl_save_dir = os.path.expanduser("~")

        ttk.Separator(tab).pack(fill="x", padx=10, pady=8)

        btn_row = tk.Frame(tab)
        btn_row.pack(anchor="w", padx=10, pady=4)
        tk.Button(btn_row, text="List Available Torrents", command=self._list_torrents).pack(side="left", padx=(0, 5))
        tk.Button(btn_row, text="Start Download", command=self._start_download).pack(side="left")

        # Torrent listbox
        tk.Label(tab, text="Available Torrents:").pack(anchor="w", padx=10, pady=(8, 2))
        list_frame = tk.Frame(tab)
        list_frame.pack(fill="x", padx=10)
        self.torrent_listbox = tk.Listbox(list_frame, height=4)
        self.torrent_listbox.pack(fill="x")
        self.torrent_listbox.bind("<<ListboxSelect>>", self._on_torrent_select)
        self._torrent_list_data = []

        ttk.Separator(tab).pack(fill="x", padx=10, pady=8)

        # Progress
        self.dl_filename_label = tk.Label(tab, text="", anchor="w")
        self.dl_filename_label.pack(anchor="w", padx=10)

        self.progress_bar = ttk.Progressbar(tab, length=600, mode="determinate")
        self.progress_bar.pack(fill="x", padx=10, pady=4)

        self.progress_label = tk.Label(tab, text="Idle", anchor="w")
        self.progress_label.pack(anchor="w", padx=10)
















    # Tab: Log 

    def _tab_log(self, nb):
        tab = tk.Frame(nb)
        nb.add(tab, text="Log")

        top_row = tk.Frame(tab)
        top_row.pack(fill="x", padx=10, pady=5)
        tk.Label(top_row, text="Activity Log", font=("TkDefaultFont", 11, "bold")).pack(side="left")
        tk.Button(top_row, text="Clear", command=self._clear_log).pack(side="right")

        self.log_box = scrolledtext.ScrolledText(tab, state="disabled", wrap="word")
        self.log_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))













    # Actions 
    def _start_tracker(self):
        port = int(self.tracker_port_var.get())
        self.tracker_server = TrackerServer(port=port, log_callback=self._log)
        threading.Thread(target=self.tracker_server.start, daemon=True).start()
        time.sleep(0.3)
        self.tracker_status_text.config(text=f"Tracker running on {self.local_ip}:{port}")
        self.start_tracker_btn.config(state="disabled")
        self.stop_tracker_btn.config(state="normal")
        self._log(f"Tracker started on {self.local_ip}:{port}")




    def _stop_tracker(self):
        if self.tracker_server:
            self.tracker_server.stop()
            self.tracker_server = None
        self.tracker_status_text.config(text="Tracker stopped")
        self.start_tracker_btn.config(state="normal")
        self.stop_tracker_btn.config(state="disabled")
        self._log("Tracker stopped.")
        
        
        

    def _pick_file(self):
        path = filedialog.askopenfilename(title="Select file to share")
        if path:
            self.share_filepath = path
            name = os.path.basename(path)
            size_mb = os.path.getsize(path) / (1024 * 1024)
            self.share_file_label.config(text=f"{name} ({size_mb:.2f} MB)")




    def _pick_save_dir(self):
        d = filedialog.askdirectory(title="Save downloaded files to...")
        if d:
            self.dl_save_dir = d
            self.dl_save_label.config(text=d)







    def _start_seeding(self):
        if not self.share_filepath:
            messagebox.showwarning("No File", "Please select a file first.")
            return

        tracker_ip = self.share_tracker_ip.get().strip()
        peer_port  = int(self.share_peer_port.get().strip())

        if self.peer_node:
            self.peer_node.stop()

        self.peer_node = PeerNode( 
            host=self.local_ip,
            peer_port=peer_port,
            tracker_ip=tracker_ip,
            log_callback=self._log,
        )

        def run():
            try:
                torrent_id = self.peer_node.share_file(self.share_filepath)
                self.root.after(0, lambda: self._show_torrent_id(torrent_id))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)))

        threading.Thread(target=run, daemon=True).start()
        
        
        
        
        
        
        
        

    def _show_torrent_id(self, torrent_id: str):
        self.torrent_id_frame.pack(fill="x", padx=10, pady=8)
        self.torrent_id_label.config(text=f"Torrent ID: {torrent_id}\nShare this ID with peers!")
        self.torrent_id_label.pack(padx=8, pady=6)
        self._log(f"Now seeding! Torrent ID: {torrent_id}")

    def _list_torrents(self):
        tracker_ip = self.dl_tracker_ip.get().strip()
        if not tracker_ip:
            messagebox.showwarning("No Tracker", "Enter tracker IP first.")
            return

        def run():
            try:
                resp = tracker_client_request(tracker_ip, TRACKER_PORT, {"action": "list_torrents"})
                self.root.after(0, lambda: self._populate_torrent_list(resp))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Cannot reach tracker: {e}"))

        threading.Thread(target=run, daemon=True).start()

    def _populate_torrent_list(self, resp: dict):
        self.torrent_listbox.delete(0, "end")
        self._torrent_list_data = []
        torrents = resp.get("torrents", [])
        if not torrents:
            self.torrent_listbox.insert("end", "No torrents available on tracker")
            return
        for t in torrents:
            size_mb = t["filesize"] / (1024 * 1024)
            label = f"{t['filename']}  |  {size_mb:.1f} MB  |  {t['num_peers']} peer(s)  |  ID: {t['torrent_id']}"
            self.torrent_listbox.insert("end", label)
            self._torrent_list_data.append(t)

    def _on_torrent_select(self, event):
        sel = self.torrent_listbox.curselection()
        if sel and self._torrent_list_data:
            idx = sel[0]
            if idx < len(self._torrent_list_data):
                t = self._torrent_list_data[idx]
                self.dl_torrent_id.delete(0, "end")
                self.dl_torrent_id.insert(0, t["torrent_id"])

    def _start_download(self):
        tracker_ip = self.dl_tracker_ip.get().strip()
        torrent_id = self.dl_torrent_id.get().strip()
        peer_port  = int(self.dl_peer_port.get().strip())

        if not tracker_ip or not torrent_id:
            messagebox.showwarning("Missing Info", "Enter tracker IP and torrent ID.")
            return

        if self.peer_node:
            self.peer_node.stop()

        self.peer_node = PeerNode(
            host=self.local_ip,
            peer_port=peer_port,
            tracker_ip=tracker_ip,
            log_callback=self._log,
            progress_callback=self._on_progress,
            done_callback=self._on_download_done,
        )

        self.progress_bar["value"] = 0
        self.progress_label.config(text="Starting download...")

        threading.Thread(
            target=self.peer_node.download_torrent,
            args=(torrent_id, self.dl_save_dir),
            daemon=True
        ).start()


















    #  Callbacks 

    def _on_progress(self, done: int, total: int, filename: str):
        pct = (done / total) * 100
        self.root.after(0, lambda: self._update_progress_ui(done, total, pct, filename))

    def _update_progress_ui(self, done, total, pct, filename):
        self.progress_bar["value"] = pct
        self.dl_filename_label.config(text=filename)
        self.progress_label.config(text=f"{done}/{total} pieces ({pct:.1f}%)")

    def _on_download_done(self, filepath: str):
        self.root.after(0, lambda: self._show_download_done(filepath))

    def _show_download_done(self, filepath: str):
        self.progress_bar["value"] = 100
        self.progress_label.config(text=f"Done. Saved to: {filepath}")
        messagebox.showinfo("Download Complete", f"File saved to:\n{filepath}")













    # Swarm Display Refresh 
    def _refresh_swarm_display(self):
        if self.tracker_server:
            info = self.tracker_server.swarm_info
            for widget in self.swarm_frame.winfo_children():
                widget.destroy()
            if info:
                for tid, data in info.items():
                    text = f"{data['filename']}  —  {data['peers']} peer(s)  —  ID: {tid}"
                    tk.Label(self.swarm_frame, text=text, anchor="w").pack(anchor="w")
            else:
                tk.Label(self.swarm_frame, text="No active swarms").pack(anchor="w")

        self.root.after(2000, self._refresh_swarm_display)













    #  Logging 

    def _log(self, msg: str):
        timestamp = time.strftime("%H:%M:%S")
        full = f"[{timestamp}] {msg}\n"
        self.root.after(0, lambda: self._append_log(full))

    def _append_log(self, text: str):
        self.log_box.config(state="normal")
        self.log_box.insert("end", text)
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def _clear_log(self):
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.config(state="disabled")


if __name__ == "__main__":
    root = tk.Tk()
    app = TorrenteApp(root)
    root.mainloop()