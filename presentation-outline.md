# Rafeeq Secure Municipal Agent — 8-minute presentation

1. **Problem (1 min):** Applicants need fast answers and safe actions across fees, status, inspections, refunds, and escalation. The data is synthetic and the assistant must never disclose an unverified record.
2. **Live demo (2 min):** Ask for the fee of a 3 m² illuminated sign; then ask to book Noura's inspection with identity data and explicit confirmation. Show the approval prompt and the audit line.
3. **Design ladder (2 min):** `AGENTS.md` prompt and trust boundary; MCP policy retrieval; local typed tools; compaction and result caps; write approval; step/cost budgets; SQLite synthetic data.
4. **Evaluation (2 min):** Show `eval-A.csv` vs `eval-B.csv`, pass rate, pass^k, average steps/tokens, and the largest error category. Explain that B changes only the retrieval instruction.
5. **Security (1 min):** Show the “SYSTEM OVERRIDE” attack, failed identity verification, and the code-enforced write gate. Explain private data + untrusted input + egress/state-change risk.

**Fallback:** run the prerecorded demo or show the saved audit/evaluation CSVs if model quota or network fails.
