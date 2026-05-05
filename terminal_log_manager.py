#!/usr/bin/env python3
"""
Terminal Log Manager Command - จัดการการแสดง/ซ่อน logs ผ่าน terminal
"""

import argparse
import sys
import os
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

try:
    from src.utils.log_manager import log_manager, enable_silent_logs, disable_silent_logs, toggle_logs, get_recent_logs
except ImportError:
    print("❌ Cannot import log_manager. Make sure src/utils/log_manager.py exists.")
    sys.exit(1)

def show_status():
    """แสดงสถานะปัจจุบัน"""
    status = "🔇 Silent" if log_manager.is_silent else "🔊 Normal"
    log_file = "Enabled" if log_manager.log_file else "Disabled"
    
    print(f"📊 Log Manager Status:")
    print(f"   Mode: {status}")
    print(f"   Log File: {log_file}")
    print(f"   Buffer Size: {len(log_manager.log_buffer)} messages")
    
def show_recent_logs(count=20):
    """แสดง logs ล่าสุด"""
    logs = get_recent_logs(count)
    if not logs:
        print("📝 No recent logs available.")
        return
        
    print(f"📝 Recent {len(logs)} log messages:")
    print("-" * 60)
    for i, log in enumerate(logs, 1):
        print(f"{i:2d}: {log.rstrip()}")
    print("-" * 60)

def main():
    parser = argparse.ArgumentParser(description="Terminal Log Manager")
    parser.add_argument("action", choices=["status", "enable", "disable", "toggle", "show", "clear"], 
                       help="Action to perform")
    parser.add_argument("--file", "-f", help="Log file name (without extension)")
    parser.add_argument("--count", "-c", type=int, default=20, help="Number of recent logs to show")
    
    args = parser.parse_args()
    
    if args.action == "status":
        show_status()
        
    elif args.action == "enable":
        log_file = args.file or f"terminal_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        enable_silent_logs(log_file)
        print(f"✅ Silent mode enabled. Logs saved to: logs/{log_file}.log")
        
    elif args.action == "disable":
        disable_silent_logs()
        print("✅ Silent mode disabled. Logs will show in terminal.")
        
    elif args.action == "toggle":
        log_file = args.file or f"terminal_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        toggle_logs(log_file)
        status = "enabled" if log_manager.is_silent else "disabled"
        print(f"✅ Silent mode {status}.")
        
    elif args.action == "show":
        show_recent_logs(args.count)
        
    elif args.action == "clear":
        log_manager.clear_buffer()
        print("✅ Log buffer cleared.")
        
if __name__ == "__main__":
    main()
