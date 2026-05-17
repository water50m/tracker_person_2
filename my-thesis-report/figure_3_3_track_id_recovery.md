# ภาพที่ 3.3 Flow การกู้คืน track_id (Track ID Recovery Flow)

```mermaid
graph TB
    subgraph Detection["Detection Frame"]
        NewDetection[Detection ใหม่<br/>person_crop + byte_id]
    end

    subgraph HybridTracker["HybridTracker"]
        CheckID[ตรวจสอบ byte_id<br/>ใน id_mapping]
        HasMapping{byte_id<br/>มีอยู่?}
        ReturnExisting[คืน our_id ที่มีอยู่<br/>is_new=False<br/>is_recovered=False]
        
        ExtractFeatures[สกัด Features<br/>- Embedding 768-dim<br/>- Color groups<br/>- Clothes list]
        MatchLost[ค้นหาใน lost_tracks<br/>เปรียบเทียบ similarity]
        CalculateSimilarity[คำนวณ Similarity<br/>- Embedding: 50%<br/>- Color: 30%<br/>- Clothes: 20%]
        CheckThreshold{Similarity<br/>>= 0.7?}
        
        RecoverTrack[กู้คืน Track<br/>- จับคู่ byte_id → our_id<br/>- ลบจาก lost_tracks<br/>is_new=False<br/>is_recovered=True]
        
        CreateNew[สร้าง Track ใหม่<br/>- จับคู่ byte_id → our_id<br/>- our_id = next_our_id++<br/>is_new=True<br/>is_recovered=False]
    end

    subgraph LostTracks["Lost Tracks Management"]
        LostTracksDict[lost_tracks dict<br/>{our_id: TrackFeatures}]
        TrackHistory[track_history dict<br/>{our_id: metadata}]
        UpdateLost[อัปเดต lost_tracks<br/>เมื่อ track หายไป]
        StoreFeatures[เก็บ Features<br/>เมื่อ track ใหม่]
    end

    NewDetection --> CheckID
    CheckID --> HasMapping
    HasMapping -->|ใช่| ReturnExisting
    HasMapping -->|ไม่| ExtractFeatures
    
    ExtractFeatures --> MatchLost
    MatchLost --> CalculateSimilarity
    CalculateSimilarity --> CheckThreshold
    
    CheckThreshold -->|ใช่| RecoverTrack
    CheckThreshold -->|ไม่| CreateNew
    
    RecoverTrack --> LostTracksDict
    CreateNew --> StoreFeatures
    StoreFeatures --> TrackHistory
    
    TrackHistory --> UpdateLost
    UpdateLost --> LostTracksDict

    style Detection fill:#e1f5ff
    style HybridTracker fill:#fff4e1
    style LostTracks fill:#ffe1f5

    classDef decision fill:#FFB6C1,stroke:#333,stroke-width:2px
    classDef action fill:#90EE90,stroke:#333,stroke-width:2px
    classDef storage fill:#87CEEB,stroke:#333,stroke-width:2px

    class HasMapping,CheckThreshold decision
    class ReturnExisting,RecoverTrack,CreateNew action
    class LostTracksDict,TrackHistory,UpdateLost,StoreFeatures storage
```

## คำอธิบาย Flow:

### 1. การตรวจสอบ Track ID ที่มีอยู่
- เมื่อมี detection ใหม่พร้อม byte_id จาก ByteTrack
- HybridTracker ตรวจสอบว่า byte_id นี้มีอยู่ใน id_mapping หรือไม่
- ถ้ามี → คืน our_id ที่มีอยู่ (ไม่ต้องสร้างใหม่)

### 2. การสกัด Features
- ถ้า byte_id ใหม่ → สกัด features จาก person_crop:
  - **Embedding**: 768-dim vector จาก ClothingEmbedder
  - **Color groups**: 22 กลุ่มสีจาก 63 สี
  - **Clothes list**: รายการประเภทเสื้อผ้า

### 3. การค้นหา Lost Tracks
- เปรียบเทียบ features ใหม่กับทุก track ใน lost_tracks
- คำนวณ similarity score แบบ weighted:
  - **Embedding similarity (50%)**: Cosine similarity ของ 768-dim vectors
  - **Color similarity (30%)**: IoU ของ color groups
  - **Clothes similarity (20%)**: Jaccard similarity ของ clothing lists

### 4. การตัดสินใจกู้คืน
- ถ้า similarity >= threshold (0.7) → กู้คืน track
  - จับคู่ byte_id → our_id เดิม
  - ลบออกจาก lost_tracks
  - คืน is_recovered=True
- ถ้า similarity < threshold → สร้าง track ใหม่
  - สร้าง our_id ใหม่ (next_our_id++)
  - จับคู่ byte_id → our_id ใหม่
  - คืน is_new=True

### 5. การจัดการ Lost Tracks
- เมื่อ track หายไป (ไม่ปรากฏใน frame ปัจจุบัน)
  - ย้ายจาก id_mapping → lost_tracks
  - เก็บ features ไว้สำหรับการกู้คืน
- เมื่อ track กลับมาปรากฏ
  - ลบออกจาก lost_tracks
  - คืนกลับไป id_mapping
