from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANSWER_VIEW = ROOT / "public" / "elements" / "AnswerView.jsx"
STYLESHEET = ROOT / "public" / "stylesheet.css"
SCRIPT = ROOT / "public" / "script.js"


def _frontend_source() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in (ANSWER_VIEW, STYLESHEET, SCRIPT))


def test_answer_view_uses_safe_whole_answer_blocks():
    source = ANSWER_VIEW.read_text(encoding="utf-8")

    assert "props?.blocks" in source
    assert 'kind === "markdown"' in source
    assert "<Markdown allowHtml={false} renderMarkdown={true}>" in source
    assert "<figure" in source
    assert "<blockquote" in source
    assert "<figcaption" in source
    assert "quran: Object.freeze({" in source
    assert "hadith: Object.freeze({" in source
    assert 'className="islamai-answer-view"' in source
    assert "const ANSWER_VIEW_STYLES = String.raw`" in source
    assert "<style>{ANSWER_VIEW_STYLES}</style>" in source


def test_answer_view_does_not_accept_model_generated_markup_or_dom_code():
    source = _frontend_source()
    forbidden = (
        "dangerouslySetInnerHTML",
        ".innerHTML",
        "MutationObserver",
        "eval(",
        "new Function",
        "document.",
    )

    assert not any(item in source for item in forbidden)
    assert "candidate.className" not in source
    assert "candidate.url" not in source
    assert "href={" not in source
    assert "src={" not in source


def test_source_cards_copy_quote_and_trusted_footer_accessibly():
    source = ANSWER_VIEW.read_text(encoding="utf-8")

    assert 'footerItems.join(" · ")' in source
    assert "`${block.text}\\n\\n${footerText}`" in source
    assert (
        'const copyTarget = `${variant.label} passage${hasFooter ? " and citation" : ""}`' in source
    )
    assert "navigator.clipboard.writeText(copyText)" in source
    assert 'type="button"' in source
    assert "aria-label={copyLabel}" in source
    assert "aria-describedby={hasFooter ? captionId : undefined}" in source
    assert 'aria-live="polite"' in source
    assert "{hasFooter ? (" in source
    assert "<span>{variant.label} source</span>" not in source


def test_source_card_styles_are_scoped_responsive_and_motion_safe():
    css = ANSWER_VIEW.read_text(encoding="utf-8")
    global_css = STYLESHEET.read_text(encoding="utf-8")

    assert ".islamai-source-card--quran" in css
    assert ".islamai-source-card--hadith" in css
    assert ".dark .islamai-answer-view" in css
    assert '[data-theme="dark"] .islamai-answer-view' in css
    assert "radial-gradient(" in css
    assert "@media (hover: hover) and (pointer: fine)" in css
    assert "@media (max-width: 40rem)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert ".islamai-source-card__copy:focus-visible" in css
    assert ".islamai-source-card" in global_css
    assert "Compatibility copy: AnswerView also carries" in global_css


def test_fallback_hiding_is_limited_to_the_answer_message_content():
    css = ANSWER_VIEW.read_text(encoding="utf-8")

    assert ".message-content:has(.inline-custom .islamai-answer-view)" in css
    assert "> .flex.flex-col.gap-4:first-child" in css
    assert ".message-content {" not in css
    assert ".message-buttons" not in css


def test_global_script_stays_inert():
    script = SCRIPT.read_text(encoding="utf-8")

    assert "AnswerView owns its interactions inside React" in script
    assert "addEventListener" not in script
    assert "querySelector" not in script
    assert "createElement" not in script
