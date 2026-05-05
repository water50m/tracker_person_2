"use client";

import { useEffect } from "react";
import { Camera as CameraIcon } from "lucide-react";
import { 
  ReactFlow, 
  Node, 
  Edge, 
  Background, 
  Controls, 
  MiniMap,
  useNodesState,
  useEdgesState,
  ConnectionMode,
  Handle,
  Position
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Camera, CameraRelationship } from "./types";

// Custom node component with 4 connection points
const CameraNode = ({ data }: { data: any }) => {
  const isActive = data.isActive;
  
  return (
    <div className="relative">
      {/* Connection handles */}
      <Handle
        type="source"
        position={Position.Top}
        id="top"
        className="w-3 h-3 bg-purple-500 border-2 border-slate-800"
      />
      <Handle
        type="source"
        position={Position.Right}
        id="right"
        className="w-3 h-3 bg-purple-500 border-2 border-slate-800"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        id="bottom"
        className="w-3 h-3 bg-purple-500 border-2 border-slate-800"
      />
      <Handle
        type="source"
        position={Position.Left}
        id="left"
        className="w-3 h-3 bg-purple-500 border-2 border-slate-800"
      />
      
      {/* Node content */}
      <div 
        className={`
          px-4 py-3 border-2 border-slate-900 rounded-lg shadow-lg 
          ${isActive ? 'bg-green-500' : 'bg-gray-500'}
        `}
      >
        <div className="text-center">
          <CameraIcon className="w-6 h-6 text-white mx-auto mb-1" />
          <div className="font-semibold text-white text-sm">{data.cameraName}</div>
        </div>
      </div>
    </div>
  );
};

// Advanced pathfinding to avoid line crossings
const calculateNonCrossingPath = (
  sourceNode: any,
  targetNode: any,
  allNodes: any[],
  allEdges: any[],
  edgeIndex: number
) => {
  const dx = targetNode.position.x - sourceNode.position.x;
  const dy = targetNode.position.y - sourceNode.position.y;
  
  // Determine connection points
  let sourceHandle = 'right';
  let targetHandle = 'left';
  
  if (Math.abs(dx) > Math.abs(dy)) {
    if (dx > 0) {
      sourceHandle = 'right';
      targetHandle = 'left';
    } else {
      sourceHandle = 'left';
      targetHandle = 'right';
    }
  } else {
    if (dy > 0) {
      sourceHandle = 'bottom';
      targetHandle = 'top';
    } else {
      sourceHandle = 'top';
      targetHandle = 'bottom';
    }
  }
  
  // Calculate path with offset to avoid crossings
  const midX = (sourceNode.position.x + targetNode.position.x) / 2;
  const midY = (sourceNode.position.y + targetNode.position.y) / 2;
  
  // Add perpendicular offset for edges with same index parity to avoid crossings
  const offset = (edgeIndex % 2 === 0 ? 20 : -20) + (edgeIndex % 4) * 10;
  
  let pathData;
  
  if (Math.abs(dx) > Math.abs(dy)) {
    // Horizontal dominant - use curved path with vertical offset
    const controlX = midX;
    const controlY = midY + offset;
    pathData = `M ${sourceNode.position.x},${sourceNode.position.y} Q ${controlX},${controlY} ${targetNode.position.x},${targetNode.position.y}`;
  } else {
    // Vertical dominant - use curved path with horizontal offset  
    const controlX = midX + offset;
    const controlY = midY;
    pathData = `M ${sourceNode.position.x},${sourceNode.position.y} Q ${controlX},${controlY} ${targetNode.position.x},${targetNode.position.y}`;
  }
  
  return { 
    sourceHandle, 
    targetHandle, 
    pathData,
    style: {
      stroke: '#8b5cf6', 
      strokeWidth: 2,
      fill: 'none',
      filter: 'drop-shadow(0 0 3px rgba(139, 92, 246, 0.3))'
    }
  };
};

