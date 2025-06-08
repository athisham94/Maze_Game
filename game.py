import pygame
import random
import time
import math

# --- Initialize Pygame ---
pygame.init()

# --- Configurations ---
WIDTH, HEIGHT = 600, 600
ROWS, COLS = 10, 10
TILE = WIDTH // COLS
switch_cooldown = 6
TOTAL_TIME = 80

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (180, 180, 180)
RED = (255, 0, 0)
GREEN = (0, 200, 0)
BLUE = (0, 0, 255)

# Load assets
try:
    background_img = pygame.transform.scale(pygame.image.load('assets/textures/background.png'), (WIDTH, HEIGHT))
except pygame.error:
    print("Warning: Background image failed to load.")
    background_img = None

wall_img = pygame.transform.scale(pygame.image.load('assets/textures/wall.png'), (TILE, TILE))
player_img = pygame.transform.scale(pygame.image.load('assets/textures/player.png'), (TILE - 1, TILE - 1))
clue_img = pygame.transform.scale(pygame.image.load('assets/textures/diamond.png'), (30, 30))
exit_img = pygame.transform.scale(pygame.image.load('assets/textures/exit.png'), (TILE, TILE))

# Fonts
font = pygame.font.SysFont(None, 24)
big_font = pygame.font.SysFont(None, 40)

# Maze setup
maze = [[0]*COLS for _ in range(ROWS)]
for r in range(ROWS):
    for c in range(COLS):
        if random.random() < 0.3 and not (r == 0 and c == 0) and not (r == ROWS-1 and c == COLS-1):
            maze[r][c] = 1

player_pos = [0, 0]
clue_positions = [(2, 3), (4, 5), (7, 2)]
clues = {
    (2, 3): "First clue: Look for the hidden code.",
    (4, 5): "Second clue: The code is MAGIC.",
    (7, 2): "Third clue: Press 'C' to enter code."
}

# Ensure no clue is inside wall at start
for pos in clue_positions:
    maze[pos[0]][pos[1]] = 0

clues_found = set()
code_input_active = False
code_input_text = ""
code_message = ""
game_won = False
graffiti_falling = False
graffiti_fall_pos = []
last_switch_time = time.time()
start_time = time.time()

screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Endless Maze with Secret Code")

# --- Functions ---
def start_graffiti():
    global graffiti_falling, graffiti_fall_pos
    graffiti_falling = True
    graffiti_fall_pos = []
    base_x, base_y = (COLS-1)*TILE + 10, (ROWS-1)*TILE + 5
    for i in range(5):
        graffiti_fall_pos.append([base_x + i*8, base_y - 50 - i*15])

def draw_graffiti():
    gravity = 4
    for pos in graffiti_fall_pos:
        pos[1] += gravity
        pygame.draw.rect(screen, (200, 0, 200), (*pos, 15, 15))

def draw_maze():
    if background_img:
        screen.blit(background_img, (0, 0))
    else:
        screen.fill(WHITE)

    for r in range(ROWS):
        for c in range(COLS):
            rect = pygame.Rect(c*TILE, r*TILE, TILE, TILE)
            if maze[r][c] == 1:
                screen.blit(wall_img, rect)
            pygame.draw.rect(screen, GRAY, rect, 1)

    for (r, c), _ in clues.items():
        if (r, c) not in clues_found:
            y_offset = int(5 * math.sin(time.time() * 3))
            screen.blit(clue_img, (c*TILE + 15, r*TILE + 15 + y_offset))

    if game_won:
        screen.blit(exit_img, ((COLS-1)*TILE, (ROWS-1)*TILE))

def draw_player():
    screen.blit(player_img, (player_pos[1]*TILE+5, player_pos[0]*TILE+5))

def draw_text(text, pos, color=BLACK):
    screen.blit(font.render(text, True, color), pos)

