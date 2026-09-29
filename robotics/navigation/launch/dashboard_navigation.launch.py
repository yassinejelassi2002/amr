"""Launch the single-robot web navigation gateway and optional rosbridge."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import AnyLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    arguments = [
        DeclareLaunchArgument('world_id', description='Exact SDF manifest world ID'),
        DeclareLaunchArgument('base_frame', default_value='base_link'),
        DeclareLaunchArgument('start_rosbridge', default_value='true'),
    ]
    params = {'use_sim_time': True}
    for name in ('world_id', 'base_frame'):
        params[name] = ParameterValue(LaunchConfiguration(name), value_type=str)
    for name in ('world_offset_x', 'world_offset_y', 'world_offset_yaw'):
        arguments.append(DeclareLaunchArgument(name, default_value='0.0'))
        params[name] = ParameterValue(LaunchConfiguration(name), value_type=float)
    return LaunchDescription(arguments + [
        Node(package='navigation', executable='dashboard_navigation_node.py',
             output='screen', parameters=[params]),
        IncludeLaunchDescription(
            AnyLaunchDescriptionSource(PathJoinSubstitution([
                FindPackageShare('rosbridge_server'), 'launch',
                'rosbridge_websocket_launch.xml',
            ])),
            condition=IfCondition(LaunchConfiguration('start_rosbridge')),
        ),
    ])
