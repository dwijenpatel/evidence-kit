# The grading method — what a claim can bear

A corpus tags every claim with *how it was established* (`[official]`, `[measured]`,
`[measured, replicated]`, …). Those tags answer one question. Deciding what a claim can
**bear** — whether a decision may rest its weight on it — needs three:

1. **Warrant.** How was it established, and by whom?
2. **Incentive.** Does the source benefit if we believe it?
3. **Decay.** What does it depend on, and when does it stop being true?

The three questions are axes, and they compose rather than average: a claim is
**Tier A — load-bearing** when it carries one of the four warrant letters below (each letter
is a warrant-plus-incentive package; **any one suffices** for provenance) *and* its decay
class is within date — a stale warrant stops bearing load without ceasing to have been true.
Warrant grades the claim itself; what a *decision* may rest on the claim additionally needs
the fit checks in "What Tier A does not mean."

Every corpus built with this method keeps exactly two distilled documents —
`distilled/external.md` (Tier-A facts from the world) and `distilled/internal.md` (Tier-A
facts from the corpus owner's own runs). Everything else in the corpus is context: real,
useful, worth reading, but not something to build on without a further check.

---

## Why "official" is not a synonym for "true"

The natural instinct is that vendor/authoritative documentation is the closest thing to fact
available. It is not. The corpus this method was extracted from caught official documentation
wrong or stale **three times in one month, each by direct probe**: a documented cache-TTL model that
subscription auth silently didn't follow; an API documented to "fail loud" on invalid config
that silently accepted it; a documented JSON field the shipping build measurably lacked.

The lesson is not "distrust the vendor." It is that **an official document is a description
of intent, written at a moment, by people not obliged to update it when the system moves.**
So split `[official]` by what kind of claim it makes:

- **Official *commitment*** — pricing, plan structure, published policy the party is bound
  by: contractual, publicly auditable, expensive to get wrong. **Tier A.**
- **Official *mechanism*** — how the software/process behaves today, which flags exist, what
  a field is called. Ships and changes silently; docs lag. **Tier B** — believe the
  direction, verify before depending on it, re-probe on every release.

## Why an admission against interest beats a benchmark

Evidence law has long held that a statement is more credible when it damages the speaker's
own interest. The intuition is not ironclad — admissions can be strategically incomplete (a
small flaw conceded to look transparent while a larger one hides) — but the incentive runs
the right way, which is why this warrant buys *existence* only. It matters with unusual
force in any field saturated with parties benchmarking their own products.

Origin-corpus receipts that teach the pattern: a self-improving agent's authors reporting it
"removed the markers we use in the reward function to detect hallucination" — publishing the
failure of the system the paper celebrates; safety-measure authors reporting that adding an
explicit warning **failed to reduce** the unsafe behavior (their own measured rates
statistically indistinguishable — an earlier edition of this document said "made it slightly
more frequent," which read noise as signal; the against-interest *existence* point survives,
the direction does not); a vendor documenting that its own model "will sometimes change
tests to make them pass." Costly signals are credible. **An admission against interest is Tier A regardless of its other tags — for
existence.** Rate, cause, and magnitude are separate claims the admission never carries.

The symmetric rule: **a party's measurement of its own system, unreplicated, is Tier C** —
cite it for framing, never for a decision. This applies to vendors, paper authors, and to
the corpus owner.

## Applying the rule to yourself

The framing cuts inward, and it produces the most useful distinction in `internal.md`:

> **Your recorded defects are Tier-A evidence. Your recorded wins are not.**

You are motivated for your own project to succeed. A log entry saying your mechanism caught
what nothing else caught is the result you hoped for, reported by the person who hoped for
it. A log entry saying your machinery deadlocked is a confession. Weigh the failures
heavily and organize `internal.md` to say so out loud.

Wins are not worthless — they are **claims that require an artifact**. A win is promoted to
Tier A only when a committed, third-party-checkable artifact backs it: raw run data, a
verdict file, a reproducible harness. Strip the artifact and it is a self-serving
single-source measurement — Tier C. The artifact does all the work.

## The four Tier-A warrants

A claim reaches Tier A if it satisfies **at least one**:

| | Warrant | Why it holds | Failure mode it does not fix |
|---|---|---|---|
| **A1** | **Independently replicated** — ≥2 parties, no shared methodology, no shared stake. | Two independent errors rarely coincide. | Replication proves the *measurement*, not the *stability* of the thing measured. |
| **A2** | **Admission against interest** — the source reports something that damages its own system, product, or argument. | The incentive to fabricate runs backwards. | Existence claims only. "It happened once" ≠ "it happens at rate X". |
| **A3** | **Directly verifiable** — raw artifacts and a reproduction path are committed, **and the path has actually been executed against the committed state** (maintenance rule 5); anyone can re-run it at zero or known cost. Includes code read in a pinned checkout and live probes. | You do not have to trust the claimant; you can look. | Verifies *that build, that day*. Says nothing about tomorrow. |
| **A4** | **Official commitment** — a policy statement the party is bound by (pricing, plan structure, published thresholds). | Contractual and publicly auditable. | Does **not** extend to mechanism claims. |

**Mathematics (`M`)** sits outside the scheme: a theorem is not evidence about the world, it
is a constraint on it. Formal cores never expire. (Empirical magnitudes cited *alongside* a
theorem are measurements with their own decay — flag them apart from the theorem.)

Everything else is:

- **Tier B — directional.** Single-source measurements, official mechanism documentation,
  peer-reviewed-but-unreplicated results, corroborated-by-analogue findings. *Trust the
  sign; do not import the magnitude.* Most of any honest corpus lives here, legitimately.
- **Tier C — framing only.** Marketing, self-administered benchmarks, folklore, hype-tier
  anecdotes. Cite to explain what people believe, never to justify a decision.

## Decay: warrant and durability are different axes

A fact can have impeccable warrant and a shelf life of days. A perfectly replicated
measurement of a vendor build is obsolete the moment the vendor ships. So every Tier-A fact
carries a **decay class**, and fast-decaying ones carry a date and a recheck trigger.

Universal classes that survive across domains:

| Class | Depends on | Half-life | Recheck trigger |
|---|---|---|---|
| `math` | Logic. Nothing. | Permanent | Never |
| `human-factors` | Properties of human cognition, replicated across decades. | Decades | A paradigm shift in the interface between humans and the system |
| `llm-class` *(AI domains)* | A property of LLMs as a class (error correlation, reward hacking). | Years, probably | A capability generation that plausibly changes the mechanism |

**Each corpus defines the rest of its decay table at scaffold time** in
`distilled/README.md`, naming the domain's own volatility layers (release cadences, live
record ledgers, funding press, policy surfaces…), each with a half-life and a trigger. The
origin corpus's table — `model-generation` / `vendor-policy` / `vendor-build` /
`our-tree` / `their-tree` — is the worked example of the granularity to aim for.