def draw_code_input():
    rect = pygame.Rect(WIDTH//4, HEIGHT//3, WIDTH//2, 50)
    pygame.draw.rect(screen, WHITE, rect)
    pygame.draw.rect(screen, BLACK, rect, 2)
    screen.blit(font.render("Enter secret code (ESC to cancel):", True, BLACK), (rect.x + 10, rect.y - 25))
    screen.blit(font.render(code_input_text, True, BLACK), (rect.x + 10, rect.y + 10))
    screen.blit(font.render(code_message, True, RED if "Incorrect" in code_message else GREEN), (rect.x, rect.y + 60))

def switch_maze():
    walls = [(r, c) for r in range(ROWS) for c in range(COLS)
             if maze[r][c] == 1 and (r,c) not in [(0,0),(ROWS-1,COLS-1)]]
    empty = [(r, c) for r in range(ROWS) for c in range(COLS)
             if maze[r][c] == 0 and (r,c) not in [(0,0),(ROWS-1,COLS-1)]]
    if len(walls) >= 5 and len(empty) >= 5:
        for w, e in zip(random.sample(walls, 5), random.sample(empty, 5)):
            maze[w[0]][w[1]] = 0
            maze[e[0]][e[1]] = 1

def check_clue():
    pos = tuple(player_pos)
    if pos in clues and pos not in clues_found:
        clues_found.add(pos)
        return clues[pos]
    return ""

def move_player(key):
    r, c = player_pos
    if key == pygame.K_UP and r > 0 and maze[r-1][c] == 0:
        player_pos[0] -= 1
    elif key == pygame.K_DOWN and r < ROWS-1 and maze[r+1][c] == 0:
        player_pos[0] += 1
    elif key == pygame.K_LEFT and c > 0 and maze[r][c-1] == 0:
        player_pos[1] -= 1
    elif key == pygame.K_RIGHT and c < COLS-1 and maze[r][c+1] == 0:
        player_pos[1] += 1

# --- Game Loop ---
def main():
    global code_input_active, code_input_text, code_message, game_won, graffiti_falling, last_switch_time
    clock = pygame.time.Clock()
    running = True
    clue_hint = ""

    while running:
        current_time = time.time()
        remaining = max(0, int(TOTAL_TIME - (current_time - start_time)))

        if remaining <= 0:
            draw_text("Time's up! You failed!", (WIDTH//2 - 100, HEIGHT//2), RED)
            pygame.display.flip()
            pygame.time.wait(3000)
            break

        if not game_won and current_time - last_switch_time > switch_cooldown:
            switch_maze()
            last_switch_time = current_time

        draw_maze()
        draw_player()
        draw_text(f"Clues found: {len(clues_found)}/{len(clues)}", (10, 10))
        draw_text(f"Time left: {remaining}s", (WIDTH - 150, 10), RED)
        if clue_hint:
            draw_text(clue_hint, (10, HEIGHT - 30))

        if graffiti_falling:
            draw_graffiti()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if code_input_active:
                    if event.key == pygame.K_RETURN:
                        if code_input_text.strip().upper() == "MAGIC":
                            game_won = True
                            code_message = "Correct! Hole created! Go through exit!"
                            code_input_active = False
                            maze[ROWS-1][COLS-2] = 0
                            maze[ROWS-1][COLS-1] = 0
                            start_graffiti()
                        else:
                            code_message = "Incorrect code! Try again."
                            code_input_text = ""
                    elif event.key == pygame.K_ESCAPE:
                        code_input_active = False
                        code_input_text = ""
                        code_message = ""
                    elif event.key == pygame.K_BACKSPACE:
                        code_input_text = code_input_text[:-1]
                    else:
                        if len(code_input_text) < 12:
                            code_input_text += event.unicode
                else:
                    if event.key == pygame.K_c and len(clues_found) == len(clues):
                        code_input_active = True
                        code_input_text = ""
                        code_message = ""
                    else:
                        move_player(event.key)
                        clue_hint = check_clue()

        if code_input_active:
            draw_code_input()

        if game_won:
            draw_text("Secret hole opened! Escape now!", (WIDTH//2 - 150, 50), GREEN)
            if tuple(player_pos) == (ROWS-1, COLS-1):
                draw_text("You escaped! Congrats!", (WIDTH//2 - 130, HEIGHT//2), BLUE)
                pygame.display.flip()
                pygame.time.wait(3000)
                running = False

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()

if __name__ == "__main__":
    main()
