import hashlib
import os
import math
import json

PIECE_SIZE = 256 * 1024  # 256 KB per piece


class PieceManager:
    def __init__(self):
        self.filepath = None
        self.filename = None
        self.filesize = 0
        self.num_pieces = 0
        self.piece_hashes = []          # SHA-1 hash per piece
        self.pieces = {}                # { index: bytes } — pieces we own
        self.pending = set()            # pieces currently being downloaded
        self.total_pieces = 0









    #  SEEDER: Load and split a file

    def load_file(self, filepath: str):
        """Load a file and split it into pieces (seeder side)."""
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        self.filesize = os.path.getsize(filepath)
        self.num_pieces = math.ceil(self.filesize / PIECE_SIZE)
        self.total_pieces = self.num_pieces
        self.piece_hashes = []
        self.pieces = {}

        with open(filepath, "rb") as f:
            for i in range(self.num_pieces):
                chunk = f.read(PIECE_SIZE)
                self.pieces[i] = chunk
                self.piece_hashes.append(hashlib.sha1(chunk).hexdigest())

        return self.get_torrent_info()








    #  LEECHER: Prepare to receive a file

    def prepare_download(self, torrent_info: dict, save_dir: str):
        """Set up piece manager for downloading (leecher side)."""
        self.filename = torrent_info["filename"]
        self.filesize = torrent_info["filesize"]
        self.num_pieces = torrent_info["num_pieces"]
        self.total_pieces = self.num_pieces
        self.piece_hashes = torrent_info["piece_hashes"]
        self.pieces = {}
        self.filepath = os.path.join(save_dir, self.filename)













    #  Piece operations
    def save_piece(self, index: int, data: bytes) -> bool:
        """Verify and store a downloaded piece. Returns True if valid."""
        expected_hash = self.piece_hashes[index]
        actual_hash = hashlib.sha1(data).hexdigest()
        if actual_hash != expected_hash:
            return False
        self.pieces[index] = data
        self.pending.discard(index)
        return True

    def get_piece(self, index: int) -> bytes:
        """Return piece data if we have it."""
        return self.pieces.get(index)

    def have_piece(self, index: int) -> bool:
        return index in self.pieces

    def missing_pieces(self) -> list:
        """Return list of piece indices we don't have and aren't downloading."""
        return [
            i for i in range(self.total_pieces)
            if i not in self.pieces and i not in self.pending
        ]

    def have_bitfield(self) -> list:
        """Return list of piece indices we currently own."""
        return list(self.pieces.keys())

    def is_complete(self) -> bool:
        return len(self.pieces) == self.total_pieces

    def progress(self) -> float:
        """Return download progress as 0.0–1.0."""
        if self.total_pieces == 0:
            return 0.0
        return len(self.pieces) / self.total_pieces

    #  File reconstruction
    def reconstruct(self) -> bool:
        """Write all pieces to disk in order."""
        if not self.is_complete():
            return False
        with open(self.filepath, "wb") as f:
            for i in range(self.total_pieces):
                f.write(self.pieces[i])
        return True











    #  Torrent info dict (shared between peers)

    def get_torrent_info(self) -> dict:
        return {
            "filename": self.filename,
            "filesize": self.filesize,
            "num_pieces": self.num_pieces,
            "piece_hashes": self.piece_hashes,
        }
