/**
 * The shape of the answer, while it is on its way.
 *
 * Roughly where the heading, the verdict and the seven rows will be, so the
 * panel does not jump when they arrive. A spinner would say "something is
 * happening"; this says what.
 */
export default function PanelSkeleton() {
  return (
    <div className="skel">
      <span className="sr-only">Loading this shipment</span>
      <span className="skel-line w60" aria-hidden="true" />
      <span className="skel-line w35" aria-hidden="true" />
      <span className="skel-tag" aria-hidden="true" />
      <span className="skel-line w80" aria-hidden="true" />
      {[0, 1, 2, 3, 4, 5, 6].map((i) => (
        <span key={i} className="skel-row" aria-hidden="true" />
      ))}
    </div>
  );
}
