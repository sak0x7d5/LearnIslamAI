from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
HSL_TRIPLET = re.compile(r"^[0-9]+([.][0-9]+)? [0-9]+([.][0-9]+)?% [0-9]+([.][0-9]+)?%$")


def _load_config() -> dict:
    with (ROOT / ".chainlit" / "config.toml").open("rb") as handle:
        return tomllib.load(handle)


def test_ui_defaults_to_dark_theme_with_project_metadata():
    ui = _load_config()["UI"]

    assert ui["name"] == "IslamAI"
    assert ui["default_theme"] == "dark"
    assert ui["description"]
    assert ui["custom_meta_url"] == "https://github.com/sak0x7d5/LearnIslamAI"
    assert "chainlit" not in ui["custom_meta_image_url"].lower()
    # Empty URLs make Chainlit serve the file-based logo and avatar below.
    assert ui["logo_file_url"] == ""
    assert ui["default_avatar_file_url"] == ""


def test_project_supplies_its_own_logo_favicon_and_avatar():
    # Chainlit resolves these by glob: public/logo_<theme>.*, public/favicon.*,
    # and public/avatars/<slugified assistant name>.*
    for relative in (
        "logo_dark.svg",
        "logo_light.svg",
        "favicon.svg",
        "avatars/islamai.svg",
    ):
        path = PUBLIC / relative
        assert path.is_file(), relative
        root = ElementTree.fromstring(path.read_bytes())
        assert root.tag.endswith("svg"), relative
        assert root.get("aria-label") == "IslamAI", relative
        assert "chainlit" not in path.read_text(encoding="utf-8").lower(), relative


def test_theme_defines_matching_light_and_dark_palettes():
    theme = json.loads((PUBLIC / "theme.json").read_text(encoding="utf-8"))
    palettes = theme["variables"]

    assert set(palettes) == {"light", "dark"}
    assert set(palettes["light"]) == set(palettes["dark"])
    for name, palette in palettes.items():
        for token, value in palette.items():
            assert token.startswith("--"), (name, token)
            assert HSL_TRIPLET.fullmatch(value), (name, token, value)
    # Both accents derive from the Quran source-card greens.
    assert palettes["dark"]["--primary"] == "150 52% 64%"
    assert palettes["light"]["--primary"] == "158 69% 28%"


def test_footer_disclaimer_is_project_specific():
    translation = json.loads(
        (ROOT / ".chainlit" / "translations" / "en-US.json").read_text(encoding="utf-8")
    )
    watermark = translation["chat"]["watermark"]

    assert watermark.startswith("IslamAI can make mistakes")
    assert "fatwa" in watermark
    assert "LLMs can make mistakes" not in watermark


def test_launcher_ships_translations_with_the_runtime_root():
    installer = (ROOT / "install_windows.ps1").read_text(encoding="utf-8")

    assert 'translations") -Destination $runtimeConfigDir -Recurse' in installer
    assert installer.index("translations") < installer.index('"public") -Destination $runtimeApp')
