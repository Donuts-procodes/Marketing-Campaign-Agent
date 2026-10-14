import { ExternalLink } from "lucide-react";
import type { SourcedPoint } from "@/types/research";
import { safeHref } from "@/lib/utils";

export function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/** Where a point came from: a link to its page, or "your brief". */
export function SourceTag({ point }: { point: SourcedPoint }) {
  const href = safeHref(point.source_url);
  if (href) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-0.5 text-[10px] text-[#8A8176] hover:text-[#1F1A17] whitespace-nowrap"
      >
        {hostOf(href)} <ExternalLink className="w-2.5 h-2.5" />
      </a>
    );
  }
  return point.from_merchant ? <span className="text-[10px] text-[#8A8176] whitespace-nowrap">your brief</span> : null;
}

/** A titled list of sourced points; renders nothing when empty. */
export function PointList({ title, points, marker = "•" }: { title: string; points: SourcedPoint[]; marker?: string }) {
  if (!points.length) return null;
  return (
    <div className="space-y-2">
      <div className="text-[11px] font-bold uppercase tracking-wide text-[#8A8176]">{title}</div>
      <ul className="space-y-1.5">
        {points.map((p, i) => (
          <li key={i} className="flex gap-2 text-xs text-[#4A4239] leading-relaxed">
            <span aria-hidden className="text-[#C7431F]">{marker}</span>
            <span className="min-w-0">
              {p.text} <SourceTag point={p} />
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
