"use client";

import React, { useState } from "react";

export function Navbar() {
  const [user, setUser] = useState<{ name: string; email: string } | null>(null);

  const handleGoogleLogin = () => {
    // Simulated Gmail Login (Can be integrated with NextAuth or Firebase)
    setUser({
      name: "Alex Turner",
      email: "alex.turner@gmail.com",
    });
  };

  const handleLogout = () => {
    setUser(null);
  };

  return (
    <nav className="w-full border-b border-gray-800/80 bg-gray-950/60 backdrop-blur-md sticky top-0 z-50 px-6 py-4 flex items-center justify-between">
      <div className="flex items-center space-x-2">
        <span className="text-xl font-black tracking-wider text-white">
          ZENTRAX<span className="text-amber-500">.AI</span>
        </span>
        <span className="text-xs px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 font-medium">
          PRO
        </span>
      </div>

      <div>
        {user ? (
          <div className="flex items-center space-x-4">
            <div className="text-right hidden sm:block">
              <p className="text-sm font-semibold text-white">{user.name}</p>
              <p className="text-xs text-gray-400">{user.email}</p>
            </div>
            <button
              onClick={handleLogout}
              className="px-4 py-2 text-xs font-semibold uppercase tracking-wider bg-gray-900 hover:bg-gray-800 text-gray-300 border border-gray-700 rounded-lg transition-all"
            >
              Sign Out
            </button>
          </div>
        ) : (
          <button
            onClick={handleGoogleLogin}
            className="flex items-center space-x-2 px-5 py-2.5 bg-white hover:bg-gray-100 text-gray-950 font-semibold text-sm rounded-xl shadow-md transition-all cursor-pointer"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24">
              <path
                fill="#EA4335"
                d="M12 5c1.6 0 3 .6 4.1 1.6l3.1-3.1C17.3 1.8 14.8 1 12 1 7.5 1 3.7 3.6 1.9 7.4l3.7 2.9C6.5 7.1 9 5 12 5z"
              />
              <path
                fill="#4285F4"
                d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.5h6.5c-.3 1.5-1.1 2.8-2.4 3.7l3.7 2.9c2.2-2 3.7-5 3.7-8.8z"
              />
              <path
                fill="#FBBC05"
                d="M5.6 14.7c-.2-.7-.4-1.5-.4-2.7s.2-2 .4-2.7L1.9 6.4C.7 8.8 0 10.3 0 12s.7 3.2 1.9 5.6l3.7-2.9z"
              />
              <path
                fill="#34A853"
                d="M12 23c3.2 0 6-1.1 8-3l-3.7-2.9c-1.1.7-2.5 1.2-4.3 1.2-3 0-5.5-2.1-6.4-5.3L1.9 15C3.7 18.8 7.5 23 12 23z"
              />
            </svg>
            <span>Sign in with Google</span>
          </button>
        )}
      </div>
    </nav>
  );
}
