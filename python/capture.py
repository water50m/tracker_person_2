import cv2
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import os
import threading
import yt_dlp
import time
from datetime import datetime

class VideoReaderThread(threading.Thread):
    def __init__(self, stream_url):
        super().__init__()
        self.stream_url = stream_url
        self.cap = None
        self.current_frame = None
        self.display_frame = None 
        self.running = True
        self.daemon = True
        self.fps = 30
        
        self._open_stream()

    def _open_stream(self):
        if self.cap:
            self.cap.release()
        self.cap = cv2.VideoCapture(self.stream_url)
        actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
        if actual_fps > 0 and actual_fps < 120:
            self.fps = actual_fps

    def run(self):
        frame_delay = 1.0 / self.fps
        while self.running:
            if not self.cap or not self.cap.isOpened():
                time.sleep(2)
                self._open_stream()
                continue

            start_time = time.time()
            ret, frame = self.cap.read()
            
            if ret:
                self.current_frame = frame.copy()
                
                h, w = frame.shape[:2]
                max_size = 1080  # ขยายภาพให้ใหญ่ขึ้น
                if w > max_size or h > max_size:
                    scale = max_size / max(w, h)
                    frame_resized = cv2.resize(frame, (int(w * scale), int(h * scale)))
                else:
                    frame_resized = frame
                    
                self.display_frame = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
            else:
                time.sleep(0.05)
                continue

            elapsed = time.time() - start_time
            if elapsed < frame_delay:
                time.sleep(frame_delay - elapsed)

    def stop(self):
        self.running = False
        if self.cap:
            self.cap.release()

