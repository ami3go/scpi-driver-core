"""Command-line interface for the E-Resistor driver."""
from __future__ import annotations

import argparse
import json
import sys

from .client import EResistorClient
from .discovery import discover_boards, discover_boards_auto


def _client(args) -> EResistorClient:
    return EResistorClient(args.host, scpi_port=args.scpi_port, http_port=args.http_port, timeout=args.timeout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eresistor", description="Control RP2040 W5500 E-Resistor board")
    parser.add_argument("--host", default="192.168.7.50")
    parser.add_argument("--scpi-port", type=int, default=5025)
    parser.add_argument("--http-port", type=int, default=80)
    parser.add_argument("--timeout", type=float, default=2.0)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("discover")
    p.add_argument("--subnet", default=None)
    p.add_argument("--timeout", type=float, default=0.25)

    sub.add_parser("idn")
    sub.add_parser("blink")
    sub.add_parser("all-off")

    p = sub.add_parser("set-mask")
    p.add_argument("--ch", type=int, required=True)
    p.add_argument("--mask", required=True)

    p = sub.add_parser("set-resistance")
    p.add_argument("--ch", type=int, required=True)
    p.add_argument("--ohm", type=float, required=True)

    p = sub.add_parser("download-cal")
    p.add_argument("--out", required=True)

    p = sub.add_parser("run-curve")
    p.add_argument("--ch", type=int, required=True)
    p.add_argument("--csv", required=True)
    p.add_argument("--repeat", type=int, default=1)

    args = parser.parse_args(argv)

    if args.cmd == "discover":
        boards = discover_boards(args.subnet, timeout=args.timeout) if args.subnet else discover_boards_auto(timeout=args.timeout)
        print(json.dumps([b.__dict__ for b in boards], indent=2))
        return 0

    with _client(args) as dev:
        if args.cmd == "idn":
            print(dev.idn())
        elif args.cmd == "blink":
            print(dev.identify())
        elif args.cmd == "all-off":
            print(dev.all_off())
        elif args.cmd == "set-mask":
            print(dev.set_mask(args.ch, args.mask))
        elif args.cmd == "set-resistance":
            result = dev.set_resistance(args.ch, args.ohm)
            print(json.dumps(result.__dict__, indent=2))
        elif args.cmd == "download-cal":
            dev.download_calibration()
            dev.save_calibration(args.out)
            print(args.out)
        elif args.cmd == "run-curve":
            sim = dev.run_curve(args.ch, args.csv, repeat=args.repeat, blocking=True)
            print(f"applied {len(sim.log)} points")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
