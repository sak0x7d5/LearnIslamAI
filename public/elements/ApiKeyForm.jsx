import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Eye, EyeOff, KeyRound } from "lucide-react";

export default function ApiKeyForm() {
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
          <KeyRound className="h-4 w-4" /> Google Gemini API key
        </CardTitle>
        <CardDescription>
          The key is validated by the local IslamAI server and saved only in the ignored root .env file.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Label htmlFor="google-api-key">API key</Label>
        <div className="mt-2 flex gap-2">
          <Input
            id="google-api-key"
            type={show ? "text" : "password"}
            value={apiKey}
            autoComplete="off"
            spellCheck={false}
            onChange={(event) => setApiKey(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") submit();
            }}
            placeholder="Enter your Google API key"
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
      <CardFooter className="justify-end">
        <Button disabled={!apiKey.trim() || submitting} onClick={submit}>
          {submitting ? "Validating…" : "Validate and save"}
        </Button>
      </CardFooter>
    </Card>
  );
}
