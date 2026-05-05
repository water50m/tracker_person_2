"use client";

import { useState } from "react";
import { Camera as CameraIcon, Link2, Plus, Network } from "lucide-react";
import { Camera, CameraRelationship, ViewMode } from "./types";
import CameraDiagram from "./CameraDiagram";
import CameraList from "./CameraList";
import RelationshipList from "./RelationshipList";
import { 
  useCameraData, 
  useCameraOperations, 
  useRelationshipOperations, 
  useCameraUtils 
} from "./hooks";

export default function CameraManagementPage() {
  const { cameras, relationships, loading, fetchData } = useCameraData();
  const { handleAddCamera, handleUpdateCamera, handleDeleteCamera } = useCameraOperations(fetchData);
  const { handleAddRelationship, handleDeleteRelationship } = useRelationshipOperations(fetchData);
  const { getCameraName } = useCameraUtils(cameras);

  // UI States
  const [editingCamera, setEditingCamera] = useState<Camera | null>(null);
  const [showAddCamera, setShowAddCamera] = useState(false);
  const [showAddRelationship, setShowAddRelationship] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>('list');
  const [activeTab, setActiveTab] = useState<'cameras' | 'relationships'>('cameras');

  // Form states
  const [newCamera, setNewCamera] = useState({
    name: "",
    source_url: "",
    is_active: true
  });

  const [newRelationship, setNewRelationship] = useState({
    from_camera_id: 0,
    to_camera_id: 0,
    avg_transition_time: 0
  });

  // Event handlers
  const handleAddCameraClick = async () => {
    const result = await handleAddCamera(newCamera);
    if (result.success) {
      setNewCamera({ name: "", source_url: "", is_active: true });
      setShowAddCamera(false);
    } else if (!result.cancelled) {
      alert(`Error adding camera: ${result.error}`);
    }
  };

  const handleUpdateCameraClick = async (camera: Camera) => {
    const result = await handleUpdateCamera(camera);
    if (result.success) {
      setEditingCamera(null);
    } else if (!result.cancelled) {
      alert(`Error updating camera: ${result.error}`);
    }
  };

  const handleDeleteCameraClick = async (id: number) => {
    const result = await handleDeleteCamera(id);
    if (!result.success && !result.cancelled) {
      alert(`Error deleting camera: ${result.error}`);
    }
  };

  const handleAddRelationshipClick = async () => {
    const result = await handleAddRelationship(newRelationship);
    if (result.success) {
      setNewRelationship({ from_camera_id: 0, to_camera_id: 0, avg_transition_time: 0 });
      setShowAddRelationship(false);
    } else if (!result.cancelled) {
      alert(`Error adding relationship: ${result.error}`);
    }
  };

  const handleDeleteRelationshipClick = async (fromId: number, toId: number) => {
    const result = await handleDeleteRelationship(fromId, toId);
    if (!result.success && !result.cancelled) {
      alert(`Error deleting relationship: ${result.error}`);
    }
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-slate-400">Loading...</div>
      </div>
    );
  }

  return (
    <div className="h-full p-4 flex flex-col gap-4">
      {/* Header */}
      <div className="bg-slate-900/50 border border-slate-800 rounded-lg p-4">
        <h1 className="text-2xl font-mono text-cyan-400 uppercase tracking-wider">Camera Management</h1>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-auto min-h-[calc(100vh-180px)]">
        {/* Tab Navigation */}
        <div className="bg-slate-900/50 border border-slate-800 rounded-lg p-2 mb-4">
          <div className="flex gap-2">
            <button
              onClick={() => setActiveTab('cameras')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${
                activeTab === 'cameras' 
                  ? 'bg-cyan-600 text-white' 
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
            >
              <CameraIcon className="w-4 h-4" />
              <span className="font-mono uppercase tracking-wider">Cameras</span>
            </button>
            <button
              onClick={() => setActiveTab('relationships')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${
                activeTab === 'relationships' 
                  ? 'bg-purple-600 text-white' 
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
            >
              <Link2 className="w-4 h-4" />
              <span className="font-mono uppercase tracking-wider">Relationships</span>
            </button>
          </div>
        </div>

        {/* Tab Content */}
        {activeTab === 'cameras' ? (
          <div className="bg-slate-900/50 border border-slate-800 rounded-lg p-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-mono text-cyan-400 uppercase tracking-wider">Camera Management</h2>
              <button
                onClick={() => setShowAddCamera(true)}
                className="flex items-center gap-1 px-3 py-1 bg-cyan-600 text-white text-xs rounded hover:bg-cyan-700 transition-colors"
              >
                <Plus className="w-3 h-3" />
                Add Camera
              </button>
            </div>

            <CameraList
              cameras={cameras}
              editingCamera={editingCamera}
              onEditCamera={setEditingCamera}
              onUpdateCamera={handleUpdateCameraClick}
              onDeleteCamera={handleDeleteCameraClick}
              onCancelEdit={() => setEditingCamera(null)}
              onSetEditingCamera={setEditingCamera}
            />
          </div>
        ) : (
          <div className="bg-slate-900/50 border border-slate-800 rounded-lg p-4 min-h-[calc(100vh-180px)]">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-mono text-purple-400 uppercase tracking-wider">Relationship Management</h2>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setViewMode(viewMode === 'list' ? 'diagram' : 'list')}
                  className="flex items-center gap-1 px-3 py-1 bg-slate-600 text-white text-xs rounded hover:bg-slate-700 transition-colors"
                  title={`Switch to ${viewMode === 'list' ? 'diagram' : 'list'} view`}
                >
                  <Network className="w-3 h-3" />
                  {viewMode === 'list' ? 'Diagram' : 'List'}
                </button>
                <button
                  onClick={() => setShowAddRelationship(true)}
                  className="flex items-center gap-1 px-3 py-1 bg-purple-600 text-white text-xs rounded hover:bg-purple-700 transition-colors"
                >
                  <Plus className="w-3 h-3" />
                  Add Relationship
                </button>
              </div>
            </div>

            {viewMode === 'list' ? (
              <RelationshipList
                relationships={relationships}
                getCameraName={getCameraName}
                onDeleteRelationship={handleDeleteRelationshipClick}
              />
            ) : (
              <CameraDiagram
                cameras={cameras}
                relationships={relationships}
              />
            )}
          </div>
        )}
      </div>

      {/* Add Camera Modal */}
      {showAddCamera && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-900 border border-slate-700 rounded-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-mono text-cyan-400 mb-4">Add New Camera</h3>
            <div className="space-y-3">
              <input
                type="text"
                placeholder="Camera Name"
                value={newCamera.name}
                onChange={(e) => setNewCamera({...newCamera, name: e.target.value})}
                className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-300"
              />
              <input
                type="text"
                placeholder="Source URL"
                value={newCamera.source_url}
                onChange={(e) => setNewCamera({...newCamera, source_url: e.target.value})}
                className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-300"
              />
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={newCamera.is_active}
                  onChange={(e) => setNewCamera({...newCamera, is_active: e.target.checked})}
                  className="rounded"
                />
                <label className="text-sm text-slate-400">Active</label>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={handleAddCameraClick}
                  className="flex-1 py-2 bg-cyan-600 text-white rounded hover:bg-cyan-700"
                >
                  Add Camera
                </button>
                <button
                  onClick={() => {
                    setShowAddCamera(false);
                    setNewCamera({ name: "", source_url: "", is_active: true });
                  }}
                  className="flex-1 py-2 bg-slate-600 text-white rounded hover:bg-slate-700"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Add Relationship Modal */}
      {showAddRelationship && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-900 border border-slate-700 rounded-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-mono text-purple-400 mb-4">Add Relationship</h3>
            <div className="space-y-3">
              <select
                value={newRelationship.from_camera_id}
                onChange={(e) => setNewRelationship({...newRelationship, from_camera_id: parseInt(e.target.value)})}
                className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-300"
              >
                <option value={0}>Select From Camera</option>
                {cameras.map(camera => (
                  <option key={camera.id} value={camera.id}>{camera.name}</option>
                ))}
              </select>
              <select
                value={newRelationship.to_camera_id}
                onChange={(e) => setNewRelationship({...newRelationship, to_camera_id: parseInt(e.target.value)})}
                className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-300"
              >
                <option value={0}>Select To Camera</option>
                {cameras.map(camera => (
                  <option key={camera.id} value={camera.id}>{camera.name}</option>
                ))}
              </select>
              <input
                type="number"
                placeholder="Average Transition Time (seconds)"
                value={newRelationship.avg_transition_time}
                onChange={(e) => setNewRelationship({...newRelationship, avg_transition_time: parseFloat(e.target.value)})}
                className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-300"
              />
              <div className="flex gap-2">
                <button
                  onClick={handleAddRelationshipClick}
                  className="flex-1 py-2 bg-purple-600 text-white rounded hover:bg-purple-700"
                >
                  Add Relationship
                </button>
                <button
                  onClick={() => {
                    setShowAddRelationship(false);
                    setNewRelationship({ from_camera_id: 0, to_camera_id: 0, avg_transition_time: 0 });
                  }}
                  className="flex-1 py-2 bg-slate-600 text-white rounded hover:bg-slate-700"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
