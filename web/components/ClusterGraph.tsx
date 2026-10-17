"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });

const COLORS: Record<string, string> = {
  Identity: "#c65d12",
  Subscriber: "#1b2430",
  Face: "#1f7a4d",
  SIM: "#3d6f8c",
  TSP: "#8c5a2f",
};

export type GraphData = {
  nodes: { id: string; label: string; type: string }[];
  links: { source: string; target: string; label: string }[];
};

export default function ClusterGraph({ data }: { data: GraphData }) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(720);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(() => setWidth(element.clientWidth));
    observer.observe(element);
    setWidth(element.clientWidth);
    return () => observer.disconnect();
  }, []);

  if (data.nodes.length === 0) {
    return <p className="text-sm text-stone-500">This cluster has no graph rows yet.</p>;
  }

  return (
    <div ref={ref} className="h-[460px] overflow-hidden rounded-2xl border border-line bg-[#fbf8f1]">
      <ForceGraph2D
        graphData={data}
        width={width}
        height={460}
        backgroundColor="#fbf8f1"
        nodeLabel={(node: { label?: string; type?: string }) => `${node.type ?? ""}: ${node.label ?? ""}`}
        nodeColor={(node: { type?: string }) => COLORS[node.type ?? ""] ?? "#64748b"}
        nodeVal={(node: { type?: string }) => (node.type === "Identity" ? 10 : node.type === "Subscriber" ? 7 : 4)}
        linkLabel="label"
        linkColor={() => "#b7ad9c"}
        cooldownTicks={80}
      />
    </div>
  );
}
