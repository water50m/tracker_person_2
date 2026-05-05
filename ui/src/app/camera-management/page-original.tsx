"use client";

import { useState, useEffect } from "react";
import { Camera, Link2, Plus, Trash2, Edit, Save, X, Network } from "lucide-react";
import { 
  ReactFlow, 
  Node, 
  Edge, 
  Background, 
  Controls, 
  MiniMap,
  useNodesState,
  useEdgesState,
  ConnectionMode
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

interface Camera {
  id: number;
  name: string;
  source_url: string;
  is_active: boolean;
}

interface CameraRelationship {
  from_camera_id: number;
  to_camera_id: number;
  avg_transition_time: number;
}

export default function CameraManagementPage() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [relationships, setRelationships] = useState<CameraRelationship[]>([]);
  const [loading, setLoading] = useState(false);
  const [editingCamera, setEditingCamera] = useState<Camera | null>(null);
  const [editingRelationship, setEditingRelationship] = useState<CameraRelationship | null>(null);
  const [showAddCamera, setShowAddCamera] = useState(false);
  const [showAddRelationship, setShowAddRelationship] = useState(false);
  const [viewMode, setViewMode] = useState<'list' | 'diagram'>('list');
  
  // Diagram states
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

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

  // Fetch data
  const fetchData = async () => {
    setLoading(true);
    try {
      // Fetch cameras
      const camerasResponse = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/cameras`);
      const camerasData = await camerasResponse.json();
      setCameras(camerasData.cameras || []);

      // Fetch relationships
      const relationshipsResponse = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/cameras/relationships/all`);
      const relationshipsData = await relationshipsResponse.json();
      setRelationships(relationshipsData.relationships || []);
    } catch (error) {
      console.error("Error fetching data:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  // Update diagram when cameras or relationships change
  useEffect(() => {
    const diagramNodes: Node[] = cameras.map((camera, index) => {
      // Create a more distributed layout for better connections
      const cols = Math.ceil(Math.sqrt(cameras.length));
      const row = Math.floor(index / cols);
      const col = index % cols;
      
      return {
        id: camera.id.toString(),
        type: 'default',
        position: {
          x: col * 250 + 100,
          y: row * 200 + 100
        },
        data: {
          label: (
            <div className="text-center">
              <div className="font-semibold text-slate-800">{camera.name}</div>
              <div className="text-xs text-slate-600">
                {camera.is_active ? 'Active' : 'Inactive'}
              </div>
            </div>
          )
        },
        style: {
          background: camera.is_active ? '#10b981' : '#6b7280',
          color: 'white',
          border: '2px solid #1e293b',
          borderRadius: '8px',
          width: 120,
          height: 60
        }
      };
    });

    const diagramEdges: Edge[] = relationships.map((rel, index) => ({
      id: `edge-${index}`,
      source: rel.from_camera_id.toString(),
      target: rel.to_camera_id.toString(),
      label: `${rel.avg_transition_time}s`,
      labelStyle: { fill: '#8b5cf6', fontWeight: 'bold' },
      style: { stroke: '#8b5cf6', strokeWidth: 2 },
      animated: true,
      type: 'straight', // Use straight lines instead of curved with arrows
      markerEnd: undefined // Remove arrow marker
    }));

    setNodes(diagramNodes);
    setEdges(diagramEdges);
  }, [cameras, relationships, setNodes, setEdges]);

  // Camera operations
  const handleAddCamera = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/cameras`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newCamera)
      });
      
      if (response.ok) {
        setNewCamera({ name: "", source_url: "", is_active: true });
        setShowAddCamera(false);
        fetchData();
      } else {
        const errorData = await response.json();
        alert(`Error adding camera: ${errorData.detail || 'Unknown error'}`);
      }
    } catch (error) {
      console.error("Error adding camera:", error);
      alert(`Error adding camera: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  };

  const handleUpdateCamera = async (camera: Camera) => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/cameras/${camera.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(camera)
      });
      
      if (response.ok) {
        setEditingCamera(null);
        fetchData();
      } else {
        const errorData = await response.json();
        alert(`Error updating camera: ${errorData.detail || 'Unknown error'}`);
      }
    } catch (error) {
      console.error("Error updating camera:", error);
      alert(`Error updating camera: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  };

  const handleDeleteCamera = async (id: number) => {
    if (!confirm("Are you sure you want to delete this camera?")) return;
    
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/cameras/${id}`, {
        method: "DELETE"
      });
      
      if (response.ok) {
        fetchData();
      } else {
        const errorData = await response.json();
        alert(`Error deleting camera: ${errorData.detail || 'Unknown error'}`);
      }
    } catch (error) {
      console.error("Error deleting camera:", error);
      alert(`Error deleting camera: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  };

  // Relationship operations
  const handleAddRelationship = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/camera-relationships`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newRelationship)
      });
      
      if (response.ok) {
        setNewRelationship({ from_camera_id: 0, to_camera_id: 0, avg_transition_time: 0 });
        setShowAddRelationship(false);
        fetchData();
      } else {
        const errorData = await response.json();
        alert(`Error adding relationship: ${errorData.detail || 'Unknown error'}`);
      }
    } catch (error) {
      console.error("Error adding relationship:", error);
      alert(`Error adding relationship: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  };

  const handleDeleteRelationship = async (fromId: number, toId: number) => {
    if (!confirm("Are you sure you want to delete this relationship?")) return;
    
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/camera-relationships/${fromId}/${toId}`, {
        method: "DELETE"
      });
      
      if (response.ok) {
        fetchData();
      } else {
        const errorData = await response.json();
        alert(`Error deleting relationship: ${errorData.detail || 'Unknown error'}`);
      }
    } catch (error) {
      console.error("Error deleting relationship:", error);
      alert(`Error deleting relationship: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  };

  const getCameraName = (id: number) => {
    const camera = cameras.find(c => c.id === id);
    return camera ? camera.name : `Camera ${id}`;
  };

  return (
    <div className="h-full p-4 flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div>
          <h1 className="font-orbitron text-xl font-bold text-cyan-400 tracking-[0.2em] uppercase glitch-text" data-text="CAMERA MANAGEMENT">
            CAMERA MANAGEMENT
          </h1>
          <p className="font-mono text-[10px] text-slate-500 mt-0.5 tracking-widest">
            CAMERAS & RELATIONSHIPS · SYSTEM CONFIGURATION
          </p>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-full">
          <div className="text-slate-400">Loading...</div>
        </div>
      ) : (
        <div className="flex-1 overflow-auto space-y-6">
          {/* Cameras Section */}
          <div className="bg-slate-900/50 border border-slate-800 rounded-lg p-4">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Camera className="w-4 h-4 text-cyan-400" />
                <h2 className="text-lg font-mono text-cyan-400 uppercase tracking-wider">Cameras</h2>
              </div>
              <button
                onClick={() => setShowAddCamera(true)}
                className="flex items-center gap-1 px-3 py-1 bg-cyan-600 text-white text-xs rounded hover:bg-cyan-700 transition-colors"
              >
                <Plus className="w-3 h-3" />
                Add Camera
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {cameras.map((camera) => (
                <div key={camera.id} className="bg-slate-800/50 border border-slate-700 rounded p-3">
                  {editingCamera?.id === camera.id ? (
                    <div className="space-y-2">
                      <input
                        type="text"
                        value={editingCamera.name}
                        onChange={(e) => setEditingCamera({...editingCamera, name: e.target.value})}
                        className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1 text-sm text-slate-300"
                      />
                      <input
                        type="text"
                        value={editingCamera.source_url}
                        onChange={(e) => setEditingCamera({...editingCamera, source_url: e.target.value})}
                        className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1 text-sm text-slate-300"
                      />
                      <div className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={editingCamera.is_active}
                          onChange={(e) => setEditingCamera({...editingCamera, is_active: e.target.checked})}
                          className="rounded"
                        />
                        <label className="text-xs text-slate-400">Active</label>
                      </div>
                      <div className="flex gap-1">
                        <button
                          onClick={() => handleUpdateCamera(editingCamera)}
                          className="flex items-center gap-1 px-2 py-1 bg-green-600 text-white text-xs rounded hover:bg-green-700"
                        >
                          <Save className="w-3 h-3" />
                          Save
                        </button>
                        <button
                          onClick={() => setEditingCamera(null)}
                          className="flex items-center gap-1 px-2 py-1 bg-slate-600 text-white text-xs rounded hover:bg-slate-700"
                        >
                          <X className="w-3 h-3" />
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <h3 className="font-mono text-sm font-bold text-slate-200">{camera.name}</h3>
                        <div className="flex gap-1">
                          <button
                            onClick={() => setEditingCamera(camera)}
                            className="p-1 text-slate-400 hover:text-slate-300"
                          >
                            <Edit className="w-3 h-3" />
                          </button>
                          <button
                            onClick={() => handleDeleteCamera(camera.id)}
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
          </div>

          {/* Relationships Section */}
          <div className="bg-slate-900/50 border border-slate-800 rounded-lg p-4">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Link2 className="w-4 h-4 text-purple-400" />
                <h2 className="text-lg font-mono text-purple-400 uppercase tracking-wider">Camera Relationships</h2>
              </div>
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
              <div className="space-y-2">
                {relationships.map((rel, index) => (
                  <div key={index} className="flex items-center justify-between p-3 bg-slate-800/50 border border-slate-700 rounded">
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-sm text-slate-300">
                        {getCameraName(rel.from_camera_id)}
                      </span>
                      <span className="text-purple-400">→</span>
                      <span className="font-mono text-sm text-slate-300">
                        {getCameraName(rel.to_camera_id)}
                      </span>
                      <span className="text-xs text-slate-500">
                        ({rel.avg_transition_time}s)
                      </span>
                    </div>
                    <button
                      onClick={() => handleDeleteRelationship(rel.from_camera_id, rel.to_camera_id)}
                      className="p-1 text-red-400 hover:text-red-300"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="h-96 border border-slate-700 rounded-lg overflow-hidden">
                <ReactFlow
                  nodes={nodes}
                  edges={edges}
                  onNodesChange={onNodesChange}
                  onEdgesChange={onEdgesChange}
                  connectionMode={ConnectionMode.Loose}
                  fitView
                  style={{ background: '#0f172a' }}
                >
                  <Background color="#1e293b" gap={16} />
                  <Controls 
                    style={{ background: '#1e293b', border: '1px solid #334155' }}
                    showInteractive={false}
                  />
                  <MiniMap 
                    style={{ background: '#1e293b', border: '1px solid #334155' }}
                    nodeColor={(node) => {
                      const camera = cameras.find(c => c.id.toString() === node.id);
                      return camera?.is_active ? '#10b981' : '#6b7280';
                    }}
                  />
                </ReactFlow>
              </div>
            )}
          </div>
        </div>
      )}

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
            </div>
            <div className="flex gap-2 mt-4">
              <button
                onClick={handleAddCamera}
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
      )}

      {/* Add Relationship Modal */}
      {showAddRelationship && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-900 border border-slate-700 rounded-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-mono text-purple-400 mb-4">Add Camera Relationship</h3>
            <div className="space-y-3">
              <select
                value={newRelationship.from_camera_id}
                onChange={(e) => setNewRelationship({...newRelationship, from_camera_id: parseInt(e.target.value)})}
                className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-300"
              >
                <option value={0}>Select From Camera</option>
                {cameras.map((camera) => (
                  <option key={camera.id} value={camera.id}>{camera.name}</option>
                ))}
              </select>
              <select
                value={newRelationship.to_camera_id}
                onChange={(e) => setNewRelationship({...newRelationship, to_camera_id: parseInt(e.target.value)})}
                className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-300"
              >
                <option value={0}>Select To Camera</option>
                {cameras.map((camera) => (
                  <option key={camera.id} value={camera.id}>{camera.name}</option>
                ))}
              </select>
              <input
                type="number"
                placeholder="Average Transition Time (seconds)"
                value={newRelationship.avg_transition_time || ""}
                onChange={(e) => setNewRelationship({...newRelationship, avg_transition_time: parseInt(e.target.value) || 0})}
                className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-300"
              />
            </div>
            <div className="flex gap-2 mt-4">
              <button
                onClick={handleAddRelationship}
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
      )}
    </div>
  );
}
