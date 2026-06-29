import socket
import json
import threading
import time

HOST = '0.0.0.0'
PORT = 5000

players = {}  # {player_id: {"health":100,"ammo":30,"active":True,"score":0}}

def handle_client(conn, addr):
    print(f"Connected: {addr}")
    while True:
        try:
            data = conn.recv(1024).decode().strip()
            if not data:
                break
            print(f"Received: {data}")
            process_message(data, conn)
        except:
            break
    conn.close()

def process_message(data, conn):
    try:
        msg = json.loads(data)
        msg_type = msg.get("type")

        if msg_type == "INIT":
            pid = msg["player_id"]
            players[pid] = {"health":100,"ammo":30,"active":True,"score":0}
            conn.sendall(b"INIT_OK\n")

        elif msg_type == "HIT":
            source = msg["source_id"]
            target = msg["target_id"]
            if target in players and players[target]["active"]:
                players[target]["health"] -= 10
                if players[target]["health"] <= 0:
                    players[target]["active"] = False
                    players[source]["score"] += 1
                    threading.Thread(target=respawn_player, args=(target, conn)).start()
                conn.sendall(b"HIT_OK\n")

    except Exception as e:
        print("Error:", e)

def respawn_player(pid, conn):
    time.sleep(5)
    players[pid]["health"] = 100
    players[pid]["ammo"] = 30
    players[pid]["active"] = True
    conn.sendall(b"RESPAWN\n")

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen(5)
    print(f"Server running on {HOST}:{PORT}")
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr)).start()

if __name__ == "__main__":
    start_server()
