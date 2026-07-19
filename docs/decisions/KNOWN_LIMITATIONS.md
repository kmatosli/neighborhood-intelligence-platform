# Known Limitations

What this project **cannot currently tell you**. Limitations of the project as it stands
today — not of the eventual product.

## The project does not yet produce any published number

There is no stored data, no analysis, and no public site. What exists is a verified
connection to the Chicago crime API and a validation layer. **Nothing here should be cited
as a finding about Bronzeville or Woodlawn.**

## It cannot say anything about a neighborhood yet

There are no boundaries. Bronzeville has no approved definition, Woodlawn's polygon is not
ingested, and no record has ever been assigned to a neighborhood. Every neighborhood-level
question is currently unanswerable.

## Its history is raw and unanalyzed

Historical crime can now be ingested year by year into Bronze, but Bronze is raw storage —
nothing is typed, deduplicated across refreshes, grouped, or aggregated. No trend has been
computed, and none should be quoted from these files.

## It does not track corrections

Without incremental refresh on `updated_on`, the project would not notice the city revising
or removing a record. Any data pulled today is a snapshot with no correction history.

---

## Limitations that will persist into the product

These are properties of the underlying data and will remain true no matter how much is built.

**Reported crime is not crime.** The data measures what was reported to and recorded by CPD.
Unreported crime is invisible, and a change in reporting behavior is indistinguishable from a
change in crime.

**Roughly the last seven days are incomplete.** Any recent-window comparison will understate
the present.

**The past changes.** Records are corrected after publication, so historical figures
legitimately shift.

**Some crimes cannot be placed.** Records without coordinates cannot be assigned to a
neighborhood or mapped. Neighborhood counts and citywide totals therefore will not reconcile
by simple subtraction.

**Arrest is not conviction.** The data cannot speak to charges, prosecution, or guilt.

**Causation is out of reach.** The project can show that a trend changed near a dated event.
It cannot show that the event caused it, and will not claim to.

**Nationality and immigration status cannot be inferred.** The dataset contains no such
fields. Questions of this kind cannot be answered from this data, and the project will say so
rather than approximating an answer.

**Bronzeville's boundary is a choice, not a fact.** Whatever boundary is approved, some
residents will disagree with it. Every Bronzeville figure is conditional on that choice, which
is why the boundary is versioned and published.

**Small numbers are noisy.** In two neighborhoods, a specific crime type over a short window
may involve very few incidents, where percentage changes are dramatic and meaningless.
