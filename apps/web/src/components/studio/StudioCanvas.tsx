import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  ReactFlow,
  type Connection,
  type Edge,
  type NodeTypes,
} from "@xyflow/react";
import { useMemo } from "react";

import type { Provider, StudioAgent, StudioEdge } from "../../lib/types";
import { StudioAgentNode, type StudioFlowNode } from "./StudioAgentNode";

const nodeTypes: NodeTypes = { studioAgent: StudioAgentNode };

interface StudioCanvasProps {
  agents: StudioAgent[];
  edges: StudioEdge[];
  providers: Provider[];
  selectedAgentId: string | null;
  selectedEdgeId: string | null;
  onSelectAgent: (agentId: string | null) => void;
  onSelectEdge: (edgeId: string | null) => void;
  onMoveAgent: (agentId: string, x: number, y: number) => void;
  onConnect: (sourceAgentId: string, targetAgentId: string) => void;
}

export function StudioCanvas({
  agents,
  edges,
  providers,
  selectedAgentId,
  selectedEdgeId,
  onSelectAgent,
  onSelectEdge,
  onMoveAgent,
  onConnect,
}: StudioCanvasProps) {
  const configured = useMemo(
    () => new Set(providers.filter((p) => p.configured).map((p) => p.name)),
    [providers],
  );

  const nodes = useMemo<StudioFlowNode[]>(
    () =>
      agents.map((agent) => ({
        id: agent.agent_id,
        type: "studioAgent" as const,
        position: { x: agent.position_x, y: agent.position_y },
        data: { agent, providerConfigured: configured.has(agent.provider) },
        selected: agent.agent_id === selectedAgentId,
      })),
    [agents, configured, selectedAgentId],
  );

  const flowEdges = useMemo<Edge[]>(
    () =>
      edges.map((edge) => ({
        id: edge.edge_id,
        source: edge.source_agent_id,
        target: edge.target_agent_id,
        label: edge.label ?? undefined,
        selected: edge.edge_id === selectedEdgeId,
        style: { stroke: edge.edge_id === selectedEdgeId ? "#818cf8" : "#3f3f46", strokeWidth: 1.5 },
        labelStyle: { fill: "#a1a1aa", fontSize: 10 },
        labelBgStyle: { fill: "#18181d" },
        markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16, color: "#52525b" },
      })),
    [edges, selectedEdgeId],
  );

  return (
    <ReactFlow
      nodes={nodes}
      edges={flowEdges}
      nodeTypes={nodeTypes}
      onNodeClick={(_, node) => onSelectAgent(node.id)}
      onEdgeClick={(_, edge) => onSelectEdge(edge.id)}
      onPaneClick={() => {
        onSelectAgent(null);
        onSelectEdge(null);
      }}
      onNodeDragStop={(_, node) => onMoveAgent(node.id, node.position.x, node.position.y)}
      onConnect={(connection: Connection) => {
        if (connection.source && connection.target && connection.source !== connection.target) {
          onConnect(connection.source, connection.target);
        }
      }}
      fitView
      fitViewOptions={{ padding: 0.2 }}
      minZoom={0.3}
      maxZoom={1.6}
      deleteKeyCode={null}
    >
      <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#1e1e25" />
      <Controls showInteractive={false} position="bottom-right" />
    </ReactFlow>
  );
}
