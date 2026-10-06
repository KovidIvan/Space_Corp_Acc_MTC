"""Download required offline voice models into models/ for setup-voice."""

from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"


def download_whisper(model_name: str = "small") -> None:
    """Download faster-whisper model weights."""
    target_dir = MODELS_DIR / f"whisper-{model_name}"
    if target_dir.exists():
        print(f"[+] Whisper model already exists at {target_dir}")
        return

    print(f"[*] Downloading faster-whisper '{model_name}' to {target_dir}...")
    try:
        from faster_whisper import download_model

        download_model(model_name, output_dir=str(target_dir))
        print(f"[+] Downloaded faster-whisper '{model_name}' successfully.")
    except Exception as exc:
        print(f"[-] Failed to download whisper model: {exc}")


def download_silero_vad() -> None:
    """Download Silero VAD model weights."""
    target_dir = MODELS_DIR / "silero-vad"
    if target_dir.exists():
        print(f"[+] Silero VAD model already exists at {target_dir}")
        return

    print(f"[*] Downloading Silero VAD to {target_dir}...")
    try:
        import torch

        torch.hub.set_dir(str(target_dir))
        _ = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            onnx=False,
            trust_repo=True,
        )
        print("[+] Downloaded Silero VAD successfully.")
    except Exception as exc:
        print(f"[-] Failed to download Silero VAD: {exc}")


def main() -> None:
    """Run model setup downloader."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    print("==========================================")
    print(" Space Corp Acc - Voice Model Downloader ")
    print("==========================================")
    download_whisper("small")
    download_silero_vad()
    print("Done.")


if __name__ == "__main__":
    main()
