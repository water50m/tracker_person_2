import type { Metadata } from "next";
import { Orbitron, Share_Tech_Mono } from "next/font/google";
import "./globals.css";
import Sidebar from "@/components/layout/Sidebar";
import TopBar from "@/components/layout/TopBar";

const orbitron = Orbitron({
  variable: "--font-orbitron",
  subsets: ["latin"],
  weight: ["400", "500", "700", "900"],
});

const shareTechMono = Share_Tech_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: "400",
});

export const metadata: Metadata = {
  title: "NEXUS-EYE // Surveillance Intelligence",
  description: "Real-time AI-powered surveillance and investigation system",
  icons: {
    icon: "/favicon.ico",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="th" className="dark">
      <body
        className={`${orbitron.variable} ${shareTechMono.variable} antialiased bg-slate-950 text-slate-100 overflow-hidden`}
      >
        {/* Animated background grid */}
        <div className="fixed inset-0 z-0 pointer-events-none">
          <div className="absolute inset-0 bg-[linear-gradient(to_right,#0f172a_1px,transparent_1px),linear-gradient(to_bottom,#0f172a_1px,transparent_1px)] bg-[size:40px_40px] [mask-image:radial-gradient(ellipse_80%_50%_at_50%_0%,#000_70%,transparent_110%)]" />
          <div className="absolute inset-0 bg-gradient-to-br from-cyan-950/20 via-transparent to-purple-950/20" />
          {/* Scanline effect */}
          <div className="absolute inset-0 bg-[repeating-linear-gradient(0deg,transparent,transparent_2px,rgba(0,255,255,0.015)_2px,rgba(0,255,255,0.015)_4px)]" />
        </div>

        <div className="relative z-10 flex h-screen w-screen overflow-hidden">
          <Sidebar />
          <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
            <TopBar />
            <main className="flex-1 overflow-auto scrollbar-thin scrollbar-track-slate-900 scrollbar-thumb-cyan-800">
              {children}
            </main>
          </div>
        </div>
      </body>
    </html>
  );
}