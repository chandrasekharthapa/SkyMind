"use client";

type Decision = {
  decision: "BOOK NOW" | "WAIT";
  confidence: number;
  reasons: string[];
};

type Props = {
  decision: Decision;
};

export default function DecisionCard({ decision }: Props) {
  const isBookNow = decision.decision === "BOOK NOW";
  const confidence = Math.round(decision.confidence * 100);

  return (
    <section className="decision-card" aria-label="Booking decision">
      <div className="decision-card__header">
        <span className="decision-card__eyebrow">Agent Decision</span>
        <span className={isBookNow ? "decision-card__badge decision-card__badge--book" : "decision-card__badge"}>
          {confidence}%
        </span>
      </div>

      <div className={isBookNow ? "decision-card__title decision-card__title--book" : "decision-card__title"}>
        {decision.decision}
      </div>

      <div className="decision-card__bar" aria-hidden="true">
        <span style={{ width: `${confidence}%` }} />
      </div>

      <ul className="decision-card__reasons">
        {decision.reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
    </section>
  );
}
