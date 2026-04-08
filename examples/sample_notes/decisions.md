# Architecture Decisions

## 2024-03-01 — Use event-driven architecture for sensor pipeline

**Context:** The sensor fusion pipeline was originally designed with a polling loop at 10 Hz. This caused unnecessary CPU usage and made latency dependent on poll interval rather than data availability.

**Decision:** Migrate to an event-driven model using asyncio queues. Each sensor publishes to a shared queue; the fusion node subscribes and processes only when new data arrives.

**Consequences:**
- Latency reduced from ~100 ms to ~5 ms average
- CPU load dropped by ~30% during idle periods
- Testing becomes more complex (event ordering must be managed in tests)

---

## 2024-03-15 — Store fused state as time-stamped snapshots

**Context:** Consumers of the fused state (navigation, visualization) need consistent snapshots, not a continuously mutating object.

**Decision:** The fusion output is written as immutable snapshots into a ring buffer. Each snapshot has a monotonic timestamp and version number.

**Consequences:**
- Consumers can request the latest snapshot or a specific time range
- No locking required for readers
- Memory bounded by ring buffer size (configurable, default: 1000 snapshots)

---

## 2024-04-02 — Reject adding a REST API at this stage

**Context:** A colleague proposed adding a REST API layer to make the system easier to query from external tools.

**Decision:** Rejected for now. The system is used exclusively by in-process components and CLI tools. A REST API would add latency, maintenance burden, and a new attack surface with no immediate benefit.

**Revisit if:** An external dashboard or multi-process integration becomes a real requirement.

---

## 2024-04-10 — Use ROS2 parameters for runtime configuration

**Context:** Several hard-coded values (thresholds, topic names) were scattered across node constructors.

**Decision:** Move all tunable values to ROS2 parameter declarations. Default values are set in code; overrides come from `params.yaml`.

**Consequences:**
- Configuration is explicit and inspectable with `ros2 param list`
- Parameter files can be committed per environment (dev, robot, simulation)
- No more magic constants in the codebase