// Custom edge component for non-crossing curves
const CustomEdge = ({ 
  id, 
  sourceX, 
  sourceY, 
  targetX, 
  targetY, 
  sourcePosition, 
  targetPosition,
  data,
  label 
}: any) => {
  const { pathData, style } = data || {};
  
  return (
    <g>
      <path
        id={id}
        style={style || {
          stroke: '#8b5cf6', 
          strokeWidth: 2,
          fill: 'none',
          filter: 'drop-shadow(0 0 3px rgba(139, 92, 246, 0.3))'
        }}
        className="react-flow__edge-path"
        d={pathData || `M ${sourceX},${sourceY} L ${targetX},${targetY}`}
      />
      {label && (
        <text>
          <textPath href={`#${id}`} startOffset="50%" textAnchor="middle" className="text-xs font-bold" fill="#8b5cf6">
            {label}
          </textPath>
        </text>
      )}
    </g>
  );
};

// Register custom node type (moved outside component for performance)
const nodeTypes = {
  camera: CameraNode,
};

interface CameraDiagramProps {
  cameras: Camera[];
  relationships: CameraRelationship[];
}

export default function CameraDiagram({ cameras, relationships }: CameraDiagramProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  // Update diagram when cameras or relationships change
  useEffect(() => {
    console.log('Camera Diagram - Cameras:', cameras);
    console.log('Camera Diagram - Relationships:', relationships);
    
    const diagramNodes: Node[] = cameras.map((camera, index) => {
      // Create a more distributed layout for better connections
      const cols = Math.ceil(Math.sqrt(cameras.length));
      const row = Math.floor(index / cols);
      const col = index % cols;
      
      return {
        id: camera.id.toString(),
        type: 'camera', // Use custom node type
        position: {
          x: col * 250 + 100,
          y: row * 200 + 100
        },
        data: {
          cameraName: camera.name,
          isActive: camera.is_active
        },
        style: {
          background: 'transparent',
          border: 'none'
        }
      };
    });

    const diagramEdges: Edge[] = relationships.map((rel, index) => {
      const sourceNode = diagramNodes.find(node => node.id === rel.from_camera_id.toString());
      const targetNode = diagramNodes.find(node => node.id === rel.to_camera_id.toString());
      
      if (sourceNode && targetNode) {
        const { sourceHandle, targetHandle, pathData, style } = calculateNonCrossingPath(
          sourceNode,
          targetNode,
          diagramNodes,
          relationships,
          index
        );
        
        const edgeConfig = {
          id: `edge-${index}`,
          source: rel.from_camera_id.toString(),
          target: rel.to_camera_id.toString(),
          sourceHandle,
          targetHandle,
          label: `${rel.avg_transition_time}s`,
          type: 'custom',
          animated: false,
          markerEnd: undefined,
          data: { pathData, style }
        };

        console.log(`Final edge config:`, edgeConfig);
        return edgeConfig;
      }
      
      // Fallback for missing nodes
      return {
        id: `edge-${index}`,
        source: rel.from_camera_id.toString(),
        target: rel.to_camera_id.toString(),
        label: `${rel.avg_transition_time}s`,
        style: { 
          stroke: '#8b5cf6', 
          strokeWidth: 2,
          filter: 'drop-shadow(0 0 3px rgba(139, 92, 246, 0.3))'
        },
        animated: false,
        type: 'smoothstep',
        markerEnd: undefined
      };
    });

    console.log('Final edges array:', diagramEdges);

    setNodes(diagramNodes);
    setEdges(diagramEdges);
  }, [cameras, relationships, setNodes, setEdges]);

  return (
    <div className="h-[calc(100vh-300px)] border-2 border-slate-700 rounded-lg overflow-hidden">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        connectionMode={ConnectionMode.Loose}
        nodeTypes={nodeTypes}
        fitView
        style={{ background: '#1e293b' }}
      >
        <Background color="#334155" gap={16} />
        <Controls 
          style={{ background: '#334155', border: '1px solid #475569' }}
          showInteractive={false}
        />
        <MiniMap 
          style={{ background: '#334155', border: '1px solid #475569' }}
          nodeColor={(node) => {
            const camera = cameras.find(c => c.id.toString() === node.id);
            return camera?.is_active ? '#10b981' : '#6b7280';
          }}
        />
      </ReactFlow>
    </div>
  );
}
