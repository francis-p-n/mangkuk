import { Check, Eye, TriangleAlert } from "lucide-react";
import type { LucideProps } from "lucide-react";

/**
 * The glyph for each verdict.
 *
 * One mapping, used by the filter, the rows and the detail panel, so a
 * shipment wears the same mark wherever it appears.
 *
 * The point is not decoration: it is a second channel. Until now a verdict was
 * carried by colour and by a phrase, and red-green colour blindness is common
 * enough that "the red ones" is not a safe instruction to give a desk. A
 * triangle, an eye and a tick differ in shape at any size and in any palette.
 *
 * Always aria-hidden. Every place this is used already has the words next to
 * it, and a screen reader announcing "triangle alert needs fixing" is worse
 * than one announcing "needs fixing".
 */
const ICONS = {
  MISMATCH: TriangleAlert,
  NEEDS_REVIEW: Eye,
  OK: Check,
} as const;

export type Status = keyof typeof ICONS;

export default function StatusIcon({
  status,
  size = 14,
  ...rest
}: { status: string; size?: number } & Omit<LucideProps, "ref">) {
  const Icon = ICONS[status as Status];
  if (!Icon) return null;
  return (
    <Icon
      size={size}
      strokeWidth={2.25}
      aria-hidden="true"
      focusable="false"
      {...rest}
    />
  );
}
