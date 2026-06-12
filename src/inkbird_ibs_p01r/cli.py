from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import replace
from pathlib import Path
from threading import Event

from .config import load_config
from .decoder import DecodeResult, decode_cs16_file
from .mqtt_client import MQTTPublisher
from .service import DirectoryWatcher, InkbirdService


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def print_result(result: DecodeResult, pretty: bool = False) -> None:
    if pretty:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(json.dumps(result.to_dict(), separators=(",", ":")))


def command_decode_file(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    result = decode_cs16_file(
        args.file,
        decoder_config=config.decoder,
        min_file_size=args.min_long_file_size,
    )
    print_result(result, pretty=args.pretty)
    return 0


def command_watch_dir(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    sdr = replace(config.sdr, capture_dir=str(args.directory), poll_interval_seconds=args.poll_interval)
    config = replace(config, sdr=sdr)
    configure_logging(config.logging.level)

    def on_result(result: DecodeResult) -> None:
        print_result(result, pretty=args.pretty)

    watcher = DirectoryWatcher(config, on_result=on_result)
    stop_event = Event()
    try:
        watcher.run(stop_event)
    except KeyboardInterrupt:
        stop_event.set()
    return 0


def command_run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    configure_logging(config.logging.level)
    service = InkbirdService(config)
    service.run()
    return 0


def command_test_mqtt(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    configure_logging(config.logging.level)
    result = DecodeResult(
        decode_ok=True,
        file="test",
        temperature_C=26.2,
        temperature_C_exact=26.2,
        field="e0c0",
        flags=7,
        raw13=192,
        confidence_count=1,
        marker="2280a280",
    )
    publisher = MQTTPublisher(config)
    publisher.connect()
    try:
        payload = publisher.publish_decode(result)
        print(json.dumps(payload, indent=2, sort_keys=True))
    finally:
        publisher.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="inkbird-ibs-p01r-mqtt")
    parser.add_argument("--version", action="version", version="inkbird-ibs-p01r-mqtt 0.1.0")
    subparsers = parser.add_subparsers(dest="command", required=True)

    decode = subparsers.add_parser("decode-file", help="decode one rtl_433 .cs16 file")
    decode.add_argument("file", type=Path)
    decode.add_argument("--config", type=Path, default=None)
    decode.add_argument("--min-long-file-size", type=int, default=0)
    decode.add_argument("--pretty", action="store_true")
    decode.set_defaults(func=command_decode_file)

    watch = subparsers.add_parser("watch-dir", help="watch a capture directory and decode long .cs16 files")
    watch.add_argument("directory", type=Path)
    watch.add_argument("--config", type=Path, default=None)
    watch.add_argument("--poll-interval", type=float, default=1.0)
    watch.add_argument("--pretty", action="store_true")
    watch.set_defaults(func=command_watch_dir)

    run = subparsers.add_parser("run", help="run the MQTT service")
    run.add_argument("--config", type=Path, required=True)
    run.set_defaults(func=command_run)

    test_mqtt = subparsers.add_parser("test-mqtt", help="publish one synthetic decode payload")
    test_mqtt.add_argument("--config", type=Path, required=True)
    test_mqtt.set_defaults(func=command_test_mqtt)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
