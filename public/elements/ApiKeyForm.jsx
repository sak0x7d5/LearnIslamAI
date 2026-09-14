import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Eye, EyeOff, KeyRound } from "lucide-react";

export default function ApiKeyForm() {
  const provider = props?.provider ?? "LLM provider";
  const placeholder = props?.placeholder ?? "Enter your API key";
  const consoleUrl = props?.consoleUrl ?? "";
  const envVar = props?.envVar ?? "the API key";
  const [apiKey, setApiKey] = useState("");
  const [show, setShow] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    const value = apiKey.trim();
    if (!value || submitting) return;
    setSubmitting(true);
    try {
      await submitElement({ apiKey: value });
      setApiKey("");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card className="mt-3 w-full max-w-xl">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <KeyRound className="h-4 w-4" /> {provider} API key
        </CardTitle>
        <CardDescription>
          The key is validated by the local IslamAI server and saved only as {envVar} in the ignored root .env file.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Label htmlFor="provider-api-key">API key</Label>
        <div className="mt-2 flex gap-2">
          <Input
            id="provider-api-key"
            type={show ? "text" : "password"}
            value={apiKey}
            autoComplete="off"
            spellCheck={false}
            onChange={(event) => setApiKey(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") submit();
            }}
            placeholder={placeholder}
          />
          <Button
            type="button"
            variant="outline"
            size="icon"
            aria-label={show ? "Hide API key" : "Show API key"}
            onClick={() => setShow((value) => !value)}
          >
            {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </Button>
        </div>
      </CardContent>
      <CardFooter className="justify-between">
        {consoleUrl ? (
          <a
            className="text-sm underline"
            href={consoleUrl}
            target="_blank"
            rel="noreferrer noopener"
          >
            Get a key
          </a>
        ) : (
          <span />
        )}
        <Button disabled={!apiKey.trim() || submitting} onClick={submit}>
          {submitting ? "Validating…" : "Validate and save"}
        </Button>
      </CardFooter>
    </Card>
  );
}
