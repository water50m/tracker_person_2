"use client";

import { Camera, Edit, Trash2, Save, X, Video } from "lucide-react"; // 1. เพิ่ม icon Video
import { useRouter } from "next/navigation"; // 2. Import useRouter
import { Camera as CameraType } from "./types";

interface CameraListProps {
  cameras: CameraType[];
  editingCamera: CameraType | null;
  onEditCamera: (camera: CameraType) => void;
  onUpdateCamera: (camera: CameraType) => void;
  onDeleteCamera: (id: number) => void;
  onCancelEdit: () => void;
  onSetEditingCamera: (camera: CameraType | null) => void;
}

export default function CameraList({
  cameras,
  editingCamera,
  onEditCamera,
  onUpdateCamera,
  onDeleteCamera,
  onCancelEdit,
  onSetEditingCamera
}: CameraListProps) {
  const router = useRouter(); // 3. เรียกใช้งาน router

  // ฟังก์ชันสำหรับกดปุ่ม Video
  const handleShowVideoCamera = (camera: CameraType) => {
    // ส่ง camera_id และบอกให้ไปที่ video tab
    router.push(`/search?camera_id=${encodeURIComponent(camera.name)}&tab=videos`);
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
      {cameras.map((camera) => (
        <div key={camera.id} className="bg-slate-800/50 border border-slate-700 rounded p-3">
          {editingCamera?.id === camera.id ? (
            <div className="space-y-2">
              {/* ... (ส่วน Edit เหมือนเดิม) ... */}
              <input
                type="text"
                value={editingCamera.name}
                onChange={(e) => onSetEditingCamera({...editingCamera, name: e.target.value})}
                className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1 text-sm text-slate-300"
              />
              <input
                type="text"
                value={editingCamera.source_url}
                onChange={(e) => onSetEditingCamera({...editingCamera, source_url: e.target.value})}
                className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1 text-sm text-slate-300"
              />
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={editingCamera.is_active}
                  onChange={(e) => onSetEditingCamera({...editingCamera, is_active: e.target.checked})}
                  className="rounded"
                />
                <label className="text-xs text-slate-400">Active</label>
              </div>
              <div className="flex gap-1">
                <button
                  onClick={() => onUpdateCamera(editingCamera)}
                  className="flex items-center gap-1 px-2 py-1 bg-green-600 text-white text-xs rounded hover:bg-green-700 cursor-pointer"
                >
                  <Save className="w-3 h-3" />
                  Save
                </button>
                <button
                  onClick={onCancelEdit}
                  className="flex items-center gap-1 px-2 py-1 bg-slate-600 text-white text-xs rounded hover:bg-slate-700 cursor-pointer"
                >
                  <X className="w-3 h-3" />
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div>
              <div className="flex items-center justify-between mb-2">
                <h3 className="font-mono text-sm text-cyan-400">{camera.name}</h3>
                <div className="flex gap-1">
                  
                  {/* 4. เพิ่มปุ่ม Video ตรงนี้ */}
                  <button
                    onClick={() => handleShowVideoCamera(camera)}
                    className="p-1 text-blue-400 hover:text-blue-300 cursor-pointer"
                    title="Search videos from this camera"
                  >
                    <Video className="w-3 h-3" />
                  </button>
                  {/* ------------------------- */}

                  <button
                    onClick={() => onEditCamera(camera)}
                    className="p-1 text-slate-400 hover:text-slate-300"
                  >
                    <Edit className="w-3 h-3" />
                  </button>
                  <button
                    onClick={() => onDeleteCamera(camera.id)}
                    className="p-1 text-red-400 hover:text-red-300"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              </div>
              <div className="text-xs text-slate-400 space-y-1">
                <p className="truncate">{camera.source_url}</p>
                <p>Status: {camera.is_active ? '✅ Active' : '❌ Inactive'}</p>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}