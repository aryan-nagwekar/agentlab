import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  ReactFlow,
  type EdgeTypes,
  type NodeTypes,
  type ReactFlowInstance,
} from "@xyflow/react";
import { useEffect, useMemo, useRef } from "react";

import type { RunGraph } from "../../lib/types";
import { AgentNode, type AgentFlowNode } from "./AgentNode";
import { layoutGraph } from "./layout";
import { MessageEdge, type MessageFlowEdge } from "./MessageEdge";

const nodeTypes: NodeTypes = { agent: AgentNode };
const edgeTypes: EdgeTypes = { message: MessageEdge };

interface TopologyViewProps {
  graph: RunGraph;
  live: boolean;
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  onSelectNode: (nodeId: string | null) => void;
  onSelectEdge: (edgeId: string) => void;
}

export function TopologyView({
  graph,
  live,
  selectedNodeId,
  selectedEdgeId,
  onSelectNode,
  onSelectEdge,
}: TopologyViewProps) {
  const instanceRef = useRef<ReactFlowInstance<AgentFlowNode, MessageFlowEdge> | null>(null);

  const nodes = useMemo<AgentFlowNode[]>(() => {
    const positions = layoutGraph(graph.nodes, graph.edges);
    return graph.nodes.map((node) => ({
      id: node.id,
      type: "agent" as const,
      position: positions.get(node.id) ?? { x: 0, y: 0 },
      data: { node },
      selected: node.id === selectedNodeId,
    }));
  }, [graph, selectedNodeId]);

  const edges = useMemo<MessageFlowEdge[]>(
    () =>
      graph.edges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        type: "message" as const,
        animated: live,
        selected: edge.id === selectedEdgeId,
        data: { edge, onSelect: onSelectEdge },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 15,
          height: 15,
          color: edge.last_status === "failed" ? "#f87171" : "#52525b",
        },
      })),
    [graph, live, selectedEdgeId, onSelectEdge],
  );

  // Re-fit when topology shape changes (agents joining during a live run).
  useEffect(() => {
    const timer = window.setTimeout(
      () => instanceRef.current?.fitView({ padding: 0.18, duration: 250 }),
      60,
    );
    return () => window.clearTimeout(timer);
  }, [graph.nodes.length, graph.edges.length]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      onInit={(instance) => {
        instanceRef.current = instance;
      }}
      onNodeClick={(_, node) => onSelectNode(node.id)}
      onEdgeClick={(_, edge) => onSelectEdge(edge.id)}
      onPaneClick={() => onSelectNode(null)}
      fitView
      fitViewOptions={{ padding: 0.18 }}
      minZoom={0.3}
      maxZoom={1.6}
      nodesConnectable={false}
      deleteKeyCode={null}
    >
      <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#1e1e25" />
      <Controls showInteractive={false} position="bottom-right" />
    </ReactFlow>
  );
}
