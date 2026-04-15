import asyncio
from pathlib import Path

from renpy_mcp.config import get_settings
from renpy_mcp.services.sdk_provisioner import SdkProvisioner


async def main():
    settings = get_settings()
    provisioner = SdkProvisioner(settings)

    def progress(stage, percent):
        print(f"[{stage}] {percent * 100:.1f}%")

    print("Starting SDK download...")
    sdk_path = await provisioner.ensure_sdk(progress_callback=progress)
    print(f"SDK ready at: {sdk_path}")
    exe = sdk_path / ("renpy.exe" if __import__("os").name == "nt" else "renpy.sh")
    print(f"Exe exists: {exe.exists()}")


if __name__ == "__main__":
    asyncio.run(main())
