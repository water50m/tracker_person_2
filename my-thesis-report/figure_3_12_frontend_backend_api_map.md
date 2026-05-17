# ภาพที่ 3.12 แผนภาพการเชื่อมต่อหน้าจอ Frontend กับ Backend API

```mermaid
flowchart LR
    subgraph Frontend["Next.js Frontend"]
        Dashboard["Dashboard<br/>LiveVideoCanvas, EventFeed, StatsWidget"]
        InputManager["Input Manager<br/>Upload, RTSP, YouTube"]
        Realtime["Realtime Page"]
        Investigation["Investigation / Search<br/>SearchFilterBar, ResultsGrid"]
        CameraMgmt["Camera Management"]
        SystemPage["System Settings"]
    end

    subgraph NextRoutes["Next.js API Routes / Proxy"]
        NextDashboard["/api/dashboard/*"]
        NextInput["/api/input/*"]
        NextSearch["/api/search/*"]
        NextVideo["/api/video/*"]
        NextSettings["/api/settings/*"]
    end

    subgraph FastAPI["FastAPI Backend"]
        DashboardAPI["/api/dashboard<br/>cameras, mjpeg, latest-detections"]
        VideoAPI["/api/video<br/>upload, stream-analyze, background"]
        QueueAPI["/api/video-queue<br/>add, pause, resume, status"]
        SearchAPI["/api/search/persons<br/>/api/search/advanced<br/>/api/search/detect-attributes"]
        CameraAPI["/api/cameras<br/>/api/camera-relationships"]
        SettingsAPI["/api/settings<br/>/api/logs"]
    end

    subgraph Services["Backend Services"]
        VP["VideoProcessor / StreamProcessor"]
        FP["FrameProcessor"]
        DB["DatabaseService"]
        Storage["StorageService / MinIO"]
        StreamManager["StreamManager"]
    end

    Dashboard --> NextDashboard --> DashboardAPI
    InputManager --> NextInput --> VideoAPI
    InputManager --> QueueAPI
    Realtime --> VideoAPI
    Investigation --> NextSearch --> SearchAPI
    Investigation --> SearchAPI
    CameraMgmt --> CameraAPI
    SystemPage --> NextSettings --> SettingsAPI

    DashboardAPI --> StreamManager
    VideoAPI --> VP
    QueueAPI --> VP
    SearchAPI --> DB
    SearchAPI --> FP
    CameraAPI --> DB
    SettingsAPI --> DB
    VP --> FP
    VP --> Storage
    VP --> DB
```

## คำอธิบายสำหรับใส่ในรายงาน

แผนภาพนี้ช่วยให้เห็นว่าแต่ละหน้าจอของ frontend เชื่อมต่อกับ API ใดบ้าง โดยบางส่วนเรียกผ่าน Next.js API route เพื่อทำหน้าที่ proxy ส่วนบางส่วนเรียก FastAPI โดยตรงผ่านค่า `NEXT_PUBLIC_API_URL` โครงสร้างนี้ทำให้ frontend แยกหน้าที่ชัดเจน เช่น Dashboard ใช้ API สำหรับข้อมูล realtime, Input Manager ใช้ API สำหรับเพิ่มงานวิดีโอหรือสตรีม, Investigation ใช้ Search API และ Camera Management ใช้ API สำหรับจัดการกล้อง
