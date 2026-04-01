import pygame
import random
import time
import math
import numpy as np
from collections import deque

pygame.mixer.pre_init(44100, -16, 1, 512)
pygame.init()
pygame.mixer.init()

#var used dont change, cna adjust switch and time, rest dont change
HUD_HEIGHT    = 50
MAZE_WIDTH    = 600
MAZE_HEIGHT   = 600
WINDOW_WIDTH  = MAZE_WIDTH
WINDOW_HEIGHT = MAZE_HEIGHT + HUD_HEIGHT

ROWS, COLS = 10, 10
TILE = MAZE_WIDTH // COLS

switch_cooldown = 1.2
TOTAL_TIME      = 80
last_enemy_move_time = time.time()
enemy_move_delay = 0.4

WHITE   = (255, 255, 255)
BLACK   = (0,   0,   0  )
GRAY    = (180, 180, 180)
RED     = (220, 50,  50 )
GREEN   = (0,   200, 0  )
BLUE    = (80,  140, 255)
YELLOW  = (255, 220, 80 )
HUD_BG  = (20,  20,  30 )


#audio use numpy
def _make_sound(freq, duration_ms, wave='sine', volume=0.4):
    sr        = 44100
    n_samples = int(sr * duration_ms / 1000)
    t         = np.linspace(0, duration_ms / 1000, n_samples, endpoint=False)
    if wave == 'sine':
        raw = np.sin(2 * np.pi * freq * t)
    elif wave == 'square':
        raw = np.sign(np.sin(2 * np.pi * freq * t))
    elif wave == 'noise':
        raw = np.random.uniform(-1, 1, n_samples)
    else:
        raw = np.sin(2 * np.pi * freq * t)
    fade = np.linspace(1.0, 0.0, n_samples)
    raw  = (raw * fade * volume * 32767).astype(np.int16)
    return pygame.sndarray.make_sound(raw)


def _make_chord(freqs, duration_ms, volume=0.35):
    sr        = 44100
    n_samples = int(sr * duration_ms / 1000)
    t         = np.linspace(0, duration_ms / 1000, n_samples, endpoint=False)
    raw       = sum(np.sin(2 * np.pi * f * t) for f in freqs) / len(freqs)
    fade      = np.linspace(1.0, 0.0, n_samples)
    raw       = (raw * fade * volume * 32767).astype(np.int16)
    return pygame.sndarray.make_sound(raw)


snd_clue    = _make_chord([523, 659, 784], 400)
snd_wrong   = _make_sound(180, 350, wave='square', volume=0.3)
snd_correct = _make_chord([523, 659, 784, 1047], 600, volume=0.4)
snd_escape  = _make_chord([392, 523, 659, 784, 1047], 900, volume=0.45)
snd_fail    = _make_sound(110, 800, wave='square', volume=0.3)
snd_wall    = _make_sound(220, 120, wave='noise',  volume=0.25)


#effect variables
flash_color  = (0, 0, 0)
flash_alpha  = 0
FLASH_DECAY  = 18

particles = []

hud_clue_message = ""
hud_clue_expire  = 0

#asset
try:
    background_img = pygame.transform.scale(
        pygame.image.load('assets/textures/background.png'),
        (MAZE_WIDTH, MAZE_HEIGHT))
except:
    background_img = None

wall_img   = pygame.transform.scale(pygame.image.load('assets/textures/wall.png'),    (TILE, TILE))
player_img = pygame.transform.scale(pygame.image.load('assets/textures/player.png'),  (TILE-1, TILE-1))
clue_img   = pygame.transform.scale(pygame.image.load('assets/textures/diamond.png'), (30, 30))
exit_img   = pygame.transform.scale(pygame.image.load('assets/textures/exit.png'),    (TILE, TILE))

hud_font = pygame.font.SysFont(None, 28)
font     = pygame.font.SysFont(None, 24)

enemy_img = pygame.transform.scale(
    pygame.image.load('assets/textures/enemy.png'),
    (TILE - 10, TILE - 10)
)


