
#!/usr/bin/env python3
"""
ESP32-S3 Laser Tag Server - FIXED VERSION
- Auto-starts game immediately
- Ctrl+C works properly
- No console input issues
"""

import socket
import json
import threading
import time
from datetime import datetime
import sys
import select
import signal

# ============ Configuration ============
HOST = '0.0.0.0'
PORT = 5000
RESPAWN_TIME = 5
MAX_PLAYERS = 20
DAMAGE_PER_HIT = 10
AUTO_START = True  # Game starts immediately!

# ============ Global Shutdown Flag ============
shutdown_flag = False

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    global shutdown_flag
    print("\n\n[SHUTDOWN] Ctrl+C detected, shutting down server...")
    shutdown_flag = True
    sys.exit(0)

# Register the signal handler
signal.signal(signal.SIGINT, signal_handler)

# ============ Game State ============
class GameState:
    def __init__(self):
        self.players = {}
        self.game_active = AUTO_START
        self.game_start_time = time.time() if AUTO_START else None
        self.lock = threading.Lock()
        self.connections = {}

    def add_player(self, player_id, team_id=1):
        with self.lock:
            self.players[player_id] = {
                "health": 100,
                "ammo": 30,
                "active": True,
                "score": 0,
                "kills": 0,
                "deaths": 0,
                "team_id": team_id,
                "connected_at": time.time(),
                "last_heartbeat": time.time()
            }
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Player {player_id} joined (Team {team_id})")
            return True

    def remove_player(self, player_id):
        with self.lock:
            if player_id in self.players:
                del self.players[player_id]
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Player {player_id} disconnected")

    def get_player(self, player_id):
        with self.lock:
            return self.players.get(player_id)

    def update_player(self, player_id, updates):
        with self.lock:
            if player_id in self.players:
                self.players[player_id].update(updates)

    def get_all_players(self):
        with self.lock:
            return dict(self.players)

    def print_scoreboard(self):
        with self.lock:
            print("\n" + "="*60)
            print("SCOREBOARD")
            print("="*60)
            if not self.players:
                print("No players")
                print("="*60 + "\n")
                return
                
            sorted_players = sorted(
                self.players.items(),
                key=lambda x: x[1]["score"],
                reverse=True
            )
            print(f"{'Rank':<6} {'Player':<12} {'Score':<8} {'K/D':<12} {'Team':<6}")
            print("-"*60)
            for i, (player_id, data) in enumerate(sorted_players, 1):
                kd_ratio = f"{data['kills']}/{data['deaths']}"
                print(f"{i:<6} {player_id:<12} {data['score']:<8} {kd_ratio:<12} {data['team_id']:<6}")
            print("="*60 + "\n")

game_state = GameState()

# ============ Client Handler ============
def handle_client(conn, addr):
    global shutdown_flag
    client_id = f"{addr[0]}:{addr[1]}"
    player_id = None

    print(f"[{datetime.now().strftime('%H:%M:%S')}] New connection from {client_id}")

    conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    conn.setblocking(False)

    buffer = ""

    try:
        while not shutdown_flag:
            ready = select.select([conn], [], [], 1.0)

            if ready[0]:
                try:
                    chunk = conn.recv(2048).decode('utf-8')

                    if not chunk:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Socket closed by client {client_id}")
                        break

                    buffer += chunk

                    while '\n' in buffer:
                        message, buffer = buffer.split('\n', 1)
                        message = message.strip()

                        if message:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] Received {message[:50]}...")
                            player_id = process_message(message, conn, player_id)

                except BlockingIOError:
                    continue
                except Exception as e:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Recv error: {e}")
                    break

            if player_id:
                player = game_state.get_player(player_id)
                if player and (time.time() - player["last_heartbeat"] > 30):
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Player {player_id} timed out")
                    break

    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Error handling {client_id}: {e}")

    finally:
        if player_id:
            game_state.remove_player(player_id)
            if player_id in game_state.connections:
                del game_state.connections[player_id]

        try:
            conn.close()
        except:
            pass
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Connection closed: {client_id}")

# ============ Message Processing ============
def process_message(data, conn, current_player_id):
    try:
        msg = json.loads(data)
        msg_type = msg.get("type")

        if msg_type == "INIT":
            player_id = msg.get("player_id")
            team_id = msg.get("team_id", 1)

            if len(game_state.players) >= MAX_PLAYERS:
                send_message(conn, {"type": "ERROR", "message": "Server full"})
                return current_player_id

            game_state.add_player(player_id, team_id)
            game_state.connections[player_id] = conn

            response = {
                "type": "INIT_OK",
                "player_id": player_id,
                "max_players": MAX_PLAYERS,
                "current_players": len(game_state.players)
            }
            send_message(conn, response)

            if game_state.game_active:
                send_message(conn, {"type": "GAME_START"})

            return player_id

        elif msg_type == "HIT":
            source_id = msg.get("source_id")
            target_id = msg.get("target_id")

            source = game_state.get_player(source_id)
            target = game_state.get_player(target_id)

            if not source or not target:
                send_message(conn, {"type": "ERROR", "message": "Invalid player"})
                return current_player_id

            if not target["active"]:
                send_message(conn, {"type": "ERROR", "message": "Target not active"})
                return current_player_id

            if source["team_id"] == target["team_id"]:
                send_message(conn, {"type": "ERROR", "message": "Friendly fire disabled"})
                return current_player_id

            new_health = target["health"] - 10
            game_state.update_player(target_id, {"health": new_health})

            send_message(conn, {"type": "HIT_OK", "target_id": target_id, "damage": 10})

            if target_id in game_state.connections:
                send_message(game_state.connections[target_id], {
                    "type": "HIT_RECEIVED",
                    "source_id": source_id,
                    "damage": 10,
                    "new_health": max(0, new_health)
                })

            if new_health <= 0:
                handle_elimination(source_id, target_id)

            return current_player_id

        elif msg_type == "STATE_UPDATE":
            player_id = msg.get("player_id")
            if player_id:
                updates = {
                    "health": msg.get("health"),
                    "ammo": msg.get("ammo"),
                    "score": msg.get("score"),
                    "active": msg.get("active"),
                    "last_heartbeat": time.time()
                }
                game_state.update_player(player_id, updates)
            return current_player_id

        elif msg_type == "REQUEST_RELOAD":
            player_id = msg.get("player_id")
            if player_id:
                game_state.update_player(player_id, {"ammo": 30})
                send_message(conn, {"type": "RELOAD"})
            return current_player_id

        return current_player_id

    except json.JSONDecodeError as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] JSON error: {e}")
        return current_player_id
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Processing error: {e}")
        return current_player_id

