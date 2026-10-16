"use client";

import GeneratorForm from "../components/GeneratorForm";

export default function Home() {
  return (
    <main className="min-h-screen bg-gray-950 text-white p-8 flex flex-col items-center justify-center">
      <div className="w-full max-w-2xl">
        <h1 className="text-4xl font-extrabold text-center mb-2 tracking-tight">
          ZentraX <span className="text-amber-500">AI</span>
        </h1>
        <p className="text-center text-gray-400 mb-8">
          Describe your idea and let ZentraX AI generate it for you.
        </p>
        <GeneratorForm />
      </div>
    </main>
  );
}

