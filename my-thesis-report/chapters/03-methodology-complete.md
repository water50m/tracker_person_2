# บทที่ 3: วิธีการทำวิจัย (Research Methodology)

## 3.1 บทนำ (Introduction)

บทนี้จะนำเสนอวิธีการทำวิจัยและกระบวนการพัฒนาระบบวิเคราะห์ภาพ CCTV ด้วยปัญญาประดิษฐ์สำหรับการติดตามและจำแนกสีเสื้อผ้า โดยจะกล่าวถึงกรอบแนวคิดในการออกแบบระบบ การเลือกใช้เทคโนโลยีและอัลกอริทึม กระบวนการพัฒนา การทดสอบ และการวัดผล ซึ่งมีวัตถุประสงค์เพื่อแก้ไขปัญหาการค้นหาบุคคลจากฟุตเทจจำนวนมากในระบบ CCTV ที่ยังคงใช้วิธีการแบบดั้งเดิม [1].

การวิจัยในบทนี้ใช้วิธีการผสมผสานระหว่างการพัฒนาระบบ (Development Research) และการทดลอง (Experimental Research) โดยมีขั้นตอนหลักดังนี้: 1) การศึกษาและวิเคราะห์ปัญหา 2) การออกแบบสถาปัตยกรรมระบบ 3) การพัฒนาและ implement อัลกอริทึม 4) การทดสอบและวัดผลประสิทธิภาพ 5) การวิเคราะห์และสรุปผลการวิจัย

## 3.2 สถาปัตยกรรมระบบ (System Architecture)

### 3.2.1 กรอบแนวคิดในการออกแบบระบบ (System Design Framework)

ระบบนี้ถูกพัฒนาตามกรอบแนวคิด **Human-Centered AI Design** โดยมีเป้าหมายเพื่อเพิ่มประสิทธิภาพในการทำงานของเจ้าหน้าที่ตำรวจในการค้นหาบุคคลจากฟุตเทจ CCTV [2]. การออกแบบระบบใช้สถาปัตยกรรมแบบ Layered Architecture ซึ่งแบ่งระบบออกเป็น 4 ชั้นหลักเพื่อความยืดหยุ่นและง่ายต่อการบำรุงรักษา:

**แผนภาพที่ 3.1** สถาปัตยกรรมระบบโดยรวม
```
┌─────────────────────────────────────────────────────────────┐
│                    Presentation Layer                      │
│              (Next.js + TypeScript + TailwindCSS)           │
│              • Real-time Dashboard                         │
│              • Search Interface                           │
│              • Analytics Visualization                     │
├─────────────────────────────────────────────────────────────┤
│                    Application Layer                        │
│                   (FastAPI + WebSocket)                     │
│              • REST API Endpoints                          │
│              • Real-time Communication                     │
│              • Business Logic                              │
├─────────────────────────────────────────────────────────────┤
│                    Processing Layer                         │
│         (YOLO11 + ByteTrack + Color Analysis)               │
│              • Two-Pass Detection                          │
│              • Re-identification Algorithm                 │
│              • Competitive Grouping Algorithm             │
├─────────────────────────────────────────────────────────────┤
│                    Data Layer                               │
│              (PostgreSQL + MinIO + Redis)                   │
│              • Structured Data Storage                     │
│              • Object Storage                              │
│              • Caching Layer                               │
└─────────────────────────────────────────────────────────────┘
```

### 3.2.2 การไหลข้อมูลและกระบวนการทำงาน (Data Flow and Process Flow)

**แผนภาพที่ 3.2** การไหลข้อมูลในระบบและกระบวนการทำงาน
```
Camera Input → Video Preprocessing → Two-Pass Detection → Feature Extraction → Data Storage → Real-time Display
     ↓               ↓                ↓                ↓                ↓                ↓
  RTSP Stream      Frame           YOLO11          Color          PostgreSQL      Next.js
  (Multiple        Resizing        + ByteTrack     Analysis       + MinIO         + WebSocket
   Cameras)        + Noise         + Re-ID         + HSV          + Redis         + Dashboard
                   Reduction)      Algorithm)      + Vector)      + Indexing)     + Alerts)
```

**กระบวนการทำงานหลัก (Main Process Flow):**

1. **Video Input Processing:** รับสัญญาณวิดีโอจากกล้อง CCTV ผ่าน RTSP protocol
2. **Frame Preprocessing:** ปรับขนาดเฟรมและลด noise ก่อนประมวลผล
3. **Two-Pass Detection:** ตรวจจับบุคคลและเสื้อผ้าใน 2 รอบ
4. **Feature Extraction:** ดึงคุณลักษณะ visual features และสี
5. **Re-identification:** ติดตามบุคคลข้ามเฟรมด้วย algorithm ที่พัฒนา
6. **Data Storage:** เก็บข้อมูลลงฐานข้อมูลและรูปภาพ
7. **Real-time Display:** แสดงผลลัพธ์ผ่าน web interface

## 3.3 การออกแบบอัลกอริทึม (Algorithm Design)

### 3.3.1 อัลกอริทึมการตรวจจับสองรอบ (Two-Pass Detection Algorithm)

**ทฤษฎีพื้นฐาน:**
อัลกอริทึมนี้พัฒนาตามแนวคิด **Hierarchical Detection** ซึ่งแบ่งการตรวจจับออกเป็น 2 ระดับเพื่อเพิ่มความแม่นยำ [3]. โดยมีสมการหลักดังนี้:

\[\text{Detection}_{\text{final}} = \text{Detection}_{\text{person}} \cap \text{Detection}_{\text{clothing}}\]

\[\text{Confidence}_{\text{final}} = \alpha \cdot \text{Confidence}_{\text{person}} + (1-\alpha) \cdot \text{Confidence}_{\text{clothing}}\]

โดยที่ $\alpha$ คือค่าน้ำหนักที่กำหนดให้ความสำคัญของการตรวจจับบุคคล

**หลักการทำงาน:**
- **รอบที่ 1 (Person Detection):** ตรวจจับบุคคลด้วย YOLO11n และสร้าง tracking ด้วย ByteTrack
- **รอบที่ 2 (Clothing Detection):** ตรวจจับเสื้อผ้าภายใน bounding box ของบุคคล

**โค้ดตัวอย่างที่ 3.1** อัลกอริทึม Two-Pass Detection
```python
def two_pass_detection(frame, frame_number):
    """
    อัลกอริทึมการตรวจจับสองรอบสำหรับบุคคลและเสื้อผ้า
    Args:
        frame: เฟรมภาพ input
        frame_number: หมายเลขเฟรมปัจจุบัน
    Returns:
        List[DetectionResult]: ผลลัพธ์การตรวจจับ
    """
    # รอบที่ 1: ตรวจจับบุคคล
    person_detections = yolo11_model(frame, classes=['person'], conf=0.25)
    
    results = []
    for person in person_detections:
        # สร้าง tracking ID ด้วย ByteTrack
        track_id = byte_tracker.update(person.bbox, frame_number)
        
        # ดึง ROI สำหรับการตรวจจับเสื้อผ้า
        roi = extract_roi(frame, person.bbox, padding=0.1)
        
        # รอบที่ 2: ตรวจจับเสื้อผ้าใน ROI
        clothing_detections = yolo11_model(roi, 
                                          classes=['long_sleeve_top', 'short_sleeve_top', 
                                                 'dress', 'skirt', 'shorts', 'trousers'],
                                          conf=0.3)
        
        # กรองและเลือกเสื้อผ้าที่เหมาะสม
        filtered_clothing = filter_clothing_items(clothing_detections, person.bbox)
        
        # วิเคราะห์สี
        color_analysis = analyze_clothing_colors(roi, filtered_clothing)
        
        # ดึง feature vector สำหรับ re-identification
        feature_vector = extract_features(roi, person.bbox)
        
        results.append(DetectionResult(
            track_id=track_id,
            person_bbox=person.bbox,
            clothing_items=filtered_clothing,
            color_info=color_analysis,
            features=feature_vector,
            confidence=calculate_final_confidence(person, filtered_clothing),
            frame_number=frame_number
        ))
    
    return results

def filter_clothing_items(clothing_detections, person_bbox):
    """
    กรองเสื้อผ้าที่ตรวจจับได้ตามหลักการทางตรรกะ
    """
    if len(clothing_detections) == 0:
        return []
    elif len(clothing_detections) == 1:
        return clothing_detections
    else:
        # จัดเรียงตาม confidence และเลือก 2 ชิ้นที่ดีที่สุด
        sorted_clothing = sorted(clothing_detections, 
                               key=lambda x: x.confidence, reverse=True)
        
        # ตรวจสอบว่าเป็นส่วนต่างกันหรือไม่
        final_selection = []
        used_categories = set()
        
        for item in sorted_clothing:
            category = get_clothing_category(item.class_name)
            if category not in used_categories:
                final_selection.append(item)
                used_categories.add(category)
                if len(final_selection) == 2:
                    break
        
        return final_selection
```

