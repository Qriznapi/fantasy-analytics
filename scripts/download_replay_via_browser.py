from __future__ import annotations

import argparse
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--chrome-binary", type=Path, required=True)
    parser.add_argument("--timeout-sec", type=int, default=120)
    parser.add_argument("--headful", action="store_true")
    args = parser.parse_args()

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    args.out_dir.mkdir(parents=True, exist_ok=True)
    before = {p.name: p.stat().st_size for p in args.out_dir.glob("*")}

    options = Options()
    options.binary_location = str(args.chrome_binary)
    if not args.headful:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1600,1200")
    options.add_argument("--disable-gpu")
    options.add_experimental_option(
        "prefs",
        {
            "download.default_directory": str(args.out_dir.resolve()),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        },
    )

    driver = webdriver.Chrome(options=options, service=Service())
    try:
        driver.get(args.url)
        deadline = time.time() + args.timeout_sec
        while time.time() < deadline:
            time.sleep(2)
            partials = list(args.out_dir.glob("*.crdownload"))
            files = [p for p in args.out_dir.glob("*") if p.is_file()]
            new_files = [p for p in files if before.get(p.name) != p.stat().st_size]
            if new_files and not partials:
                for p in new_files:
                    print(f"{p}\t{p.stat().st_size}")
                return 0
        print("TIMEOUT")
        for p in sorted(args.out_dir.glob("*")):
            print(f"{p}\t{p.stat().st_size}")
        return 1
    finally:
        driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
