#!/usr/bin/env python3
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eink_dashboard.device.server import create_app


def main():
    parser = argparse.ArgumentParser(description="E-Ink Dashboard Device Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=5000, help="Port to bind to")
    parser.add_argument("--mock", action="store_true", default=True, help="Use mock display (default)")
    parser.add_argument("--real", action="store_true", help="Use real e-ink display")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    mock = not args.real

    app = create_app(mock_display=mock)
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