#state fucntion
maze = [[0]*COLS for _ in range(ROWS)]
for r in range(ROWS):
    for c in range(COLS):
        if random.random() < 0.3 and (r, c) not in [(0,0),(ROWS-1,COLS-1)]:
            maze[r][c] = 1

player_pos = [0, 0]
enemy_pos = [ROWS - 1, 0]

clues = {
    (2, 3): "First clue: Look for the hidden code.",
    (4, 5): "Second clue: The code is MAGIC.",
    (7, 2): "Third clue: Press 'C' to enter code."
}
for pos in clues:
    maze[pos[0]][pos[1]] = 0

clues_found       = set()
code_input_active = False
code_input_text   = ""
code_message      = ""
game_won          = False
game_over = False
game_over_message = ""

graffiti_falling  = False
graffiti_fall_pos = []

last_switch_time  = time.time()
start_time        = time.time()

screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
pygame.display.set_caption("Endless Maze with Secret Code")


# also ui
def my(y):
    return y + HUD_HEIGHT


def trigger_flash(color, alpha=160):
    global flash_color, flash_alpha
    flash_color = color
    flash_alpha = alpha


def spawn_particles(px, py, color, count=20):
    for _ in range(count):
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(1.5, 4.5)
        life  = random.randint(25, 50)
        particles.append([float(px), float(py),
                           math.cos(angle)*speed, math.sin(angle)*speed,
                           life, life, color])


def update_and_draw_particles():
    dead = []
    for p in particles:
        p[0] += p[2]
        p[1] += p[3]
        p[3] += 0.15
        p[4] -= 1
        if p[4] <= 0:
            dead.append(p)
            continue
        ratio  = p[4] / p[5]
        r, g, b = p[6]
        radius = max(1, int(4 * ratio))
        pygame.draw.circle(screen, (int(r*ratio), int(g*ratio), int(b*ratio)),
                           (int(p[0]), int(p[1])), radius)
    for p in dead:
        particles.remove(p)


def draw_screen_flash():
    if flash_alpha <= 0:
        return
    overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
    overlay.fill((*flash_color, min(int(flash_alpha), 200)))
    screen.blit(overlay, (0, 0))

#effect use some basic

def start_graffiti():
    global graffiti_falling, graffiti_fall_pos
    graffiti_falling  = True
    graffiti_fall_pos = []
    base_x = (COLS-1)*TILE + 10
    base_y = (ROWS-1)*TILE + 5 + HUD_HEIGHT
    for i in range(5):
        graffiti_fall_pos.append([base_x + i*8, base_y - 50 - i*15])


def draw_graffiti():
    for pos in graffiti_fall_pos:
        pos[1] += 4
        pygame.draw.rect(screen, (200, 0, 200), (*pos, 15, 15))


#  HUD fix