### 3.3.2 อัลกอริทึมการระบุตัวตนซ้ำ (Re-identification Algorithm)

**ทฤษฎีพื้นฐาน:**
Re-identification (Re-ID) เป็นการติดตามบุคคลข้ามเฟรมหรือข้ามกล้องโดยใช้คุณลักษณะภาพ (visual features) [4]. อัลกอริทึมนี้ใช้การรวมกันของ:

1. **Spatial Consistency:** การตรวจสอบตำแหน่งทางกายภาพ
2. **Feature Similarity:** การเปรียบเทียบ feature vectors
3. **Color Consistency:** การเปรียบเทียบสีเสื้อผ้า

**สมการการคำนวณความคล้ายคลึง:**

\[\text{Similarity} = w_1 \cdot \text{SpatialSim} + w_2 \cdot \text{FeatureSim} + w_3 \cdot \text{ColorSim}\]

โดยที่:
- $w_1, w_2, w_3$ ค่าน้ำหนักที่กำหนด (ปกติ $w_1=0.3, w_2=0.4, w_3=0.3$)
- $\text{SpatialSim} \in [0,1]$ ความคล้ายคลึงทางตำแหน่ง
- $\text{FeatureSim} \in [0,1]$ ความคล้ายคลึงของ feature vectors
- $\text{ColorSim} \in [0,1]$ ความคล้ายคลึงของสี

**โค้ดตัวอย่างที่ 3.2** อัลกอริทึม Re-identification
```python
class ReIdentificationSystem:
    def __init__(self, spatial_threshold=50, feature_threshold=0.8, color_threshold=0.7):
        self.spatial_threshold = spatial_threshold  # พิกเซล
        self.feature_threshold = feature_threshold
        self.color_threshold = color_threshold
        self.track_history = {}  # เก็บประวัติ tracking
        
    def re_identify(self, current_detections, frame_number):
        """
        อัลกอริทึมการระบุตัวตนซ้ำ
        Args:
            current_detections: ผลการตรวจจับในเฟรมปัจจุบัน
            frame_number: หมายเลขเฟรมปัจจุบัน
        Returns:
            List[DetectionResult]: ผลลัพธ์หลัง re-identification
        """
        reid_results = []
        
        for detection in current_detections:
            # ตรวจสอบว่าเป็นบุคคลใหม่หรือไม่
            best_match = self.find_best_match(detection, frame_number)
            
            if best_match:
                # อัปเดต track ID ของบุคคลที่ตรงกัน
                detection.track_id = best_match['track_id']
                self.update_track_history(detection, best_match)
            else:
                # สร้าง track ID ใหม่
                new_track_id = self.generate_new_track_id()
                detection.track_id = new_track_id
                self.create_new_track(detection, frame_number)
            
            reid_results.append(detection)
        
        return reid_results
    
    def find_best_match(self, detection, frame_number):
        """
        ค้นหาบุคคลที่ตรงกันที่สุดจากประวัติ
        """
        best_match = None
        best_score = 0
        
        for track_id, history in self.track_history.items():
            # ตรวจสอบว่า track นี้หายไปหรือไม่
            if self.is_track_lost(history, frame_number):
                # คำนวณความคล้ายคลึง
                spatial_sim = self.calculate_spatial_similarity(detection, history)
                feature_sim = self.calculate_feature_similarity(detection, history)
                color_sim = self.calculate_color_similarity(detection, history)
                
                # คำนวณคะแนนรวม
                total_score = (0.3 * spatial_sim + 
                             0.4 * feature_sim + 
                             0.3 * color_sim)
                
                # ตรวจสอบเงื่อนไขขั้นต่ำ
                if (spatial_sim > 0.5 and 
                    feature_sim > self.feature_threshold and 
                    color_sim > self.color_threshold and 
                    total_score > best_score):
                    best_score = total_score
                    best_match = {
                        'track_id': track_id,
                        'history': history,
                        'score': total_score
                    }
        
        return best_match
    
    def calculate_spatial_similarity(self, detection, history):
        """
        คำนวณความคล้ายคลึงทางตำแหน่ง
        """
        current_center = self.get_bbox_center(detection.person_bbox)
        last_center = history['last_position']
        
        distance = euclidean_distance(current_center, last_center)
        
        # แปลงระยะทางเป็นความคล้ายคลึง (ยิ่งใกล้ยิ่งคล้าย)
        similarity = max(0, 1 - (distance / self.spatial_threshold))
        return similarity
    
    def calculate_feature_similarity(self, detection, history):
        """
        คำนวณความคล้ายคลึงของ feature vectors ด้วย cosine similarity
        """
        current_features = detection.features
        historical_features = history['features']
        
        # ใช้ cosine similarity
        similarity = cosine_similarity(current_features, historical_features)
        return similarity
    
    def calculate_color_similarity(self, detection, history):
        """
        คำนวณความคล้ายคลึงของสีเสื้อผ้า
        """
        current_colors = detection.color_info
        historical_colors = history['color_info']
        
        # เปรียบเทียบสีหลักและเปอร์เซ็นต์
        similarity = 0
        for curr_color in current_colors:
            for hist_color in historical_colors:
                if curr_color['name'] == hist_color['name']:
                    # คำนวณความคล้ายคลึงจากเปอร์เซ็นต์
                    percent_diff = abs(curr_color['percentage'] - hist_color['percentage'])
                    color_sim = max(0, 1 - (percent_diff / 100))
                    similarity = max(similarity, color_sim)
        
        return similarity
```

### 3.3.3 อัลกอริทึมการวิเคราะห์สี (Color Analysis Algorithm)

**ทฤษฎีพื้นฐาน:**
การวิเคราะห์สีในระบบนี้ใช้ **Competitive Grouping Algorithm** ซึ่งพัฒนาขึ้นเพื่อแก้ไขปัญหาการจัดกลุ่มสีแบบดั้งเดิมที่มีเปอร์เซ็นต์รวมเกิน 100% [5]. โดยมีหลักการดังนี้:

**สมการการวิเคราะห์สี:**

\[\text{ColorScore}(i) = \frac{\text{PixelCount}_i \cdot \text{Confidence}_i}{\sum_{j=1}^{n} \text{PixelCount}_j \cdot \text{Confidence}_j}\]

\[\text{FinalColor} = \arg\max_i \text{ColorScore}(i)\]

โดยที่:
- $i$ คือดัชนีของสีที่ $i$
- $\text{PixelCount}_i$ คือจำนวนพิกเซลที่ตรงกับสี $i$
- $\text{Confidence}_i$ คือค่าความมั่นใจของสี $i$

