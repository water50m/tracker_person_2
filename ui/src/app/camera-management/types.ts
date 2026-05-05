export interface Camera {
  id: number;
  name: string;
  source_url: string;
  is_active: boolean;
}

export interface CameraRelationship {
  from_camera_id: number;
  to_camera_id: number;
  avg_transition_time: number;
}

export type ViewMode = 'list' | 'diagram';
