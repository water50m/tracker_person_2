import scipy.io
import os
import shutil
import random
import numpy as np

# --- ตั้งค่าพาธ ---
mat_file_path = 'python/manage_img/annotation.mat'
source_img_dir = r'C:\Users\pmach\Downloads\PA-100K\data' 
output_base_dir = 'organized_dataset'

# --- ตั้งค่าโควตาที่ต้องการต่อ Class ---
# คลาสที่รวมกัน (Manual Review) ผมตั้งให้เยอะกว่าปกติหน่อยตามที่คุณต้องการครับ
BASE_COUNT = 50  # จำนวนที่อยากได้ต่อ 1 คลาสจริง

quota = {
    'short_sleeve_top': BASE_COUNT,
    'long_sleeve_top': BASE_COUNT,
    'short_sleeve_outwear': BASE_COUNT,
    'long_sleeve_outwear': BASE_COUNT,
    'short_sleeve_dress': BASE_COUNT,
    'long_sleeve_dress': BASE_COUNT,
    'trousers': BASE_COUNT,
    'shorts': BASE_COUNT,
    
    # กลุ่ม 2.1: รวม 3 คลาส (skirt, vest dress, sling dress)
    'manual_review_skirt_or_dress': BASE_COUNT * 3,  # จะได้ 1,500 รูป
    
    # กลุ่ม 2.2: รวม 2 คลาส (vest, sling)
    'manual_review_top_only': BASE_COUNT * 2         # จะได้ 1,000 รูป
}

# --- 1. เตรียมโฟลเดอร์และเช็กจำนวนไฟล์ที่มีอยู่แล้ว ---
current_counts = {}
for cls in quota.keys():
    path = os.path.join(output_base_dir, cls)
    os.makedirs(path, exist_ok=True)
    # นับไฟล์เดิมที่มีอยู่แล้ว
    current_counts[cls] = len([f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))])

# --- 2. โหลดและเตรียมรายชื่อ Index ที่จะสุ่ม ---
mat_data = scipy.io.loadmat(mat_file_path)
# รวมชื่อภาพและ labels จากทุกชุด (train, val, test) เพื่อให้มีตัวเลือกสุ่มได้ครบ 100,000 รูป
all_images = list(mat_data['train_images_name']) + list(mat_data['val_images_name']) + list(mat_data['test_images_name'])
all_labels = np.vstack((mat_data['train_label'], mat_data['val_label'], mat_data['test_label']))

# สร้างรายการ Index 0 - 99999 แล้วสลับตำแหน่ง (Shuffle)
indices = list(range(len(all_images)))
random.shuffle(indices)

print("--- เริ่มการสุ่มจัดหมวดหมู่ ---")
processed_count = 0

for idx in indices:
    # ตรวจสอบว่าทุกคลาสได้ครบโควตาหรือยัง
    if all(current_counts[cls] >= quota[cls] for cls in quota):
        print("🎉 ครบโควตาทุกคลาสแล้ว!")
        break

    img_name = all_images[idx][0][0]
    lbl = all_labels[idx]
    
    # ลอจิกการตัดสินใจเลือกโฟลเดอร์
    target_folders = [] # ใช้เป็น list เพราะ 1 รูปอาจเข้าได้หลายคลาส (เช่น เสื้อ+กางเกง)

    is_short_sleeve = lbl[13] == 1
    is_long_sleeve = lbl[14] == 1
    is_long_coat = lbl[21] == 1
    is_trousers = lbl[22] == 1
    is_shorts = lbl[23] == 1
    is_skirt_dress = lbl[24] == 1

    # --- เช็กเงื่อนไขตามลอจิกที่ตกลงกัน ---
    # กลุ่มท่อนล่าง
    if is_trousers: target_folders.append('trousers')
    if is_shorts: target_folders.append('shorts')

    # กลุ่มท่อนบน/เดรส
    u_folder = ""
    if is_skirt_dress:
        if is_short_sleeve: u_folder = 'short_sleeve_dress'
        elif is_long_sleeve: u_folder = 'long_sleeve_dress'
        else: u_folder = 'manual_review_skirt_or_dress'
    elif is_long_coat:
        if is_long_sleeve: u_folder = 'long_sleeve_outwear'
        else: u_folder = 'short_sleeve_outwear'
    elif is_short_sleeve: u_folder = 'short_sleeve_top'
    elif is_long_sleeve: u_folder = 'long_sleeve_top'
    elif not is_short_sleeve and not is_long_sleeve:
        # เคสไม่มีแขน (Manual Review)
        if not is_skirt_dress: u_folder = 'manual_review_top_only'

    if u_folder: target_folders.append(u_folder)

    # --- ทำการ Copy ไฟล์ ---
    for folder in target_folders:
        if current_counts[folder] < quota[folder]:
            source_path = os.path.join(source_img_dir, img_name)
            if os.path.exists(source_path):
                # ตรวจสอบก่อนว่าในโฟลเดอร์เป้าหมายมีไฟล์ชื่อนี้หรือยัง (กันซ้ำ)
                if not os.path.exists(os.path.join(output_base_dir, folder, img_name)):
                    shutil.copy(source_path, os.path.join(output_base_dir, folder, img_name))
                    current_counts[folder] += 1
                    processed_count += 1
                    
                    if processed_count % 100 == 0:
                        print(f"คัดลอกแล้ว {processed_count} รูป...")

print("\n--- สรุปจำนวนภาพปัจจุบัน ---")
for cls, count in current_counts.items():
    print(f"{cls}: {count}/{quota[cls]}")