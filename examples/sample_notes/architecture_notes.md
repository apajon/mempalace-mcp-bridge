# Architecture Notes

## System overview

This project is a distributed sensor fusion and navigation stack for a mobile robot platform. It runs on ROS2 Humble on Ubuntu 22.04.

Components:

| Component | Language | Responsibility |
|---|---|---|
| `sensor_bridge` | Python | Reads raw sensor data, republishes as ROS2 msgs |
| `fusion_node` | Python | Fuses IMU + odometry + LiDAR into a pose estimate |
| `planner` | C++ | Computes collision-free paths given a goal and a costmap |
| `controller` | C++ | Executes velocity commands to follow the planned path |
| `viz_bridge` | Python | Streams state to a web dashboard via WebSocket |

---

## Data flows

```
/imu/data   ──┐
/odom       ──┤──► fusion_node ──► /fused_pose ──► planner ──► /cmd_vel ──► controller
/scan       ──┘                                         ▲
                                                        │
                                                  /map (static)
```

---

## Design principles applied

1. **Separation of concerns:** Each node has one responsibility. No node reads sensors and plans simultaneously.
2. **Parameterization over hardcoding:** All tunable values are ROS2 parameters with defaults in YAML.
3. **Fail-safe defaults:** If fusion loses a sensor, it continues with degraded accuracy rather than crashing.
4. **Testability:** Nodes accept mocked sensor input. Integration tests use bag file replay.

---

## Performance constraints

- End-to-end latency from sensor input to `/cmd_vel` output: < 50 ms
- Fusion runs at 50 Hz
- Path planning is triggered at 5 Hz (or on significant pose change)
- Controller runs at 20 Hz

These constraints are documented in `docs/perf_requirements.md` (not in this repo).

---

## Open questions (as of 2024-04-10)

- Should `viz_bridge` be a separate process or a plugin within `fusion_node`?
  - Current stance: separate process. Visualization latency is not critical; coupling would complicate testing.
- Is the costmap update rate (1 Hz) sufficient for dynamic environments?
  - Needs benchmarking with real sensor data. Raise to 5 Hz if latency budget allows.
- Long-term: consider replacing `fusion_node` with a Kalman filter library (robot_localization?) for better covariance handling.

---

## Dependency decisions

| Dependency | Why chosen |
|---|---|
| `rclpy` | Standard ROS2 Python client library |
| `tf2_ros` | ROS2-native TF handling, well integrated with rosbag |
| `numpy` | Required for all numerical fusion operations |
| `scipy` | Used for quaternion interpolation only — may be removed |
| `websockets` | Lightweight WebSocket server for viz_bridge |

Dependencies to avoid:
- No `rospy` (ROS1 only)
- No Flask/FastAPI in nodes (adds unnecessary HTTP overhead)
- No OpenCV in the core stack (only in optional perception addon)

---

## Known technical debt

- `sensor_bridge` uses a polling loop instead of interrupt-driven callbacks. Acceptable for now (sensor runs at 50 Hz), but should be replaced with a proper interrupt-based driver.
- Error handling in `controller` is minimal — it logs errors but does not attempt recovery. A proper safety monitor should be added before production use.
- No automated tests for the C++ nodes yet. Python nodes have pytest-based unit tests.
