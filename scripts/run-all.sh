#!/usr/bin/env bash
# Start the whole AMR-X Live Map demo on Ubuntu (warehouse, Gazebo window on):
#   Gazebo + robot -> Nav2 -> dashboard gateway + rosbridge -> backend -> frontend
# Usage: bash scripts/run-all.sh [rviz]     (Ctrl+C stops everything)
# Logs: .tmp/logs/*.log
set -uo pipefail

cd "$(dirname "$0")/.."
ROOT=$PWD
TOOLS=$HOME/.local/share/amrx-tools
RVIZ=false; [[ "${1:-}" == "rviz" ]] && RVIZ=true
LOGS=$ROOT/.tmp/logs; mkdir -p "$LOGS"

if [[ ! -f "$ROOT/install/setup.bash" ]]; then
  echo "Workspace not built. Run the build step in QUICKSTART_SIMULATION_DASHBOARD.md." >&2
  exit 1
fi
set +u
source /opt/ros/jazzy/setup.bash
source "$ROOT/install/setup.bash"
set -u

# Optional local tool folders (used when Node or rosbridge are not installed system-wide).
if [[ -d $TOOLS/node-v20.20.2/bin ]]; then export PATH=$TOOLS/node-v20.20.2/bin:$PATH; fi
RB=$TOOLS/rosbridge-jazzy/opt/ros/jazzy
if [[ -d $RB ]]; then
  export AMENT_PREFIX_PATH="$RB:$AMENT_PREFIX_PATH"
  export PYTHONPATH="$RB/lib/python3.12/site-packages:$ROOT/.venv/lib/python3.12/site-packages:$PYTHONPATH"
  export LD_LIBRARY_PATH="$RB/lib:${LD_LIBRARY_PATH:-}"
fi

missing=0
ros2 pkg prefix rosbridge_server >/dev/null 2>&1 || { echo "rosbridge_server not found: sudo apt install ros-jazzy-rosbridge-server" >&2; missing=1; }
command -v node >/dev/null 2>&1 || { echo "Node.js 20 not found (see QUICKSTART_SIMULATION_DASHBOARD.md)" >&2; missing=1; }
[[ -x "$ROOT/.venv/bin/python" && -d "$ROOT/dashboard_app/frontend/node_modules" ]] || { echo "Dashboard not set up: npm run setup:dashboard" >&2; missing=1; }
(( missing == 0 )) || exit 1

pids=()
cleanup() {
  trap - EXIT INT TERM
  echo; echo "Stopping everything..."
  for pid in "${pids[@]}"; do kill -INT -- "-$pid" 2>/dev/null; done
  sleep 5
  for pid in "${pids[@]}"; do kill -KILL -- "-$pid" 2>/dev/null; done
  echo "Stopped."
}
trap cleanup EXIT
trap 'exit 130' INT TERM

start() {  # start <name> <command...> : own process group, output to a log
  local name=$1; shift
  setsid "$@" > "$LOGS/$name.log" 2>&1 &
  pids+=($!)
  echo "  started $name (log: .tmp/logs/$name.log)"
}

wait_for() {  # wait_for <description> <timeout s> <test command...>
  local what=$1 timeout=$2; shift 2
  printf '  waiting for %s' "$what"
  for ((i = 0; i < timeout; i++)); do
    if "$@" >/dev/null 2>&1; then echo " ok"; return 0; fi
    printf '.'; sleep 1
  done
  echo " TIMEOUT - check the logs"; return 1
}

for port in 5173 8000 9090; do
  if ss -ltn | grep -q ":$port "; then
    echo "Port $port is already in use: stop the old run first." >&2; exit 1
  fi
done

echo "[1/5] Gazebo warehouse + robot"
start gazebo ros2 launch bringup simulation.launch.py \
  environment:=warehouse simulator_variant:=harmonic gui:=true rviz:=false
wait_for "/clock" 120 bash -c "timeout 3 ros2 topic echo /clock --once"

echo "[2/5] Nav2"
start nav2 ros2 launch navigation nav2.launch.py \
  map:="$ROOT/robotics/navigation/maps/warehouse_harmonic.yaml" \
  mission_server:=false rviz:=$RVIZ
wait_for "AMCL active" 120 bash -c "ros2 lifecycle get /amcl | grep -q active"

# warehouse_harmonic.yaml was recorded by SLAM from the spawn bay, so the map
# origin is the spawn pose (-1.2639, -3.9049) of the Gazebo world: the robot
# starts at map (0, 0) and the gateway needs that pose as its world offset.
WORLD_OFFSET_X=-1.2639
WORLD_OFFSET_Y=-3.9049
ros2 topic pub --once -w 1 /initialpose geometry_msgs/msg/PoseWithCovarianceStamped \
  "{header: {frame_id: map}, pose: {pose: {position: {x: 0.0, y: 0.0}, orientation: {w: 1.0}},
    covariance: [0.25,0,0,0,0,0, 0,0.25,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0.068]}}" \
  > "$LOGS/initialpose.log" 2>&1 && echo "  initial pose sent to AMCL"

echo "[3/5] Dashboard gateway + rosbridge (ws://localhost:9090)"
start gateway ros2 launch navigation dashboard_navigation.launch.py world_id:=warehouse-harmonic \
  world_offset_x:=$WORLD_OFFSET_X world_offset_y:=$WORLD_OFFSET_Y world_offset_yaw:=0.0
wait_for "gateway ready" 90 bash -c \
  "timeout 3 ros2 topic echo /dashboard/navigation/state --once --full-length | grep -q '\"ready\": true'"

echo "[4/5] Backend API (http://localhost:8000)"
start backend bash scripts/dashboard-backend.sh
wait_for "backend" 60 curl -sf -o /dev/null http://localhost:8000/docs

echo "[5/5] Frontend (http://localhost:5173)"
start frontend bash scripts/dashboard-frontend.sh
wait_for "frontend" 60 curl -sf -o /dev/null http://localhost:5173/

cat <<EOF

All running. Open http://localhost:5173/map
  - Demo off, world "warehouse-harmonic", then Choose on map -> Go to destination.
  - If the gateway was not ready: see .tmp/logs/gateway.log and nav2.log.
Press Ctrl+C here to stop everything.
EOF

wait -n "${pids[@]}"
echo "A component exited; see .tmp/logs/. Stopping the rest."
