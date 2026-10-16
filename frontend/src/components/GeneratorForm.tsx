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
      setResult(data.result || data.message || "Successfully Generated Luxury Asset!");
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
          <label className="block text-sm font-semibold text-gray-300 mb-2 tracking-wide">
            Describe Your Luxury Concept (e.g., Luxury Sports Bike):
          </label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            required
            rows={4}
            className="w-full p-4 bg-gray-950/90 border border-gray-800 rounded-2xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-transparent transition-all resize-none shadow-inner text-sm"
            placeholder="Enter details for your custom design..."
          />
        </div>

        <button
          type="submit"
          disabled={isLoading}
          className="w-full py-4 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-600 hover:to-amber-700 text-gray-950 font-extrabold rounded-2xl shadow-xl shadow-amber-500/20 transition-all duration-200 disabled:opacity-50 cursor-pointer tracking-wider uppercase text-sm"
        >
          {isLoading ? "Crafting Luxury Design..." : "Generate Luxury Concept"}
        </button>
      </form>

      {error && (
        <div className="mt-6 p-4 bg-red-950/60 border border-red-900/60 text-red-300 rounded-2xl text-sm backdrop-blur-md">
          {error}
        </div>
      )}

      {result && (
        <div className="mt-6 p-6 bg-gray-950/90 border border-gray-800 rounded-2xl shadow-2xl backdrop-blur-md">
          <h2 className="text-xs font-bold tracking-widest text-amber-400 uppercase mb-3">Generated Output:</h2>
          <p className="text-gray-200 whitespace-pre-wrap text-sm leading-relaxed">{result}</p>
        </div>
      )}
    </div>
  );
}
