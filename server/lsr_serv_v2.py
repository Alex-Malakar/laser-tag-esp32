"""
ESP32-S3 Laser Tag Server - VERSION 2
Fixed: Connection staying alive after INIT_OK
"""

import socket
import json
import threading
import time
from datetime import datetime
from collections import defaultdict
import sys
import select

# ============ Configuration ============
HOST = '0.0.0.0'
PORT = 5000
RESPAWN_TIME = 5  # seconds
MAX_PLAYERS = 20
DAMAGE_PER_HIT = 10
GAME_TIME_LIMIT = 600  # 10 minutes

# ============ Game State ============
class GameState:
    def __init__(self):
        self.players = {}  # {player_id: PlayerData}
        self.game_active = False
        self.game_start_time = None
        self.lock = threading.Lock()
        self.connections = {}  # {player_id: connection}

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

    def start_game(self):
        with self.lock:
            self.game_active = True
            self.game_start_time = time.time()
            # Reset all players
            for player_id in self.players:
                self.players[player_id].update({
                    "health": 100,
                    "ammo": 30,
                    "active": True,
                    "score": 0,
                    "kills": 0,
                    "deaths": 0
                })
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Game started!")

    def end_game(self):
        with self.lock:
            self.game_active = False
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Game ended!")
            self.print_scoreboard()

    def print_scoreboard(self):
        with self.lock:
            print("\n" + "="*60)
            print("FINAL SCOREBOARD")
            print("="*60)
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
    """Handle individual client connections"""
    client_id = f"{addr[0]}:{addr[1]}"
    player_id = None

    print(f"[{datetime.now().strftime('%H:%M:%S')}] New connection from {client_id}")

    # Set socket options
    conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    # Set non-blocking mode to use select()
    conn.setblocking(False)

    buffer = ""

    try:
        while True:
            # Use select to wait for data with timeout
            ready = select.select([conn], [], [], 1.0)

            if ready[0]:
                try:
                    chunk = conn.recv(2048).decode('utf-8')

                    if not chunk:
                        # Empty recv means socket closed
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Socket closed by client {client_id}")
                        break

                    buffer += chunk

                    # Process complete messages
                    while '\n' in buffer:
                        message, buffer = buffer.split('\n', 1)
                        message = message.strip()

                        if message:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] Received {message[:50]}...")
                            player_id = process_message(message, conn, player_id)

                except BlockingIOError:
                    # No data available right now, continue
                    continue
                except Exception as e:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Recv error from {client_id}: {e}")
                    break

            # Check if player has timed out (no heartbeat for 30 seconds)
            if player_id:
                player = game_state.get_player(player_id)
                if player and (time.time() - player["last_heartbeat"] > 30):
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Player {player_id} timed out")
                    break

    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Error handling {client_id}: {e}")
        import traceback
        traceback.print_exc()

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
    """Process incoming messages from clients"""
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

            # Send current game state
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

            # Check friendly fire
            if source["team_id"] == target["team_id"]:
                send_message(conn, {"type": "ERROR", "message": "Friendly fire disabled"})
                return current_player_id

            # Process hit
            new_health = target["health"] - DAMAGE_PER_HIT
            game_state.update_player(target_id, {"health": max(0, new_health)})

            # Notify shooter
            send_message(conn, {"type": "HIT_OK", "target_id": target_id, "damage": DAMAGE_PER_HIT})

            # Notify target
            if target_id in game_state.connections:
                send_message(game_state.connections[target_id], {
                    "type": "HIT_RECEIVED",
                    "source_id": source_id,
                    "damage": DAMAGE_PER_HIT,
                    "new_health": max(0, new_health)
                })

            # Check for elimination
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

        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Unknown message type: {msg_type}")

        return current_player_id

    except json.JSONDecodeError as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] JSON error: {e}")
        return current_player_id
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Processing error: {e}")
        import traceback
        traceback.print_exc()
        return current_player_id

