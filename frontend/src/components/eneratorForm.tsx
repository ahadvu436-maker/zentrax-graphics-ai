"use client";

import { useState, FormEvent } from "react";

export type DesignType = "logo" | "banner";

export interface GenerationResult {
  request_id: string;
  status: string;
  design_type: DesignType;
  prompt: string;
  image_url: string;
  thumbnail_url ? : string;
  created_at: string;
}

interface GeneratorFormProps {
  onResult: (result: GenerationResult) => void;
  onError: (message: string) => void;
  onLoadingChange: (loading: boolean) => void;
}

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function GeneratorForm({
  onResult,
  onError,
  onLoadingChange,
}: GeneratorFormProps) {
  const [prompt, setPrompt] = useState("");
  const [designType, setDesignType] = useState < DesignType > ("logo");
  const [isSubmitting, setIsSubmitting] = useState(false);
  
  const charLimit = 500;
  const isPromptValid = prompt.trim().length >= 3;
  
  async function handleSubmit(event: FormEvent < HTMLFormElement > ) {
    event.preventDefault();
    
    if (!isPromptValid || isSubmitting) return;
    
    setIsSubmitting(true);
    onLoadingChange(true);
    onError("");
    
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/design/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: prompt.trim(),
          design_type: designType,
        }),
      });
      
      if (!response.ok) {
        const errorBody = await response.json().catch(() => null);
        throw new Error(
          errorBody?.detail ?? `Generation failed (status ${response.status})`
        );
      }
      
      const data: GenerationResult = await response.json();
      onResult(data);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Something went wrong. Please try again.";
      onError(message);
    } finally {
      setIsSubmitting(false);
      onLoadingChange(false);
    }
  }
  
  return (
    <form
      onSubmit={handleSubmit}
      className="w-full max-w-xl rounded-2xl border border-white/10 bg-neutral-900/60 p-6 shadow-xl backdrop-blur"
    >
      {/* Prompt input */}
      <div className="mb-5">
        <label
          htmlFor="prompt"
          className="mb-2 block text-sm font-medium text-neutral-200"
        >
          Describe your design
        </label>
        <textarea
          id="prompt"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value.slice(0, charLimit))}
          placeholder="e.g. A minimalist coffee cup logo with steam rising, gold accents"
          rows={4}
          maxLength={charLimit}
          className="w-full resize-none rounded-xl border border-white/10 bg-neutral-950 px-4 py-3 text-sm text-neutral-100 placeholder:text-neutral-500 outline-none transition focus:border-amber-500/60 focus:ring-1 focus:ring-amber-500/60"
        />
        <div className="mt-1 flex justify-between text-xs text-neutral-500">
          <span>{!isPromptValid && prompt.length > 0 ? "Prompt is too short" : ""}</span>
          <span>
            {prompt.length}/{charLimit}
          </span>
        </div>
      </div>

      {/* Design type selector */}
      <div className="mb-6">
        <label
          htmlFor="design-type"
          className="mb-2 block text-sm font-medium text-neutral-200"
        >
          Design type
        </label>
        <select
          id="design-type"
          value={designType}
          onChange={(e) => setDesignType(e.target.value as DesignType)}
          className="w-full rounded-xl border border-white/10 bg-neutral-950 px-4 py-3 text-sm text-neutral-100 outline-none transition focus:border-amber-500/60 focus:ring-1 focus:ring-amber-500/60"
        >
          <option value="logo">Logo</option>
          <option value="banner">Banner</option>
        </select>
      </div>

      {/* Submit */}
      <button
        type="submit"
        disabled={!isPromptValid || isSubmitting}
        className="w-full rounded-xl bg-amber-500 px-4 py-3 text-sm font-semibold text-neutral-950 transition hover:bg-amber-400 disabled:cursor-not-allowed disabled:bg-neutral-700 disabled:text-neutral-400"
      >
        {isSubmitting ? "Generating…" : "Generate Design"}
      </button>
    </form>
  );
}