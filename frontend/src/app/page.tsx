import "./globals.css";
import { Navbar } from "../components/Navbar";
import { GeneratorForm } from "../components/GeneratorForm";

export default function Home() {
  return (
    <main className="min-h-screen bg-[#030307] text-white flex flex-col selection:bg-amber-500 selection:text-black">
      <Navbar />
      
      <div className="flex-1 flex flex-col items-center justify-center p-6 sm:p-12 relative overflow-hidden">
        {/* Background ambient lighting effects */}
        <div className="absolute w-96 h-96 bg-amber-500/5 rounded-full blur-3xl pointer-events-none -top-20 -left-20"></div>
        <div className="absolute w-96 h-96 bg-purple-500/5 rounded-full blur-3xl pointer-events-none -bottom-20 -right-20"></div>

        <div className="w-full max-w-xl bg-gradient-to-b from-white/[0.07] to-white/[0.02] border border-white/10 p-8 sm:p-10 rounded-3xl shadow-2xl backdrop-blur-2xl relative z-10">
          <div className="text-center mb-8">
            <h1 className="text-3xl sm:text-4xl font-black tracking-tight mb-3">
              Luxury AI <span className="text-transparent bg-clip-text bg-gradient-to-r from-amber-400 to-amber-600">Studio</span>
            </h1>
            <p className="text-gray-400 text-sm max-w-sm mx-auto">
              Command elite intelligence to render high-end concepts and custom assets instantly.
            </p>
          </div>

          <GeneratorForm />
        </div>
      </div>
    </main>
  );
}
