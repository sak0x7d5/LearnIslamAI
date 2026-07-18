"""Compatibility entry point; the Windows launcher calls Chainlit directly."""

from __future__ import annotations

from pathlib import Path


def main() -> None:
    from chainlit.cli import run_chainlit

    run_chainlit(str(Path(__file__).resolve().with_name("app.py")))


if __name__ == "__main__":
    main()
