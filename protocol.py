import json
import struct

# Message Types
MSG_HANDSHAKE  = 0
MSG_BITFIELD   = 1   # "here are all the pieces I have"
MSG_REQUEST    = 2   # "give me piece N"
MSG_PIECE      = 3   # actual data payload
MSG_HAVE       = 4   # "I just got piece N"
MSG_INTERESTED = 5
MSG_CHOKE      = 6

HEADER_SIZE = 5  # 1 byte type + 4 byte length


def encode(msg_type: int, payload: dict) -> bytes:
    """Encode a message into bytes: [type(1)] [length(4)] [json body]"""
    body = json.dumps(payload).encode("utf-8")
    header = struct.pack("!BI", msg_type, len(body))
    return header + body





def recv_message(sock) -> tuple:
    """
    Reliably receive one full message from a socket.
    Returns (msg_type, payload_dict) or raises on error.
    """
    header = _recv_exact(sock, HEADER_SIZE)
    msg_type, length = struct.unpack("!BI", header)
    body = _recv_exact(sock, length)
    payload = json.loads(body.decode("utf-8"))
    return msg_type, payload





def _recv_exact(sock, n: int) -> bytes:
    """Read exactly n bytes from socket, looping as needed."""
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Socket closed before all bytes received")
        data += chunk
    return data
