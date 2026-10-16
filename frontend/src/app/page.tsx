"import "./globals.css";
import { Navbar } from "../components/Navbar";
import { GeneratorForm } from "../components/GeneratorForm";

export default function Home() {
  return (
    <main className="min-h-screen bg-gradient-to-b from-gray-950 via-gray-900 to-gray-950 text-white flex flex-col">
      <Navbar />
      
      <div className="flex-1 flex flex-col items-center justify-center p-6 sm:p-12">
        <div className="w-full max-w-xl bg-gray-900/40 border border-gray-800/80 p-8 rounded-3xl shadow-2xl backdrop-blur-xl">
          <div className="text-center mb-8">
            <h1 className="text-3xl sm:text-4xl font-black tracking-tight mb-3">
              AI Content <span className="text-transparent bg-clip-text bg-gradient-to-r from-amber-400 to-amber-600">Generator</span>
            </h1>
            <p className="text-gray-400 text-sm max-w-md mx-auto">
              Transform your creative concepts into production-ready assets instantly using advanced intelligence.
            </p>
          </div>

          <GeneratorForm />
        </div>
      </div>
    </main>
  );
}
