# Compliance notes (not legal advice; verify with MTS and primary texts)

## Basis
Law of the Republic of Belarus No. 99-Z on personal data protection (7 May 2021); cross-border transfer rules and the list of countries with adequate protection (order of the National Personal Data Protection Center No. 14, 15 Nov 2021); constitutional protection of the secrecy of telephone communications (Art. 28) and criminal liability for violating it (Criminal Code Art. 203). MTS lecture requirements: notify the caller, subscriber consent, audit of access, local processing preferred.

## Controls in the product
| Topic | Control | Requirement |
|---|---|---|
| Caller notice | Spoken AI + recording disclosure on every call | FR-02 |
| Subscriber consent | Recorded in wizard, calls rejected without it | FR-12 |
| Local processing | STT, LLM, TTS, storage on the local machine; allowlist for outgoing HTTP | NFR-01, FR-14 |
| Minimization | Audio not stored by default; retention days; delete-all | FR-19, NFR-03 |
| Caller objection | No-record mode stores metadata only | FR-21 |
| Access audit | Hash-chained audit log: who viewed or edited what, when | FR-13 |
| Encryption | Field-level encryption of transcripts, summaries, slots | FR-13 |
| Notices | Masked Telegram notices, full data only in dashboard | FR-08 |

## Open questions for the pitch and the MTS working chat
1. Does a Telegram notice with masked content count as cross-border transfer for the operator's compliance team?
2. What retention period and access model does MTS require for call content and transcripts?
3. How should the subscriber's consent be captured at activation of the service in MTS channels?
4. Is the caller disclosure wording acceptable, and in which languages?
5. Which hosting is acceptable for models in production (operator data center only)?
