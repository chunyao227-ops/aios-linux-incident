"""Small loopback dependency used by deterministic scenario fixtures."""

from __future__ import annotations

import socket
import time


def main() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 6379))
        server.listen(16)
        server.settimeout(1)
        while True:
            try:
                connection, _ = server.accept()
            except TimeoutError:
                time.sleep(0.05)
                continue
            with connection:
                connection.sendall(b"PONG\n")


if __name__ == "__main__":
    main()
