#!/usr/bin/env python3
"""Echo commanded joint positions back as JointState.

joint_trajectory_controller normally consumes <controller>/joint_trajectory and
the joint state broadcaster reports the result on /joint_states. Both live in
controller_manager, which crashes on Windows, so the control panel's commands
move nothing. Feed the commands straight back so the model follows them.

Open loop: positions are echoed as requested, with no dynamics and no hardware.
Pair with joint_state_publisher's source_list, which fills in the other joints.
"""

from __future__ import annotations

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from trajectory_msgs.msg import JointTrajectory

OUTPUT_TOPIC = '/lucy/commanded_joint_states'
COMMAND_SUFFIX = '/joint_trajectory'
COMMAND_TYPE = 'trajectory_msgs/msg/JointTrajectory'
PUBLISH_HZ = 30.0
DISCOVER_PERIOD_S = 2.0


class _Motion:
    """A joint ramping from where it was to what was asked, over the goal's duration."""

    __slots__ = ('start', 'target', 'started_at', 'duration')

    def __init__(self, start: float, target: float, started_at: float, duration: float):
        self.start = start
        self.target = target
        self.started_at = started_at
        self.duration = duration

    def value_at(self, now: float) -> float:
        if self.duration <= 0.0:
            return self.target
        ratio = (now - self.started_at) / self.duration
        if ratio >= 1.0:
            return self.target
        return self.start + (self.target - self.start) * ratio


class JointCommandEcho(Node):
    def __init__(self) -> None:
        super().__init__('lucy_joint_command_echo')
        self._motions: dict[str, _Motion] = {}
        self._subscriptions_by_topic: dict = {}
        self._pub = self.create_publisher(JointState, OUTPUT_TOPIC, 10)
        self.create_timer(DISCOVER_PERIOD_S, self._discover)
        self.create_timer(1.0 / PUBLISH_HZ, self._publish)
        self._discover()

    def _now(self) -> float:
        return self.get_clock().now().nanoseconds / 1e9

    def _discover(self) -> None:
        """Controllers come and go with the robot package, so poll for them."""
        for topic, types in self.get_topic_names_and_types():
            if topic in self._subscriptions_by_topic:
                continue
            if topic.endswith(COMMAND_SUFFIX) and COMMAND_TYPE in types:
                self._subscriptions_by_topic[topic] = self.create_subscription(
                    JointTrajectory, topic, self._on_trajectory, 10
                )
                self.get_logger().info(f'following {topic}')

    def _on_trajectory(self, msg: JointTrajectory) -> None:
        if not msg.points:
            return
        point = msg.points[-1]
        # Honour time_from_start so motion looks like a controller executing a
        # goal rather than the joint teleporting to its target.
        duration = point.time_from_start.sec + point.time_from_start.nanosec / 1e9
        now = self._now()
        for index, name in enumerate(msg.joint_names):
            if index >= len(point.positions):
                continue
            target = float(point.positions[index])
            current = self._motions[name].value_at(now) if name in self._motions else target
            self._motions[name] = _Motion(current, target, now, max(duration, 0.0))

    def _publish(self) -> None:
        if not self._motions:
            return
        now = self._now()
        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.name = list(self._motions)
        msg.position = [self._motions[name].value_at(now) for name in msg.name]
        self._pub.publish(msg)


def main() -> None:
    rclpy.init()
    node = JointCommandEcho()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
