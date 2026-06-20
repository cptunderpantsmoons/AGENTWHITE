"""Thin launcher for the FastAPI server inside the Electron shell.

Usage:
    python start_server.py --port 7860 --data-dir /path/to/data
"""
import argparse
import os
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args()

    if args.data_dir:
        os.environ["ODYSSEUS_DATA_DIR"] = args.data_dir

    os.environ.setdefault("AUTH_ENABLED", "true")

    import uvicorn
    uvicorn.run(
        "app:app",
        host="127.0.0.1",
        port=args.port,
        log_level="warning",
        access_log=False,
    )


if __name__ == "__main__":
    main()