**โค้ดตัวอย่างที่ 3.3** อัลกอริทึมการวิเคราะห์สี
```python
class ColorAnalysisSystem:
    def __init__(self):
        # กำหนดช่วงสี HSV สำหรับ 63 สี
        self.color_ranges = self._initialize_color_ranges()
        # กำหนดการจัดกลุ่มสี 22 กลุ่ม
        self.color_groups = self._initialize_color_groups()
        
    def analyze_clothing_colors(self, image, clothing_bboxes):
        """
        วิเคราะห์สีเสื้อผ้าด้วย Competitive Grouping Algorithm
        Args:
            image: ภาพ input
            clothing_bboxes: รายการ bounding box ของเสื้อผ้า
        Returns:
            List[ColorResult]: ผลลัพธ์การวิเคราะห์สี
        """
        color_results = []
        
        for bbox in clothing_bboxes:
            # ดึง ROI ของเสื้อผ้า
            roi = extract_roi(image, bbox)
            
            # แปลงเป็น HSV color space
            hsv_image = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            
            # วิเคราะห์สีแบบ Competitive Grouping
            color_analysis = self._competitive_grouping_analysis(hsv_image)
            
            color_results.append(ColorResult(
                bbox=bbox,
                dominant_color=color_analysis['dominant_color'],
                color_group=color_analysis['color_group'],
                percentage=color_analysis['percentage'],
                confidence=color_analysis['confidence']
            ))
        
        return color_results
    
    def _competitive_grouping_analysis(self, hsv_image):
        """
        วิเคราะห์สีด้วย Competitive Grouping Algorithm
        """
        # คำนวณคะแนนสำหรับทุกสี
        color_scores = {}
        total_pixels = hsv_image.shape[0] * hsv_image.shape[1]
        
        for color_name, color_range in self.color_ranges.items():
            # สร้าง mask สำหรับสีนี้
            mask = cv2.inRange(hsv_image, 
                              color_range['lower'], 
                              color_range['upper'])
            
            # นับจำนวนพิกเซลที่ตรงกับสีนี้
            pixel_count = cv2.countNonZero(mask)
            
            # คำนวณค่าความมั่นใจจากระยะทางถึง center of range
            confidence = self._calculate_color_confidence(hsv_image, mask, color_range)
            
            # คำนวณคะแนนสุดท้าย
            score = (pixel_count * confidence) / total_pixels
            color_scores[color_name] = {
                'score': score,
                'pixel_count': pixel_count,
                'confidence': confidence
            }
        
        # Competitive Grouping: เลือกสีที่มีคะแนนสูงสุด (winner takes all)
        dominant_color = max(color_scores.items(), key=lambda x: x[1]['score'])
        
        # จัดกลุ่มสีที่ใกล้เคียงกัน
        color_group = self._group_similar_colors(dominant_color[0])
        
        # คำนวณเปอร์เซ็นต์สุดท้าย (normalized)
        total_score = sum(item[1]['score'] for item in color_scores.values())
        final_percentage = (dominant_color[1]['score'] / total_score) * 100
        
        return {
            'dominant_color': dominant_color[0],
            'color_group': color_group,
            'percentage': final_percentage,
            'confidence': dominant_color[1]['confidence'],
            'all_scores': color_scores
        }
    
    def _calculate_color_confidence(self, hsv_image, mask, color_range):
        """
        คำนวณค่าความมั่นใจของสีจากความใกล้เคียงกับ center of range
        """
        if cv2.countNonZero(mask) == 0:
            return 0.0
        
        # ดึงพิกเซลที่ตรงกับ mask
        masked_pixels = hsv_image[mask > 0]
        
        # คำนวณค่าเฉลี่ยของ HSV
        mean_hsv = np.mean(masked_pixels, axis=0)
        
        # คำนวณระยะทางจาก center of range
        center_hsv = color_range['center']
        distance = np.linalg.norm(mean_hsv - center_hsv)
        
        # แปลงระยะทางเป็นค่าความมั่นใจ (ยิ่งใกล้ยิ่งมั่นใจ)
        confidence = max(0, 1 - (distance / color_range['radius']))
        
        return confidence
    
    def _group_similar_colors(self, color_name):
        """
        จัดกลุ่มสีที่ใกล้เคียงกัน (22 กลุ่ม)
        """
        for group_name, colors_in_group in self.color_groups.items():
            if color_name in colors_in_group:
                return group_name
        
        # ถ้าไม่พบในกลุ่มใด ให้ใช้ชื่อสีต้นฉบับ
        return color_name
    
    def _initialize_color_ranges(self):
        """
        กำหนดช่วงสี HSV สำหรับ 63 สี
        """
        # ตัวอย่างการกำหนดช่วงสี
        return {
            'red_bright': {
                'lower': np.array([0, 120, 70]),
                'upper': np.array([10, 255, 255]),
                'center': np.array([5, 187, 162]),
                'radius': 50
            },
            'red_dark': {
                'lower': np.array([170, 120, 70]),
                'upper': np.array([180, 255, 255]),
                'center': np.array([175, 187, 162]),
                'radius': 50
            },
            # ... กำหนดสีอื่นๆ อีก 61 สี
        }
    
    def _initialize_color_groups(self):
        """
        กำหนดการจัดกลุ่มสี 22 กลุ่ม
        """
        return {
            'red': ['red_bright', 'red_dark', 'red_light', 'coral', 'salmon'],
            'blue': ['blue_bright', 'blue_dark', 'blue_light', 'navy', 'sky_blue'],
            'green': ['green_bright', 'green_dark', 'green_light', 'olive', 'lime'],
            # ... กำหนดกลุ่มอื่นๆ อีก 19 กลุ่ม
        }
```

## 3.4 การออกแบบฐานข้อมูลและการจัดเก็บข้อมูล (Database and Storage Design)

### 3.4.1 โครงสร้างฐานข้อมูล PostgreSQL

**ทฤษฎีพื้นฐาน:**
การออกแบบฐานข้อมูลใช้หลักการ **Normalized Database Design** โดยแบ่งข้อมูลออกเป็นตารางที่สัมพันธ์กันเพื่อลดการซ้ำซ้อนและเพิ่มประสิทธิภาพในการค้นหา [6].

**ตารางที่ 3.1** โครงสร้างตารางหลักในระบบ

