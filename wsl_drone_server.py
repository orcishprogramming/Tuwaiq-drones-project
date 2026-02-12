#!/usr/bin/env python3
import asyncio
import math
from mavsdk import System
from mavsdk.mission import MissionItem, MissionPlan

# TCP server (your client connects here)
HOST = "0.0.0.0"
PORT = 9999

# MAVSDK connection to PX4
# Common for PX4 SITL: udp://:14540
# If your PX4 is elsewhere, change it (example: "udp://192.168.x.x:14540")
PX4_SYSTEM_ADDRESS = "udp://:14540"

def build_square_mission(lat, lon, alt=5.0, side_m=10.0, speed_m_s=5.0):
    """
    Build a simple square mission around (lat, lon).
    NOTE: Requires Global Position + Home position to be OK in PX4.
    """
    dlat = side_m / 1.11e5
    # protect against cos(lat)=0 near poles
    dlon = side_m / (1.11e5 * max(0.2, abs(math.cos(math.radians(lat)))))

    items = [
        MissionItem(
            lat + dlat, lon, alt, speed_m_s, True,
            float("nan"), float("nan"),
            MissionItem.CameraAction.NONE,
            float("nan"), float("nan"),
            float("nan"), float("nan"), float("nan"),
            MissionItem.VehicleAction.NONE,
        ),
        MissionItem(
            lat + dlat, lon + dlon, alt, speed_m_s, True,
            float("nan"), float("nan"),
            MissionItem.CameraAction.NONE,
            float("nan"), float("nan"),
            float("nan"), float("nan"), float("nan"),
            MissionItem.VehicleAction.NONE,
        ),
        MissionItem(
            lat, lon + dlon, alt, speed_m_s, True,
            float("nan"), float("nan"),
            MissionItem.CameraAction.NONE,
            float("nan"), float("nan"),
            float("nan"), float("nan"), float("nan"),
            MissionItem.VehicleAction.NONE,
        ),
        MissionItem(
            lat, lon, alt, speed_m_s, True,
            float("nan"), float("nan"),
            MissionItem.CameraAction.NONE,
            float("nan"), float("nan"),
            float("nan"), float("nan"), float("nan"),
            MissionItem.VehicleAction.NONE,
        ),
    ]
    return MissionPlan(items)

async def wait_connected(drone: System, timeout_s: float = 15.0):
    print("Waiting for MAVSDK connection_state() ...", flush=True)

    async def _wait():
        async for state in drone.core.connection_state():
            if state.is_connected:
                return True
        return False

    return await asyncio.wait_for(_wait(), timeout=timeout_s)

async def wait_health_ok(drone: System, timeout_s: float = 30.0):
    """
    Wait for global position and home position. In SITL, this should become OK.
    """
    print("Waiting for telemetry health (global/home position)...", flush=True)

    async def _wait():
        async for health in drone.telemetry.health():
            if health.is_global_position_ok and health.is_home_position_ok:
                return health
        return None

    return await asyncio.wait_for(_wait(), timeout=timeout_s)

async def get_home(drone: System, timeout_s: float = 10.0):
    """
    Get home location from telemetry.home().
    """
    print("Fetching home position...", flush=True)

    async def _wait():
        async for home in drone.telemetry.home():
            if abs(home.latitude_deg) > 0.0001 and abs(home.longitude_deg) > 0.0001:
                return home
        return None

    return await asyncio.wait_for(_wait(), timeout=timeout_s)

async def safe_write(writer: asyncio.StreamWriter, msg: str):
    writer.write(msg.encode("utf-8"))
    await writer.drain()

async def handle_client(reader, writer, drone, state):
    addr = writer.get_extra_info("peername")
    print(f"Client connected: {addr}", flush=True)
    await safe_write(writer, "OK connected to server\n")

    try:
        while True:
            line = await reader.readline()
            if not line:
                break

            cmd = line.decode().strip().lower()
            print(f"CMD: {cmd}", flush=True)

            if cmd in ("takeoff", "take off"):
                try:
                    await drone.action.arm()
                    await asyncio.sleep(1)
                    await drone.action.takeoff()
                    state["flying"] = True
                    await safe_write(writer, "OK takeoff\n")
                except Exception as e:
                    await safe_write(writer, f"ERR {e}\n")

            elif cmd == "mission":
                try:
                    if not state["flying"]:
                        await safe_write(writer, "ERR not flying\n")
                        continue

                    home = await get_home(drone)
                    plan = build_square_mission(home.latitude_deg, home.longitude_deg)

                    # Clear any old mission before uploading a new one (helps with retries)
                    try:
                        await drone.mission.clear_mission()
                        await asyncio.sleep(0.3)
                    except Exception:
                        pass

                    await drone.mission.upload_mission(plan)
                    await asyncio.sleep(0.5)
                    await drone.mission.start_mission()

                    await safe_write(writer, "OK mission started\n")
                except Exception as e:
                    await safe_write(writer, f"ERR {e}\n")

            elif cmd == "land":
                try:
                    await drone.action.land()
                    state["flying"] = False
                    await safe_write(writer, "OK land\n")
                except Exception as e:
                    await safe_write(writer, f"ERR {e}\n")

            elif cmd == "status":
                try:
                    # minimal status
                    async for state_conn in drone.core.connection_state():
                        conn = state_conn.is_connected
                        break
                    await safe_write(writer, f"OK connected={conn} flying={state['flying']}\n")
                except Exception as e:
                    await safe_write(writer, f"ERR {e}\n")

            elif cmd == "stop":
                await safe_write(writer, "OK stop\n")
                break

            else:
                await safe_write(writer, "IGNORED\n")

    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        print(f"Client disconnected: {addr}", flush=True)

async def main():
    print("Starting MAVSDK + TCP server...", flush=True)

    state = {"flying": False}

    drone = System()

    print(f"Connecting to PX4 via: {PX4_SYSTEM_ADDRESS}", flush=True)
    await drone.connect(system_address=PX4_SYSTEM_ADDRESS)

    try:
        await wait_connected(drone, timeout_s=20.0)
        print("✅ Drone is connected!", flush=True)
    except asyncio.TimeoutError:
        print("❌ Timeout waiting for drone connection.", flush=True)
        print("   Likely MAVLink packets are not reaching WSL on udp://:14540", flush=True)
        print("   Try tcpdump: sudo tcpdump -n udp port 14540", flush=True)
        return

    # Make mission upload reliable
    try:
        await wait_health_ok(drone, timeout_s=45.0)
        print("✅ Health OK: global position & home position are ready.", flush=True)
    except asyncio.TimeoutError:
        print("⚠️ Health not OK yet (global/home). Mission may fail.", flush=True)
        print("   In SITL this should become OK; in real drone ensure GPS/home are set.", flush=True)

    # Start TCP server
    server = await asyncio.start_server(
        lambda r, w: handle_client(r, w, drone, state),
        host=HOST,
        port=PORT,
    )

    addrs = ", ".join(str(sock.getsockname()) for sock in server.sockets)
    print(f"✅ Server listening on {addrs}", flush=True)
    print("Commands: takeoff | mission | land | status | stop", flush=True)

    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped by user.", flush=True)