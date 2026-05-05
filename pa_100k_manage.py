import pandas as pd
import matplotlib.pyplot as plt

# โหลดไฟล์ (สมมติว่า column แรกคือ image_name)
df = pd.read_csv(r"C:\Users\pmach\Downloads\PA-100K\train.csv")
attributes = df.columns[1:] # เลือกเฉพาะชื่อ attribute

# นับจำนวนคนที่มี attribute นั้นๆ (ค่าเป็น 1)
counts = df[attributes].sum().sort_values(ascending=False)

# Plot กราฟดูความต่าง
plt.figure(figsize=(12, 6))
counts.plot(kind='bar')
plt.title('Distribution of Attributes in PA-100K')
plt.ylabel('Number of Samples (Positive)')
plt.show()

# พิมพ์สัดส่วนออกมาดู
print(counts / len(df) * 100) # ดูเป็น %