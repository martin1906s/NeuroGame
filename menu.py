import cv2
import mediapipe as mp
import pygame
import random
import sys
import math
import numpy as np
from pygame import mixer
from pygame import gfxdraw
from collections import deque
import time

# Inicialización de MediaPipe Hands
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(max_num_hands=1, min_detection_confidence=0.7, min_tracking_confidence=0.5)
mp_drawing = mp.solutions.drawing_utils

# Configuración de PyGame
pygame.init()
mixer.init()
WIDTH, HEIGHT = 1280, 720
SCREEN_WIDTH, SCREEN_HEIGHT = 1024, 768  # Para Torre de Bloques
screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.DOUBLEBUF)
pygame.display.set_caption("Juegos Combinados")

# Sistema de temas unificado
THEMES = {
    "Neon": {
        "snake": (0, 255, 0),
        "food": (255, 0, 255),
        "powerup": (0, 255, 255),
        "bg": (10, 10, 20),
        "trail": (0, 100, 100)
    },
    "Retro": {
        "snake": (0, 255, 0),
        "food": (255, 0, 0),
        "powerup": (255, 255, 0),
        "bg": (0, 0, 0),
        "trail": (0, 80, 0)
    },
    "Clásico": {
        "colors": [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255)],
        "bg": (240, 240, 240)
    },
    "Nocturno": {
        "colors": [(70, 130, 180), (100, 149, 237), (123, 104, 238), (138, 43, 226), (147, 112, 219)],
        "bg": (30, 30, 40)
    },
    "Naturaleza": {
        "colors": [(34, 139, 34), (107, 142, 35), (152, 251, 152), (60, 179, 113), (46, 139, 87)],
        "bg": (245, 245, 220)
    }
}

# Variables globales para Torre de Bloques
TOWER_X = SCREEN_WIDTH // 2 - 40
TOWER_Y = SCREEN_HEIGHT // 2
zone_glow_alpha = 0
zone_pulse_direction = 1
target_block_ghost = None
current_theme = "Neon"
difficulty = "Normal"

# Clase de partícula compartida
class Particle:
    def __init__(self, x, y, color, velocity=(0, 0), lifetime=30, size=None):
        self.x = x
        self.y = y
        self.color = color
        self.velocity = list(velocity)
        self.lifetime = lifetime
        self.age = 0
        self.size = size if size else random.randint(3, 8)
        
    def update(self):
        self.x += self.velocity[0]
        self.y += self.velocity[1]
        self.velocity[1] += 0.1  # Gravedad
        self.age += 1
        self.size = max(0, self.size * 0.95)
        
    def draw(self, surface):
        alpha = min(255, int(255 * (1 - self.age/self.lifetime)))
        color = (*self.color[:3], alpha)
        gfxdraw.filled_circle(surface, int(self.x), int(self.y), int(self.size), color)