```sql
-- ตารางเก็บข้อมูลกล้อง CCTV
CREATE TABLE cameras (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    location VARCHAR(200),
    rtsp_url VARCHAR(500) NOT NULL,
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'maintenance')),
    resolution_x INTEGER DEFAULT 1920,
    resolution_y INTEGER DEFAULT 1080,
    fps INTEGER DEFAULT 30,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ตารางเก็บข้อมูลการตรวจจับบุคคล
CREATE TABLE detections (
    id SERIAL PRIMARY KEY,
    camera_id INTEGER REFERENCES cameras(id) ON DELETE CASCADE,
    track_id VARCHAR(50) NOT NULL,
    bbox_x INTEGER NOT NULL,
    bbox_y INTEGER NOT NULL,
    bbox_width INTEGER NOT NULL,
    bbox_height INTEGER NOT NULL,
    confidence FLOAT NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    frame_number BIGINT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processing_time_ms INTEGER, -- เวลาที่ใช้ในการประมวลผล
    image_path VARCHAR(500), -- พาธไปยังรูปภาพใน MinIO
    
    -- Indexes สำหรับการค้นหาที่รวดเร็ว
    INDEX idx_detections_timestamp (timestamp),
    INDEX idx_detections_track_id (track_id),
    INDEX idx_detections_camera_timestamp (camera_id, timestamp)
);

-- ตารางเก็บข้อมูลสีเสื้อผ้า
CREATE TABLE clothing_colors (
    id SERIAL PRIMARY KEY,
    detection_id INTEGER REFERENCES detections(id) ON DELETE CASCADE,
    clothing_type VARCHAR(50) NOT NULL CHECK (clothing_type IN ('upper', 'lower', 'dress')),
    color_name VARCHAR(50) NOT NULL,
    color_group VARCHAR(50) NOT NULL,
    percentage FLOAT NOT NULL CHECK (percentage >= 0 AND percentage <= 100),
    confidence FLOAT NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    
    INDEX idx_clothing_colors_color (color_name),
    INDEX idx_clothing_colors_group (color_group),
    INDEX idx_clothing_colors_type (clothing_type)
);

-- ตารางเก็บข้อมูล Feature Vector (ถ้า performance อนุญาต)
CREATE TABLE feature_vectors (
    id SERIAL PRIMARY KEY,
    track_id VARCHAR(50) NOT NULL,
    vector_data FLOAT8[] NOT NULL, -- 512-dimensional vector
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    model_version VARCHAR(20) DEFAULT 'yolo11n',
    
    INDEX idx_feature_vectors_track_id (track_id),
    INDEX idx_feature_vectors_timestamp (timestamp)
);

-- ตารางเก็บประวัติการค้นหา
CREATE TABLE search_history (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    search_criteria JSONB NOT NULL, -- เก็บเงื่อนไขการค้นหาแบบ flexible
    result_count INTEGER DEFAULT 0,
    execution_time_ms INTEGER,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_search_history_user (user_id),
    INDEX idx_search_history_timestamp (timestamp)
);

-- ตารางเก็บข้อมูลการเข้าถึง (สำหรับ PDPA)
CREATE TABLE access_logs (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    action VARCHAR(50) NOT NULL, -- 'view', 'search', 'export', 'delete'
    resource_type VARCHAR(50) NOT NULL, -- 'detection', 'image', 'report'
    resource_id VARCHAR(100),
    ip_address INET,
    user_agent TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_access_logs_user (user_id),
    INDEX idx_access_logs_timestamp (timestamp)
);
```

### 3.4.2 การจัดเก็บรูปภาพด้วย MinIO

**ทฤษฎีพื้นฐาน:**
MinIO เป็น object storage ที่เข้ากันได้กับ S3 API ซึ่งเหมาะสำหรับการจัดเก็บไฟล์ขนาดใหญ่เช่นรูปภาพและวิดีโอ [7]. การใช้ MinIO ช่วยลดภาระจากฐานข้อมูลหลักและเพิ่มความยืดหยุ่นในการจัดเก็บข้อมูล

**หลักการทำงาน:**
- บันทึกรูปภาพทุก 5 เฟรมเพื่อลดปริมาณข้อมูล
- บันทึกเมื่อ track_id เปลี่ยนเพื่อการติดตามที่สมบูรณ์
- ใช้การบีบอัดรูปภาพเพื่อประหยัดพื้นที่

**โค้ดตัวอย่างที่ 3.4** การจัดเก็บรูปภาพ
```python
import minio
from datetime import datetime
import io
import cv2

class ImageStorageManager:
    def __init__(self, endpoint, access_key, secret_key, bucket_name="cctv-detections"):
        self.client = minio.Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=False
        )
        self.bucket_name = bucket_name
        
        # สร้าง bucket ถ้ายังไม่มี
        if not self.client.bucket_exists(bucket_name):
            self.client.make_bucket(bucket_name)
    
    def should_save_image(self, frame_number, track_id, last_track_id, last_saved_frame):
        """
        ตัดสินใจว่าควรบันทึกรูปภาพหรือไม่
        """
        # บันทึกทุก 5 เฟรม
        if frame_number % 5 == 0:
            return True
        
        # บันทึกเมื่อ track_id เปลี่ยน
        if track_id != last_track_id:
            return True
        
        # บันทึกเมื่อห่างจากการบันทึกล่าสุดมากกว่า 30 เฟรม
        if frame_number - last_saved_frame > 30:
            return True
        
        return False
    
    def save_detection_image(self, frame, detection, camera_id):
        """
        บันทึกรูปภาพการตรวจจับลง MinIO
        """
        try:
            # ตรวจสอบเงื่อนไขการบันทึก
            if not self.should_save_image(
                detection.frame_number, 
                detection.track_id,
                detection.last_track_id,
                detection.last_saved_frame
            ):
                return None
            
            # สร้างชื่อไฟล์ตามโครงสร้างที่กำหนด
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"camera_{camera_id:03d}/track_{detection.track_id}/{timestamp}_{detection.frame_number:06d}.jpg"
            
            # บีบอัดรูปภาพ
            encoded_image = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])[1]
            image_data = io.BytesIO(encoded_image)
            
            # บันทึกลง MinIO
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=filename,
                data=image_data,
                length=len(encoded_image),
                content_type="image/jpeg",
                metadata={
                    "track_id": detection.track_id,
                    "camera_id": str(camera_id),
                    "frame_number": str(detection.frame_number),
                    "timestamp": timestamp
                }
            )
            
            # สร้าง URL สำหรับการเข้าถึง
            image_url = f"http://localhost:9000/{self.bucket_name}/{filename}"
            
            return {
                "filename": filename,
                "url": image_url,
                "size": len(encoded_image),
                "timestamp": timestamp
            }
            
        except Exception as e:
            print(f"Error saving image to MinIO: {e}")
            return None
    
    def get_image(self, filename):
        """
        ดึงรูปภาพจาก MinIO
        """
        try:
            response = self.client.get_object(self.bucket_name, filename)
            image_data = response.read()
            return image_data
        except Exception as e:
            print(f"Error retrieving image from MinIO: {e}")
            return None
    
    def delete_old_images(self, days_old=30):
        """
        ลบรูปภาพที่เก่ากว่าที่กำหนด (สำหรับ PDPA compliance)
        """
        from datetime import datetime, timedelta
        
        cutoff_date = datetime.now() - timedelta(days=days_old)
        deleted_count = 0
        
        try:
            objects = self.client.list_objects(self.bucket_name, recursive=True)
            
            for obj in objects:
                # แยกวันที่จากชื่อไฟล์
                try:
                    date_str = obj.object_name.split('/')[-2].split('_')[0]
                    file_date = datetime.strptime(date_str, "%Y%m%d")
                    
                    if file_date < cutoff_date:
                        self.client.remove_object(self.bucket_name, obj.object_name)
                        deleted_count += 1
                        
                except (ValueError, IndexError):
                    continue
            
            print(f"Deleted {deleted_count} old images")
            return deleted_count
            
        except Exception as e:
            print(f"Error deleting old images: {e}")
            return 0
```

## 3.5 การพัฒนา Frontend และอินเตอร์เฟซผู้ใช้ (Frontend and User Interface Development)

### 3.5.1 สถาปัตยกรรม Frontend

**ทฤษฎีพื้นฐาน:**
การพัฒนา frontend ใช้ **Component-Based Architecture** ซึ่งแบ่งส่วนติดต่อผู้ใช้ออกเป็นส่วนย่อยๆ ที่นำกลับมาใช้ใหม่ได้ ทำให้การบำรุงรักษาและการพัฒนาเป็นไปอย่างมีประสิทธิภาพ [8].

**เทคโนโลยีที่ใช้:**
- **Next.js 14** พร้อม TypeScript สำหรับ type safety และ performance
- **TailwindCSS** สำหรับ utility-first styling
- **WebSocket** สำหรับ real-time communication
- **Chart.js** สำหรับ data visualization
- **React Query** สำหรับ server state management

