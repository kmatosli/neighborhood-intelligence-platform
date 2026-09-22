/**
 * The top of every section: the resident question it answers, in the shared hierarchy.
 *
 * V2 pages lead with a plain-language question, then the answer, then supporting figures, a
 * short explanation, and expandable method (DisclosureNote). This is the first layer, shared so
 * every page opens the same way and the question-oriented navigation carries through onto the
 * page itself.
 */

import type { ReactNode } from "react";

export function QuestionHeader({
  id,
  eyebrow = "Main question",
  question,
  lede,
  children,
}: {
  /** Heading id, so the enclosing section can be labelled by it. */
  id?: string;
  /** The small label above the question. */
  eyebrow?: string;
  question: ReactNode;
  /** One short sentence on what the page answers. Optional. */
  lede?: ReactNode;
  /** Notices that belong with the question (year-to-date, coming soon). */
  children?: ReactNode;
}) {
  return (
    <>
      <p className="wire-label mb-1">{eyebrow}</p>
      <h1 id={id} className="font-serif text-2xl leading-snug sm:text-3xl">
        {question}
      </h1>
      {lede && <p className="mt-2 max-w-2xl text-base text-muted-foreground">{lede}</p>}
      {children}
    </>
  );
}
