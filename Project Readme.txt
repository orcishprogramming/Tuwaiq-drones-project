1: 

Open powershell

2: type wsl


3:open px4 and jmavsim using:

cd ~/PX4-Autopilot
make clean
LIBGL_ALWAYS_SOFTWARE=1 make px4_sitl jmavsim


4:open drone server in wsl terminal 2

cd /mnt/c/Users/p0a/OneDrive/Desktop/DronesProject
python3 -u wsl_drone_server.py

You should see:

✅ Drone is connected!

5: open terminal 3 Powershell

cd "C:\Users\p0a\OneDrive\Desktop\DronesProject"
py windows_voice_client.py