# ============ Game Logic ============
def handle_elimination(killer_id, victim_id):
    """Handle player elimination"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {killer_id} eliminated {victim_id}")

    # Update scores
    game_state.update_player(killer_id, {
        "score": game_state.get_player(killer_id)["score"] + 100,
        "kills": game_state.get_player(killer_id)["kills"] + 1
    })

    game_state.update_player(victim_id, {
        "active": False,
        "deaths": game_state.get_player(victim_id)["deaths"] + 1
    })

    # Start respawn timer
    threading.Thread(target=respawn_player, args=(victim_id,), daemon=True).start()

def respawn_player(player_id):
    """Respawn player after delay"""
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
    """Send JSON message to client"""
    try:
        json_msg = json.dumps(message) + '\n'
        conn.sendall(json_msg.encode('utf-8'))
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Sent: {message['type']}")
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Send error: {e}")

def broadcast_message(message):
    """Send message to all connected players"""
    for player_id, conn in list(game_state.connections.items()):
        send_message(conn, message)

def monitor_connections():
    """Monitor player connections and remove stale ones"""
    while True:
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
    """Display server status periodically"""
    while True:
        time.sleep(30)
        players = game_state.get_all_players()
        if players:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] === Server Status ===")
            print(f"Active Players: {len(players)}")
            print(f"Game Active: {game_state.game_active}")
            for player_id, data in players.items():
                status = "ACTIVE" if data["active"] else "INACTIVE"
                print(f"  {player_id}: HP={data['health']}, Ammo={data['ammo']}, Score={data['score']} [{status}]")
            print("=" * 40 + "\n")

# ============ Console Commands ============
def console_input():
    """Handle console commands"""
    print("\nServer Commands:")
    print("  start - Start game")
    print("  end - End game")
    print("  status - Show status")
    print("  players - List players")
    print("  kick <player_id> - Kick player")
    print("  quit - Shutdown server\n")

    while True:
        try:
            cmd = input().strip().lower().split()
            if not cmd:
                continue

            if cmd[0] == "start":
                game_state.start_game()
                broadcast_message({"type": "GAME_START"})
                print("Game started!")

            elif cmd[0] == "end":
                game_state.end_game()
                broadcast_message({"type": "GAME_END"})
                print("Game ended!")

            elif cmd[0] == "status":
                players = game_state.get_all_players()
                print(f"\n=== Server Status ===")
                print(f"Players Connected: {len(players)}")
                print(f"Game Active: {game_state.game_active}")
                print("=" * 40 + "\n")

            elif cmd[0] == "players":
                players = game_state.get_all_players()
                if players:
                    print("\n=== Player List ===")
                    for player_id, data in players.items():
                        print(f"{player_id}: HP={data['health']}, Score={data['score']}, Active={data['active']}")
                    print("=" * 40 + "\n")
                else:
                    print("No players connected.")

            elif cmd[0] == "kick" and len(cmd) > 1:
                player_id = cmd[1]
                if player_id in game_state.connections:
                    game_state.connections[player_id].close()
                    game_state.remove_player(player_id)
                    print(f"Kicked {player_id}")
                else:
                    print(f"Player {player_id} not found")

            elif cmd[0] == "quit":
                print("Shutting down server...")
                broadcast_message({"type": "SERVER_SHUTDOWN"})
                sys.exit(0)

            else:
                print("Unknown command")

        except EOFError:
            break
        except Exception as e:
            print(f"Console error: {e}")

# ============ Server Start ============
def start_server():
    """Start the laser tag server"""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server.bind((HOST, PORT))
        server.listen(10)
        print(f"\n{'='*60}")
        print(f"Laser Tag Server Started (v2)")
        print(f"Listening on {HOST}:{PORT}")
        print(f"Max Players: {MAX_PLAYERS}")
        print(f"{'='*60}\n")

        # Start monitoring threads
        threading.Thread(target=monitor_connections, daemon=True).start()
        threading.Thread(target=status_display, daemon=True).start()
        threading.Thread(target=console_input, daemon=True).start()

        while True:
            try:
                conn, addr = server.accept()
                client_thread = threading.Thread(
                    target=handle_client,
                    args=(conn, addr),
                    daemon=True
                )
                client_thread.start()
            except KeyboardInterrupt:
                print("\nShutting down server...")
                break
            except Exception as e:
                print(f"Error accepting connection: {e}")

    finally:
        server.close()
        print("Server stopped.")

if __name__ == "__main__":
    start_server()