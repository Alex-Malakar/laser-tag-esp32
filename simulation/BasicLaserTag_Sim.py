
import time
import random as rand
import threading

import matplotlib.pyplot as plt

# -----------------------------
# CONFIGURATION
# -----------------------------
MAX_HEALTH = 100
MAX_AMMO = 30
RESPAWN_TIME = 5  # seconds
GAME_DURATION = 600  # 10 minutes in seconds


# -----------------------------
# PLAYER CLASS
# -----------------------------
class Player:
    def __init__(self, player_id, team): # Constructor Class
        self.player_id = player_id
        self.team = team
        self.health = MAX_HEALTH
        self.ammo = MAX_AMMO
        self.alive = True
        self.score = 0
        
        # For the graph
        self.hit_history = []
        

    def shoot(self, target):
        if not self.alive:
            print(f"{self.player_id} is dead and cannot shoot.")
            return None
        if self.ammo <= 0:
            print(f"{self.player_id} is out of ammo! Reload required.")
            return None
        
        self.ammo -= 1
        hit_success = rand.random() < 0.7 #hit_success = random.choice([True, False])  # Simulate hit probability
        if hit_success:
            print(f"{self.player_id} hit!!!")
            return {"type": "HIT", "source": self, "target": target}
        else: 
            print(f"{self.player_id} missed!!!")
            return None

    def reload(self):
        print(f"{self.player_id} is reloading...")
        time.sleep(2)
        self.ammo = MAX_AMMO

    def respawn(self):
        print(f"{self.player_id} respawning...")
        time.sleep(RESPAWN_TIME)
        self.health = MAX_HEALTH
        self.alive = True

# -----------------------------
# GAME CONTROLLER
# -----------------------------
class GameController:
    def __init__(self, players):
        self.players = players
        self.start_time = time.time()
        self.game_active = True

        # Added for the game 
        self.score_log = {p.player_id: [(0,0)] for p in players}

    def process_hit(self, hit_event):
        target = hit_event["target"]
        source = hit_event["source"]

        target.hit_history.append(time.time())

        if target.alive:
            target.health -= 20
            if target.health <= 0:
                target.alive = False
                print(f"{target.player_id} eliminated!")
                source.score += 100

                self.score_log[source.player_id].append((time.time() - self.start_time, source.score))

                # Respawn in background
                threading.Thread(target=target.respawn).start()

    def check_game_end(self):
        if time.time() - self.start_time >= GAME_DURATION:
            self.game_active = False
            print("Game Over!")
            self.display_scores()

    def display_scores(self):
        print("\nFinal Scores:")
        for p in self.players:
            print(f"{p.player_id} (Team {p.team}): {p.score}")

        for pid, data in self.score_log.items():
            t,s = zip(*data)
            plt.plot(t, s, 'o-', label=f'{pid}')
        
        plt.title("Player Score Progression in a 10 second match")
        plt.xlabel("Time (seconds)")
        plt.ylabel("Player")
        plt.legend()
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.tight_layout()
        plt.show()

# -----------------------------
# SIMULATION LOOP
# -----------------------------
def simulate_game():
    players = [Player("Player_1", "Red"), Player("Player_2", "Blue")]
    controller = GameController(players)

    count = 0

    while controller.game_active:
        tagger = rand.choice(players)
        target = rand.choice([p for p in players if p != tagger])
        
        print("="*50)
        print(f"Instance: {count+1}")
        print(f"Tagger: {tagger.player_id}\nTarget: {target.player_id}")
    
        if tagger.ammo <= 0:
            threading.Thread(target=tagger.reload, daemon=True).start()
        else:
            hit_event = tagger.shoot(target)
            if hit_event:
                controller.process_hit(hit_event)

        # Instances of them doing stuff
        print(f"{tagger.player_id} {tagger.health}/{MAX_HEALTH} || {target.player_id} {target.health}/{MAX_HEALTH}")        
        count += 1

        controller.check_game_end()
        time.sleep(1)

if __name__ == "__main__":
    simulate_game()