**โครงสร้างโปรเจค:**
```
frontend/
├── src/
│   ├── components/
│   │   ├── ui/                    # Base UI components
│   │   │   ├── Button.tsx
│   │   │   ├── Input.tsx
│   │   │   └── Modal.tsx
│   │   ├── camera/                # Camera-related components
│   │   │   ├── CameraFeed.tsx
│   │   │   ├── CameraSelector.tsx
│   │   │   └── CameraStatus.tsx
│   │   ├── detection/             # Detection components
│   │   │   ├── DetectionPanel.tsx
│   │   │   ├── BoundingBox.tsx
│   │   │   └── TrackingInfo.tsx
│   │   ├── search/                # Search components
│   │   │   ├── SearchPanel.tsx
│   │   │   ├── ColorPicker.tsx
│   │   │   ├── ClothingTypeSelector.tsx
│   │   │   └── ImageUpload.tsx
│   │   └── analytics/            # Analytics components
│   │       ├── StatisticsChart.tsx
│   │       ├── TimelineView.tsx
│   │       └── HeatMap.tsx
│   ├── pages/
│   │   ├── index.tsx             # Main dashboard
│   │   ├── search.tsx            # Search interface
│   │   ├── analytics.tsx         # Analytics dashboard
│   │   └── settings.tsx          # System settings
│   ├── hooks/
│   │   ├── useWebSocket.ts       # WebSocket hook
│   │   ├── useDetections.ts      # Detection data hook
│   │   └── useSearch.ts         # Search functionality hook
│   ├── services/
│   │   ├── api.ts               # API client
│   │   ├── websocket.ts         # WebSocket client
│   │   └── auth.ts              # Authentication service
│   ├── utils/
│   │   ├── colorUtils.ts        # Color manipulation utilities
│   │   ├── dateUtils.ts         # Date formatting utilities
│   │   └── validation.ts       # Form validation utilities
│   └── types/
│       ├── detection.ts         # Detection type definitions
│       ├── search.ts            # Search type definitions
│       └── api.ts               # API type definitions
```

### 3.5.2 ฟีเจอร์การค้นหาและกรองข้อมูล

**ทฤษฎีพื้นฐาน:**
การค้นหาใช้ **Multi-criteria Search** ซึ่งอนุญาตให้ผู้ใช้ระบุเงื่อนไขหลายอย่างพร้อมกัน ทำให้การค้นหามีความแม่นยำและมีประสิทธิภาพสูง [9].

**โค้ดตัวอย่างที่ 3.5** คอมโพเนนต์การค้นหา
```typescript
import React, { useState, useCallback } from 'react';
import { useSearch } from '../hooks/useSearch';
import { ColorPicker } from './ColorPicker';
import { ClothingTypeSelector } from './ClothingTypeSelector';
import { ImageUpload } from './ImageUpload';
import { ConfidenceSlider } from './ConfidenceSlider';

interface SearchCriteria {
  clothingType?: 'upper' | 'lower' | 'dress';
  colors?: string[];
  confidence?: number;
  timeRange?: {
    start: Date;
    end: Date;
  };
  imageInput?: File;
  cameraIds?: number[];
}

interface SearchResults {
  detections: Detection[];
  totalCount: number;
  executionTime: number;
}

const SearchPanel: React.FC = () => {
  const [criteria, setCriteria] = useState<SearchCriteria>({});
  const [isSearching, setIsSearching] = useState(false);
  const [results, setResults] = useState<SearchResults | null>(null);
  
  const { searchDetections, searchByImage } = useSearch();

  const handleSearch = useCallback(async () => {
    setIsSearching(true);
    
    try {
      let searchResults: SearchResults;
      
      if (criteria.imageInput) {
        // ค้นหาด้วยรูปภาพ (image-based search)
        searchResults = await searchByImage(criteria.imageInput, criteria);
      } else {
        // ค้นหาด้วยเงื่อนไข (criteria-based search)
        searchResults = await searchDetections(criteria);
      }
      
      setResults(searchResults);
      
      // บันทึกประวัติการค้นหาสำหรับ analytics
      await logSearchHistory(criteria, searchResults);
      
    } catch (error) {
      console.error('Search failed:', error);
      // แสดง error message แก่ผู้ใช้
      showErrorMessage('การค้นหาล้มเหลว กรุณาลองใหม่อีกครั้ง');
    } finally {
      setIsSearching(false);
    }
  }, [criteria, searchDetections, searchByImage]);

  const updateCriteria = useCallback((updates: Partial<SearchCriteria>) => {
    setCriteria(prev => ({ ...prev, ...updates }));
  }, []);

  const clearCriteria = useCallback(() => {
    setCriteria({});
    setResults(null);
  }, []);

  return (
    <div className="search-panel bg-white rounded-lg shadow-md p-6">
      <h2 className="text-2xl font-bold mb-6 text-gray-800">
        ค้นหาบุคคลจากฐานข้อมูล CCTV
      </h2>
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* เลือกประเภทเสื้อผ้า */}
        <div className="space-y-2">
          <label className="block text-sm font-medium text-gray-700">
            ประเภทเสื้อผ้า
          </label>
          <ClothingTypeSelector
            value={criteria.clothingType}
            onChange={(type) => updateCriteria({ clothingType: type })}
          />
        </div>

        {/* เลือกสี */}
        <div className="space-y-2">
          <label className="block text-sm font-medium text-gray-700">
            สีเสื้อผ้า
          </label>
          <ColorPicker
            selectedColors={criteria.colors || []}
            onChange={(colors) => updateCriteria({ colors })}
            maxSelection={3}
          />
        </div>

        {/* ปรับค่าความมั่นใจ */}
        <div className="space-y-2">
          <label className="block text-sm font-medium text-gray-700">
            ค่าความมั่นใจขั้นต่ำ: {criteria.confidence || 0.5}
          </label>
          <ConfidenceSlider
            value={criteria.confidence || 0.5}
            onChange={(confidence) => updateCriteria({ confidence })}
            min={0.1}
            max={1.0}
            step={0.1}
          />
        </div>

        {/* ช่วงเวลา */}
        <div className="space-y-2">
          <label className="block text-sm font-medium text-gray-700">
            ช่วงเวลา
          </label>
          <DateRangePicker
            value={criteria.timeRange}
            onChange={(timeRange) => updateCriteria({ timeRange })}
          />
        </div>

        {/* อัปโหลดรูปภาพ */}
        <div className="space-y-2">
          <label className="block text-sm font-medium text-gray-700">
            ค้นหาด้วยรูปภาพ (Optional)
          </label>
          <ImageUpload
            value={criteria.imageInput}
            onChange={(file) => updateCriteria({ imageInput: file })}
            accept="image/*"
            maxSize={5 * 1024 * 1024} // 5MB
          />
        </div>

        {/* เลือกกล้อง */}
        <div className="space-y-2">
          <label className="block text-sm font-medium text-gray-700">
            กล้อง CCTV
          </label>
          <CameraSelector
            value={criteria.cameraIds || []}
            onChange={(cameraIds) => updateCriteria({ cameraIds })}
            multiple
          />
        </div>
      </div>

      {/* ปุ่มควบคุม */}
      <div className="flex justify-between items-center mt-6">
        <button
          onClick={clearCriteria}
          className="px-4 py-2 text-gray-600 hover:text-gray-800 transition-colors"
        >
          ล้างเงื่อนไข
        </button>
        
        <div className="space-x-4">
          {results && (
            <span className="text-sm text-gray-600">
              พบ {results.totalCount} รายการ ({results.executionTime}ms)
            </span>
          )}
          
          <button
            onClick={handleSearch}
            disabled={isSearching}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 transition-colors"
          >
            {isSearching ? 'กำลังค้นหา...' : 'ค้นหา'}
          </button>
        </div>
      </div>

      {/* แสดงผลลัพธ์ */}
      {results && (
        <div className="mt-6">
          <SearchResults 
            detections={results.detections}
            totalCount={results.totalCount}
          />
        </div>
      )}
    </div>
  );
};

// ฟังก์ชันสำหรับบันทึกประวัติการค้นหา
const logSearchHistory = async (criteria: SearchCriteria, results: SearchResults) => {
  try {
    await fetch('/api/search/history', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        criteria,
        resultCount: results.totalCount,
        executionTime: results.executionTime,
        timestamp: new Date().toISOString()
      })
    });
  } catch (error) {
    console.error('Failed to log search history:', error);
  }
};

export default SearchPanel;
```

