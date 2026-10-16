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
        headers: {
          "Content-Type": "application/json",
        },
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
      <form onSubmit={handleSubmit} className="space-y-5">
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Enter your prompt or idea:
          </label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            required
            rows={4}
            className="w-full p-4 bg-gray-950/80 border border-gray-800 rounded-xl text-white placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-transparent transition-all resize-none shadow-inner"
            placeholder="Describe what you want to create..."
          />
        </div>

        <button
          type="submit"
          disabled={isLoading}
          className="w-full py-4 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-600 hover:to-amber-700 text-gray-950 font-bold rounded-xl shadow-lg shadow-amber-500/10 transition-all duration-200 disabled:opacity-50 cursor-pointer"
        >
          {isLoading ? "Generating..." : "Generate with AI"}
        </button>
      </form>

      {error && (
        <div className="mt-6 p-4 bg-red-950/50 border border-red-900/50 text-red-300 rounded-xl text-sm backdrop-blur-sm">
          {error}
        </div>
      )}

      {result && (
        <div className="mt-6 p-6 bg-gray-950/90 border border-gray-800 rounded-xl shadow-xl backdrop-blur-sm">
          <h2 className="text-sm font-semibold tracking-wider text-amber-400 uppercase mb-2">Generation Result:</h2>
          <p className="text-gray-300 whitespace-pre-wrap text-sm leading-relaxed">{result}</p>
        </div>
      )}
    </div>
  );
}