class YouTubeLiveAnnotator:
    def __init__(self, root):
        self.root = root
        self.root.title("โปรแกรมแคปภาพจาก YouTube Live และจัดหมวดหมู่เสื้อผ้า")
        
        self.classes = [
            'short sleeve top', 'long sleeve top', 'short sleeve outwear', 'long sleeve outwear',
            'vest', 'sling', 'shorts', 'trousers', 'skirt', 'short sleeve dress', 'long sleeve dress',
            'vest dress', 'sling dress'
        ]
        
        self.video_thread = None
        self.captured_frame_img = None
        
        self.setup_ui()
        self.update_display()
        self.connect_youtube() # ออโต้คอนเนคตอนเปิดโปรแกรม

    def setup_ui(self):
        # ---------------- ส่วนบน: กรอก URL ----------------
        top_frame = tk.Frame(self.root)
        top_frame.pack(pady=10)
        
        tk.Label(top_frame, text="YouTube Live URL:", font=('', 12)).pack(side=tk.LEFT, padx=5)
        self.url_entry = tk.Entry(top_frame, width=50, font=('', 12))
        self.url_entry.pack(side=tk.LEFT, padx=5)
        self.url_entry.insert(0, "https://www.youtube.com/watch?v=UemFRPrl1hk")
        
        self.btn_connect = tk.Button(top_frame, text="เชื่อมต่อ Live", command=self.connect_youtube, font=('', 10), bg="lightgray")
        self.btn_connect.pack(side=tk.LEFT, padx=5)

        # ---------------- ส่วนกลาง: วิดีโอ (ซ้าย) + Monitor (ขวา) ----------------
        main_content_frame = tk.Frame(self.root)
        main_content_frame.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Label(main_content_frame, bg="black", width=100, height=25)
        self.canvas.pack(side=tk.LEFT, padx=10)
        
        sidebar_frame = tk.LabelFrame(main_content_frame, text="📊 สถิติการจัดเก็บ (Monitor)", font=('', 12, 'bold'))
        sidebar_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, ipadx=10, ipady=10)
        
        self.class_count_labels = {}
        for cls in self.classes:
            lbl = tk.Label(sidebar_frame, text=f"{cls}: 0", font=('', 11), anchor="w", justify="left")
            lbl.pack(fill=tk.X, pady=2, padx=5)
            self.class_count_labels[cls] = lbl
            
        self.total_count_label = tk.Label(sidebar_frame, text="รวมทั้งหมด: 0 รูป", font=('', 12, 'bold'), fg="blue", pady=10)
        self.total_count_label.pack(side=tk.BOTTOM, fill=tk.X)

        # ---------------- ส่วนล่าง: ปุ่มควบคุม ----------------
        control_frame = tk.Frame(self.root)
        control_frame.pack(pady=10)
        
        self.btn_cap = tk.Button(control_frame, text="📸 จับภาพ (Cap)", command=self.capture_frame, width=15, bg="lightblue", font=('', 12), state=tk.DISABLED)
        self.btn_cap.grid(row=0, column=0, padx=10)
        
        self.btn_skip = tk.Button(control_frame, text="1. ข้ามภาพนี้", command=self.resume_live, width=15, font=('', 12), state=tk.DISABLED)
        self.btn_skip.grid(row=0, column=1, padx=10)
        
        self.selected_class = tk.StringVar(value=self.classes[0])
        self.dropdown = ttk.Combobox(control_frame, textvariable=self.selected_class, values=self.classes, state="disabled", width=20, font=('', 12))
        self.dropdown.grid(row=0, column=2, padx=10)
        
        self.btn_save = tk.Button(control_frame, text="3. บันทึก", command=self.save_frame, width=15, bg="lightgreen", font=('', 12), state=tk.DISABLED)
        self.btn_save.grid(row=0, column=3, padx=10)
        
        self.status_label = tk.Label(self.root, text="รอการเชื่อมต่อ...", font=('', 10), fg="gray")
        self.status_label.pack(pady=5)

        self.update_file_count()

    def connect_youtube(self):
        url = self.url_entry.get().strip()
        if not url:
            return
        self.btn_connect.config(state=tk.DISABLED)
        self.status_label.config(text="กำลังดึงข้อมูลสตรีม โปรดรอสักครู่...", fg="blue")
        threading.Thread(target=self._extract_and_start, args=(url,), daemon=True).start()

    def _extract_and_start(self, url):
        try:
            ydl_opts = {'format': 'best', 'quiet': True, 'no_warnings': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                stream_url = info.get('url', None)
                
            if stream_url:
                if self.video_thread:
                    self.video_thread.stop()
                self.video_thread = VideoReaderThread(stream_url)
                self.video_thread.start()
                self.btn_cap.config(state=tk.NORMAL)
                self.status_label.config(text="เชื่อมต่อ Live สำเร็จ! กำลังเล่น...", fg="green")
            else:
                self.status_label.config(text="ดึงสตรีมไม่สำเร็จ โปรดตรวจสอบ URL", fg="red")
        except Exception as e:
            self.status_label.config(text="เกิดข้อผิดพลาดในการดึง Live", fg="red")
        finally:
            self.btn_connect.config(state=tk.NORMAL)

    def update_display(self):
        if self.video_thread and getattr(self.video_thread, 'display_frame', None) is not None:
            if self.captured_frame_img is None:
                self._show_image_on_canvas(self.video_thread.display_frame)
        self.root.after(20, self.update_display)

    def _show_image_on_canvas(self, frame_rgb):
        img = Image.fromarray(frame_rgb)
        imgtk = ImageTk.PhotoImage(image=img)
        self.canvas.imgtk = imgtk
        self.canvas.configure(image=imgtk, width=imgtk.width(), height=imgtk.height())

    def capture_frame(self):
        if not self.video_thread or self.video_thread.current_frame is None:
            return
        self.captured_frame_img = self.video_thread.current_frame.copy()
        self.btn_cap.config(state=tk.DISABLED)
        self.btn_skip.config(state=tk.NORMAL)
        self.dropdown.config(state="readonly")
        self.btn_save.config(state=tk.NORMAL)
        self.status_label.config(text="จับภาพแล้ว! กรุณาเลือก Class และบันทึก หรือกดข้าม", fg="orange")

    def resume_live(self):
        self.captured_frame_img = None
        self.btn_cap.config(state=tk.NORMAL)
        self.btn_skip.config(state=tk.DISABLED)
        self.dropdown.config(state="disabled")
        self.btn_save.config(state=tk.DISABLED)
        self.status_label.config(text="กำลังเล่น Live...", fg="green")

    def save_frame(self):
        if self.captured_frame_img is None:
            return
        cls_name = self.selected_class.get()
        if not os.path.exists(cls_name):
            os.makedirs(cls_name)
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        filename = os.path.join(cls_name, f"cap_{timestamp}.jpg")
        cv2.imwrite(filename, self.captured_frame_img)
        
        self.update_file_count()
        self.resume_live()

    def update_file_count(self):
        total = 0
        for cls_name in self.classes:
            if os.path.exists(cls_name):
                files = [f for f in os.listdir(cls_name) if os.path.isfile(os.path.join(cls_name, f))]
                num_files = len(files)
            else:
                num_files = 0
            self.class_count_labels[cls_name].config(text=f"{cls_name}: {num_files}")
            total += num_files
        self.total_count_label.config(text=f"รวมทั้งหมด: {total} รูป")

    def on_closing(self):
        if self.video_thread:
            self.video_thread.stop()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = YouTubeLiveAnnotator(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()