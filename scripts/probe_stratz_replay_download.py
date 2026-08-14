from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--match-id", type=int, required=True)
    parser.add_argument("--token", type=str, default="")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--chrome-binary", type=Path, required=True)
    parser.add_argument("--headful", action="store_true")
    parser.add_argument(
        "--query",
        type=str,
        default="query($id: Long!) { match(id: $id) { id clusterId replaySalt didRequestDownload } }",
    )
    parser.add_argument(
        "--query-file",
        type=Path,
        default=None,
        help="Optional path to a UTF-8 GraphQL query file. Overrides --query.",
    )
    parser.add_argument(
        "--variables-json",
        type=str,
        default="",
        help="Optional JSON object for GraphQL variables. Defaults to {'id': match_id}.",
    )
    parser.add_argument(
        "--variables-file",
        type=Path,
        default=None,
        help="Optional path to a UTF-8 JSON file for GraphQL variables. Overrides --variables-json.",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / ".tmp_pydeps"))

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    args.out_dir.mkdir(parents=True, exist_ok=True)

    options = Options()
    options.binary_location = str(args.chrome_binary)
    if not args.headful:
        options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1600,1200")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-gpu")

    driver = webdriver.Chrome(options=options, service=Service())
    try:
        url = f"https://stratz.com/matches/{args.match_id}"
        driver.get(url)
        time.sleep(12)

        result = {
            "requested_url": url,
            "current_url": driver.current_url,
            "title": driver.title,
            "cookies": driver.get_cookies(),
            "page_source_head": driver.page_source[:10000],
        }

        if args.token:
            variables = {"id": args.match_id}
            if args.variables_file:
                variables = json.loads(args.variables_file.read_text(encoding="utf-8"))
            elif args.variables_json:
                variables = json.loads(args.variables_json)
            query = args.query_file.read_text(encoding="utf-8") if args.query_file else args.query
            js = """
                const token = arguments[0];
                const query = arguments[1];
                const variables = arguments[2];
                const done = arguments[arguments.length - 1];
                fetch("https://api.stratz.com/graphql", {
                  method: "POST",
                  headers: {
                    "content-type": "application/json",
                    "authorization": "Bearer " + token
                  },
                  body: JSON.stringify({
                    query,
                    variables
                  })
                })
                .then(async (resp) => {
                  const text = await resp.text();
                  done({ ok: resp.ok, status: resp.status, text });
                })
                .catch((err) => done({ ok: false, error: String(err) }));
            """
            result["graphql_query"] = query
            result["graphql_variables"] = variables
            result["graphql_fetch"] = driver.execute_async_script(js, args.token, query, variables)

        out_path = args.out_dir / f"stratz_probe_{args.match_id}.json"
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(out_path)
        return 0
    finally:
        driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
