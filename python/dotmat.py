import scipy.io
import numpy as np

# 1. ระบุพาธของไฟล์ .mat ที่ต้องการเปิด
file_path = 'python/annotation.mat'  # <-- เปลี่ยนชื่อไฟล์ตรงนี้

try:
    # 2. โหลดไฟล์ .mat (ข้อมูลจะถูกเก็บในรูปแบบ Dictionary)
    mat_data = scipy.io.loadmat(file_path)
    
    print("✅ โหลดไฟล์สำเร็จ!")
    print("-" * 50)
    
    # 3. ดูว่าในไฟล์นี้มีตัวแปร (Keys) อะไรเก็บไว้บ้าง
    print("🔑 ตัวแปร (Keys) ที่อยู่ในไฟล์นี้:")
    for key in mat_data.keys():
        # ข้าม key ที่เป็นข้อมูลระบบของ MATLAB (มักจะขึ้นต้นและลงท้ายด้วย __)
        if not key.startswith('__'):
            data = mat_data[key]
            
            # เช็คว่าเป็น Numpy Array หรือไม่ เพื่อดูขนาด (Shape)
            if isinstance(data, np.ndarray):
                print(f" - {key}: เป็น Array ขนาด {data.shape} (ชนิดข้อมูล: {data.dtype})")
            else:
                print(f" - {key}: {type(data)}")
                
    print("-" * 50)
    
    # ==========================================
    # 🎯 ตัวอย่างการดึงข้อมูลมาดูจริงๆ (สมมติว่ามี Key ชื่อ 'train_images_name')
    # ==========================================
    
    # พิมพ์ชื่อ Key ที่คุณเห็นจากด้านบนลงไปในนี้ เพื่อดูข้อมูลข้างใน
    target_key = input("พิมพ์ชื่อ Key ที่ต้องการดูข้อมูลตัวอย่าง (หรือกด Enter เพื่อข้าม): ")
    
    if target_key in mat_data:
        print(f"\n📊 ข้อมูลตัวอย่าง 5 รายการแรกของ '{target_key}':")
        sample_data = mat_data[target_key][:26] # ดึงมาดูแค่ 5 อันแรก
        print(sample_data)
    elif target_key != "":
        print("❌ หา Key นี้ไม่เจอครับ")

except FileNotFoundError:
    print(f"❌ ไม่พบไฟล์ '{file_path}' กรุณาตรวจสอบชื่อไฟล์และตำแหน่งอีกครั้ง")
except Exception as e:
    print(f"❌ เกิดข้อผิดพลาด: {e}")