"""ROS-independent coordinate and occupancy helpers for dashboard navigation."""
import math


def yaw_of(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y),
                      1 - 2 * (q.y * q.y + q.z * q.z))


def map_to_world(x, y, yaw, offset):
    """offset is the pose of the map origin in the SDF world."""
    dx, dy, angle = offset
    c, s = math.cos(angle), math.sin(angle)
    return dx + c * x - s * y, dy + s * x + c * y, yaw + angle


def world_to_map(x, y, yaw, offset):
    dx, dy, angle = offset
    c, s = math.cos(angle), math.sin(angle)
    x, y = x - dx, y - dy
    return c * x + s * y, -s * x + c * y, yaw - angle


def cell_cost(grid, x, y):
    info = grid.info
    if info.resolution <= 0:
        return -1
    origin = info.origin
    gx, gy, _ = world_to_map(x, y, 0, (
        origin.position.x, origin.position.y, yaw_of(origin.orientation)))
    # floor, not int: a point just outside a negative boundary is outside.
    mx, my = math.floor(gx / info.resolution), math.floor(gy / info.resolution)
    if not (0 <= mx < info.width and 0 <= my < info.height):
        return -1
    index = my * info.width + mx
    return grid.data[index] if index < len(grid.data) else -1
