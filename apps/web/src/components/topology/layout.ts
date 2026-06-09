import type { GraphEdge, GraphNode } from "../../lib/types";

const COL_WIDTH = 290;
const ROW_HEIGHT = 150;

/**
 * Deterministic layered DAG layout (left → right).
 * Depth = BFS first-visit distance from the roots, which naturally ignores
 * back-edges (e.g. a security reviewer bouncing work back to a coder), so
 * cyclic message flows still render as a readable pipeline.
 */
export function layoutGraph(
  nodes: GraphNode[],
  edges: GraphEdge[],
): Map<string, { x: number; y: number }> {
  const ids = nodes.map((node) => node.id);
  const known = new Set(ids);
  const adjacency = new Map<string, string[]>(ids.map((id) => [id, []]));
  const inDegree = new Map<string, number>(ids.map((id) => [id, 0]));

  for (const edge of edges) {
    if (edge.source === edge.target) continue;
    if (!known.has(edge.source) || !known.has(edge.target)) continue;
    adjacency.get(edge.source)!.push(edge.target);
    inDegree.set(edge.target, (inDegree.get(edge.target) ?? 0) + 1);
  }

  let roots = ids.filter((id) => (inDegree.get(id) ?? 0) === 0);
  if (roots.length === 0 && ids.length > 0) roots = [ids[0]];

  const depth = new Map<string, number>();
  const queue = [...roots];
  for (const root of roots) depth.set(root, 0);
  while (queue.length > 0) {
    const current = queue.shift()!;
    for (const next of adjacency.get(current) ?? []) {
      if (!depth.has(next)) {
        depth.set(next, (depth.get(current) ?? 0) + 1);
        queue.push(next);
      }
    }
  }

  // Nodes unreachable from any root (isolated participants) share a trailing column.
  const unplaced = ids.filter((id) => !depth.has(id));
  if (unplaced.length > 0) {
    const column = Math.max(0, ...depth.values()) + 1;
    for (const id of unplaced) depth.set(id, column);
  }

  const columns = new Map<number, string[]>();
  for (const id of ids) {
    const col = depth.get(id) ?? 0;
    if (!columns.has(col)) columns.set(col, []);
    columns.get(col)!.push(id);
  }

  const positions = new Map<string, { x: number; y: number }>();
  for (const [col, members] of columns) {
    members.forEach((id, row) => {
      positions.set(id, {
        x: col * COL_WIDTH,
        y: (row - (members.length - 1) / 2) * ROW_HEIGHT,
      });
    });
  }
  return positions;
}
