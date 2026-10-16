"use client";

import React, { useState } from "react";

export function Navbar({ onOpenAuth }: { onOpenAuth: () => void }) {
  const [user, setUser] = useState<{ name: string; email: string } | null>(null);

  return (
    <header className="w-full border-b border-white/10 bg-black/60 backdrop-blur-2xl sticky top-0 z-50 px-6 py-4 flex items-center justify-between">
      <div className="flex items-center space-x-3">
        <span className="text-xl font-black tracking-wider bg-gradient-to-r from-white via-gray-200 to-amber-400 bg-clip-text text-transparent">
          ZENTRAX<span className="text-amber-500">.AI</span>
        </span>
        <span className="text-[10px] px-2.5 py-1 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 font-bold tracking-widest uppercase">
          ENTERPRISE
        </span>
      </div>

      <div>
        {user ? (
          <div className="flex items-center space-x-4">
            <div className="text-right hidden sm:block">
              <p className="text-sm font-bold text-white">{user.name}</p>
              <p className="text-xs text-amber-400">Verified Account</p>
            </div>
            <button
              onClick={() => setUser(null)}
              className="px-4 py-2 text-xs font-bold uppercase tracking-wider bg-white/5 hover:bg-white/10 text-gray-300 border border-white/10 rounded-xl transition-all"
            >
              Sign Out
            </button>
          </div>
        ) : (
          <button
            onClick={onOpenAuth}
            className="flex items-center space-x-2 px-5 py-2.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-gray-950 font-bold text-sm rounded-xl shadow-xl shadow-amber-500/10 transition-all cursor-pointer transform hover:scale-[1.02]"
          >
            <span>Sign In / Verify ID</span>
          </button>
        )}
      </div>
    </header>
  );
}

