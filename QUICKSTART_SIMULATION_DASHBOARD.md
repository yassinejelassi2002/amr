# Quickstart: Gazebo simulation + web dashboard

This guide takes a fresh Ubuntu machine to the point where you see the AMR-X robot in
the Gazebo window **and** on the dashboard's Live Map, and can send it to a destination
from the browser.

What runs in the end:

```
Gazebo (robot in the warehouse) -> Nav2 (navigation) -> dashboard_navigation gateway
  + rosbridge (ws://localhost:9090) -> backend API (:8000) -> dashboard in the browser (:5173)
```

## 1. Requirements

- **Ubuntu 24.04** (desktop, so the Gazebo window can open).
- **ROS 2 Jazzy**, installed following the official guide:
  <https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html>
  (`ros-jazzy-desktop`).

Then install the extra packages used by the simulation, navigation and dashboard:

```bash
sudo apt update
sudo apt install -y git python3-venv python3-colcon-common-extensions python3-rosdep \
  ros-jazzy-ros-gz ros-jazzy-navigation2 ros-jazzy-nav2-bringup ros-jazzy-rosbridge-server
```

`ros-jazzy-ros-gz` installs Gazebo Harmonic together with the ROS bridge.

**Node.js 20** (for the dashboard frontend), for example with nvm:

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.bashrc
nvm install 20
node -v   # v20.x
```

## 2. Clone

```bash
git clone https://github.com/yassinejelassi2002/amr.git
cd amr
```

Until the pull request is merged into `main`, switch to the branch that contains the
dashboard navigation work:

```bash
git switch feat/dashboard-navigation-ubuntu-validation
```

All the commands below are run **from this `amr` folder**.

## 3. Build the ROS 2 packages

Only the packages needed for this demo are built (the arm / MoveIt packages are skipped):

```bash
source /opt/ros/jazzy/setup.bash
sudo rosdep init 2>/dev/null; rosdep update
rosdep install --ignore-src -r -y --from-paths robotics/bringup robotics/control \
  robotics/navigation robotics/navigation_msgs robotics/robot_description robotics/simulation
colcon build --symlink-install --packages-up-to bringup navigation
```

This creates `build/`, `install/` and `log/` in the repository folder (they are git-ignored).

## 4. Set up the dashboard

```bash
npm run setup:dashboard
```

This creates the Python environment `.venv`, installs the backend and frontend
dependencies, and creates the `.env` configuration file from `.env.example`.

**Database.** By default `.env` points to a PostgreSQL database started with Docker.
Choose one option:

- **With Docker:** `npm run dashboard:db` (starts PostgreSQL in the background).
- **Without Docker (simplest):** use a local SQLite file. Edit `.env` and replace the
  `DATABASE_URL=...` line with:

  ```
  DATABASE_URL=sqlite:///./dashboard.sqlite3
  ```

  The file is created automatically in `dashboard_app/backend/` at first start.

## 5. Launch everything

```bash
bash scripts/run-all.sh
```

Add `rviz` to also open RViz: `bash scripts/run-all.sh rviz`.

The script starts, in order and waiting for each one to be ready:

1. Gazebo with the warehouse and the robot (**the Gazebo window opens**),
2. Nav2, then sets the robot's initial position for localization,
3. the navigation gateway and rosbridge,
4. the backend API,
5. the dashboard frontend.

The first start of Gazebo can take a minute (models are loaded). When you see
**`All running`**, everything is up. Logs are in `.tmp/logs/`.

**Stop everything with `Ctrl+C`** in that terminal.

## 6. Open the dashboard and move the robot

1. Open <http://localhost:5173> and click **Register**. The **first** account created
   becomes the administrator and is approved automatically. Log in.
2. Open **Live map** in the left menu.
3. Turn **Demo** off and select the world **warehouse-harmonic**.
4. The robot `amr_x` appears on the map at its real position. If it does not, go to
   **Settings → Robot connection**, set `ws://localhost:9090` and save.
5. In the navigation panel, click **Choose on map** and click a free spot near the robot
   (or type X, Y and a heading), then **Go to destination**.

You should see the robot drive in the Gazebo window and, at the same time, on the Live
Map. The panel shows *Navigating*, the remaining distance, then **Destination reached**.
**Cancel navigation** stops it on the way.

## Troubleshooting

| Symptom | What to do |
|---|---|
| `Port 5173/8000/9090 is already in use` | A previous run is still active: stop it with `Ctrl+C` in its terminal. |
| `rosbridge_server not found` | `sudo apt install ros-jazzy-rosbridge-server` |
| `Dashboard not set up` | Run `npm run setup:dashboard` (step 4). |
| `Workspace not built` | Run the build (step 3). |
| A step prints `TIMEOUT` | Open the matching log in `.tmp/logs/` (`gazebo.log`, `nav2.log`, `gateway.log`, `backend.log`, `frontend.log`). |
| Backend fails to start | Check `DATABASE_URL` in `.env` (step 4): Docker running, or the SQLite line. |
| Robot not shown on the Live Map | Demo must be off, world must be `warehouse-harmonic`, Settings URL `ws://localhost:9090`. |
| Destination refused | The panel explains why: occupied cell, outside the map, wrong world, or a goal is already active. |

## Useful checks (optional)

In a new terminal, from the `amr` folder:

```bash
source /opt/ros/jazzy/setup.bash && source install/setup.bash
ros2 topic echo /dashboard/navigation/state --once   # "ready": true when everything is up
```

Only use `scripts/run-all.sh` to launch this demo: it passes the calibrated offset between
the Nav2 map and the Gazebo world. Launching the pieces by hand without it shows the robot
about 4 m away from its real position.