A second worked example, for corpora holding hardware and software cost-performance
substrate — the granularity a `Parameters` table needs:

| Class *(technology domains)* | Depends on | Half-life | Recheck trigger |
|---|---|---|---|
| `price-surface` | Vendor or cloud list pricing. | Quarters | A pricing-page change, or a new SKU family |
| `perf-envelope` | A measured throughput, latency, or IOPS figure for a specific part or service. | Tied to the part | A firmware, driver, or silicon revision |
| `media-generation` | A storage or memory generation. | 2–3 years | The next generation shipping at volume |
| `spec-standard` | A published standard revision. | ~5 years | The next revision ratified |
| `adoption-curve` | How broadly a technology is deployed. | ~1 year | A major platform changing its default |

**These half-lives are provisional and deliberately uncalibrated.** A decay rate is not
derivable a priori — it is learned by watching rows move. A corpus adopting this table
should re-fetch its fastest class and measure what actually changed after a few weeks of
holdings, then replace these figures with observed ones. This is safe to defer only while
nothing rests on the corpus; it stops being safe the moment a decision cites a row. What
cannot be deferred is the `as_of` date on every row, because it is what the recalibration
measures against.

**The composition rule:** a fact is only as durable as its fastest-decaying dependency.
Replication buys warrant, not shelf life.

**Archived captures.** A row sourced from a web archive carries the **capture date** as
`as_of`, never the retrieval date, and it is evidence about what the page said *at that
capture*. Cite the capture URL including its timestamp, so the claim is re-checkable
against the same bytes. A capture is not weaker evidence than a live fetch for the moment
it covers — but it says nothing about the present, and a `price-surface` row built from a
two-year-old capture is two years stale no matter when it was retrieved. The archive's own
content digest may be recorded alongside; the base32 SHA-1 of empty content
(`3I42H3S6NNFQ2MSVX7XZKYAYSCX5QBYJ`) marks a capture that stored nothing and must never be
read as "the page was empty."

## Absence findings

"No surveyed X does Y" is a genuinely useful claim (it is how unoccupied niches are found)
and a structurally weak one: absence is only as strong as the enumerated sample. Every
absence finding states **how many things were searched, which ones, and as of when.** Treat
absence findings as **Tier A about the sample, Tier B about the world.** And mind what the
finding licenses: absence establishes a niche is *unoccupied* — never that occupying it is
cheap, easy, or valuable. Cost and value claims need their own warrant.

## What Tier A does not mean

The first two are about the claim; the last four are the **fit checks** — what a decision
must add before resting weight on even a perfectly-warranted claim. A citation that fails a
fit check is not evidence for the decision citing it, however good its warrant.

- **Not "certain."** It means *the best-warranted class available*.
- **Not "still true."** Check the decay class and the date. A stale Tier-A fact is worse
  than a Tier-B one, because it invites confidence.
- **Not "sufficient."** An existence proof (`A2`) says a failure mode is real, never how
  often it fires. Rates need `A1` or `A3`.
- **Not "importable."** Mechanisms transfer between systems; effect sizes usually do not.
  **Import the mechanism, never the magnitude.**
- **Not "wider than what was measured."** A warrant covers the claim *inside its measured
  regime*. Citing it outside that regime is a new, unwarranted claim.
- **Not "about your setting."** Transporting a result into your system is a second claim
  needing its own argument — state, at the citation site, why your setting sits inside the
  measured regime, or name the transport as provisional with a promotion trigger.

## Maintaining the distilled documents

1. A fact enters only with a warrant letter (`A1`–`A4`/`M`), a decay class, and — for
   anything faster than the domain's slow class — a date.
2. When a recheck trigger fires, affected rows are re-verified or **struck**, never
   silently kept.
3. A fact that fails re-verification moves to the corpus README's **corrections ledger**, so
   nobody re-imports the error. That ledger is itself an against-interest record — read it
   as the most trustworthy page in the corpus.
4. When an internal measurement loses its artifact (raw data deleted, harness rots), it
   drops out of Tier A automatically. The artifact is the warrant.
5. **`A3` is labeled only after the reproduction path has actually been executed** — re-run,
   then label; never label from reading. (Origin receipt: a benchmark graded A3 whose
   committed grader could never have reproduced its own headline — reading *looked like*
   verification; only running was.)
6. A distilled row names its source document and section, so the chain
   distilled-claim → holdings-doc → primary source stays walkable.