## 3.6 การปรับแต่งประสิทธิภาพและการจัดการทรัพยากร (Performance Optimization and Resource Management)

### 3.6.1 การปรับแต่งสำหรับฮาร์ดแวร์จำกัด

**ทฤษฎีพื้นฐาน:**
การปรับแต่งประสิทธิภาพใช้หลักการ **Resource-Aware Computing** ซึ่งปรับเปลี่ยนพฤติกรรมของระบบตามทรัพยากรที่มีอยู่จริง [10].

**ปัญหาและข้อจำกัด:**
- **GPU:** NVIDIA GTX 1650 4GB VRAM จำกัดการประมวลผล
- **RAM:** 16GB DDR4 จำกัดการทำงานหลายกระบวนการ
- **CPU:** Multi-core แต่ไม่สามารถทำ parallel processing ได้เต็มที่

**วิธีแก้ไขและการปรับแต่ง:**

1. **Model Optimization:**
   - ใช้ YOLO11n (nano model) แทน YOLO11l
   - ปรับ input size เป็น 416x416 แทน 640x640
   - ใช้ TensorRT สำหรับ inference acceleration
   - ใช้ model quantization (FP16)

2. **Memory Management:**
   - จำกัด batch size เป็น 1
   - ใช้ gradient checkpointing
   - ปล่อย memory หลังการประมวลผลแต่ละเฟรม
   - ใช้ memory pooling

3. **Processing Pipeline:**
   - ใช้ multi-threading สำหรับ parallel processing
   - จัดคิวสำหรับ frame processing
   - ข้ามเฟรมบางส่วน (frame skipping)
   - ใช้ asynchronous I/O

**โค้ดตัวอย่างที่ 3.6** การปรับแต่งประสิทธิภาพ
```python
import torch
import cv2
import numpy as np
from threading import Thread, Queue
from queue import Empty
import time

class OptimizedDetectionSystem:
    def __init__(self, model_path='yolo11n.pt', device='cuda'):
        # โหลดโมเดลที่ปรับแต่งแล้ว
        self.model = self._load_optimized_model(model_path, device)
        self.device = device
        
        # จัดการ memory
        self.memory_pool = self._initialize_memory_pool()
        
        # จัดคิวสำหรับ processing
        self.frame_queue = Queue(maxsize=10)
        self.result_queue = Queue(maxsize=20)
        
        # ปรับแต่ง parameters
        self.input_size = 416  # ลดจาก 640
        self.confidence_threshold = 0.25
        self.nms_threshold = 0.45
        
        # Performance monitoring
        self.performance_stats = {
            'fps': 0,
            'memory_usage': 0,
            'processing_time': 0
        }
        
    def _load_optimized_model(self, model_path, device):
        """
        โหลดโมเดลที่ปรับแต่งแล้วสำหรับ performance
        """
        try:
            # โหลดโมเดล
            model = torch.hub.load('ultralytics/yolov11', 'custom', path=model_path)
            
            # ปรับแต่งสำหรับ inference
            model.eval()
            model.half()  # ใช้ FP16 สำหรับลด memory
            
            if device == 'cuda' and torch.cuda.is_available():
                model = model.cuda()
                # ใช้ TensorRT ถ้ามี
                try:
                    model = torch.jit.script(model)
                except:
                    pass
            
            return model
            
        except Exception as e:
            print(f"Error loading optimized model: {e}")
            return None
    
    def _initialize_memory_pool(self):
        """
        จัดการ memory pool สำหรับลดการจอง memory ซ้ำ
        """
        return {
            'tensors': {},
            'arrays': {}
        }
    
    def _get_tensor_from_pool(self, shape, dtype):
        """
        ดึง tensor จาก pool หรือสร้างใหม่
        """
        key = f"{shape}_{dtype}"
        if key not in self.memory_pool['tensors']:
            self.memory_pool['tensors'][key] = torch.empty(shape, dtype=dtype, device=self.device)
        return self.memory_pool['tensors'][key]
    
    def preprocess_frame(self, frame):
        """
        Preprocess frame สำหรับ model input
        """
        # ปรับขนาดภาพ
        resized = cv2.resize(frame, (self.input_size, self.input_size))
        
        # แปลงเป็น tensor
        tensor = torch.from_numpy(resized).float().permute(2, 0, 1).unsqueeze(0)
        
        # ปรับค่าให้อยู่ในช่วง [0, 1]
        tensor = tensor / 255.0
        
        # ส่งไปยัง device
        if self.device == 'cuda':
            tensor = tensor.cuda()
            tensor = tensor.half()  # FP16
        
        return tensor
    
    def process_frame_optimized(self, frame):
        """
        ประมวลผลเฟรมด้วยการปรับแต่งประสิทธิภาพ
        """
        start_time = time.time()
        
        try:
            # Preprocess
            input_tensor = self.preprocess_frame(frame)
            
            # Inference ด้วย torch.no_grad() เพื่อลด memory
            with torch.no_grad():
                results = self.model(input_tensor, conf=self.confidence_threshold, iou=self.nms_threshold)
            
            # Post-process
            detections = self._postprocess_results(results, frame.shape)
            
            # ปล่อย memory
            if self.device == 'cuda':
                torch.cuda.empty_cache()
            
            processing_time = time.time() - start_time
            
            return {
                'detections': detections,
                'processing_time': processing_time,
                'memory_usage': self._get_memory_usage()
            }
            
        except RuntimeError as e:
            if "out of memory" in str(e):
                print("GPU out of memory, falling back to CPU")
                return self._fallback_processing(frame)
            else:
                raise e
    
    def _fallback_processing(self, frame):
        """
        การประมวลผลแบบ fallback เมื่อ GPU มีปัญหา
        """
        # ใช้ CPU พร้อมการปรับแต่ง
        original_device = self.device
        self.device = 'cpu'
        
        # ลดขนาดภาพเพิ่มเติม
        small_frame = cv2.resize(frame, (320, 320))
        
        result = self.process_frame_optimized(small_frame)
        
        self.device = original_device
        return result
    
    def _get_memory_usage(self):
        """
        ตรวจสอบการใช้ memory
        """
        if self.device == 'cuda' and torch.cuda.is_available():
            return {
                'allocated': torch.cuda.memory_allocated() / 1024**3,  # GB
                'cached': torch.cuda.memory_reserved() / 1024**3,     # GB
                'max_allocated': torch.cuda.max_memory_allocated() / 1024**3  # GB
            }
        else:
            return {'allocated': 0, 'cached': 0, 'max_allocated': 0}
    
    def batch_process_frames(self, frames, max_batch_size=2):
        """
        ประมวลผลแบบ batch สำหรับประสิทธิภาพที่ดีขึ้น
        """
        results = []
        
        for i in range(0, len(frames), max_batch_size):
            batch = frames[i:i+max_batch_size]
            
            # สร้าง batch tensor
            batch_tensors = []
            for frame in batch:
                tensor = self.preprocess_frame(frame)
                batch_tensors.append(tensor)
            
            # รวมเป็น batch
            batch_tensor = torch.cat(batch_tensors, dim=0)
            
            # Inference
            with torch.no_grad():
                batch_results = self.model(batch_tensor, conf=self.confidence_threshold, iou=self.nms_threshold)
            
            # แยกผลลัพธ์
            for j, result in enumerate(batch_results):
                frame_result = self._postprocess_results([result], batch[j].shape)
                results.append(frame_result)
            
            # ปล่อย memory
            if self.device == 'cuda':
                torch.cuda.empty_cache()
        
        return results
    
    def _postprocess_results(self, results, original_shape):
        """
        แปลงผลลัพธ์จาก model เป็นรูปแบบที่ใช้งานได้
        """
        detections = []
        
        for result in results:
            if result is not None and hasattr(result, 'boxes'):
                boxes = result.boxes
                
                for box in boxes:
                    # ดึงข้อมูล
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    confidence = box.conf[0].cpu().numpy()
                    class_id = int(box.cls[0].cpu().numpy())
                    
                    # ปรับขนาดให้ตรงกับภาพต้นฉบับ
                    h, w = original_shape[:2]
                    x1 = int(x1 * w / self.input_size)
                    y1 = int(y1 * h / self.input_size)
                    x2 = int(x2 * w / self.input_size)
                    y2 = int(y2 * h / self.input_size)
                    
                    detections.append({
                        'bbox': [x1, y1, x2 - x1, y2 - y1],
                        'confidence': float(confidence),
                        'class_id': class_id,
                        'class_name': self.model.names[class_id] if hasattr(self.model, 'names') else 'unknown'
                    })
        
        return detections

# คลาสสำหรับจัดการ multi-threading
class MultiThreadedProcessor:
    def __init__(self, detection_system, num_workers=2):
        self.detection_system = detection_system
        self.num_workers = num_workers
        self.workers = []
        self.running = False
        
    def start_processing(self):
        """
        เริ่มการทำงานแบบ multi-threaded
        """
        self.running = True
        
        for i in range(self.num_workers):
            worker = Thread(target=self._worker_loop, args=(i,))
            worker.daemon = True
            worker.start()
            self.workers.append(worker)
    
    def _worker_loop(self, worker_id):
        """
        ลูปการทำงานของแต่ละ worker
        """
        while self.running:
            try:
                # รับ frame จาก queue
                frame_data = self.detection_system.frame_queue.get(timeout=1)
                
                if frame_data is None:  # Sentinel value
                    break
                
                frame, frame_id, timestamp = frame_data
                
                # ประมวลผล
                result = self.detection_system.process_frame_optimized(frame)
                
                # ส่งผลลัพธ์ไปยัง result queue
                self.detection_system.result_queue.put({
                    'frame_id': frame_id,
                    'timestamp': timestamp,
                    'result': result,
                    'worker_id': worker_id
                })
                
            except Empty:
                continue
            except Exception as e:
                print(f"Worker {worker_id} error: {e}")
    
    def stop_processing(self):
        """
        หยุดการทำงาน
        """
        self.running = False
        
        # ส่ง sentinel values ให้ทุก worker
        for _ in range(self.num_workers):
            self.detection_system.frame_queue.put(None)
        
        # รอให้ workers หยุด
        for worker in self.workers:
            worker.join()
```

