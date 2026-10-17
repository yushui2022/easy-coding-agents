import argparse
import sys
import urllib.request
from pathlib import Path
from typing import Dict


DATASETS: Dict[str, Dict[str, str]] = {
    "longmemeval_s": {
        "url": "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main/longmemeval_s_cleaned.json",
        "path": "longmemeval_s_cleaned.json",
    },
    "locomo10": {
        "url": "https://raw.githubusercontent.com/snap-research/locomo/main/data/locomo10.json",
        "path": "locomo10.json",
    },
}


def download(name: str, output_dir: Path, force: bool = False) -> Path:
    spec = DATASETS[name]
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / spec["path"]
    if target.exists() and not force:
        print(f"{name}: already exists at {target}")
        return target

    url = spec["url"]
    tmp = target.with_suffix(target.suffix + ".tmp")
    print(f"{name}: downloading {url}")
    with urllib.request.urlopen(url, timeout=60) as response, tmp.open("wb") as handle:
        total = int(response.headers.get("content-length") or 0)
        downloaded = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
            downloaded += len(chunk)
            if total:
                percent = downloaded * 100 / total
                print(f"\r{name}: {downloaded / 1024 / 1024:.1f}MB / {total / 1024 / 1024:.1f}MB ({percent:.1f}%)", end="")
        print()
    tmp.replace(target)
    print(f"{name}: saved to {target}")
    return target


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=list(DATASETS) + ["all"], default="all")
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parent / "datasets"),
        help="Local ignored directory for downloaded benchmark data.",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    names = list(DATASETS) if args.dataset == "all" else [args.dataset]
    output_dir = Path(args.output_dir)
    for name in names:
        try:
            download(name, output_dir=output_dir, force=args.force)
        except Exception as exc:
            print(f"{name}: download failed: {exc}", file=sys.stderr)
            raise


if __name__ == "__main__":
    main()
