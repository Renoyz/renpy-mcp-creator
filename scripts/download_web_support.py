import httpx
import zipfile
from pathlib import Path

URL = "https://www.renpy.org/dl/8.3.4/renpy-8.3.4-web.zip"
DEST = Path.home() / ".renpy-mcp" / "sdk" / "renpy-web.zip"
SDK_DIR = Path.home() / ".renpy-mcp" / "sdk" / "renpy-8.3.4-sdk"
LOG = Path(__file__).resolve().parent / "download_web_support.log"


def log(msg: str) -> None:
    print(msg)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")
        f.flush()


def main():
    LOG.write_text("", encoding="utf-8")
    log("Downloading RenPy web support...")

    DEST.parent.mkdir(parents=True, exist_ok=True)
    SDK_DIR.mkdir(parents=True, exist_ok=True)

    if DEST.exists():
        DEST.unlink()

    with httpx.stream("GET", URL, follow_redirects=True, timeout=300) as response:
        response.raise_for_status()
        with open(DEST, "wb") as f:
            for chunk in response.iter_bytes(chunk_size=8192):
                f.write(chunk)

    log(f"Downloaded: {DEST.stat().st_size} bytes")
    log("Extracting...")

    with zipfile.ZipFile(DEST, "r") as zf:
        zf.extractall(SDK_DIR)

    log(f"web dir exists: {(SDK_DIR / 'web').exists()}")
    DEST.unlink()
    log("Done")


if __name__ == "__main__":
    main()
