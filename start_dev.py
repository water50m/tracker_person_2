#!/usr/bin/env python3
"""
Development Server Starter - รันหน้าบ้าน + หลังบ้าน + Database พร้อมกัน
"""
import subprocess
import sys
import os
import time
import signal
from pathlib import Path

# Colors for output
class Colors:
    GREEN = '\033[92m'
    BLUE = '\033[94m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    CYAN = '\033[96m'
    END = '\033[0m'

def print_header(text, color=Colors.BLUE):
    print(f"\n{color}{'='*60}{Colors.END}")
    print(f"{color}{text:^60}{Colors.END}")
    print(f"{color}{'='*60}{Colors.END}\n")

def run_backend():
    """รัน FastAPI Backend"""
    print_header("🚀 STARTING BACKEND SERVER", Colors.BLUE)
    print(f"{Colors.CYAN}URL: http://localhost:8000{Colors.END}")
    print(f"{Colors.CYAN}Docs: http://localhost:8000/docs\n{Colors.END}")
    
    return subprocess.Popen(
        ["python", "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"],
        cwd=os.path.dirname(__file__),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
        shell=True
    )

def run_frontend():
    """รัน Next.js Frontend"""
    print_header("🎨 STARTING FRONTEND SERVER", Colors.GREEN)
    print(f"{Colors.CYAN}URL: http://localhost:3000\n{Colors.END}")
    
    ui_path = os.path.join(os.path.dirname(__file__), "ui")
    # Use cmd /c for Windows compatibility
    return subprocess.Popen(
        "npm run dev",
        cwd=ui_path,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )

def run_database():
    """รัน Docker Database"""
    print_header("🐘 STARTING DATABASE (Docker)", Colors.YELLOW)
    
    docker_path = os.path.join(os.path.dirname(__file__), "docker")
    return subprocess.Popen(
        "docker-compose up -d",
        cwd=docker_path,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

def stream_output(process, prefix, color):
    """แสดง output จาก process"""
    for line in process.stdout:
        print(f"{color}[{prefix}]{Colors.END} {line.rstrip()}")

def main():
    print_header("🎯 RE-ID TRACKING SYSTEM - DEV MODE", Colors.CYAN)
    
    processes = []
    
    try:
        # 1. Start Database (optional)
        start_db = input("Start Docker Database? (y/n): ").strip().lower()
        if start_db == 'y':
            db_proc = run_database()
            processes.append((db_proc, "DB", Colors.YELLOW))
            time.sleep(3)  # Wait for DB to start
        
        # 2. Start Backend
        backend_proc = run_backend()
        processes.append((backend_proc, "API", Colors.BLUE))
        time.sleep(2)
        
        # 3. Start Frontend
        frontend_proc = run_frontend()
        processes.append((frontend_proc, "UI", Colors.GREEN))
        
        print_header("✅ ALL SERVERS STARTED", Colors.GREEN)
        print("  • Backend:  http://localhost:8000")
        print("  • Frontend: http://localhost:3000")
        print("  • API Docs: http://localhost:8000/docs")
        print("\n  Press Ctrl+C to stop all servers\n")
        
        # Monitor processes
        while True:
            for proc, name, color in processes:
                if proc.poll() is not None:
                    print(f"\n{Colors.RED}⚠️  {name} server stopped unexpectedly{Colors.END}")
            time.sleep(1)
            
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}🛑 Stopping all servers...{Colors.END}")
        
        for proc, name, color in processes:
            print(f"  Stopping {name}...")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        
        print(f"\n{Colors.GREEN}✅ All servers stopped{Colors.END}")

if __name__ == "__main__":
    main()
