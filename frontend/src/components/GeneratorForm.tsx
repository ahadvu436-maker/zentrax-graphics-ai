"use client";

import React, { useState } from "react";

export function GeneratorForm() {
  const [prompt, setPrompt] = useState("");
  const [result, setResult] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError("");
    setResult("");

    try {
      const backendUrl = process.env.NEXT_PUBLIC_API_URL || "https://app-backend-production-77ee.up.railway.app";
      const response = await fetch(`${backendUrl}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });

      if (!response.ok) {
        throw new Error("Failed to generate content from backend.");
      }

      const data = await response.json();
      setResult(data.result || data.message || "Successfully Generated!");
    } catch (err: any) {
      setError(err.message || "Something went wrong.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="w-full">
      <form onSubmit={handleSubmit} className="space-y-6">
        <div>
          <label className="block text-xs font-bold uppercase tracking-wider text-gray-400 mb-2">
            Prompt / Design Idea
          </label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            required
            rows={4}
            className="w-full p-4 bg-black/60 border border-white/10 rounded-2xl text-white placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500 transition-all resize-none shadow-inner text-sm"
            placeholder="Describe your luxury concept or asset..."
          />
        </div>

        <button
          type="submit"
          disabled={isLoading}
          className="w-full py-4 bg-gradient-to-r from-amber-500 via-amber-400 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-gray-950 font-black uppercase tracking-wider rounded-2xl shadow-xl shadow-amber-500/10 transition-all duration-300 disabled:opacity-50 cursor-pointer transform hover:-translate-y-0.5"
        >
          {isLoading ? "Generating Luxury Asset..." : "Generate with AI"}
        </button>
      </form>

      {error && (
        <div className="mt-6 p-4 bg-red-950/40 border border-red-900/50 text-red-300 rounded-2xl text-sm backdrop-blur-xl">
          {error}
        </div>
      )}

      {result && (
        <div className="mt-6 p-6 bg-black/80 border border-amber-500/20 rounded-2xl shadow-2xl backdrop-blur-xl">
          <h2 className="text-xs font-bold uppercase tracking-widest text-amber-400 mb-3 flex items-center justify-between">
            <span>Generation Output</span>
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse"></span>
          </h2>
          <p className="text-gray-300 whitespace-pre-wrap text-sm leading-relaxed">{result}</p>
        </div>
      )}
    </div>
  );
}
