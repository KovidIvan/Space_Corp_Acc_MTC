"""Bundle project context into one text file for chat-only AIs (e.g. DeepSeek).

Usage: python -m scripts.make_context [--lite]
--lite: AGENTS.md, STATUS, contracts and the last two handoff notes only.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def collect(lite: bool) -> list[Path]:
    files = [ROOT / "AGENTS.md", ROOT / "docs/STATUS.md"]
    files += sorted((ROOT / "contracts").glob("*"))
    handoffs = sorted(p for p in (ROOT / "docs/handoff").glob("*.md"))
    files += handoffs[-2:]
    if not lite:
        files += [ROOT / "docs/REQUIREMENTS.md", ROOT / "docs/ARCHITECTURE.md", ROOT / "docs/DECISIONS.md"]
    return [p for p in files if p.exists()]


def main() -> None:
    lite = "--lite" in sys.argv
    parts = []
    for p in collect(lite):
        parts.append(f"===== FILE: {p.relative_to(ROOT).as_posix()} =====\n{p.read_text(encoding='utf-8')}\n")
    text = "\n".join(parts)
    out = ROOT / "context_bundle.txt"
    out.write_text(text, encoding="utf-8")
    print(f"Wrote {out.name}: {len(text)} chars, about {len(text) // 3} tokens (Russian/mixed text is token-heavy).")


if __name__ == "__main__":
    main()
