# Semantic Deduplication Reference

> This page is a compact reference. For full context, see [Advanced Memory Strategy](advanced_memory_strategy.md).

---

## Why it matters

Storing the same rule twice — in different phrasings, different rooms, or different wings — makes retrieval noisy and maintenance expensive. Agents surface contradictory entries. Updates get applied inconsistently. The store degrades.

Deduplication prevents that. The primary mechanism is **disciplined writing**: before creating a new entry, check whether one already exists.

---

## Scoped comparison

Always compare a candidate entry only against entries in the **same wing and room**.

Cross-wing or cross-room comparison produces misleading signals. A rule that is 85% similar to an entry in `myapp/architecture` may still be appropriate in `myapp/anti-patterns` — because the type is different and the purpose differs.

---

## Threshold guidance

Similarity scores are guidance, not enforcement. Use them to calibrate judgment, not to replace it.

| Similarity | Signal | Suggested action |
|-----------|--------|-----------------|
| ≥ 0.86 | Near-duplicate | Enrich the existing entry; do not create a new one |
| 0.55 – 0.85 | Related content | Review manually; create only if the new entry captures a genuinely distinct rule, contract, or anti-pattern |
| < 0.55 | Likely distinct | Creating a new entry is acceptable if persistence criteria are met |

These ranges work as an advanced refinement layered on top of writing discipline. They are not a gate.

---

## Enrich vs. create

Prefer enriching over creating:

- **Enrich** when the new information extends, qualifies, or adds rationale to an existing entry.
- **Create** when the new entry captures a genuinely distinct rule, contract, or anti-pattern.
- When enriching, **preserve the original rule** and extend it. Do not rewrite it from scratch.

---

## Type-aware exception

If two entries are similar in content but differ in type — for example, an `architecture-rule` and an `anti-pattern` that describe the same component — do **not** merge them automatically. Different types communicate different weight and serve different retrieval purposes. Keep them as separate entries.

---

## Human-first rule

Semantic similarity is a signal. Human judgment is the decision.

A high similarity score is a prompt to review — not an automatic veto on creating a new entry. If a new entry captures something genuinely distinct, create it regardless of score. If it doesn't, enrich what exists.

Writing discipline remains the primary deduplication mechanism.

---

*Related: [Advanced Memory Strategy §5.3](advanced_memory_strategy.md#53-deduplication-policy) · [Memory Example](memory_example.md#optional-semantic-deduplication)*
