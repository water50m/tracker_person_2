"use client";

import { Trash2 } from "lucide-react";
import { CameraRelationship } from "./types";

interface RelationshipListProps {
  relationships: CameraRelationship[];
  getCameraName: (id: number) => string;
  onDeleteRelationship: (fromId: number, toId: number) => void;
}

export default function RelationshipList({
  relationships,
  getCameraName,
  onDeleteRelationship
}: RelationshipListProps) {
  return (
    <div className="space-y-2">
      {relationships.map((rel, index) => (
        <div key={index} className="flex items-center justify-between p-3 bg-slate-800/50 border border-slate-700 rounded">
          <div className="flex items-center gap-3">
            <span className="font-mono text-sm text-slate-300">
              {getCameraName(rel.from_camera_id)}
            </span>
            <span className="text-purple-400">—</span>
            <span className="font-mono text-sm text-slate-300">
              {getCameraName(rel.to_camera_id)}
            </span>
            <span className="text-xs text-slate-500">
              ({rel.avg_transition_time}s)
            </span>
          </div>
          <button
            onClick={() => onDeleteRelationship(rel.from_camera_id, rel.to_camera_id)}
            className="p-1 text-red-400 hover:text-red-300"
          >
            <Trash2 className="w-3 h-3" />
          </button>
        </div>
      ))}
    </div>
  );
}
