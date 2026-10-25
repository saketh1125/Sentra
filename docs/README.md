# Sentra documentation

Use these documents for the current implementation:

- [Implementation status](IMPLEMENTATION_STATUS.md) — verified capabilities and
  known limits.
- [Architecture](ARCHITECTURE.md) — components and data flow.
- [API reference](API.md) — local HTTP routes and request behavior.
- [Data model](DATA_MODEL.md) — persisted tables and relationships.
- [Scoring](SCORING.md) — severity weights, caps, labels, and calculations.
- [Operations and privacy](OPERATIONS_AND_PRIVACY.md) — configuration,
  integrations, data handling, service commands, and troubleshooting.
- [Architecture decision log](decisions/DECISION_LOG.md) — historical
  research decisions and measurements.
- [Resource incident](resource-incident.md) — historical retrieval experiment
  resource-limit investigation.

`development-status.md`, `SESSION_PROGRESS.md`, and `../Sentra_research.md`
preserve earlier research checkpoints. Their original “not implemented” or
“blocked” status statements are historical; use `IMPLEMENTATION_STATUS.md` for
the current product state. Files under `evidence/` are experiment outputs, not
live application state.
