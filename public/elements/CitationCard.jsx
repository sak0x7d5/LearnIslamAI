import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Check, Copy, BookOpenText } from "lucide-react";

export default function CitationCard() {
  const [copied, setCopied] = useState(false);
  const isQuran = props.kind === "quran";
  const accent = isQuran ? "border-emerald-500/50" : "border-blue-500/50";
  const label = isQuran ? "Quran" : "Hadith";

  const copyCitation = async () => {
    const lines = [props.text, `${props.title} — ${props.locator}`];
    if (props.grading) lines.push(`Grading: ${props.grading}`);
    await navigator.clipboard.writeText(lines.join("\n"));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  return (
    <Card className={`my-3 w-full border-l-4 ${accent}`}>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <BookOpenText className="h-4 w-4" /> {label}: {props.title}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <blockquote className="whitespace-pre-wrap text-sm leading-6">{props.text}</blockquote>
        <div className="text-xs text-muted-foreground">
          <span>{props.locator}</span>
          {props.grading ? <span> · {props.grading}</span> : null}
        </div>
      </CardContent>
      <CardFooter className="justify-end pt-0">
        <Button variant="ghost" size="sm" onClick={copyCitation}>
          {copied ? <Check className="mr-2 h-4 w-4" /> : <Copy className="mr-2 h-4 w-4" />}
          {copied ? "Copied" : "Copy citation"}
        </Button>
      </CardFooter>
    </Card>
  );
}
