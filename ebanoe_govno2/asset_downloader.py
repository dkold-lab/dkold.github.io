"""Download optional CS2 workshop weapon geometry for EbanoE GovnO 2.

The game is playable without these files. This helper only downloads and extracts
assets supplied by the URL requested by the project owner. Review Valve/Steam
Workshop terms before redistributing anything extracted by this script.
"""
from __future__ import annotations

import json
import sys
import urllib.request
import zipfile
from pathlib import Path

ASSET_URL = "https://media.steampowered.com/apps/csgo/images/workshop/workshop/cs2_weapon_model_geometry.zip"
ROOT = Path(__file__).resolve().parent
ASSET_DIR = ROOT / "assets" / "cs2_weapon_model_geometry"
MANIFEST = ROOT / "assets" / "asset_manifest.json"
ARCHIVE = ROOT / "assets" / "cs2_weapon_model_geometry.zip"


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url}")
    with urllib.request.urlopen(url, timeout=60) as response:
        total = int(response.headers.get("Content-Length", "0") or 0)
        received = 0
        with destination.open("wb") as file:
            while True:
                chunk = response.read(1024 * 128)
                if not chunk:
                    break
                file.write(chunk)
                received += len(chunk)
                if total:
                    pct = received / total * 100
                    print(f"\r{pct:5.1f}%", end="", flush=True)
    print("\nDownload complete")


def extract(archive: Path, destination: Path) -> list[str]:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zip_file:
        unsafe = [name for name in zip_file.namelist() if Path(name).is_absolute() or ".." in Path(name).parts]
        if unsafe:
            raise RuntimeError(f"Archive contains unsafe paths: {unsafe[:3]}")
        zip_file.extractall(destination)
        return zip_file.namelist()


def main() -> int:
    try:
        download(ASSET_URL, ARCHIVE)
        files = extract(ARCHIVE, ASSET_DIR)
    except Exception as exc:  # noqa: BLE001 - CLI should print a helpful failure reason.
        print(f"Asset download failed: {exc}", file=sys.stderr)
        print("The game still works with procedural fallback weapons.", file=sys.stderr)
        return 1

    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        json.dumps(
            {
                "source_url": ASSET_URL,
                "extracted_to": str(ASSET_DIR.relative_to(ROOT)),
                "file_count": len(files),
                "sample_files": files[:20],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"Extracted {len(files)} files to {ASSET_DIR}")
    print(f"Wrote {MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