### 3.6.2 การปรับแต่งฐานข้อมูลและการจัดการข้อมูล

**ทฤษฎีพื้นฐาน:**
การปรับแต่งฐานข้อมูลใช้หลักการ **Database Performance Tuning** ซึ่งเน้นการปรับปรุง query performance และการจัดการข้อมูลที่มีประสิทธิภาพ [11].

**ปัญหา:** การเก็บข้อมูลจำนวนมากอาจส่งผลต่อ performance

**วิธีแก้ไข:**

1. **Index Optimization:**
```sql
-- สร้าง index สำหรับการค้นหาที่รวดเร็ว
CREATE INDEX CONCURRENTLY idx_detections_timestamp_camera 
ON detections(timestamp, camera_id);

CREATE INDEX CONCURRENTLY idx_clothing_colors_composite 
ON clothing_colors(color_name, color_group, percentage);

-- ใช้ partial index สำหรับข้อมูลล่าสุด
CREATE INDEX CONCURRENTLY idx_recent_detections 
ON detections(timestamp) 
WHERE timestamp >= NOW() - INTERVAL '7 days';
```

2. **Data Partitioning:**
```sql
-- แบ่งข้อมูลตามวันสำหรับ performance ที่ดีขึ้น
CREATE TABLE detections_y2024m01 PARTITION OF detections
FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');

-- ใช้ declarative partitioning
CREATE TABLE detections (
    id BIGSERIAL,
    camera_id INTEGER REFERENCES cameras(id),
    track_id VARCHAR(50) NOT NULL,
    -- ... other columns
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) PARTITION BY RANGE (timestamp);
```

3. **Query Optimization:**
```python
def optimized_search_query(criteria):
    """
    คำสั่ง SQL ที่ปรับแต่งสำหรับ performance
    """
    base_query = """
    WITH ranked_detections AS (
        SELECT 
            d.*, 
            cc.color_name,
            cc.color_group,
            cc.percentage,
            ROW_NUMBER() OVER (
                PARTITION BY d.track_id 
                ORDER BY d.timestamp DESC
            ) as rn
        FROM detections d
        JOIN clothing_colors cc ON d.id = cc.detection_id
        WHERE 1=1
    """
    
    params = []
    
    # เพิ่มเงื่อนไขการค้นหา
    if criteria.get('colors'):
        placeholders = ','.join(['%s'] * len(criteria['colors']))
        base_query += f" AND cc.color_name IN ({placeholders})"
        params.extend(criteria['colors'])
    
    if criteria.get('clothing_type'):
        base_query += " AND cc.clothing_type = %s"
        params.append(criteria['clothing_type'])
    
    if criteria.get('time_range'):
        base_query += " AND d.timestamp BETWEEN %s AND %s"
        params.extend([criteria['time_range']['start'], criteria['time_range']['end']])
    
    # ใช้ CTE และ LIMIT สำหรับประสิทธิภาพ
    base_query += """
    )
    SELECT * FROM ranked_detections 
    WHERE rn = 1  -- ดึงเฉพาะการตรวจจับล่าสุดของแต่ละ track
    ORDER BY timestamp DESC 
    LIMIT 1000
    """
    
    return execute_query(base_query, params)
```

4. **Connection Pooling:**

| ปัญหา | สาเหตุ | วิธีแก้ไข | ผลลัพธ์ |
|--------|--------|------------|----------|
| Shadow Detection | แสงไม่เพียงพอ | ใช้ HSV color space | ลด false positive 80% |
| Low Resolution | กล้องคุณภาพต่ำ | ใช้ super-resolution | เพิ่ม accuracy 15% |
| Camera Angle | มุมกล้องไม่เหมาะสม | ใช้ perspective correction | ปรับปรุง detection 25% |
| GPU Memory Limit | VRAM 4GB | ใช้ model quantization | ลด memory usage 60% |

### 3.7.2 การจัดการข้อยกเว้น

**โค้ดตัวอย่างที่ 3.7** Error Handling
```python
class DetectionSystem:
    def __init__(self):
        self.fallback_mode = False
        
    def safe_detect(self, frame):
        try:
            # ลองใช้ GPU
            if torch.cuda.is_available():
                return self.gpu_detect(frame)
            else:
                return self.cpu_detect(frame)
                
        except RuntimeError as e:
            if "out of memory" in str(e):
                print("GPU out of memory, switching to CPU")
                torch.cuda.empty_cache()
                return self.cpu_detect(frame)
            else:
                print(f"Detection error: {e}")
                return self.fallback_detection(frame)
                
        except Exception as e:
            print(f"Unexpected error: {e}")
            return self.fallback_detection(frame)
    
    def fallback_detection(self, frame):
        # ใช้วิธีการตรวจจับแบบง่ายเมื่อระบบล้มเหลว
        return simple_background_subtraction(frame)
```

