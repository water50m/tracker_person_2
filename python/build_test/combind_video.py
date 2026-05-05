import os
from moviepy import VideoFileClip, concatenate_videoclips

# 1. ตั้งค่าโฟลเดอร์
video_folder = "tracked_results"
# สร้าง path ให้ชัดเจน
output_dir = os.path.join(video_folder, "combined_results")
output_filename = os.path.join(output_dir, "combined_target_ids.mp4")

# 2. รายชื่อ ID ที่ต้องการ
target_ids = [2, 24, 36, 49]

def combine_id_videos(folder, ids, output_full_path):
    # --- เพิ่มส่วนนี้: สร้างโฟลเดอร์ปลายทางถ้ายังไม่มี ---
    target_dir = os.path.dirname(output_full_path)
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
        print(f"Created directory: {target_dir}")
    # -------------------------------------------

    clips = []
    for tid in ids:
        file_name = f"person_id_{tid}.mp4"
        file_path = os.path.join(folder, file_name)
        
        if os.path.exists(file_path):
            print(f"Adding: {file_name}")
            clip = VideoFileClip(file_path)
            clips.append(clip)
        else:
            print(f"Warning: File {file_name} not found")

    if clips:
        print("Concatenating videos...")
        # ใช้ method="compose" เพื่อป้องกันปัญหาเรื่องขนาดเฟรมไม่เท่ากัน
        final_clip = concatenate_videoclips(clips, method="compose")
        
        # รันการเขียนไฟล์
        final_clip.write_videofile(output_full_path, codec="libx264", audio=False)
        
        for c in clips:
            c.close()
        print(f"Successfully created: {output_full_path}")
    else:
        print("No clips found to combine.")

if __name__ == "__main__":
    combine_id_videos(video_folder, target_ids, output_filename)