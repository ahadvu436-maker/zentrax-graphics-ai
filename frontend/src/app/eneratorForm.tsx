"use client";

import { useState } from "react";
import Image from "next/image";
import GeneratorForm, { GenerationResult } from "@/components/GeneratorForm";

export default function GeneratorPage() {
  const [result, setResult] = useState<GenerationResult | null>(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  return (
    <main className="flex min-h-screen flex-col items-center p-8">
      {/* Header */}
      <div className="mb-10 text-center">
        <h1 className="text-3xl font-bold tracking-tight">
          ZentraX <span className="text-amber-500">AI</span>
        </h1>
        <p className="mt-2 text-sm text-neutral-400">
          Describe a logo or banner and let ZentraX generate it for you.
        </p>
      </div>

      {/* Generator Form Component */}
      <div className="w-full max-w-xl">
        <GeneratorForm 
          onResult={(res) => setResult(res)} 
          onError={(err) => setError(err)}
          onLoading={(loading) => setIsLoading(loading)}
        />

        {error && (
          <div className="mt-4 p-4 bg-red-950/50 border border-red-500 text-red-200 rounded-lg text-sm">
            {error}
          </div>
        )}

        {result && result.success && (
          <div className="mt-6 p-4 bg-neutral-900 border border-neutral-800 rounded-lg text-center">
            <h3 className="text-lg font-semibold mb-2">Generation Result</h3>
            {result.imageUrl && (
              <div className="relative w-full h-64 mt-2 rounded overflow-hidden">
                <Image 
                  src={result.imageUrl} 
                  alt="Generated design" 
                  fill 
                  className="object-contain"
                />
              </div>
            )}
            {result.message && <p className="mt-2 text-sm text-neutral-300">{result.message}</p>}
          </div>
        )}
      </div>
    </main>
  );
}
