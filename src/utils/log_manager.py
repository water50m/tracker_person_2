"""
Terminal Log Manager - จัดการการแสดง/ซ่อน logs ใน terminal
"""

import logging
import sys
from typing import Optional
from datetime import datetime

class LogManager:
    """จัดการการแสดงผล logs ใน terminal"""
    
    def __init__(self):
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        self.log_file = None
        self.is_silent = False
        self.log_buffer = []
        
    def enable_silent_mode(self, log_file: Optional[str] = None):
        """เปิดโหมด silent - ไม่แสดง logs ใน terminal"""
        if self.is_silent:
            return
            
        self.is_silent = True
        
        # สร้าง log file ถ้าระบุ
        if log_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.log_file = open(f"logs/{log_file}_{timestamp}.log", "w", encoding="utf-8")
            
        # สร้าง custom writer
        class LogWriter:
            def __init__(self, manager, is_error=False):
                self.manager = manager
                self.is_error = is_error
                
            def write(self, text):
                if self.manager.log_file:
                    self.manager.log_file.write(text)
                    self.manager.log_file.flush()
                    
                # เก็บไว้ใน buffer
                self.manager.log_buffer.append(text)
                
            def flush(self):
                if self.manager.log_file:
                    self.manager.log_file.flush()
                    
        # แทนที่ stdout/stderr
        sys.stdout = LogWriter(self, False)
        sys.stderr = LogWriter(self, True)
        
        print(f"🔇 [LogManager] Silent mode enabled at {datetime.now()}")
        
    def disable_silent_mode(self):
        """ปิดโหมด silent - แสดง logs ใน terminal ตามปกติ"""
        if not self.is_silent:
            return
            
        self.is_silent = False
        
        # คืนค่า stdout/stderr
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr
        
        # ปิด log file
        if self.log_file:
            self.log_file.close()
            self.log_file = None
            
        print(f"🔊 [LogManager] Silent mode disabled at {datetime.now()}")
        
    def get_recent_logs(self, count: int = 50) -> list:
        """ดึง logs ล่าสุด"""
        return self.log_buffer[-count:] if self.log_buffer else []
        
    def clear_buffer(self):
        """ล้าง log buffer"""
        self.log_buffer.clear()
        
    def toggle_logs(self, log_file: Optional[str] = None):
        """สลับการแสดง logs"""
        if self.is_silent:
            self.disable_silent_mode()
        else:
            self.enable_silent_mode(log_file)

# Global instance
log_manager = LogManager()

# ฟังก์ชันสำหรับใช้งานง่ายๆ
def enable_silent_logs(log_file: Optional[str] = None):
    """เปิด silent mode"""
    log_manager.enable_silent_mode(log_file)
    
def disable_silent_logs():
    """ปิด silent mode"""
    log_manager.disable_silent_mode()
    
def toggle_logs(log_file: Optional[str] = None):
    """สลับการแสดง logs"""
    log_manager.toggle_logs(log_file)
    
def get_recent_logs(count: int = 50) -> list:
    """ดึง logs ล่าสุด"""
    return log_manager.get_recent_logs(count)
