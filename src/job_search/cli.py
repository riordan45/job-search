from __future__ import annotations

import argparse

from job_search.service import JobSearchService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="job-search")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("run-once")
    subparsers.add_parser("seed-demo")
    subparsers.add_parser("show-sources")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    service = JobSearchService()
    if args.command == "run-once":
        service.run_once()
    elif args.command == "seed-demo":
        service.run_once(source_names=["demo-google", "demo-datadog", "demo-optiver"])
    elif args.command == "show-sources":
        for source in service.list_sources(include_disabled=True, include_demo=True):
            status = "enabled" if source.get("enabled", True) else "disabled"
            print(f'{source["name"]}: {source["company_name"]} [{source["adapter"]}] ({status})')


if __name__ == "__main__":
    main()