# ============ Game Logic ============
def handle_elimination(killer_id, victim_id):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {killer_id} eliminated {victim_id}!")

    game_state.update_player(killer_id, {
        "score": game_state.get_player(killer_id)["score"] + 100,
        "kills": game_state.get_player(killer_id)["kills"] + 1
    })

    game_state.update_player(victim_id, {
        "active": False,
        "deaths": game_state.get_player(victim_id)["deaths"] + 1
    })

    threading.Thread(target=respawn_player, args=(victim_id,), daemon=True).start()

def respawn_player(player_id):
    time.sleep(RESPAWN_TIME)

    player = game_state.get_player(player_id)
    if player and not player["active"]:
        game_state.update_player(player_id, {
            "health": 100,
            "ammo": 30,
            "active": True
        })

        if player_id in game_state.connections:
            send_message(game_state.connections[player_id], {"type": "RESPAWN"})

        print(f"[{datetime.now().strftime('%H:%M:%S')}] {player_id} respawned")

# ============ Utility Functions ============
def send_message(conn, message):
    try:
        json_msg = json.dumps(message) + '\n'
        conn.sendall(json_msg.encode('utf-8'))
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Sent: {message['type']}")
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Send error: {e}")

def broadcast_message(message):
    for player_id, conn in list(game_state.connections.items()):
        send_message(conn, message)

def monitor_connections():
    global shutdown_flag
    while not shutdown_flag:
        time.sleep(10)
        current_time = time.time()

        disconnected = []
        for player_id, player in game_state.get_all_players().items():
            if current_time - player["last_heartbeat"] > 30:
                disconnected.append(player_id)

        for player_id in disconnected:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Removing inactive player: {player_id}")
            game_state.remove_player(player_id)
            if player_id in game_state.connections:
                try:
                    game_state.connections[player_id].close()
                except:
                    pass
                del game_state.connections[player_id]

def status_display():
    global shutdown_flag
    while not shutdown_flag:
        time.sleep(5)
        players = game_state.get_all_players()
        if players:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] === Server Status ===")
            print(f"Active Players: {len(players)}")
            print(f"Game Active: {game_state.game_active}")
            for player_id, data in players.items():
                status = "ACTIVE" if data["active"] else "DEAD"
                print(f"  {player_id}: HP={data['health']}, Ammo={data['ammo']}, Score={data['score']} [{status}]")
            print("=" * 40 + "\n")

# ============ Server Start ============
def start_server():
    global shutdown_flag
    
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.settimeout(1.0)  # Add timeout so Ctrl+C works

    try:
        server.bind((HOST, PORT))
        server.listen(10)
        
        print(f"\n{'='*60}")
        print(f"ESP32 Laser Tag Server - READY!")
        print(f"{'='*60}")
        print(f"Host: {HOST}:{PORT}")
        print(f"Max Players: {MAX_PLAYERS}")
        print(f"Damage per Hit: {DAMAGE_PER_HIT}")
        print(f"Respawn Time: {RESPAWN_TIME}s")
        if AUTO_START:
            print(f"GAME IS ACTIVE - Players can play immediately!")
        print(f"{'='*60}")
        print(f"\nPress Ctrl+C to stop the server\n")

        # Start monitoring threads
        threading.Thread(target=monitor_connections, daemon=True).start()
        threading.Thread(target=status_display, daemon=True).start()

        while not shutdown_flag:
            try:
                conn, addr = server.accept()
                client_thread = threading.Thread(
                    target=handle_client,
                    args=(conn, addr),
                    daemon=True
                )
                client_thread.start()
            except socket.timeout:
                continue
            except Exception as e:
                if not shutdown_flag:
                    print(f"Error accepting connection: {e}")

    except KeyboardInterrupt:
        print("\n\n[SHUTDOWN] Keyboard interrupt detected")
    except Exception as e:
        print(f"\n[ERROR] Server error: {e}")
    finally:
        shutdown_flag = True
        print("\n[SHUTDOWN] Closing all connections...")
        
        # Show final scoreboard
        if game_state.players:
            game_state.print_scoreboard()
        
        # Close all client connections
        for player_id, conn in list(game_state.connections.items()):
            try:
                conn.close()
            except:
                pass
        
        server.close()
        print("[SHUTDOWN] Server stopped.\n")

if __name__ == "__main__":
    print("Starting ESP32 Laser Tag Server...")
    print("(This may take a moment...)\n")
    start_server()