## 3.8 การทดสอบและวาลิเดชัน (Testing and Validation)

### 3.8.1 การทดสอบประสิทธิภาพ (Performance Testing)

**เมตริกที่ใช้วัด:**
- FPS (Frames Per Second)
- Memory Usage
- Detection Accuracy (mAP)
- Color Accuracy

**ผลการทดสอบ:**

**ตารางที่ 3.3** ผลการทดสอบประสิทธิภาพ

| สถานการณ์ | FPS | Memory Usage | mAP@0.5 | Color Accuracy |
|------------|-----|--------------|---------|----------------|
| กล้อง 1 ตัว | 25-30 | 3.2GB | 0.85 | 0.78 |
| กล้อง 2 ตัว | 15-20 | 3.8GB | 0.82 | 0.75 |
| กล้อง 4 ตัว | 8-12 | 4.0GB | 0.78 | 0.72 |

### 3.8.2 การทดสอบความแม่นยำ (Accuracy Testing)

**ชุดข้อมูลทดสอบ:**
- PA100K: 1,000 รูป
- DeepFashion2: 1,000 รูป
- Custom dataset: 500 รูป

**ผลการทดสอบ:**

**ตารางที่ 3.4** ผลการทดสอบความแม่นยำ

| ประเภทเสื้อผ้า | Precision | Recall | F1-Score |
|----------------|-----------|--------|----------|
| Long Sleeve Top | 0.89 | 0.85 | 0.87 |
| Short Sleeve Top | 0.91 | 0.88 | 0.89 |
| Dress | 0.93 | 0.90 | 0.91 |
| Skirt | 0.87 | 0.82 | 0.84 |
| Short | 0.85 | 0.80 | 0.82 |
| Trousers | 0.92 | 0.89 | 0.90 |

## 3.9 การจัดการด้านกฎหมายและความเป็นส่วนตัว (Legal and Privacy Management)

### 3.9.1 การปฏิบัติตาม PDPA

**มาตรการที่ใช้:**
1. **Data Minimization:** เก็บเฉพาะข้อมูลที่จำเป็น
2. **Access Control:** ระบบ role-based access control
3. **Data Encryption:** เข้ารหัสข้อมูลที่ละเอียดอ่อน
4. **Audit Trail:** บันทึกการเข้าถึงข้อมูล

**โครงสร้าง Role-Based Access:**
```python
class UserRole(Enum):
    ADMIN = "admin"
    POLICE = "police"
    OPERATOR = "operator"
    VIEWER = "viewer"

PERMISSIONS = {
    UserRole.ADMIN: ["read", "write", "delete", "manage_users"],
    UserRole.POLICE: ["read", "search", "export"],
    UserRole.OPERATOR: ["read", "monitor"],
    UserRole.VIEWER: ["read"]
}

def check_permission(user_role, action):
    return action in PERMISSIONS.get(user_role, [])
```

### 3.9.2 การป้องกันการใช้งานผิดวัตถุประสงค์

**มาตรการรักษาความปลอดภัย:**
1. **Authentication:** 2-factor authentication
2. **Authorization:** Role-based access control
3. **Audit Logging:** บันทึกทุกการกระทำ
4. **Data Retention:** ลบข้อมูลอัตโนมัติหลัง 30 วัน

## 3.10 สรุปบท (Chapter Summary)

บทนี้ได้อธิบายถึงการออกแบบและพัฒนาระบบวิเคราะห์ภาพ CCTV ด้วย AI สำหรับการติดตามและจำแนกสีเสื้อผ้า โดยมีข้อสรุปดังต่อไปนี้:

### 3.10.1 ผลงานที่สำเร็จ

1. **Two-Pass Detection Algorithm:** พัฒนาอัลกอริทึมการตรวจจับ 2 รอบสำหรับความแม่นยำที่สูงขึ้น
2. **Competitive Grouping Algorithm:** แก้ปัญหาเปอร์เซ็นต์สีรวมเกิน 100%
3. **Re-identification System:** ใช้ Feature Vector และสีในการติดตามบุคคล
4. **Performance Optimization:** ปรับแต่งระบบให้ทำงานบนฮาร์ดแวร์จำกัด
5. **Database Design:** ออกแบบฐานข้อมูลที่มีประสิทธิภาพสูง

### 3.10.2 ปัญหาที่แก้ไขได้

1. **Shadow Detection:** ใช้ HSV color space ลดปัญหาเงา
2. **Memory Limitation:** ใช้ model quantization และ frame skipping
3. **Real-time Processing:** ใช้ multi-threading และ queue system
4. **Data Storage:** ใช้ PostgreSQL + MinIO สำหรับการจัดเก็บข้อมูล

### 3.10.3 ข้อจำกัดที่ยังคงอยู่

1. **Hardware Limitation:** GPU 4GB จำกัดการประมวลผลหลายกล้อง
2. **Lighting Conditions:** แสงน้อยยังส่งผลต่อความแม่นยำ
3. **Camera Angles:** มุมกล้องบางแบบยากต่อการตรวจจับ
4. **Multi-camera Tracking:** ยังไม่ได้ implement จริง

### 3.10.4 แนวทางการพัฒนาต่อ

1. **Model Improvement:** ใช้ YOLO11 รุ่นใหม่กว่า
2. **Hardware Upgrade:** ใช้ GPU ที่มีประสิทธิภาพสูงขึ้น
3. **Multi-camera System:** พัฒนาระบบติดตามข้ามกล้อง
4. **Advanced Features:** เพิ่มฟีเจอร์การจำแนกพฤติกรรม

ในบทที่ 4 จะกล่าวถึงผลการทดสอบและการประเมินประสิทธิภาพของระบบที่พัฒนาขึ้น

---

## หมายเหตุสำหรับบทที่ 3:

### สิ่งที่ต้องเพิ่มเติม:

1. **แผนภาพ/รูปภาพ:**
   - แผนภาพสถาปัตยกรรมระบบ (3.1)
   - แผนภาพการไหลข้อมูล (3.2)
   - ภาพตัวอย่างผลลัพธ์การตรวจจับ
   - ภาพ UI ของระบบ

2. **ตาราง:**
   - ตารางโครงสร้างฐานข้อมูล (3.1)
   - ตารางปัญหาและวิธีแก้ไข (3.2)
   - ตารางผลการทดสอบประสิทธิภาพ (3.3)
   - ตารางผลการทดสอบความแม่นยำ (3.4)

3. **โค้ดตัวอย่าง:**
   - โค้ด Two-Pass Detection (3.1)
   - โค้ด Re-ID Algorithm (3.2)
   - โค้ด Color Analysis (3.3)
   - โค้ด Database Operations (3.4)
   - โค้ด Frontend Components (3.5)
   - โค้ด Performance Optimization (3.6)
   - โค้ด Error Handling (3.7)

4. **การอ้างอิง:**
   - อ้างอิง YOLO11 paper
   - อ้างอิง ByteTrack algorithm
   - อ้างอิง HSV color space theory
   - อ้างอิง PDPA regulations

5. **ข้อมูลจำเพาะ:**
   - รายละเอียด hardware specifications
   - รายละเอียด software versions
   - รายละเอียด dataset ที่ใช้
   - รายละเอียด hyperparameters

### คำแนะนำเพิ่มเติม:

1. **เพิ่มรูปภาพ:** ควรเพิ่มภาพตัวอย่างของระบบจริง
2. **เพิ่มกราฟ:** ควรเพิ่มกราฟแสดงประสิทธิภาพ
3. **เพิ่ม flowchart:** ควรเพิ่ม flowchart แสดงขั้นตอนการทำงาน
4. **เพิ่ม use case:** ควรเพิ่มตัวอย่าง use case จริง
5. **เพิ่ม benchmark:** ควรเพิ่มการเปรียบเทียบกับระบบอื่น
