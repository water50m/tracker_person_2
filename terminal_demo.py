#!/usr/bin/env python3
"""
Terminal Demo - แสดงผล AI Detection + Re-ID แบบ Real-time
ไม่ต้อง database, ไม่ต้อง server, แค่รันแล้วดูผลที่หน้าจอ
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import cv2
import torch
import numpy as np
from datetime import datetime
from collections import defaultdict

# Import AI modules
from ai.color_system import analyze_detailed_colors, group_colors, get_primary_colors
from ai.feature_extractor import ClothingEmbedder
from ai.reid_utils import match_lost_track, update_lost_tracks
from ultralytics import YOLO


class TerminalDemo:
    def __init__(self, video_path):
        self.video_path = video_path
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        print("🚀 Initializing Terminal Demo...")
        print(f"   Device: {self.device}")
        
        # Load models
        print("   Loading YOLO models...")
        self.person_model = YOLO('yolo11n.pt')
        self.clothing_model = YOLO(r'E:\ALL_CODE\my-project\models\prepare_dataset.pt')
        
        print("   Loading Clothing Embedder...")
        self.embedder = ClothingEmbedder(
            model_path=r'E:\ALL_CODE\my-project\models\prepare_dataset.pt',
            device=self.device
        )
        
        # Hybrid Tracking State
        self.next_our_id = 1
        self.id_mapping = {}  # byte_id -> our_id
        self.lost_tracks = {}
        self.track_history = {}
        self.frame_count = 0
        
        print("✅ Ready!\n")
    
    def process_video(self):
        """ประมวลผลวิดีโอและแสดงผล"""
        cap = cv2.VideoCapture(self.video_path)
        
        if not cap.isOpened():
            print(f"❌ Cannot open video: {self.video_path}")
            return
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        print(f"📹 Video Info:")
        print(f"   Resolution: {frame_width}x{frame_height}")
        print(f"   FPS: {fps:.1f}")
        print(f"   Total frames: {total_frames}")
        print(f"\n⌨️  Controls:")
        print(f"   [SPACE] Pause/Resume")
        print(f"   [Q] Quit")
        print(f"   [S] Screenshot\n")
        print("=" * 60)
        
        paused = False
        
        while True:
            if not paused:
                ret, frame = cap.read()
                if not ret:
                    print("\n✅ Video finished!")
                    break
                
                self.frame_count += 1
                
                # Process frame
                display_frame = self._process_frame(frame)
                
                # Add info overlay
                self._add_info_overlay(display_frame, fps)
                
                # Show frame
                cv2.imshow('🔍 Re-ID Terminal Demo', display_frame)
            
            # Handle key press
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q'):
                print("\n👋 Quit by user")
                break
            elif key == ord(' '):
                paused = not paused
                print(f"{'⏸️  Paused' if paused else '▶️  Resumed'}")
            elif key == ord('s'):
                filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                cv2.imwrite(filename, display_frame)
                print(f"📸 Screenshot saved: {filename}")
        
        cap.release()
        cv2.destroyAllWindows()
    
    def _process_frame(self, frame):
        """ประมวลผลเฟรมเดียว"""
        # 1. Person Detection with tracking
        results = self.person_model.track(
            frame,
            persist=True,
            classes=[0],
            device=self.device,
            verbose=False,
            tracker="bytetrack.yaml",
            conf=0.3
        )
        
        display_frame = frame.copy()
        current_ids = []
        
        if results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy().astype(int)
            track_ids = results[0].boxes.id.cpu().numpy().astype(int)
            
            for box, byte_id in zip(boxes, track_ids):
                x1, y1, x2, y2 = box
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
                
                # Hybrid tracking logic
                if byte_id in self.id_mapping:
                    our_id = self.id_mapping[byte_id]
                else:
                    # Try to match with lost tracks
                    matched_id = None
                    if self.lost_tracks:
                        # Build features from current person
                        features = self._extract_features(frame, x1, y1, x2, y2)
                        matched_id = match_lost_track(features, self.lost_tracks, threshold=0.7)
                    
                    if matched_id:
                        our_id = matched_id
                        self.id_mapping[byte_id] = our_id
                        print(f"🔄 Recovered ID:{our_id} (Byte ID:{byte_id})")
                    else:
                        our_id = self.next_our_id
                        self.next_our_id += 1
                        self.id_mapping[byte_id] = our_id
                        print(f"✨ New ID:{our_id} (Byte ID:{byte_id})")
                
                current_ids.append(our_id)
                
                # Extract features
                features = self._extract_features(frame, x1, y1, x2, y2)
                self.track_history[our_id] = features
                
                # Get clothing info
                clothing_type = features.get('clothes', ['Unknown'])[0] if features.get('clothes') else 'Unknown'
                primary_color = features.get('primary_detailed_color', 'Unknown')
                
                # Draw bounding box
                color = self._get_id_color(our_id)
                cv2.rectangle(display_frame, (x1, y1), (x2, y2), color, 2)
                
                # Draw label
                label = f"ID:{our_id} {clothing_type}"
                label_color = (255, 255, 255)
                
                # Label background
                (label_w, label_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                cv2.rectangle(display_frame, (x1, y1 - label_h - 10), (x1 + label_w, y1), color, -1)
                
                # Label text
                cv2.putText(display_frame, label, (x1, y1 - 5),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, label_color, 2)
                
                # Draw color info below box
                if primary_color:
                    color_text = f"Color: {primary_color}"
                    cv2.putText(display_frame, color_text, (x1, y2 + 15),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
                
                # Draw clothing items
                clothes_str = ', '.join(features.get('clothes', [])[:2])
                if clothes_str:
                    cv2.putText(display_frame, clothes_str, (x1, y2 + 30),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        # Update lost tracks
        update_lost_tracks(
            self.lost_tracks,
            self.track_history,
            current_ids,
            self.frame_count,
            timeout=60
        )
        
        return display_frame
    
    def _extract_features(self, frame, x1, y1, x2, y2):
        """ดึง features จาก person crop"""
        person_crop = frame[y1:y2, x1:x2]
        if person_crop.size == 0:
            return {}
        
        # Get clothing detection
        clothing_results = self.clothing_model(person_crop, device=self.device, verbose=False)
        
        clothes_list = []
        for c_res in clothing_results:
            for c_box in c_res.boxes:
                if float(c_box.conf[0]) > 0.40:
                    cls_name = self.clothing_model.names[int(c_box.cls[0])]
                    if cls_name not in clothes_list:
                        clothes_list.append(cls_name)
        
        # Get detailed colors
        detailed_colors = analyze_detailed_colors(person_crop)
        color_groups = group_colors(detailed_colors)
        primary_detailed, primary_group = get_primary_colors(detailed_colors, color_groups)
        
        # Get embedding
        embedding, _ = self.embedder.extract(person_crop, clothing_results)
        
        return {
            'detailed_colors': detailed_colors,
            'color_groups': color_groups,
            'primary_detailed_color': primary_detailed,
            'primary_color_group': primary_group,
            'clothes': clothes_list,
            'embedding': embedding
        }
    
    def _get_id_color(self, track_id):
        """สีประจำ ID"""
        colors = [
            (0, 255, 0),    # Green
            (0, 255, 255),  # Cyan
            (255, 255, 0),  # Yellow
            (255, 0, 255),  # Magenta
            (0, 128, 255),  # Orange
            (255, 128, 0),  # Blue-Orange
            (128, 0, 255),  # Purple
            (255, 0, 128),  # Pink
        ]
        return colors[track_id % len(colors)]
    
    def _add_info_overlay(self, frame, fps):
        """เพิ่มข้อมูลบนจอ"""
        # Background
        overlay = frame.copy()
        cv2.rectangle(overlay, (10, 10), (350, 120), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
        
        # Info text
        info_lines = [
            f"Frame: {self.frame_count}",
            f"Active Tracks: {len(self.id_mapping)}",
            f"Lost Tracks: {len(self.lost_tracks)}",
            f"FPS: {fps:.1f}",
            f"Device: {self.device.upper()}",
        ]
        
        y_offset = 30
        for line in info_lines:
            cv2.putText(frame, line, (20, y_offset),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            y_offset += 18


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Re-ID Terminal Demo - Real-time AI Detection')
    parser.add_argument('video_path', help='Path to video file')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.video_path):
        print(f"❌ Video not found: {args.video_path}")
        sys.exit(1)
    
    demo = TerminalDemo(args.video_path)
    demo.process_video()


if __name__ == "__main__":
    main()
