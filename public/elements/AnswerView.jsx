import React, { useEffect, useId, useMemo, useRef, useState } from "react";
import { BookOpenText, Check, Copy, ScrollText, TriangleAlert } from "lucide-react";
import { Markdown } from "@/components/markdown";

const CARD_VARIANTS = Object.freeze({
  quran: Object.freeze({
    className: "islamai-source-card islamai-source-card--quran",
    label: "Quran",
    Icon: BookOpenText,
  }),
  hadith: Object.freeze({
    className: "islamai-source-card islamai-source-card--hadith",
    label: "Hadith",
    Icon: ScrollText,
  }),
});

const DEFAULT_POINTER = Object.freeze({ x: 50, y: 18 });

function textValue(value) {
  return typeof value === "string" ? value.trim() : "";
}

function normalizeBlocks(value) {
  if (!Array.isArray(value)) return [];

  return value.flatMap((candidate) => {
    if (!candidate || typeof candidate !== "object") return [];

    const kind = textValue(candidate.kind).toLowerCase();
    const text = textValue(candidate.text);
    if (!text) return [];

    if (kind === "markdown") {
      return [{ kind, text }];
    }

    if (!Object.hasOwn(CARD_VARIANTS, kind)) return [];

    return [
      {
        kind,
        text,
        title: textValue(candidate.title),
        locator: textValue(candidate.locator),
        grading: textValue(candidate.grading),
      },
    ];
  });
}

function MarkdownBlock({ text }) {
  return (
    <div className="islamai-answer-prose">
      <Markdown allowHtml={false} renderMarkdown={true}>
        {text}
      </Markdown>
    </div>
  );
}

function SourceCard({ block, index }) {
  const variant = CARD_VARIANTS[block.kind];
  const { Icon } = variant;
  const labelId = useId();
  const captionId = useId();
  const resetTimer = useRef(null);
  const [copyStatus, setCopyStatus] = useState("idle");
  const [pointer, setPointer] = useState(DEFAULT_POINTER);

  const footerItems = useMemo(
    () => [block.title, block.locator, block.grading].filter(Boolean),
    [block.title, block.locator, block.grading]
  );
  const hasFooter = footerItems.length > 0;
  const footerText = footerItems.join(" · ");
  const copyText = hasFooter ? `${block.text}\n\n${footerText}` : block.text;

  useEffect(
    () => () => {
      if (resetTimer.current) window.clearTimeout(resetTimer.current);
    },
    []
  );

  const resetCopyStatusLater = () => {
    if (resetTimer.current) window.clearTimeout(resetTimer.current);
    resetTimer.current = window.setTimeout(() => setCopyStatus("idle"), 2000);
  };

  const copyCard = async () => {
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(copyText);
      setCopyStatus("copied");
    } catch {
      setCopyStatus("failed");
    }
    resetCopyStatusLater();
  };

  const updateGlow = (event) => {
    if (event.pointerType && event.pointerType !== "mouse") return;
    const bounds = event.currentTarget.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    const x = Math.max(
      0,
      Math.min(100, ((event.clientX - bounds.left) / bounds.width) * 100)
    );
    const y = Math.max(
      0,
      Math.min(100, ((event.clientY - bounds.top) / bounds.height) * 100)
    );
    setPointer({ x, y });
  };

  const copyTarget = `${variant.label} passage${hasFooter ? " and citation" : ""}`;
  const copyLabel =
    copyStatus === "copied"
      ? `Copied ${copyTarget}`
      : copyStatus === "failed"
        ? `Could not copy ${copyTarget}`
        : `Copy ${copyTarget}`;

  return (
    <figure
      className={variant.className}
      aria-labelledby={labelId}
      aria-describedby={hasFooter ? captionId : undefined}
      onPointerMove={updateGlow}
      onPointerLeave={() => setPointer(DEFAULT_POINTER)}
      style={{
        "--islamai-glow-x": `${pointer.x}%`,
        "--islamai-glow-y": `${pointer.y}%`,
      }}
    >
      <div className="islamai-source-card__header">
        <div className="islamai-source-card__kind" id={labelId}>
          <Icon aria-hidden="true" focusable="false" />
          <span>{variant.label}</span>
        </div>
        <button
          className="islamai-source-card__copy"
          type="button"
          onClick={copyCard}
          aria-label={copyLabel}
          aria-describedby={hasFooter ? captionId : undefined}
          title={copyLabel}
        >
          {copyStatus === "copied" ? (
            <Check aria-hidden="true" focusable="false" />
          ) : copyStatus === "failed" ? (
            <TriangleAlert aria-hidden="true" focusable="false" />
          ) : (
            <Copy aria-hidden="true" focusable="false" />
          )}
          <span aria-live="polite">
            {copyStatus === "copied" ? "Copied" : copyStatus === "failed" ? "Retry" : "Copy"}
          </span>
        </button>
      </div>

      <blockquote className="islamai-source-card__quote">{block.text}</blockquote>

      {hasFooter ? (
        <figcaption className="islamai-source-card__footer" id={captionId}>
          {footerItems.map((item, itemIndex) => (
            <React.Fragment key={`${index}-${itemIndex}`}>
              {itemIndex > 0 ? <span aria-hidden="true">·</span> : null}
              <span>{item}</span>
            </React.Fragment>
          ))}
        </figcaption>
      ) : null}
    </figure>
  );
}

export default function AnswerView() {
  const blocks = normalizeBlocks(props?.blocks);
  if (!blocks.length) return null;

  return (
    <section className="islamai-answer-view" aria-label="IslamAI answer">
      {blocks.map((block, index) =>
        block.kind === "markdown" ? (
          <MarkdownBlock key={`markdown-${index}`} text={block.text} />
        ) : (
          <SourceCard key={`${block.kind}-${index}`} block={block} index={index} />
        )
      )}
    </section>
  );
}
