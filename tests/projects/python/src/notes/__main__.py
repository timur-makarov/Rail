"""python -m notes [PORT] [DATABASE]: serve the API."""

import sys

from notes.api import serve
from notes.store import Store


def main(argv: list[str]) -> int:
    port = int(argv[1]) if len(argv) > 1 else 8000
    server = serve(Store(argv[2] if len(argv) > 2 else "notes.db"), port)
    print(f"notes on http://127.0.0.1:{server.server_address[1]}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