def draw_hud(remaining, clues_found_count, total_clues, status_msg=""):
    pygame.draw.rect(screen, HUD_BG, (0, 0, WINDOW_WIDTH, HUD_HEIGHT))
    pygame.draw.line(screen, GRAY, (0, HUD_HEIGHT-1), (WINDOW_WIDTH, HUD_HEIGHT-1), 1)


    if clues_found_count == total_clues:
        pulse = int(abs(math.sin(time.time() * 4)) * 80)
        clue_color = (255, 200 + pulse // 3, 0)
    else:
        clue_color = WHITE
    clue_text = hud_font.render(f"Clues: {clues_found_count}/{total_clues}", True, clue_color)
    screen.blit(clue_text, (12, HUD_HEIGHT//2 - clue_text.get_height()//2))


    if remaining <= 20:
        pulse = int(abs(math.sin(time.time() * 5)) * 100)
        timer_color = (220, 50 + pulse // 4, 50)
    else:
        timer_color = WHITE
    timer_text = hud_font.render(f"Time: {remaining}s", True, timer_color)
    timer_x    = WINDOW_WIDTH - timer_text.get_width() - 12
    screen.blit(timer_text, (timer_x, HUD_HEIGHT//2 - timer_text.get_height()//2))


    if hud_clue_message and time.time() < hud_clue_expire:
        msg_surf = hud_font.render(hud_clue_message, True, YELLOW)
        msg_x    = timer_x - msg_surf.get_width() - 16
        screen.blit(msg_surf, (max(msg_x, clue_text.get_width() + 20),
                                HUD_HEIGHT//2 - msg_surf.get_height()//2))
    elif status_msg:
        msg_surf = hud_font.render(status_msg, True, GREEN)
        screen.blit(msg_surf, (WINDOW_WIDTH//2 - msg_surf.get_width()//2,
                                HUD_HEIGHT//2 - msg_surf.get_height()//2))


#draw the maze
def draw_maze():
    if background_img:
        screen.blit(background_img, (0, HUD_HEIGHT))
    else:
        pygame.draw.rect(screen, WHITE, (0, HUD_HEIGHT, MAZE_WIDTH, MAZE_HEIGHT))

    for r in range(ROWS):
        for c in range(COLS):
            rect = pygame.Rect(c*TILE, my(r*TILE), TILE, TILE)
            if maze[r][c] == 1:
                screen.blit(wall_img, rect)
            pygame.draw.rect(screen, GRAY, rect, 1)

    for (r, c) in clues:
        if (r, c) not in clues_found:
            offset = int(5 * math.sin(time.time() * 3))
            # animated glow ring
            cx     = c*TILE + TILE//2
            cy     = my(r*TILE + TILE//2)
            glow_r = int(18 + 4 * math.sin(time.time() * 3))
            pygame.draw.circle(screen, (255, 230, 80), (cx, cy), glow_r, 2)
            screen.blit(clue_img, (c*TILE + 15, my(r*TILE + 15 + offset)))

    if game_won:
        screen.blit(exit_img, ((COLS-1)*TILE, my((ROWS-1)*TILE)))


def draw_player():
   #glow effect use gem key (anant)
    if len(clues_found) == len(clues) and not game_won:
        glow_r    = int(26 + 6 * math.sin(time.time() * 6))
        cx        = player_pos[1]*TILE + TILE//2
        cy        = my(player_pos[0]*TILE + TILE//2)
        glow_surf = pygame.Surface((glow_r*2, glow_r*2), pygame.SRCALPHA)
        pygame.draw.circle(glow_surf, (255, 220, 0, 80), (glow_r, glow_r), glow_r)
        screen.blit(glow_surf, (cx - glow_r, cy - glow_r))

    screen.blit(player_img, (player_pos[1]*TILE + 5, my(player_pos[0]*TILE + 5)))


 # input ahtisham
def draw_code_input():
    dim = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 140))
    screen.blit(dim, (0, 0))

    box_x = WINDOW_WIDTH // 4
    box_y = HUD_HEIGHT + MAZE_HEIGHT // 3
    rect  = pygame.Rect(box_x, box_y, WINDOW_WIDTH // 2, 50)

    pygame.draw.rect(screen, (240, 240, 240), rect, border_radius=6)
    pygame.draw.rect(screen, BLACK, rect, 2, border_radius=6)

    screen.blit(font.render("Enter secret code:", True, BLACK), (rect.x + 10, rect.y - 25))
    screen.blit(font.render(code_input_text, True, BLACK),      (rect.x + 10, rect.y + 12))
    screen.blit(
        font.render(code_message, True, RED if "Incorrect" in code_message else GREEN),
        (rect.x, rect.y + 60))


#switch here 
def switch_maze():
    walls = [(r,c) for r in range(ROWS) for c in range(COLS)
             if maze[r][c] == 1 and (r,c) not in [(0,0),(ROWS-1,COLS-1)]]
    empty = [(r,c) for r in range(ROWS) for c in range(COLS)
             if maze[r][c] == 0 and (r,c) not in [(0,0),(ROWS-1,COLS-1)]]
    if len(walls) >= 8 and len(empty) >= 8:
        for w, e in zip(random.sample(walls, 8), random.sample(empty, 8)):
            if (w[0], w[1]) == tuple(player_pos):
                trigger_flash((200, 0, 0), 140)
                snd_wall.play()
            maze[w[0]][w[1]] = 0
            maze[e[0]][e[1]] = 1


#fixed clue check, dont push
def check_clue():
    global hud_clue_message, hud_clue_expire
    pos = tuple(player_pos)
    if pos in clues and pos not in clues_found:
        clues_found.add(pos)
        hud_clue_message = clues[pos]
        hud_clue_expire  = time.time() + 4
        cx = player_pos[1]*TILE + TILE//2
        cy = my(player_pos[0]*TILE + TILE//2)
        spawn_particles(cx, cy, (255, 220, 50), count=30)
        trigger_flash((255, 215, 0), 80)
        snd_clue.play()


#use movement imported from unity
def move_player(key):
    r, c = player_pos
    if   key == pygame.K_UP    and r > 0      and maze[r-1][c] == 0: player_pos[0] -= 1
    elif key == pygame.K_DOWN  and r < ROWS-1 and maze[r+1][c] == 0: player_pos[0] += 1
    elif key == pygame.K_LEFT  and c > 0      and maze[r][c-1] == 0: player_pos[1] -= 1
    elif key == pygame.K_RIGHT and c < COLS-1 and maze[r][c+1] == 0: player_pos[1] += 1

#enemy
def bfs(start, goal):
    queue = deque([start])
    visited = {tuple(start): None}

    while queue:
        current = queue.popleft()

        if current == goal:
            path = []
            while current:
                path.append(current)
                current = visited[current]
            return path[::-1]

        r, c = current

        for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
            nr, nc = r + dr, c + dc

            if (
                0 <= nr < ROWS and
                0 <= nc < COLS and
                maze[nr][nc] == 0 and
                (nr, nc) not in visited
            ):
                visited[(nr, nc)] = current
                queue.append((nr, nc))

    return []

def move_enemy():
    global enemy_pos

    path = bfs(tuple(enemy_pos), tuple(player_pos))

    if len(path) > 1:
        enemy_pos[0], enemy_pos[1] = path[1]
        
def draw_enemy():
    # create glow surface
    glow_size = 60
    glow = pygame.Surface((glow_size, glow_size), pygame.SRCALPHA)

    pygame.draw.circle(
        glow,
        (255, 0, 0, 70),   # red glow with transparency
        (glow_size // 2, glow_size // 2),
        glow_size // 2
    )

    # draw glow behind enemy
    screen.blit(
        glow,
        (
            enemy_pos[1]*TILE + (TILE - glow_size)//2,
            my(enemy_pos[0]*TILE + (TILE - glow_size)//2)
        )
    )

    # draw enemy sprite
    screen.blit(
        enemy_img,
        (
            enemy_pos[1]*TILE + (TILE - 50)//2,
            my(enemy_pos[0]*TILE + (TILE - 50)//2)
        )
    )
def restart_game():
    global player_pos, enemy_pos
    global clues_found, game_over, game_won
    global start_time, code_input_active

    player_pos[:] = [0, 0]
    enemy_pos[:] = [ROWS - 1, 0]

    clues_found.clear()

    game_over = False
    game_won = False

    code_input_active = False

    start_time = time.time()
    
    
#main loop and all
def main():
    global code_input_active, code_input_text, code_message
    global game_won, last_switch_time, flash_alpha
    global last_enemy_move_time
    global game_over, game_over_message

    clock   = pygame.time.Clock()
    running = True
    time_up_sound_played = False

    while running:
        current_time = time.time()
        remaining    = max(0, int(TOTAL_TIME - (current_time - start_time)))

        #time up
        if remaining <= 0:
            if not time_up_sound_played:
                snd_fail.play()
                time_up_sound_played = True
            trigger_flash((200, 0, 0), 200)
            screen.fill(BLACK)
            draw_hud(0, len(clues_found), len(clues))
            msg = hud_font.render("Time's up!  You failed!", True, RED)
            screen.blit(msg, (WINDOW_WIDTH//2 - msg.get_width()//2,
                               HUD_HEIGHT + MAZE_HEIGHT//2))
            draw_screen_flash()
            pygame.display.flip()
            pygame.time.wait(3000)
            break

        # shuffle
        if not game_won and not game_over and current_time - last_switch_time > switch_cooldown:
            switch_maze()
            last_switch_time = current_time
            
        # enemy AI movement (autonomous chasing)
        if current_time - last_enemy_move_time > enemy_move_delay:
            if not game_over:
                move_enemy()
            last_enemy_move_time = current_time

        #
        screen.fill(BLACK)
        draw_maze()
        draw_player()
        draw_enemy()
        update_and_draw_particles()
        
        #collidsion
        if enemy_pos == player_pos and not game_over:
            snd_fail.play()
            trigger_flash((255, 0, 0), 200)

            game_over = True
            game_over_message = "Caught by enemy! Press R to restart"

        hud_status = "Secret hole opened!  Escape now!" if game_won else ""
        draw_hud(remaining, len(clues_found), len(clues), hud_status)
        
        if game_over:
            overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 180))
            screen.blit(overlay, (0, 0))

            msg = hud_font.render(game_over_message, True, RED)

            screen.blit(
                msg,
                (
                    WINDOW_WIDTH//2 - msg.get_width()//2,
                    HUD_HEIGHT + MAZE_HEIGHT//2
                )
            )

        if graffiti_falling:
            draw_graffiti()

        draw_screen_flash()
        if flash_alpha > 0:
            flash_alpha = max(0, flash_alpha - FLASH_DECAY)

        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if code_input_active:
                    if event.key == pygame.K_RETURN:
                        if code_input_text.upper() == "MAGIC":
                            game_won          = True
                            code_message      = "Correct! Escape opened!"
                            code_input_active = False
                            maze[ROWS-1][COLS-2] = 0
                            maze[ROWS-1][COLS-1] = 0
                            start_graffiti()
                            ex = (COLS-1)*TILE + TILE//2
                            ey = my((ROWS-1)*TILE + TILE//2)
                            spawn_particles(ex, ey, (0, 255, 120), count=50)
                            trigger_flash((0, 200, 80), 120)
                            snd_correct.play()
                        else:
                            code_message    = "Incorrect code!"
                            code_input_text = ""
                            trigger_flash((200, 0, 0), 100)
                            snd_wrong.play()
                    elif event.key == pygame.K_BACKSPACE:
                        code_input_text = code_input_text[:-1]
                    elif event.key == pygame.K_ESCAPE:
                        code_input_active = False
                    else:
                        if len(code_input_text) < 12:
                            code_input_text += event.unicode
                else:
                    if game_over and event.key == pygame.K_r:
                        restart_game()

                    elif event.key == pygame.K_c and len(clues_found) == len(clues):
                        code_input_active = True
                        code_input_text   = ""
                        code_message      = ""

                    elif not game_over:
                        move_player(event.key)
                        check_clue()
                        

        if code_input_active:
            draw_code_input()
            

       
        if game_won and tuple(player_pos) == (ROWS-1, COLS-1):
            snd_escape.play()
            trigger_flash((255, 255, 255), 220)
            cx = (COLS-1)*TILE + TILE//2
            cy = my((ROWS-1)*TILE + TILE//2)
            spawn_particles(cx, cy, (255, 255, 100), count=80)
            draw_screen_flash()
            msg = hud_font.render("You escaped!  Congrats!", True, BLUE)
            screen.blit(msg, (WINDOW_WIDTH//2 - msg.get_width()//2,
                               HUD_HEIGHT + MAZE_HEIGHT//2))
            pygame.display.flip()
            pygame.time.wait(3000)
            running = False

        pygame.display.flip()
        clock.tick(60)
        
        
        

    pygame.quit()


if __name__ == "__main__":
    main()