# Clase para el juego de bloques
class Block:
    def __init__(self, width=80, height=30, color=None):
        self.width = width
        self.height = height
        self.spawn_position(width, height)
        self.color = color if color else random.choice(THEMES[current_theme]["colors"])
        self.grabbed = False
        self.attempts = 0
        self.rotation = 0
        self.target_rotation = 0
        self.scale = 1.0
        self.target_scale = 1.0
        self.particles = []
        
    def spawn_position(self, width, height):
        while True:
            x = random.randint(50, SCREEN_WIDTH - 50 - width)
            y = random.randint(50, SCREEN_HEIGHT // 2 - 50)
            distance_to_tower = math.sqrt((x - TOWER_X)**2 + (y - TOWER_Y)**2)
            if distance_to_tower > 200:
                break
        self.x = x
        self.y = y
    
    def add_particles(self, count=10):
        for _ in range(count):
            self.particles.append(Particle(
                self.x + random.randint(0, self.width),
                self.y + random.randint(0, self.height),
                self.color,
                (random.uniform(-1, 1), random.uniform(-1, 1)),
                random.randint(20, 40)
            ))
    
    def update(self):
        self.rotation += (self.target_rotation - self.rotation) * 0.1
        self.scale += (self.target_scale - self.scale) * 0.1
        for particle in self.particles[:]:
            particle.update()
            if particle.age >= particle.lifetime:
                self.particles.remove(particle)
    
    def draw(self, surface):
        for particle in self.particles:
            particle.draw(surface)
        block_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        pygame.draw.rect(block_surface, self.color, (0, 0, self.width, self.height))
        pygame.draw.rect(block_surface, (0, 0, 0), (0, 0, self.width, self.height), 2)
        scaled_width = int(self.width * self.scale)
        scaled_height = int(self.height * self.scale)
        scaled_surface = pygame.transform.scale(block_surface, (scaled_width, scaled_height))
        rotated_surface = pygame.transform.rotate(scaled_surface, self.rotation)
        rotated_rect = rotated_surface.get_rect(center=(self.x + self.width//2, self.y + self.height//2))
        surface.blit(rotated_surface, rotated_rect)
        font = pygame.font.SysFont('Arial', 20)
        attempts_text = font.render(str(self.attempts), True, (0, 0, 0))
        text_rect = attempts_text.get_rect(center=(self.x + self.width//2, self.y + self.height//2))
        surface.blit(attempts_text, text_rect)
    
    def is_over(self, pos):
        return (self.x <= pos[0] <= self.x + self.width and 
                self.y <= pos[1] <= self.y + self.height)

# Clase para la serpiente
class Snake:
    def __init__(self):
        self.reset()
        
    def reset(self):
        self.positions = deque([(WIDTH//2, HEIGHT//2)])
        self.direction = (1, 0)
        self.length = 3
        self.score = 0
        self.speed = 10
        self.level = 1
        self.growth_pending = 0
        self.trail_particles = []
        
    def get_head_position(self):
        return self.positions[0]
    
    def update(self):
        head = self.get_head_position()
        x, y = self.direction
        new_head = (
            (head[0] + (x * 20)) % WIDTH,
            (head[1] + (y * 20)) % HEIGHT
        )
        if new_head in list(self.positions)[1:]:
            return False
        self.positions.appendleft(new_head)
        if self.growth_pending > 0:
            self.growth_pending -= 1
        else:
            if len(self.positions) > self.length:
                self.positions.pop()
        if random.random() < 0.3:
            self.trail_particles.append(Particle(
                head[0] + 10, head[1] + 10,
                THEMES[current_theme]["trail"],
                (random.uniform(-1, 1), random.uniform(-1, 1)),
                random.randint(20, 40)
            ))
        return True
    
    def change_direction(self, direction):
        if (direction[0] * -1, direction[1] * -1) != self.direction:
            self.direction = direction
    
    def draw(self, surface):
        for particle in self.trail_particles[:]:
            particle.update()
            particle.draw(surface)
            if particle.age >= particle.lifetime:
                self.trail_particles.remove(particle)
        for i, p in enumerate(self.positions):
            alpha = 255 - int(200 * (i / len(self.positions)))
            color = (*THEMES[current_theme]["snake"], alpha)
            pygame.draw.rect(surface, color, (p[0], p[1], 20, 20), border_radius=4)
            border_color = (min(color[0]+50, 255), min(color[1]+50, 255), min(color[2]+50, 255))
            pygame.draw.rect(surface, border_color, (p[0], p[1], 20, 20), 2, border_radius=4)

# Clase para la comida
class Food:
    def __init__(self):
        self.positions = []
        self.particles = []
        
    def spawn_food(self, snake_positions):
        available_positions = [
            (x, y) for x in range(20, WIDTH-20, 20) 
            for y in range(20, HEIGHT-20, 20)
            if (x, y) not in snake_positions
        ]
        if available_positions and (not self.positions or random.random() < 0.1):
            self.positions.append(random.choice(available_positions))
    
    def draw(self, surface):
        for particle in self.particles[:]:
            particle.update()
            particle.draw(surface)
            if particle.age >= particle.lifetime:
                self.particles.remove(particle)
        for pos in self.positions:
            pygame.draw.rect(surface, THEMES[current_theme]["food"], (pos[0], pos[1], 20, 20), border_radius=10)

# Funciones auxiliares
def cv2_to_pygame(image):
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    return pygame.image.frombuffer(image.tobytes(), image.shape[1::-1], "RGB")

def get_hand_landmarks(frame):
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = hands.process(frame_rgb)
    if results.multi_hand_landmarks:
        return results.multi_hand_landmarks[0]
    return None

def get_finger_direction(landmarks):
    wrist = landmarks.landmark[0]
    index_tip = landmarks.landmark[8]
    dx = index_tip.x - wrist.x
    dy = index_tip.y - wrist.y
    threshold = 0.1
    if abs(dx) > abs(dy):
        if dx > threshold:
            return (1, 0)
        elif dx < -threshold:
            return (-1, 0)
    else:
        if dy > threshold:
            return (0, 1)
        elif dy < -threshold:
            return (0, -1)
    return None

# Funciones específicas de Torre de Bloques
def draw_button(surface, text, rect, color, hover_color, text_color=(255, 255, 255)):
    mouse_pos = pygame.mouse.get_pos()
    is_hovered = rect.collidepoint(mouse_pos)
    button_color = hover_color if is_hovered else color
    pygame.draw.rect(surface, button_color, rect, border_radius=10)
    pygame.draw.rect(surface, (0, 0, 0), rect, 2, border_radius=10)
    font = pygame.font.SysFont('Arial', 24)
    text_surface = font.render(text, True, text_color)
    text_rect = text_surface.get_rect(center=rect.center)
    surface.blit(text_surface, text_rect)
    return is_hovered

def draw_tower_zone(surface, current_block, tower_height):
    global zone_glow_alpha, zone_pulse_direction, target_block_ghost
    pygame.draw.rect(surface, (180, 180, 180), (TOWER_X, tower_height, current_block.width, TOWER_Y - tower_height))
    zone_glow_alpha += zone_pulse_direction * 3
    if zone_glow_alpha > 150 or zone_glow_alpha < 0:
        zone_pulse_direction *= -1
    zone_glow_alpha = max(0, min(150, zone_glow_alpha))
    glow_surface = pygame.Surface((current_block.width + 4, TOWER_Y - tower_height + 4), pygame.SRCALPHA)
    glow_color = (100, 255, 100, int(zone_glow_alpha))
    pygame.draw.rect(glow_surface, glow_color, (0, 0, current_block.width + 4, TOWER_Y - tower_height + 4), 4)
    surface.blit(glow_surface, (TOWER_X - 2, tower_height - 2))
    if target_block_ghost is None:
        target_block_ghost = pygame.Surface((current_block.width, current_block.height), pygame.SRCALPHA)
        pygame.draw.rect(target_block_ghost, (*current_block.color[:3], 80), (0, 0, current_block.width, current_block.height))
    surface.blit(target_block_ghost, (TOWER_X, tower_height - current_block.height))
    font = pygame.font.SysFont('Arial', 22, bold=True)
    text = font.render("¡COLÓCAME AQUÍ!", True, (255, 255, 255))
    text_rect = text.get_rect(center=(TOWER_X + current_block.width//2, tower_height - 30))
    surface.blit(text, text_rect)

def draw_menu_blocks():
    global current_theme, difficulty
    screen.fill(THEMES[current_theme]["bg"])
    title_font = pygame.font.SysFont('Arial', 60)
    title_text = title_font.render("Torre de Bloques Mágica", True, (0, 0, 0))
    title_rect = title_text.get_rect(center=(SCREEN_WIDTH//2, 100))
    screen.blit(title_text, title_rect)
    easy_rect = pygame.Rect(SCREEN_WIDTH//2 - 150, 200, 300, 50)
    normal_rect = pygame.Rect(SCREEN_WIDTH//2 - 150, 270, 300, 50)
    hard_rect = pygame.Rect(SCREEN_WIDTH//2 - 150, 340, 300, 50)
    easy_color = (100, 200, 100) if difficulty == "Fácil" else (150, 150, 150)
    normal_color = (100, 150, 200) if difficulty == "Normal" else (150, 150, 150)
    hard_color = (200, 100, 100) if difficulty == "Difícil" else (150, 150, 150)
    if draw_button(screen, "Fácil", easy_rect, easy_color, (120, 220, 120)):
        if pygame.mouse.get_pressed()[0]:
            difficulty = "Fácil"
    if draw_button(screen, "Normal", normal_rect, normal_color, (120, 170, 220)):
        if pygame.mouse.get_pressed()[0]:
            difficulty = "Normal"
    if draw_button(screen, "Difícil", hard_rect, hard_color, (220, 120, 120)):
        if pygame.mouse.get_pressed()[0]:
            difficulty = "Difícil"
    theme_y = 440
    for i, theme in enumerate(["Clásico", "Nocturno", "Naturaleza"]):
        theme_rect = pygame.Rect(SCREEN_WIDTH//2 - 150 + (i-1)*160, theme_y, 140, 50)
        theme_color = THEMES[theme]["colors"][0] if current_theme != theme else THEMES[theme]["colors"][2]
        if draw_button(screen, theme, theme_rect, theme_color, THEMES[theme]["colors"][1]):
            if pygame.mouse.get_pressed()[0]:
                current_theme = theme
    start_rect = pygame.Rect(SCREEN_WIDTH//2 - 100, 520, 200, 60)
    if draw_button(screen, "Comenzar", start_rect, (100, 200, 100), (120, 220, 120)):
        if pygame.mouse.get_pressed()[0]:
            return False
    return True

# Funciones específicas de Snake
def show_start_screen_snake():
    title_font = pygame.font.SysFont('Arial', 80, bold=True)
    subtitle_font = pygame.font.SysFont('Arial', 30)
    title_text = title_font.render("SNAKE VISION", True, (0, 255, 0))
    subtitle_text = subtitle_font.render("Usa tu mano para controlar la serpiente", True, (200, 200, 200))
    start_text = subtitle_font.render("Presiona ESPACIO para comenzar", True, (255, 255, 255))
    waiting = True
    while waiting:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                waiting = False
        screen.fill(THEMES[current_theme]["bg"])
        screen.blit(title_text, (WIDTH//2 - title_text.get_width()//2, HEIGHT//3))
        screen.blit(subtitle_text, (WIDTH//2 - subtitle_text.get_width()//2, HEIGHT//2))
        screen.blit(start_text, (WIDTH//2 - start_text.get_width()//2, HEIGHT//2 + 100))
        pygame.display.flip()
        pygame.time.delay(30)

def show_game_over_screen_snake(score, level):
    font_large = pygame.font.SysFont('Arial', 72, bold=True)
    font_medium = pygame.font.SysFont('Arial', 36)
    game_over_text = font_large.render("GAME OVER", True, (255, 0, 0))
    score_text = font_medium.render(f"Puntuación final: {score}", True, (255, 255, 255))
    level_text = font_medium.render(f"Nivel alcanzado: {level}", True, (255, 255, 255))
    restart_text = font_medium.render("Presiona ESPACIO para reiniciar", True, (200, 200, 200))
    waiting = True
    while waiting:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                waiting = False
        screen.fill(THEMES[current_theme]["bg"])
        screen.blit(game_over_text, (WIDTH//2 - game_over_text.get_width()//2, HEIGHT//3))
        screen.blit(score_text, (WIDTH//2 - score_text.get_width()//2, HEIGHT//2))
        screen.blit(level_text, (WIDTH//2 - level_text.get_width()//2, HEIGHT//2 + 50))
        screen.blit(restart_text, (WIDTH//2 - restart_text.get_width()//2, HEIGHT//2 + 120))
        pygame.display.flip()
        pygame.time.delay(30)

# Menú principal
def show_game_selection():
    global current_theme
    current_theme = "Neon"  # Tema inicial para el menú
    font = pygame.font.SysFont('Arial', 60, bold=True)
    title_text = font.render("Selecciona un juego", True, (255, 255, 255))
    snake_button = pygame.Rect(WIDTH//2 - 150, HEIGHT//2 - 100, 300, 50)
    blocks_button = pygame.Rect(WIDTH//2 - 150, HEIGHT//2 + 50, 300, 50)
    theme_rect = pygame.Rect(WIDTH//2 - 100, HEIGHT//2 + 150, 200, 50)
    while True:
        screen.fill(THEMES["Neon"]["bg"])
        screen.blit(title_text, (WIDTH//2 - title_text.get_width()//2, HEIGHT//3))
        pygame.draw.rect(screen, (0, 255, 0), snake_button)
        pygame.draw.rect(screen, (255, 0, 0), blocks_button)
        snake_text = font.render("Snake", True, (0, 0, 0))
        blocks_text = font.render("Bloques", True, (0, 0, 0))
        screen.blit(snake_text, (snake_button.centerx - snake_text.get_width()//2, snake_button.centery - snake_text.get_height()//2))
        screen.blit(blocks_text, (blocks_button.centerx - blocks_text.get_width()//2, blocks_button.centery - blocks_text.get_height()//2))
        if draw_button(screen, f"Tema Snake: {current_theme}", theme_rect, (100, 100, 100), (150, 150, 150)):
            if pygame.mouse.get_pressed()[0]:
                current_theme = "Retro" if current_theme == "Neon" else "Neon"
        pygame.display.flip()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if snake_button.collidepoint(event.pos):
                    current_theme = "Neon"  # Asegurar tema válido para Snake
                    return "snake"
                elif blocks_button.collidepoint(event.pos):
                    current_theme = "Clásico"  # Tema inicial para Bloques
                    return "blocks"
# Juego de bloques
def play_blocks():
    global current_theme, difficulty, zone_glow_alpha, zone_pulse_direction, target_block_ghost
    current_theme = "Clásico"
    difficulty = "Normal"
    zone_glow_alpha = 0
    zone_pulse_direction = 1
    target_block_ghost = None
    grab_sound = drop_sound = success_sound = level_up_sound = game_over_sound = None
    try:
        if pygame.mixer.get_init():
            grab_sound = mixer.Sound('grab.wav') if pygame.mixer.get_init() else None
            drop_sound = mixer.Sound('drop.wav') if pygame.mixer.get_init() else None
            success_sound = mixer.Sound('success.wav') if pygame.mixer.get_init() else None
            level_up_sound = mixer.Sound('level_up.wav') if pygame.mixer.get_init() else None
            game_over_sound = mixer.Sound('game_over.wav') if pygame.mixer.get_init() else None
    except:
        pass
    current_block = Block()
    tower = []
    tower_height = TOWER_Y
    max_tower_height = TOWER_Y - 200
    game_over = False
    score = 0
    high_score = 0
    level = 1
    block_width_decrease = 5
    game_start_time = time.time()
    particles = []
    show_menu = True
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: No se pudo abrir la cámara")
        return
    running = True
    clock = pygame.time.Clock()
    try:
        while running:
            ret, frame = cap.read()
            if not ret:
                print("Error: No se pudo leer el frame de la cámara")
                continue
            frame = cv2.flip(frame, 1)
            h, w, _ = frame.shape
            landmarks = get_hand_landmarks(frame)
            if landmarks:
                mp_drawing.draw_landmarks(frame, landmarks, mp_hands.HAND_CONNECTIONS)
            bg = cv2_to_pygame(frame)
            bg = pygame.transform.scale(bg, (SCREEN_WIDTH, SCREEN_HEIGHT))
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_r and (game_over or show_menu):
                        current_block = Block(80 - (level-1)*block_width_decrease)
                        tower = []
                        tower_height = TOWER_Y
                        game_over = False
                        score = 0
                        level = 1
                        game_start_time = time.time()
                        show_menu = False
                        target_block_ghost = None
                    elif event.key == pygame.K_m:
                        show_menu = not show_menu
                    elif event.key == pygame.K_ESCAPE:
                        running = False
            if show_menu:
                show_menu = draw_menu_blocks()
                pygame.display.flip()
                clock.tick(30)
                continue
            if not game_over and landmarks:
                index_tip = landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
                hand_x = int(index_tip.x * SCREEN_WIDTH)
                hand_y = int(index_tip.y * SCREEN_HEIGHT)
                if current_block.is_over((hand_x, hand_y)) or current_block.grabbed:
                    if not current_block.grabbed:
                        current_block.grabbed = True
                        current_block.add_particles(15)
                        current_block.target_rotation = random.uniform(-10, 10)
                        current_block.target_scale = 1.1
                        if grab_sound: grab_sound.play()
                    current_block.x = hand_x - current_block.width//2
                    current_block.y = hand_y - current_block.height//2
                    if (abs(current_block.x + current_block.width/2 - (TOWER_X + current_block.width/2)) <= 20 and 
                        abs(current_block.y - (tower_height - current_block.height)) <= 10):
                        tower.append(current_block)
                        tower_height -= current_block.height
                        score += max(1, 5 - current_block.attempts)
                        for _ in range(50):
                            particles.append(Particle(
                                TOWER_X + current_block.width//2,
                                tower_height,
                                (255, 255, 100)
                            ))
                        if success_sound: success_sound.play()
                        for block in tower:
                            block.y += 5
                        current_block.grabbed = False
                        if tower_height <= max_tower_height:
                            level += 1
                            if level > 10:
                                game_over = True
                                if game_over_sound: game_over_sound.play()
                                high_score = max(high_score, score)
                            else:
                                tower_height = TOWER_Y
                                tower = []
                                if level_up_sound: level_up_sound.play()
                        block_width = max(30, 80 - (level-1)*block_width_decrease)
                        current_block = Block(block_width)
                        current_block.grabbed = False
                        target_block_ghost = None
                else:
                    if current_block.grabbed:
                        current_block.grabbed = False
                        current_block.attempts += 1
                        current_block.target_rotation = 0
                        current_block.target_scale = 1.0
                        current_block.add_particles(10)
                        if drop_sound: drop_sound.play()
            for particle in particles[:]:
                particle.update()
                if particle.age >= particle.lifetime:
                    particles.remove(particle)
            current_block.update()
            screen.blit(bg, ((WIDTH - SCREEN_WIDTH) // 2, (HEIGHT - SCREEN_HEIGHT) // 2))
            draw_tower_zone(screen, current_block, tower_height)
            for block in tower:
                block.draw(screen)
            current_block.draw(screen)
            for particle in particles:
                particle.draw(screen)
            font = pygame.font.SysFont('Arial', 30)
            elapsed_time = time.time() - game_start_time
            info_texts = [
                f'Puntuación: {score}',
                f'Récord: {high_score}',
                f'Nivel: {level}',
                f'Intentos: {current_block.attempts}',
                f'Tiempo: {int(elapsed_time)}s'
            ]
            pygame.draw.rect(screen, (0, 0, 0, 128), (10, 10, 300, 180))
            for i, text in enumerate(info_texts):
                text_surface = font.render(text, True, (255, 255, 255))
                screen.blit(text_surface, (20, 20 + i * 30))
            instruction_font = pygame.font.SysFont('Arial', 20)
            instructions = [
                'Instrucciones:',
                'Mueve el dedo índice sobre el bloque',
                'para arrastrarlo a la zona gris',
                'Presiona M para menú, R para reiniciar'
            ]
            for i, text in enumerate(instructions):
                text_surface = instruction_font.render(text, True, (255, 255, 255))
                screen.blit(text_surface, (20, 180 + i * 20))
            if game_over:
                overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 180))
                screen.blit(overlay, (0, 0))
                font_large = pygame.font.SysFont('Arial', 50)
                game_over_text = font_large.render('¡Juego Completado!', True, (255, 255, 255))
                score_text = font.render(f'Puntuación final: {score}', True, (255, 255, 255))
                time_text = font.render(f'Tiempo: {int(elapsed_time)} segundos', True, (255, 255, 255))
                restart_text = font.render('Presiona R para reiniciar', True, (255, 255, 255))
                text_rect = game_over_text.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2 - 80))
                score_rect = score_text.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2 - 20))
                time_rect = time_text.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2 + 20))
                restart_rect = restart_text.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2 + 80))
                screen.blit(game_over_text, text_rect)
                screen.blit(score_text, score_rect)
                screen.blit(time_text, time_rect)
                screen.blit(restart_text, restart_rect)
            pygame.display.flip()
            clock.tick(60)
    finally:
        cap.release()

# Juego de la serpiente
def play_snake():
    global current_theme
    current_theme = "Neon"  # Forzar tema válido para Snake
    snake = Snake()
    food = Food()
    clock = pygame.time.Clock()
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: No se pudo abrir la cámara")
        return
    show_start_screen_snake()
    running = True
    try:
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
            ret, frame = cap.read()
            if not ret:
                continue
            frame = cv2.flip(frame, 1)
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(frame_rgb)
            if results.multi_hand_landmarks:
                for hand_landmarks in results.multi_hand_landmarks:
                    direction = get_finger_direction(hand_landmarks)
                    if direction:
                        snake.change_direction(direction)
            if not snake.update():
                show_game_over_screen_snake(snake.score, snake.level)
                snake.reset()
                food = Food()
                continue
            head_pos = snake.get_head_position()
            for food_pos in food.positions[:]:
                if head_pos == food_pos:
                    food.positions.remove(food_pos)
                    snake.growth_pending += 1
                    snake.score += 10 * snake.level
                    for _ in range(20):
                        food.particles.append(Particle(
                            food_pos[0] + 10, food_pos[1] + 10,
                            THEMES[current_theme]["food"],
                            (random.uniform(-3, 3), random.uniform(-3, 3)),
                            random.randint(20, 40)
                        ))
                    if snake.score >= snake.level * 50:
                        snake.level += 1
                        snake.speed += 1
                    break
            food.spawn_food(snake.positions)
            screen.fill(THEMES[current_theme]["bg"])
            food.draw(screen)
            snake.draw(screen)
            font = pygame.font.SysFont('Arial', 30)
            score_text = font.render(f'Puntuación: {snake.score}', True, (255, 255, 255))
            level_text = font.render(f'Nivel: {snake.level}', True, (255, 255, 255))
            screen.blit(score_text, (20, 20))
            screen.blit(level_text, (20, 50))
            pygame.display.flip()
            clock.tick(snake.speed)
    finally:
        cap.release()

# Función principal
def main():
    global current_theme
    current_theme = "Neon"
    while True:
        selected_game = show_game_selection()
        if selected_game == "snake":
            play_snake()
        elif selected_game == "blocks":
            play_blocks()

if __name__ == "__main__":
    main()
pygame.quit()
