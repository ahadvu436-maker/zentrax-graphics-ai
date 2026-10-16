"use client";

import "./globals.css";
import React, { useState } from "react";
import { Navbar } from "../components/Navbar";
import { GeneratorForm } from "../components/GeneratorForm";
import { AuthModal } from "../components/AuthModal";

export default function Home() {
  const [isAuthOpen, setIsAuthOpen] = useState(false);

  return (
    <main className="min-h-screen bg-[#030307] text-white flex flex-col selection:bg-amber-500 selection:text-black">
      <Navbar onOpenAuth={() => setIsAuthOpen(true)} />
      
      <div className="flex-1 flex flex-col items-center justify-center p-6 sm:p-12 relative overflow-hidden">
        {/* Ambient Glow Effects */}
        <div className="absolute w-[500px] h-[500px] bg-amber-500/5 rounded-full blur-[120px] pointer-events-none -top-20 -left-20"></div>
        <div className="absolute w-[500px] h-[500px] bg-purple-500/5 rounded-full blur-[120px] pointer-events-none -bottom-20 -right-20"></div>

        <div className="w-full max-w-3xl bg-gradient-to-b from-white/[0.08] to-white/[0.02] border border-white/10 p-8 sm:p-12 rounded-3xl shadow-2xl backdrop-blur-2xl relative z-10">
          <div className="text-center mb-10">
            <h1 className="text-4xl sm:text-5xl font-black tracking-tight mb-4">
              Luxury AI <span className="text-transparent bg-clip-text bg-gradient-to-r from-amber-400 to-amber-600">Studio</span>
            </h1>
            <p className="text-gray-400 text-sm sm:text-base max-w-lg mx-auto">
              The elite enterprise platform for advanced intelligence, secure identity verification, and high-end asset creation.
            </p>
          </div>

          <GeneratorForm />
        </div>
      </div>

      <AuthModal isOpen={isAuthOpen} onClose={() => setIsAuthOpen(false)} />
    </main>
  );
}

