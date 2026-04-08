import pygame
import random
import time
import math
import json
import os
import numpy as np
from collections import deque


pygame.mixer.pre_init(44100, -16, 1, 512)
pygame.init()
pygame.mixer.init()

# ── cross-platform windowed fullscreen ────────────────────────────────────────
#   pygame.SCALED  = pygame stretches our fixed render surface to fill the
#   window on any resolution/DPI (Mac Retina, Windows DPI scaling, etc.)
#   pygame.RESIZABLE lets the OS window manager handle maximise/minimise.
_info    = pygame.display.Info()
SCREEN_W = _info.current_w
SCREEN_H = _info.current_h

ROWS, COLS  = 10, 10
HUD_HEIGHT  = 70
RENDER_SIZE = min(SCREEN_W, SCREEN_H - HUD_HEIGHT)
TILE        = (RENDER_SIZE // COLS) & ~1   # even number, pixel-perfect
MAZE_WIDTH  = TILE * COLS
MAZE_HEIGHT = TILE * ROWS
WIN_W       = MAZE_WIDTH
WIN_H       = MAZE_HEIGHT + HUD_HEIGHT
MAZE_OFFSET_X = 0
MAZE_OFFSET_Y = HUD_HEIGHT

try:
    # pygame >= 2.0: SCALED handles Mac Retina + Windows DPI automatically
    screen = pygame.display.set_mode((WIN_W, WIN_H), pygame.SCALED | pygame.RESIZABLE)
except Exception:
    screen = pygame.display.set_mode((WIN_W, WIN_H), pygame.RESIZABLE)

pygame.display.set_caption("Maze Runner")

# ── constants ──────────────────────────────────────────────────────────────────
TOTAL_TIME           = 90
SCORE_PER_DIAMOND    = 10
DIAMOND_RESPAWN_SEC  = 5
DIAMOND_POSITIONS    = [(2,3),(4,5),(7,2),(1,7),(6,8)]
LEADERBOARD_FILE     = "leaderboard.json"
MAX_LB_ENTRIES       = 5

# (min_score, enemy_delay_s, switch_cooldown_s, label)
SPEED_LEVELS = [
    (0,   0.50, 1.20, "LVL 1"),
    (50,  0.42, 1.00, "LVL 2"),
    (100, 0.34, 0.85, "LVL 3"),
    (180, 0.26, 0.70, "LVL 4"),
    (280, 0.18, 0.55, "LVL 5  FAST!"),
]

WHITE  = (255, 255, 255)
BLACK  = (0,   0,   0)
GRAY   = (180, 180, 180)
RED    = (220, 50,  50)
GREEN  = (0,   200, 0)
BLUE   = (80,  140, 255)
YELLOW = (255, 220, 80)
CYAN   = (0,   220, 220)
ORANGE = (255, 140, 0)
PURPLE = (180, 80,  255)
HUD_BG = (15,  15,  25)


# ── SFX only (no BGM) ─────────────────────────────────────────────────────────
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

snd_diamond = _make_chord([988, 1319],           280, volume=0.45)
snd_fail    = _make_sound(110, 800, wave='square', volume=0.30)
snd_wall    = _make_sound(220, 120, wave='noise',  volume=0.25)
snd_levelup = _make_chord([659, 784, 1047],      400, volume=0.40)


# ── background music (looping procedural track) ───────────────────────────────
def _make_bgm():
    sr       = 44100
    bpm      = 110
    beat     = sr * 60 // bpm
    bar      = beat * 4
    n_bars   = 8
    total    = bar * n_bars
    track    = np.zeros(total, dtype=np.float32)

    chord_freqs = [
        [220.0, 261.6, 329.6],
        [174.6, 220.0, 261.6],
        [130.8, 164.8, 196.0],
        [196.0, 246.9, 293.7],
    ]
    for bar_i in range(n_bars):
        cf    = chord_freqs[bar_i % 4]
        s     = bar_i * bar
        e     = s + bar
        t_seg = np.linspace(0, bar / sr, bar, endpoint=False)
        pad   = sum(0.18 * np.sin(2 * np.pi * f * t_seg) for f in cf)
        env   = np.ones(bar)
        r0    = int(sr * 0.05)
        env[:r0]  = np.linspace(0, 1, r0)
        env[-r0:] = np.linspace(1, 0, r0)
        track[s:e] += (pad * env).astype(np.float32)

    arp_notes = [220, 261.6, 329.6, 392, 329.6, 261.6]
    note_len  = beat // 2
    for i in range(total // note_len):
        freq  = arp_notes[i % len(arp_notes)]
        s     = i * note_len
        e     = min(s + note_len, total)
        t_seg = np.linspace(0, (e - s) / sr, e - s, endpoint=False)
        wave  = 0.10 * np.sin(2 * np.pi * freq * t_seg)
        env   = np.linspace(1, 0, e - s)
        track[s:e] += (wave * env).astype(np.float32)

    for bar_i in range(n_bars):
        for beat_i in [0, 2]:
            s     = bar_i * bar + beat_i * beat
            e     = min(s + int(sr * 0.18), total)
            t_seg = np.linspace(0, (e - s) / sr, e - s, endpoint=False)
            freq  = 120 * np.exp(-30 * t_seg)
            kick  = 0.35 * np.sin(2 * np.pi * freq * t_seg)
            env   = np.exp(-20 * t_seg)
            track[s:e] += (kick * env).astype(np.float32)

    hat_len = beat // 2
    for i in range(total // hat_len):
        s     = i * hat_len
        e     = min(s + hat_len // 3, total)
        t_seg = np.linspace(0, (e - s) / sr, e - s, endpoint=False)
        hat   = 0.06 * np.random.uniform(-1, 1, e - s).astype(np.float32)
        env   = np.exp(-60 * t_seg)
        track[s:e] += hat * env

    mx_val = np.max(np.abs(track))
    if mx_val > 0:
        track /= mx_val
    out = (track * 0.55 * 32767).astype(np.int16)
    return pygame.sndarray.make_sound(out)

bgm = _make_bgm()
bgm.play(loops=-1)


# ── visual effects ─────────────────────────────────────────────────────────────
flash_color = (0, 0, 0)
flash_alpha = 0
FLASH_DECAY = 18
particles   = []
popups      = []  # floating score/status text


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


def spawn_popup(px, py, text, color=YELLOW):
    popups.append({'text': text, 'x': px, 'y': float(py),
                   'vy': -1.8, 'life': 60, 'maxlife': 60, 'color': color})


def update_and_draw_particles():
    dead = []
    for p in particles:
        p[0] += p[2]; p[1] += p[3]; p[3] += 0.15; p[4] -= 1
        if p[4] <= 0:
            dead.append(p)
            continue
        ratio   = p[4] / p[5]
        r, g, b = p[6]
        radius  = max(1, int(4 * ratio))
        pygame.draw.circle(screen, (int(r*ratio), int(g*ratio), int(b*ratio)),
                           (int(p[0]), int(p[1])), radius)
    for p in dead:
        particles.remove(p)


def update_and_draw_popups():
    dead = []
    for p in popups:
        p['y']    += p['vy']
        p['life'] -= 1
        if p['life'] <= 0:
            dead.append(p)
            continue
        alpha = int(255 * p['life'] / p['maxlife'])
        surf  = font.render(p['text'], True, p['color'])
        surf.set_alpha(alpha)
        screen.blit(surf, (int(p['x']) - surf.get_width()//2, int(p['y'])))
    for p in dead:
        popups.remove(p)


def draw_screen_flash():
    if flash_alpha <= 0:
        return
    overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    overlay.fill((*flash_color, min(int(flash_alpha), 200)))
    screen.blit(overlay, (0, 0))


# ── assets ─────────────────────────────────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def _load_scaled(filename, size, smooth=True):
    """Try multiple path candidates so assets are found next to the script."""
    basename = os.path.basename(filename)
    candidates = [
        filename,
        os.path.join(_SCRIPT_DIR, basename),
        basename,
        os.path.join(_SCRIPT_DIR, 'assets', 'textures', basename),
    ]
    for p in candidates:
        try:
            img = pygame.image.load(p).convert_alpha()
            return (pygame.transform.smoothscale(img, size)
                    if smooth else pygame.transform.scale(img, size))
        except Exception:
            continue
    # Fallback coloured surface
    surf = pygame.Surface(size, pygame.SRCALPHA)
    colours = {
        'wall':    (100, 60,  30),
        'player':  (80,  140, 255),
        'diamond': (0,   220, 220),
        'exit':    (0,   180, 80),
        'enemy':   (220, 50,  50),
        'bg':      (30,  30,  50),
    }
    for key, col in colours.items():
        if key in filename.lower():
            surf.fill(col)
            break
    else:
        surf.fill((120, 120, 120))
    return surf

background_img = _load_scaled('background.png', (MAZE_WIDTH, MAZE_HEIGHT))
wall_img    = _load_scaled('wall.png',    (TILE, TILE),          smooth=False)
player_img  = _load_scaled('player.png',  (TILE-4, TILE-4),      smooth=True)
diamond_img = _load_scaled('diamond.png', (int(TILE*0.55), int(TILE*0.55)), smooth=True)
exit_img    = _load_scaled('exit.png',    (TILE, TILE),           smooth=True)
enemy_img   = _load_scaled('enemy.png',   (TILE-10, TILE-10),    smooth=True)

_fs      = max(18, TILE // 4)
hud_font = pygame.font.SysFont(None, _fs + 8)
font     = pygame.font.SysFont(None, _fs + 4)
big_font = pygame.font.SysFont(None, _fs + 16)
sm_font  = pygame.font.SysFont(None, max(16, _fs - 2))


# ── leaderboard ────────────────────────────────────────────────────────────────
def load_leaderboard():
    if os.path.exists(LEADERBOARD_FILE):
        try:
            with open(LEADERBOARD_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_leaderboard(lb):
    try:
        with open(LEADERBOARD_FILE, 'w') as f:
            json.dump(lb, f)
    except Exception:
        pass

def add_to_leaderboard(score_val):
    lb = load_leaderboard()
    lb.append(score_val)
    lb = sorted(lb, reverse=True)[:MAX_LB_ENTRIES]
    save_leaderboard(lb)
    return lb


# ── maze ───────────────────────────────────────────────────────────────────────
def make_maze():
    m = [[0]*COLS for _ in range(ROWS)]
    for r in range(ROWS):
        for c in range(COLS):
            if random.random() < 0.3 and (r, c) not in [(0,0),(ROWS-1,COLS-1)]:
                m[r][c] = 1
    return m


# ── mutable game state ─────────────────────────────────────────────────────────
maze       = make_maze()
player_pos = [0, 0]
enemy_pos  = [ROWS-1, 0]

diamonds = []
for (_r, _c) in DIAMOND_POSITIONS:
    maze[_r][_c] = 0
    diamonds.append({'r': _r, 'c': _c, 'collected': False, 'respawn_at': 0})

score             = 0
high_score        = max(load_leaderboard(), default=0)
game_over         = False
game_over_message = ""
start_time        = time.time()
last_switch_time  = time.time()
last_enemy_move   = time.time()
enemy_move_delay  = SPEED_LEVELS[0][1]
switch_cooldown   = SPEED_LEVELS[0][2]
current_level     = 0
level_label       = SPEED_LEVELS[0][3]

powerup           = None
powerup_active    = False
powerup_end_time  = 0.0
powerup_next_spawn= time.time() + 12.0


# ── coordinate helpers ─────────────────────────────────────────────────────────
def my(y): return y + MAZE_OFFSET_Y
def mx(x): return x + MAZE_OFFSET_X


# ── speed level ────────────────────────────────────────────────────────────────
def update_speed_level():
    global enemy_move_delay, switch_cooldown, current_level, level_label
    for i in range(len(SPEED_LEVELS)-1, -1, -1):
        if score >= SPEED_LEVELS[i][0]:
            if i != current_level:
                current_level    = i
                enemy_move_delay = SPEED_LEVELS[i][1]
                switch_cooldown  = SPEED_LEVELS[i][2]
                level_label      = SPEED_LEVELS[i][3]
                snd_levelup.play()
                trigger_flash((255, 200, 0), 100)
                spawn_popup(WIN_W//2, MAZE_OFFSET_Y + MAZE_HEIGHT//3,
                            f"SPEED UP!  {level_label}", ORANGE)
            break


# ── power-up (spawn/check stubs – shield UI removed) ──────────────────────────
def try_spawn_powerup():
    pass


def check_powerup():
    pass


# ── diamond score ────────────────────────────────────────────────────────────
def collect_diamond_score():
    return SCORE_PER_DIAMOND, 1


# ── HUD ────────────────────────────────────────────────────────────────────────
def draw_hud(remaining):
    pygame.draw.rect(screen, HUD_BG, (0, 0, WIN_W, HUD_HEIGHT))
    pygame.draw.line(screen, (60, 60, 80), (0, HUD_HEIGHT-1), (WIN_W, HUD_HEIGHT-1), 1)
    cy = HUD_HEIGHT // 2

    # Score
    score_surf = hud_font.render(f"SCORE  {score:05d}", True, YELLOW)
    screen.blit(score_surf, (10, cy - score_surf.get_height()//2))

    # Level (centre)
    lvl_surf = sm_font.render(level_label, True, (100, 220, 100))
    screen.blit(lvl_surf, (WIN_W//2 - lvl_surf.get_width()//2,
                            cy - lvl_surf.get_height()//2))

    # Timer
    if remaining <= 20:
        pulse       = int(abs(math.sin(time.time() * 5)) * 100)
        timer_color = (220, 50 + pulse // 4, 50)
    else:
        timer_color = WHITE
    ts = hud_font.render(f"TIME  {remaining:02d}", True, timer_color)
    screen.blit(ts, (WIN_W - ts.get_width() - 10, cy - ts.get_height()//2))


# ── maze drawing ───────────────────────────────────────────────────────────────
def draw_maze():
    if background_img:
        screen.blit(background_img, (MAZE_OFFSET_X, MAZE_OFFSET_Y))
    else:
        pygame.draw.rect(screen, (30, 30, 50),
                         (MAZE_OFFSET_X, MAZE_OFFSET_Y, MAZE_WIDTH, MAZE_HEIGHT))

    for r in range(ROWS):
        for c in range(COLS):
            rect = pygame.Rect(mx(c*TILE), my(r*TILE), TILE, TILE)
            if maze[r][c] == 1:
                screen.blit(wall_img, rect)

    now = time.time()

    # Diamonds
    for d in diamonds:
        if d['collected']:
            continue
        r, c   = d['r'], d['c']
        offset = int(4 * math.sin(now * 3 + r + c))
        cx     = mx(c*TILE + TILE//2)
        cy_    = my(r*TILE + TILE//2)
        pygame.draw.circle(screen, CYAN, (cx, cy_), int(14 + 4*math.sin(now*3)), 2)
        dw = diamond_img.get_width()
        dh = diamond_img.get_height()
        screen.blit(diamond_img,
                    (mx(c*TILE + (TILE-dw)//2),
                     my(r*TILE + (TILE-dh)//2 + offset)))




def draw_player():
    screen.blit(player_img,
                (mx(player_pos[1]*TILE + 2), my(player_pos[0]*TILE + 2)))


def draw_enemy():
    glow_size = TILE + 10
    glow      = pygame.Surface((glow_size, glow_size), pygame.SRCALPHA)
    alpha     = min(70 + current_level * 18, 160)
    pygame.draw.circle(glow, (255, 0, 0, alpha),
                       (glow_size//2, glow_size//2), glow_size//2)
    screen.blit(glow, (mx(enemy_pos[1]*TILE + (TILE-glow_size)//2),
                        my(enemy_pos[0]*TILE + (TILE-glow_size)//2)))
    ew = enemy_img.get_width()
    eh = enemy_img.get_height()
    screen.blit(enemy_img,
                (mx(enemy_pos[1]*TILE + (TILE-ew)//2),
                 my(enemy_pos[0]*TILE + (TILE-eh)//2)))


# ── maze shuffle ──────────────────────────────────────────────────────────────
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
        for d in diamonds:
            if not d['collected']:
                maze[d['r']][d['c']] = 0
        if powerup:
            maze[powerup['r']][powerup['c']] = 0


# ── movement ───────────────────────────────────────────────────────────────────
def move_player(key):
    r, c = player_pos
    if   key == pygame.K_UP    and r > 0      and maze[r-1][c] == 0: player_pos[0] -= 1
    elif key == pygame.K_DOWN  and r < ROWS-1 and maze[r+1][c] == 0: player_pos[0] += 1
    elif key == pygame.K_LEFT  and c > 0      and maze[r][c-1] == 0: player_pos[1] -= 1
    elif key == pygame.K_RIGHT and c < COLS-1 and maze[r][c+1] == 0: player_pos[1] += 1


# ── diamond collection ────────────────────────────────────────────────────────
def check_diamonds():
    global score
    pos = tuple(player_pos)
    for d in diamonds:
        if not d['collected'] and (d['r'], d['c']) == pos:
            d['collected']  = True
            d['respawn_at'] = time.time() + DIAMOND_RESPAWN_SEC
            pts, mult       = collect_diamond_score()
            score          += pts
            cx = mx(pos[1]*TILE + TILE//2)
            cy = my(pos[0]*TILE + TILE//2)
            spawn_particles(cx, cy, (0, 220, 220), count=30)
            trigger_flash((0, 200, 200), 60)
            snd_diamond.play()
            spawn_popup(cx, cy - 20, f"+{pts}", YELLOW)
            update_speed_level()


def respawn_diamonds():
    now      = time.time()
    occupied = {(d['r'], d['c']) for d in diamonds if not d['collected']}
    for d in diamonds:
        if d['collected'] and now >= d['respawn_at']:
            candidates = [
                (r, c) for r in range(ROWS) for c in range(COLS)
                if maze[r][c] == 0
                and (r, c) not in [(0,0), tuple(player_pos), tuple(enemy_pos)]
                and (r, c) not in occupied
            ]
            if candidates:
                nr, nc = random.choice(candidates)
                d['r'], d['c'] = nr, nc
                d['collected'] = False
                occupied.add((nr, nc))


# ── BFS enemy ─────────────────────────────────────────────────────────────────
def bfs(start, goal):
    queue   = deque([start])
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
            nr, nc = r+dr, c+dc
            if (0 <= nr < ROWS and 0 <= nc < COLS
                    and maze[nr][nc] == 0
                    and (nr,nc) not in visited):
                visited[(nr,nc)] = current
                queue.append((nr,nc))
    return []

def move_enemy():
    global enemy_pos
    path = bfs(tuple(enemy_pos), tuple(player_pos))
    if len(path) > 1:
        enemy_pos[0], enemy_pos[1] = path[1]


# ── leaderboard screen ────────────────────────────────────────────────────────
def draw_leaderboard_screen(final_score):
    lb = add_to_leaderboard(final_score)
    screen.fill((10, 10, 20))

    title = big_font.render("LEADERBOARD", True, YELLOW)
    screen.blit(title, (WIN_W//2 - title.get_width()//2, 40))

    medals = ["1ST", "2ND", "3RD", "4TH", "5TH"]
    for i, s in enumerate(lb):
        col = (255, 215, 0) if s == final_score else WHITE
        row = hud_font.render(f"  {medals[i]}   {s:05d}", True, col)
        screen.blit(row, (WIN_W//2 - row.get_width()//2, 110 + i*46))

    sub = font.render("R  to play again        ESC  to quit", True, GRAY)
    screen.blit(sub, (WIN_W//2 - sub.get_width()//2, WIN_H - 55))
    pygame.display.flip()


# ── restart ────────────────────────────────────────────────────────────────────
def restart_game():
    global maze, score, game_over, start_time
    global last_switch_time, last_enemy_move
    global enemy_move_delay, switch_cooldown, current_level, level_label
    global powerup, powerup_active, powerup_end_time, powerup_next_spawn

    maze          = make_maze()
    player_pos[:] = [0, 0]
    enemy_pos[:]  = [ROWS-1, 0]

    diamonds.clear()
    for (_r, _c) in DIAMOND_POSITIONS:
        maze[_r][_c] = 0
        diamonds.append({'r': _r, 'c': _c, 'collected': False, 'respawn_at': 0})

    score              = 0
    game_over          = False
    start_time         = time.time()
    last_switch_time   = time.time()
    last_enemy_move    = time.time()
    enemy_move_delay   = SPEED_LEVELS[0][1]
    switch_cooldown    = SPEED_LEVELS[0][2]
    current_level      = 0
    level_label        = SPEED_LEVELS[0][3]
    powerup            = None
    powerup_active     = False
    powerup_end_time   = 0.0
    powerup_next_spawn = time.time() + 12.0

    particles.clear()
    popups.clear()


# ── leaderboard wait loop (reusable) ──────────────────────────────────────────
def show_leaderboard_and_wait(final_score, clock):
    """Show leaderboard, block until R (restart) or ESC (quit).
    Returns True if restarting, False if quitting."""
    draw_leaderboard_screen(final_score)
    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return False
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    return False
                elif ev.key == pygame.K_r:
                    restart_game()
                    return True
        clock.tick(30)


# ── main loop ──────────────────────────────────────────────────────────────────
def main():
    global flash_alpha, game_over, game_over_message, high_score
    global last_enemy_move, last_switch_time
    global powerup_active, powerup_end_time, powerup_next_spawn
    bgm.set_volume(0.4)

    clock                = pygame.time.Clock()
    running              = True
    time_up_sound_played = False

    while running:
        current_time = time.time()
        remaining    = max(0, int(TOTAL_TIME - (current_time - start_time)))

        # ── time up ────────────────────────────────────────────────────────────
        if remaining <= 0 and not game_over:
            if not time_up_sound_played:
                snd_fail.play()
                time_up_sound_played = True
                high_score = max(high_score, score)
            keep_playing = show_leaderboard_and_wait(score, clock)
            if keep_playing:
                time_up_sound_played = False
                continue
            else:
                break

        # ── powerup expiry ─────────────────────────────────────────────────────
        if powerup_active and current_time > powerup_end_time:
            powerup_active = False

        # ── powerup spawn ──────────────────────────────────────────────────────
        if not game_over and powerup is None and current_time >= powerup_next_spawn:
            try_spawn_powerup()
            powerup_next_spawn = current_time + 12.0

        # ── maze shuffle ───────────────────────────────────────────────────────
        if not game_over and current_time - last_switch_time > switch_cooldown:
            switch_maze()
            last_switch_time = current_time

        # ── enemy move ─────────────────────────────────────────────────────────
        if not game_over and current_time - last_enemy_move > enemy_move_delay:
            move_enemy()
            last_enemy_move = current_time

        # ── respawn ────────────────────────────────────────────────────────────
        if not game_over:
            respawn_diamonds()

        # ── draw ───────────────────────────────────────────────────────────────
        screen.fill(BLACK)
        draw_maze()
        draw_player()
        draw_enemy()
        update_and_draw_particles()
        update_and_draw_popups()

        # ── enemy collision ────────────────────────────────────────────────────
        if enemy_pos == player_pos and not game_over:
            snd_fail.play()
            trigger_flash((255, 0, 0), 200)
            high_score        = max(high_score, score)
            game_over         = True
            game_over_message = "CAUGHT!   R for leaderboard"

        draw_hud(remaining)

        # ── game-over overlay ──────────────────────────────────────────────────
        if game_over:
            overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 180))
            screen.blit(overlay, (0, 0))

            msg = big_font.render(game_over_message, True, RED)
            screen.blit(msg, (WIN_W//2 - msg.get_width()//2,
                               MAZE_OFFSET_Y + MAZE_HEIGHT//2 - 40))
            sc  = hud_font.render(f"Score: {score}   Best: {high_score}", True, YELLOW)
            screen.blit(sc, (WIN_W//2 - sc.get_width()//2,
                              MAZE_OFFSET_Y + MAZE_HEIGHT//2 + 8))

        draw_screen_flash()
        if flash_alpha > 0:
            flash_alpha = max(0, flash_alpha - FLASH_DECAY)

        # ── events ─────────────────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

                elif game_over:
                    if event.key == pygame.K_r:
                        keep_playing = show_leaderboard_and_wait(score, clock)
                        if not keep_playing:
                            running = False

                else:
                    move_player(event.key)
                    check_diamonds()
                    check_powerup()

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()