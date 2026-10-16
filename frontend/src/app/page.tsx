"use client";

import { useState } from "formidable"; // প্রয়োজন নেই, তাই বাদ দিতে পারেন
import React from "react";

export default function Home() {
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
      setResult(data.result || data.message || "Success!");
    } catch (err: any) {
      setError(err.message || "Something went wrong.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-gray-950 text-white p-8 flex flex-col items-center justify-center">
      <div className="w-full max-w-xl bg-gray-900 p-6 rounded-2xl shadow-xl border border-gray-800">
        <h1 className="text-3xl font-extrabold text-center mb-2 tracking-tight">
          ZentraX <span className="text-amber-500">AI</span>
        </h1>
        <p className="text-center text-gray-400 mb-6 text-sm">
          আপনার আইডিয়া লিখুন এবং ZentraX AI দিয়ে জেনারেট করুন।
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              প্রম্পট বা আইডিয়া দিন:
            </label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              required
              rows={4}
              className="w-full p-3 bg-gray-950 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-amber-500"
              placeholder="এখানে আপনার প্রম্পট লিখুন..."
            />
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full py-3 bg-amber-500 hover:bg-amber-600 text-gray-950 font-bold rounded-lg transition duration-200 disabled:opacity-50"
          >
            {isLoading ? "জেনারেট হচ্ছে..." : "জেনারেট করুন"}
          </button>
        </form>

        {error && (
          <div className="mt-4 p-3 bg-red-900/50 border border-red-700 text-red-200 rounded-lg text-sm">
            {error}
          </div>
        )}

        {result && (
          <div className="mt-6 p-4 bg-gray-950 border border-gray-800 rounded-lg">
            <h2 className="text-lg font-semibold text-amber-400 mb-2">রেজাল্ট:</h2>
            <p className="text-gray-300 whitespace-pre-wrap">{result}</p>
          </div>
        )}
      </div>
    </main>
  );
}

