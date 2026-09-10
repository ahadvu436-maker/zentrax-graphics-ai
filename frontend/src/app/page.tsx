"use client";

import { useState } from "react";
import Image from "next/image";
import GeneratorForm, {
  GenerationResult,
} from "@/components/GeneratorForm";

export default function GeneratorPage() {
  const [result, setResult] = useState < GenerationResult | null > (null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  
  return (
    <main className="flex min-h-screen flex-col items-center bg-neutral-950 px-6 py-16 text-neutral-100">
      {/* Header */}
      <div className="mb-10 text-center">
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
          Zentrax <span className="text-amber-500">AI</span> Generator
        </h1>
        <p className="mt-2 text-sm text-neutral-400">
          Describe a logo or banner and let Zentrax generate it for you.
        </p>
      </div>

      {/* Form + Preview */}
      <div className="flex w-full max-w-5xl flex-col items-start gap-8 lg:flex-row">
        <GeneratorForm
          onResult={(r) => {
            setResult(r);
            setError("");
          }}
          onError={setError}
          onLoadingChange={setIsLoading}
        />

        <PreviewArea result={result} error={error} isLoading={isLoading} />
      </div>
    </main>
  );
}

function PreviewArea({
  result,
  error,
  isLoading,
}: {
  result: GenerationResult | null;
  error: string;
  isLoading: boolean;
}) {
  return (
    <div className="flex w-full max-w-xl flex-1 flex-col items-center justify-center rounded-2xl border border-white/10 bg-neutral-900/60 p-6 shadow-xl backdrop-blur">
      <div className="flex aspect-square w-full max-w-sm items-center justify-center overflow-hidden rounded-xl border border-dashed border-white/15 bg-neutral-950">
        {isLoading && (
          <div className="flex flex-col items-center gap-3 text-neutral-400">
            <span className="h-8 w-8 animate-spin rounded-full border-2 border-amber-500 border-t-transparent" />
            <span className="text-sm">Generating your design…</span>
          </div>
        )}

        {!isLoading && error && (
          <div className="px-6 text-center text-sm text-red-400">{error}</div>
        )}

        {!isLoading && !error && result && (
          <Image
            src={result.image_url}
            alt={result.prompt}
            width={1024}
            height={1024}
            unoptimized
            className="h-full w-full object-cover"
          />
        )}

        {!isLoading && !error && !result && (
          <div className="px-6 text-center text-sm text-neutral-500">
            Your generated design will appear here
          </div>
        )}
      </div>

      {result && !isLoading && !error && (
        <div className="mt-4 w-full text-xs text-neutral-500">
          <p className="truncate">
            <span className="text-neutral-400">Prompt:</span> {result.prompt}
          </p>
          <p className="mt-1 flex items-center justify-between">
            <span className="capitalize text-neutral-400">
              {result.design_type}
            </span>
            <a
              href={result.image_url}
              download
              className="text-amber-500 hover:underline"
            >
              Download
            </a>
          </p>
        </div>
      )}
    </div>
  );
}