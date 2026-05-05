import { useState, useEffect } from "react";
import { Camera, CameraRelationship } from "./types";

type OperationResult = { success: true } | { success: false; error: string; cancelled?: never };
type DeleteResult = { success: true } | { success: false; error: string; cancelled?: never } | { success: false; cancelled: true; error?: never };

export function useCameraData() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [relationships, setRelationships] = useState<CameraRelationship[]>([]);
  const [loading, setLoading] = useState(false);

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

  return {
    cameras,
    relationships,
    loading,
    fetchData,
    setCameras,
    setRelationships
  };
}

export function useCameraOperations(fetchData: () => Promise<void>) {
  const handleAddCamera = async (camera: Omit<Camera, 'id'>): Promise<OperationResult> => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/cameras`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(camera)
      });
      
      if (response.ok) {
        await fetchData();
        return { success: true };
      } else {
        const errorData = await response.json();
        return { success: false, error: errorData.detail || 'Unknown error' };
      }
    } catch (error) {
      console.error("Error adding camera:", error);
      return { success: false, error: error instanceof Error ? error.message : 'Unknown error' };
    }
  };

  const handleUpdateCamera = async (camera: Camera): Promise<OperationResult> => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/cameras/${camera.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(camera)
      });
      
      if (response.ok) {
        await fetchData();
        return { success: true };
      } else {
        const errorData = await response.json();
        return { success: false, error: errorData.detail || 'Unknown error' };
      }
    } catch (error) {
      console.error("Error updating camera:", error);
      return { success: false, error: error instanceof Error ? error.message : 'Unknown error' };
    }
  };

  const handleDeleteCamera = async (id: number): Promise<DeleteResult> => {
    if (!confirm("Are you sure you want to delete this camera?")) return { success: false, cancelled: true };
    
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/cameras/${id}`, {
        method: "DELETE"
      });
      
      if (response.ok) {
        await fetchData();
        return { success: true };
      } else {
        const errorData = await response.json();
        return { success: false, error: errorData.detail || 'Unknown error' };
      }
    } catch (error) {
      console.error("Error deleting camera:", error);
      return { success: false, error: error instanceof Error ? error.message : 'Unknown error' };
    }
  };

  return {
    handleAddCamera,
    handleUpdateCamera,
    handleDeleteCamera
  };
}

export function useRelationshipOperations(fetchData: () => Promise<void>) {
  const handleAddRelationship = async (relationship: CameraRelationship): Promise<OperationResult> => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/camera-relationships`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(relationship)
      });
      
      if (response.ok) {
        await fetchData();
        return { success: true };
      } else {
        const errorData = await response.json();
        return { success: false, error: errorData.detail || 'Unknown error' };
      }
    } catch (error) {
      console.error("Error adding relationship:", error);
      return { success: false, error: error instanceof Error ? error.message : 'Unknown error' };
    }
  };

  const handleDeleteRelationship = async (fromId: number, toId: number): Promise<DeleteResult> => {
    if (!confirm("Are you sure you want to delete this relationship?")) return { success: false, cancelled: true };
    
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/camera-relationships/${fromId}/${toId}`, {
        method: "DELETE"
      });
      
      if (response.ok) {
        await fetchData();
        return { success: true };
      } else {
        const errorData = await response.json();
        return { success: false, error: errorData.detail || 'Unknown error' };
      }
    } catch (error) {
      console.error("Error deleting relationship:", error);
      return { success: false, error: error instanceof Error ? error.message : 'Unknown error' };
    }
  };

  return {
    handleAddRelationship,
    handleDeleteRelationship
  };
}

export function useCameraUtils(cameras: Camera[]) {
  const getCameraName = (id: number) => {
    const camera = cameras.find(c => c.id === id);
    return camera ? camera.name : `Camera ${id}`;
  };

  return { getCameraName };
}
