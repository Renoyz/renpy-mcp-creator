import asyncio
import sys
from pathlib import Path

from renpy_mcp.config import get_settings
from renpy_mcp.services.sdk_provisioner import SdkProvisioner


LOG_PATH = Path(__file__).resolve().parent / "download_sdk.log"


def log(msg: str) -> None:
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(msg + "\n")
        f.flush()
    print(msg)
    sys.stdout.flush()


async def main():
    LOG_PATH.write_text("", encoding="utf-8")
    settings = get_settings()
    provisioner = SdkProvisioner(settings)

    last_percent = -1

    def progress(stage, percent):
        nonlocal last_percent
        p = int(percent * 100)
        if p > last_percent:
            last_percent = p
            log(f"[{stage}] {p}%")

    log("Starting SDK download...")
    try:
        sdk_path = await provisioner.ensure_sdk(progress_callback=progress)
        exe = sdk_path / ("renpy.exe" if __import__("os").name == "nt" else "renpy.sh")
        log(f"SDK ready at: {sdk_path}")
        log(f"Exe exists: {exe.exists()}")
    except Exception as e:
        log(f"ERROR: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
