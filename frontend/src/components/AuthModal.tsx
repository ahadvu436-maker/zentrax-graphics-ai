"use client";

import React, { useState } from "react";

export function AuthModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const [step, setStep] = useState<"login" | "verify">("login");
  const [docType, setDocType] = useState("NID");

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4">
      <div className="w-full max-w-md bg-gradient-to-b from-gray-900 to-black border border-white/10 p-8 rounded-3xl shadow-2xl relative">
        <button 
          onClick={onClose}
          className="absolute top-4 right-4 text-gray-400 hover:text-white text-lg font-bold"
        >
          ✕
        </button>

        {step === "login" ? (
          <div>
            <h2 className="text-2xl font-black text-white mb-2">Welcome to ZentraX</h2>
            <p className="text-gray-400 text-sm mb-6">Access elite AI studio services securely.</p>
            
            <button
              onClick={() => setStep("verify")}
              className="w-full flex items-center justify-center space-x-3 py-3.5 bg-white hover:bg-gray-100 text-gray-950 font-bold rounded-xl transition-all mb-4 shadow-lg"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24">
                <path fill="#EA4335" d="M12 5c1.6 0 3 .6 4.1 1.6l3.1-3.1C17.3 1.8 14.8 1 12 1 7.5 1 3.7 3.6 1.9 7.4l3.7 2.9C6.5 7.1 9 5 12 5z"/>
                <path fill="#4285F4" d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.5h6.5c-.3 1.5-1.1 2.8-2.4 3.7l3.7 2.9c2.2-2 3.7-5 3.7-8.8z"/>
                <path fill="#FBBC05" d="M5.6 14.7c-.2-.7-.4-1.5-.4-2.7s.2-2 .4-2.7L1.9 6.4C.7 8.8 0 10.3 0 12s.7 3.2 1.9 5.6l3.7-2.9z"/>
                <path fill="#34A853" d="M12 23c3.2 0 6-1.1 8-3l-3.7-2.9c-1.1.7-2.5 1.2-4.3 1.2-3 0-5.5-2.1-6.4-5.3L1.9 15C3.7 18.8 7.5 23 12 23z"/>
              </svg>
              <span>Continue with Google Gmail</span>
            </button>
          </div>
        ) : (
          <div>
            <h2 className="text-2xl font-black text-white mb-2">Identity Verification</h2>
            <p className="text-gray-400 text-sm mb-6">Compliance requires valid document verification.</p>

            <div className="space-y-4">
              <div>
                <label className="block text-xs font-bold uppercase text-gray-400 mb-2">Select Document Type</label>
                <select 
                  value={docType} 
                  onChange={(e) => setDocType(e.target.value)}
                  className="w-full p-3 bg-black border border-white/10 rounded-xl text-white focus:outline-none focus:border-amber-500 text-sm"
                >
                  <option value="NID">National ID Card (NID)</option>
                  <option value="Passport">Passport</option>
                  <option value="License">Driving License</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-bold uppercase text-gray-400 mb-2">Upload Document Scan</label>
                <input 
                  type="file" 
                  className="w-full text-sm text-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-bold file:bg-amber-500 file:text-gray-950 hover:file:bg-amber-400 cursor-pointer"
                />
              </div>

              <button
                onClick={onClose}
                className="w-full py-3.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 text-gray-950 font-bold rounded-xl transition-all shadow-lg mt-4"
              >
                Submit for Verification
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
