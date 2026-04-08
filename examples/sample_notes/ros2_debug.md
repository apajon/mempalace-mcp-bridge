# ROS2 Debug Notes

## Issue — Node not receiving messages from topic /scan

**Date:** 2024-02-20

**Symptom:** `ros2 topic echo /scan` shows data, but the subscriber node never calls the callback.

**Investigation:**

```bash
ros2 topic info /scan --verbose
# QoS profile: BEST_EFFORT, VOLATILE
```

Node was configured with default QoS (RELIABLE, VOLATILE). Mismatched QoS prevents message delivery.

**Fix:**

```python
from rclpy.qos import QoSProfile, ReliabilityPolicy

qos = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    depth=10
)
self.sub = self.create_subscription(LaserScan, '/scan', self.callback, qos)
```

**Lesson:** Always check QoS compatibility when a subscriber receives nothing. Use `ros2 topic info --verbose` to inspect publisher QoS.

---

## Issue — TF lookup fails intermittently during startup

**Date:** 2024-03-05

**Symptom:** `tf2.LookupException: "base_link" passed to lookupTransform argument target_frame does not exist.` — only during the first few seconds after launch.

**Cause:** The node was performing TF lookups before the TF tree was fully populated. Static transforms from `robot_state_publisher` take a short time to propagate.

**Fix:** Wrap TF lookups in a try/except and retry with a timer:

```python
def on_timer(self):
    try:
        t = self.tf_buffer.lookup_transform('map', 'base_link', rclpy.time.Time())
        self.process_transform(t)
    except tf2_ros.LookupException:
        self.get_logger().warn('TF not yet available, retrying...')
    except tf2_ros.ExtrapolationException as e:
        self.get_logger().error(f'TF extrapolation error: {e}')
```

---

## Issue — High latency on /odom topic with bag replay

**Date:** 2024-03-18

**Symptom:** When replaying a bag file, the odometry pipeline lags 2–3 seconds behind real time. Live operation is fine.

**Investigation:**
- Bag replay publishes at wall clock rate, not simulation time
- `use_sim_time` was set to `true` on some nodes but not all

**Fix:** Either:
1. Set `use_sim_time: false` for all nodes when replaying bags without a clock source
2. Or add `--clock` to `ros2 bag play` to publish a `/clock` topic

```bash
ros2 bag play my_bag.db3 --clock
```

---

## Issue — Parameter file not loaded on launch

**Date:** 2024-04-01

**Symptom:** Node starts with default parameters despite a `params.yaml` file being passed to the launch file.

**Investigation:** Parameter file path was relative. The launch file was called from a different working directory.

**Fix:** Always use absolute paths or `os.path.join(get_package_share_directory(...), 'config', 'params.yaml')` in launch files.

```python
import os
from ament_index_python.packages import get_package_share_directory

params_file = os.path.join(
    get_package_share_directory('my_package'),
    'config',
    'params.yaml'
)
```

---

## Useful diagnostic commands

```bash
# Check active nodes
ros2 node list

# Inspect a node's parameters
ros2 param list /my_node
ros2 param get /my_node some_param

# Verify TF tree
ros2 run tf2_tools view_frames

# Check topic Hz and latency
ros2 topic hz /scan
ros2 topic delay /scan

# Check for QoS mismatches
ros2 topic info /scan --verbose
```
