#!/usr/bin/env python
"""
Script to run all Kansas City spiders and save output to separate JSON files.

Usage:
    python run_all_spiders.py [--output-dir OUTPUT_DIR] [--parallel N]

Options:
    --output-dir    Directory to save spider outputs (default: spider_outputs)
    --parallel      Number of spiders to run in parallel (default: 8)
    --spider        Run a specific spider by name (optional)
    --list          List all available spiders
"""

import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path


def get_all_spiders():
    """Get list of all available spiders."""
    result = subprocess.run(
        ["scrapy", "list"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent,
    )
    if result.returncode != 0:
        print(f"Error listing spiders: {result.stderr}")
        sys.exit(1)

    spiders = [s.strip() for s in result.stdout.strip().split("\n") if s.strip()]
    return spiders


def run_spider(spider_name, output_dir):
    """Run a single spider and save output to a JSON file."""
    output_file = output_dir / f"{spider_name}.json"

    cmd = [
        "scrapy",
        "crawl",
        spider_name,
        "-O",
        str(output_file),
        "-s", "LOG_LEVEL=ERROR",
        "-s", "CONCURRENT_REQUESTS=16",
        "-s", "DOWNLOAD_DELAY=0",
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent,
    )

    if result.returncode == 0:
        try:
            import json

            with open(output_file, "r") as f:
                items = json.load(f)
            # Delete empty files (no meetings found)
            if len(items) == 0:
                output_file.unlink()
                return spider_name, 0, None
            return spider_name, len(items), None
        except Exception:
            return spider_name, 0, None
    else:
        # Delete file if it was created but spider failed
        if output_file.exists():
            output_file.unlink()
        return spider_name, -1, result.stderr


def main():
    parser = argparse.ArgumentParser(description="Run all Kansas City spiders")
    parser.add_argument(
        "--output-dir",
        default="spider_outputs",
        help="Directory to save spider outputs (default: spider_outputs)",
    )
    parser.add_argument(
        "--spider",
        help="Run a specific spider by name",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available spiders",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=8,
        help="Number of spiders to run in parallel (default: 8)",
    )
    args = parser.parse_args()

    # Get all spiders
    spiders = get_all_spiders()

    if args.list:
        print(f"Available spiders ({len(spiders)} total):")
        for spider in spiders:
            print(f"  - {spider}")
        return

    # Filter to specific spider if requested
    if args.spider:
        if args.spider not in spiders:
            print(f"Error: Spider '{args.spider}' not found")
            print(f"Available spiders: {', '.join(spiders[:5])}...")
            sys.exit(1)
        spiders = [args.spider]

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    # Run spiders
    print(f"Running {len(spiders)} spider(s)...")
    print(f"Output directory: {output_dir.absolute()}")
    print(f"Parallel workers: {args.parallel}")
    print("-" * 60)

    start_time = datetime.now()
    results = {"success": 0, "empty": 0, "failed": 0, "total_items": 0}

    # Always use parallel execution for speed
    with ThreadPoolExecutor(max_workers=args.parallel) as executor:
        futures = {
            executor.submit(run_spider, spider, output_dir): spider
            for spider in spiders
        }
        for future in as_completed(futures):
            spider_name, items, error = future.result()
            if items > 0:
                results["success"] += 1
                results["total_items"] += items
                print(f"✓ {spider_name} ({items} items)")
            elif items == 0:
                results["empty"] += 1
                print(f"○ {spider_name} (no meetings)")
            else:
                results["failed"] += 1
                print(f"✗ {spider_name} (error)")

    end_time = datetime.now()
    duration = end_time - start_time

    # Print summary
    print("-" * 60)
    print(f"Completed in {duration}")
    print(f"With meetings: {results['success']}")
    print(f"No meetings: {results['empty']} (no file created)")
    print(f"Failed: {results['failed']}")
    print(f"Total items scraped: {results['total_items']}")
    print(f"Outputs saved to: {output_dir.absolute()}")


if __name__ == "__main__":
    main()
