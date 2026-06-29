import socket
import json
import threading
import time
from datetime import datetime

# ============================================
# CONFIGURATION
# ============================================
HOST = '0.0.0.0'  # Listen on all network interfaces
PORT = 5000
RESPAWN_TIME = 5  # seconds

# ============================================
# GAME STATE
# ============================================
players = {}  # {player_id: {health, ammo, active, score, conn}}
game_lock = threading.Lock()

# ============================================
# HANDLE CLIENT CONNECTION
# ============================================
def handle_client(conn, addr):
    print(f"[{timestamp()}] New connection from {addr}")
    
    try:
        while True:
            data = conn.recv(1024).decode().strip()
            if not data:
                break
            
            print(f"[{timestamp()}] Received: {data}")
            process_message(data, conn, addr)
            
    except Exception as e:
        print(f"[{timestamp()}] Error with {addr}: {e}")
    finally:
        # Clean up disconnected player
        with game_lock:
            for pid, pdata in list(players.items()):
                if pdata.get("conn") == conn:
                    print(f"[{timestamp()}] Player {pid} disconnected")
                    del players[pid]
        conn.close()

# ============================================
# PROCESS MESSAGES
# ============================================
def process_message(data, conn, addr):
    try:
        msg = json.loads(data)
        msg_type = msg.get("type")

        # INIT: Player joining game
        if msg_type == "INIT":
            pid = msg["player_id"]
            with game_lock:
                players[pid] = {
                    "health": 100,
                    "ammo": 30,
                    "active": True,
                    "score": 0,
                    "conn": conn,
                    "addr": addr
                }
            conn.sendall(b"INIT_OK\n")
            print(f"[{timestamp()}] Player {pid} initialized")
            broadcast_game_state()

        # HIT: Player hit another player
        elif msg_type == "HIT":
            source = msg["source_id"]
            target = msg["target_id"]
            
            with game_lock:
                if target in players and players[target]["active"]:
                    # Reduce target health
                    players[target]["health"] -= 20
                    
                    print(f"[{timestamp()}] {source} hit {target}! " +
                          f"Health: {players[target]['health']}")
                    
                    # Check if target is eliminated
                    if players[target]["health"] <= 0:
                        players[target]["active"] = False
                        players[target]["health"] = 0
                        
                        # Award points to shooter
                        if source in players:
                            players[source]["score"] += 100
                        
                        print(f"[{timestamp()}] {target} ELIMINATED by {source}!")
                        
                        # Notify target they're eliminated
                        target_conn = players[target]["conn"]
                        target_conn.sendall(b"ELIMINATED\n")
                        
                        # Start respawn timer
                        threading.Thread(
                            target=respawn_player, 
                            args=(target,),
                            daemon=True
                        ).start()
                    
                    conn.sendall(b"HIT_OK\n")
                    broadcast_game_state()

    except json.JSONDecodeError:
        print(f"[{timestamp()}] Invalid JSON from {addr}")
    except Exception as e:
        print(f"[{timestamp()}] Error processing message: {e}")

# ============================================
# RESPAWN PLAYER
# ============================================
def respawn_player(pid):
    print(f"[{timestamp()}] {pid} respawning in {RESPAWN_TIME} seconds...")
    time.sleep(RESPAWN_TIME)
    
    with game_lock:
        if pid in players:
            players[pid]["health"] = 100
            players[pid]["ammo"] = 30
            players[pid]["active"] = True
            
            # Notify player they respawned
            conn = players[pid]["conn"]
            conn.sendall(b"RESPAWN\n")
            
            print(f"[{timestamp()}] {pid} RESPAWNED")
            broadcast_game_state()

# ============================================
# BROADCAST GAME STATE
# ============================================
def broadcast_game_state():
    """Print current game state"""
    print(f"\n{'='*60}")
    print(f"[{timestamp()}] GAME STATE:")
    print(f"{'='*60}")
    
    with game_lock:
        for pid, data in players.items():
            status = "ACTIVE" if data["active"] else "DEAD"
            print(f"{pid}: Health={data['health']}, Ammo={data['ammo']}, "
                  f"Score={data['score']}, Status={status}")
    
    print(f"{'='*60}\n")

# ============================================
# START SERVER
# ============================================
def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(10)
    
    print(f"\n{'='*60}")
    print(f"LASER TAG SERVER RUNNING")
    print(f"{'='*60}")
    print(f"Host: {HOST}")
    print(f"Port: {PORT}")
    print(f"Time: {timestamp()}")
    print(f"{'='*60}\n")
    print("Waiting for players to connect...\n")
    
    try:
        while True:
            conn, addr = server.accept()
            threading.Thread(
                target=handle_client, 
                args=(conn, addr),
                daemon=True
            ).start()
    except KeyboardInterrupt:
        print(f"\n[{timestamp()}] Server shutting down...")
        server.close()

# ============================================
# HELPER FUNCTIONS
# ============================================
def timestamp():
    return datetime.now().strftime("%H:%M:%S")

# ============================================
# MAIN
# ============================================
if __name__ == "__main__":
    start_server()
