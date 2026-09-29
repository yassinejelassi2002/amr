#!/usr/bin/env python3
"""Single-robot Gazebo navigation gateway for the web Live Map.

The browser uses acknowledged services, not unacknowledged goal topics.
Nav2 remains responsible for planning, collision avoidance and goal results.
"""
import json
import math

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from rclpy.time import Time
from action_msgs.msg import GoalStatus
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid
from std_msgs.msg import String
from std_srvs.srv import Trigger
from tf2_ros import Buffer, TransformListener, TransformException
from navigation_msgs.srv import SubmitNavigationGoal

from dashboard_navigation_math import cell_cost, map_to_world, world_to_map, yaw_of


BUSY = {'sending', 'navigating', 'canceling'}


class DashboardNavigation(Node):
    def __init__(self):
        super().__init__('dashboard_navigation')
        for name, value in (
            ('world_id', ''), ('base_frame', 'base_link'),
            ('world_offset_x', 0.0), ('world_offset_y', 0.0),
            ('world_offset_yaw', 0.0), ('occupied_threshold', 65),
        ):
            self.declare_parameter(name, value)
        self.world_id = self.get_parameter('world_id').value
        self.base_frame = self.get_parameter('base_frame').value
        self.offset = tuple(self.get_parameter(key).value for key in (
            'world_offset_x', 'world_offset_y', 'world_offset_yaw'))
        self.threshold = self.get_parameter('occupied_threshold').value
        self.tf = Buffer()
        self.listener = TransformListener(self.tf, self)
        self.nav = ActionClient(self, NavigateToPose, 'navigate_to_pose')
        self.costmap = None
        self.costmap_received = None
        self.handle = None
        self.cancel_requested = False
        self.phase = 'idle'
        self.detail = 'Waiting for a destination'
        self.request_id = ''
        self.target = None
        self.distance_remaining = None
        self.publisher = self.create_publisher(String, '/dashboard/navigation/state', 10)
        qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                         reliability=ReliabilityPolicy.RELIABLE)
        self.create_subscription(OccupancyGrid, '/global_costmap/costmap',
                                 self._on_costmap, qos)
        self.create_service(SubmitNavigationGoal, '/dashboard/navigation/submit',
                            self._submit)
        self.create_service(Trigger, '/dashboard/navigation/cancel', self._cancel)
        self.create_timer(0.25, self._publish)

    def _on_costmap(self, message):
        self.costmap = message
        self.costmap_received = self.get_clock().now()

    def _pose(self):
        try:
            transform = self.tf.lookup_transform('map', self.base_frame, Time())
            age = (self.get_clock().now() - Time.from_msg(transform.header.stamp)).nanoseconds / 1e9
            if not -0.5 <= age <= 2.0:
                return None
            t, q = transform.transform.translation, transform.transform.rotation
            x, y, yaw = map_to_world(t.x, t.y, yaw_of(q), self.offset)
            if not all(math.isfinite(v) for v in (x, y, yaw)):
                return None
            return {'x': x, 'y': y, 'yaw': yaw}
        except TransformException:
            return None

    def _unavailable(self, pose):
        if not self.get_parameter('use_sim_time').value:
            return 'Simulation mode required (use_sim_time:=true)'
        if not self.world_id:
            return 'Configure world_id to match the dashboard world'
        if not self.nav.server_is_ready():
            return 'Nav2 action server unavailable'
        if pose is None:
            return 'Waiting for a fresh map-to-robot transform; localize in RViz'
        if self.costmap is None or self.costmap.header.frame_id != 'map':
            return 'Waiting for the global costmap in map coordinates'
        age = (self.get_clock().now() - self.costmap_received).nanoseconds / 1e9
        if not 0 <= age <= 5:
            return 'Global costmap is stale'
        return ''

    def _publish(self):
        pose = self._pose()
        reason = self._unavailable(pose)
        payload = {
            'version': 1, 'world_id': self.world_id, 'robot_name': 'amr_x',
            'request_id': self.request_id, 'phase': self.phase,
            'detail': self.detail, 'ready': not reason,
            'unavailable_reason': reason, 'pose': pose, 'target': self.target,
            'distance_remaining': self.distance_remaining,
        }
        self.publisher.publish(String(data=json.dumps(payload, allow_nan=False)))

    def _set(self, phase, detail):
        self.phase, self.detail = phase, detail
        self._publish()

    def _submit(self, request, response):
        response.accepted = False
        if not request.request_id or len(request.request_id) > 128:
            response.message = 'A request ID of 1 to 128 characters is required'
            return response
        if request.request_id == self.request_id:
            response.message = 'Request already received; consult navigation state'
            return response
        if self.phase in BUSY:
            response.message = 'A goal is already active; cancel it first'
            return response
        if request.world_id != self.world_id:
            response.message = 'Selected world does not match the simulation'
            return response
        if not all(math.isfinite(v) for v in (request.x, request.y, request.yaw)):
            response.message = 'Destination must contain finite coordinates'
            return response
        reason = self._unavailable(self._pose())
        if reason:
            response.message = reason
            return response
        x, y, yaw = world_to_map(request.x, request.y, request.yaw, self.offset)
        cost = cell_cost(self.costmap, x, y)
        if cost < 0 or cost >= self.threshold:
            response.message = 'Destination is outside known free space or occupied'
            return response
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = 'map'
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = x
        goal.pose.pose.position.y = y
        goal.pose.pose.orientation.z = math.sin(yaw / 2)
        goal.pose.pose.orientation.w = math.cos(yaw / 2)
        self.request_id = request.request_id
        self.target = {'x': request.x, 'y': request.y, 'yaw': request.yaw}
        self.distance_remaining = None
        self.cancel_requested = False
        self._set('sending', 'Destination submitted to Nav2')
        try:
            future = self.nav.send_goal_async(goal, feedback_callback=self._feedback)
            future.add_done_callback(self._accepted)
        except Exception as error:
            self._set('failed', str(error))
            response.message = 'Could not submit destination to Nav2'
            return response
        response.accepted = True
        response.message = 'Request received; waiting for Nav2 acceptance'
        return response

    def _accepted(self, future):
        try:
            self.handle = future.result()
            if not self.handle.accepted:
                self.handle = None
                self._set('rejected', 'Nav2 rejected the destination')
                return
            self.handle.get_result_async().add_done_callback(self._result)
            if self.cancel_requested:
                self._request_cancel()
            else:
                self._set('navigating', 'Robot navigating to destination')
        except Exception as error:
            self.handle = None
            self._set('failed', str(error))

    def _feedback(self, message):
        distance = float(message.feedback.distance_remaining)
        self.distance_remaining = distance if math.isfinite(distance) else None

    def _result(self, future):
        try:
            status = future.result().status
            phase, detail = {
                GoalStatus.STATUS_SUCCEEDED: ('succeeded', 'Destination reached'),
                GoalStatus.STATUS_CANCELED: ('canceled', 'Navigation canceled'),
            }.get(status, ('failed', f'Nav2 ended with status {status}'))
        except Exception as error:
            phase, detail = 'failed', str(error)
        self.handle = None
        self.cancel_requested = False
        self._set(phase, detail)

    def _cancel(self, request, response):
        if self.phase not in BUSY:
            response.success, response.message = False, 'No active destination'
            return response
        if not self.cancel_requested:
            self.cancel_requested = True
            self._set('canceling', 'Cancellation requested; waiting for Nav2')
            if self.handle is not None:
                self._request_cancel()
        response.success, response.message = True, 'Cancellation requested'
        return response

    def _request_cancel(self):
        try:
            self.handle.cancel_goal_async().add_done_callback(self._cancel_response)
        except Exception as error:
            self.cancel_requested = False
            self._set('navigating', f'Cancellation failed: {error}')

    def _cancel_response(self, future):
        if self.phase not in BUSY:
            return  # A terminal result can arrive before the cancellation reply.
        try:
            if not future.result().goals_canceling:
                self.cancel_requested = False
                self._set('navigating', 'Nav2 did not accept cancellation; check robot state')
        except Exception as error:
            self.cancel_requested = False
            self._set('navigating', f'Cancellation failed: {error}')


def main():
    rclpy.init()
    node = DashboardNavigation()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
