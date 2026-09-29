#!/usr/bin/env python3
"""Génère la vidéo de présentation du stage (AMR-X, supervision web).

Usage : python3 make_video.py [sortie.mp4]
Les images sont dessinées avec Pillow et encodées avec ffmpeg (ou OpenCV à défaut).
"""
import math
import os
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1280, 720, 24
HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, '..', 'figures')

BG = (10, 20, 34)
PANEL = (19, 35, 56)
TEXT = (232, 238, 245)
MUTED = (150, 168, 190)
ACCENT = (64, 214, 186)      # vert d'eau du dashboard
BLUE = (88, 150, 255)
ORANGE = (255, 170, 70)
RED = (240, 90, 90)
GREEN = (110, 210, 120)


def font(size, bold=False):
    names = (['DejaVuSans-Bold.ttf', 'NotoSans-Bold.ttf', 'Ubuntu-B.ttf'] if bold else
             ['DejaVuSans.ttf', 'NotoSans-Regular.ttf', 'Ubuntu-R.ttf'])
    for root in ('/usr/share/fonts', os.path.expanduser('~/.local/share/fonts')):
        for dirpath, _, files in os.walk(root):
            for n in names:
                if n in files:
                    return ImageFont.truetype(os.path.join(dirpath, n), size)
    return ImageFont.load_default(size)


F_TITLE = font(46, True)
F_H = font(34, True)
F_B = font(26)
F_BB = font(26, True)
F_S = font(20)
F_SB = font(20, True)
F_CAP = font(25)
F_BIG = font(64, True)


def load(name):
    p = os.path.join(FIG, name)
    return Image.open(p).convert('RGB') if os.path.exists(p) else None


IMG = {k: load(v) for k, v in {
    'gazebo': 'gazebo_warehouse.png', 'livemap': 'live_map_navigation.png',
    'web_b': 'nav_web_before.png', 'web_a': 'nav_web_after.png',
    'gz_b': 'nav_gz_before.png', 'gz_a': 'nav_gz_after.png',
    'status': 'nav_status_succeeded.png'}.items()}


# ------------------------------------------------------------------ helpers
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def appear(t, start, dur=0.6):
    return ease((t - start) / dur)


def mix(c1, c2, a):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * a) for i in range(3))


def fade_color(c, a):
    return mix(BG, c, a)


def text_c(d, xy, s, f, fill=TEXT, anchor='mm'):
    d.text(xy, s, font=f, fill=fill, anchor=anchor)


def wrap(d, s, f, width):
    lines, cur = [], ''
    for word in s.split():
        test = (cur + ' ' + word).strip()
        if d.textlength(test, font=f) <= width:
            cur = test
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def caption(d, s, a=1.0):
    """Sous-titre en bas de l'écran."""
    if not s or a <= 0:
        return
    lines = wrap(d, s, F_CAP, W - 200)
    h = 38 * len(lines) + 24
    y0 = H - h - 26
    d.rounded_rectangle((70, y0, W - 70, y0 + h), 14, fill=fade_color((6, 12, 22), a))
    for i, line in enumerate(lines):
        text_c(d, (W // 2, y0 + 12 + 19 + 38 * i), line, F_CAP, fade_color(TEXT, a))


def header(d, title, a=1.0, step=None):
    text_c(d, (70, 58), title, F_H, fade_color(TEXT, a), anchor='lm')
    d.line((70, 88, 70 + 90 * a, 88), fill=ACCENT, width=4)
    if step:
        text_c(d, (W - 70, 58), step, F_S, fade_color(MUTED, a), anchor='rm')


def box(d, xy, label, sub=None, color=BLUE, a=1.0, fill=PANEL, width=3):
    x0, y0, x1, y1 = xy
    d.rounded_rectangle(xy, 16, fill=fade_color(fill, a), outline=fade_color(color, a), width=width)
    cy = (y0 + y1) / 2
    if sub:
        text_c(d, ((x0 + x1) / 2, cy - 14), label, F_BB, fade_color(TEXT, a))
        text_c(d, ((x0 + x1) / 2, cy + 18), sub, F_S, fade_color(MUTED, a))
    else:
        text_c(d, ((x0 + x1) / 2, cy), label, F_BB, fade_color(TEXT, a))


def arrow(d, p0, p1, color=MUTED, a=1.0, width=4, progress=1.0):
    (x0, y0), (x1, y1) = p0, p1
    x1p, y1p = x0 + (x1 - x0) * progress, y0 + (y1 - y0) * progress
    c = fade_color(color, a)
    d.line((x0, y0, x1p, y1p), fill=c, width=width)
    if progress > 0.95:
        ang = math.atan2(y1 - y0, x1 - x0)
        s = 14
        pts = [(x1, y1),
               (x1 - s * math.cos(ang - 0.45), y1 - s * math.sin(ang - 0.45)),
               (x1 - s * math.cos(ang + 0.45), y1 - s * math.sin(ang + 0.45))]
        d.polygon(pts, fill=c)


def paste_fit(frame, img, box_xy, zoom=1.0, alpha=1.0, border=ACCENT):
    if img is None:
        return
    x0, y0, x1, y1 = box_xy
    bw, bh = x1 - x0, y1 - y0
    iw, ih = img.size
    # crop centre selon le zoom (effet Ken Burns)
    cw, ch = iw / zoom, ih / zoom
    crop = img.crop((int((iw - cw) / 2), int((ih - ch) / 2),
                     int((iw + cw) / 2), int((ih + ch) / 2)))
    scale = min(bw / crop.width, bh / crop.height)
    im = crop.resize((max(1, int(crop.width * scale)), max(1, int(crop.height * scale))),
                     Image.LANCZOS)
    px, py = int(x0 + (bw - im.width) / 2), int(y0 + (bh - im.height) / 2)
    if alpha < 1:
        base = frame.crop((px, py, px + im.width, py + im.height))
        im = Image.blend(base, im, alpha)
    frame.paste(im, (px, py))
    ImageDraw.Draw(frame).rectangle((px - 2, py - 2, px + im.width + 1, py + im.height + 1),
                                    outline=fade_color(border, alpha), width=2)


def robot_icon(d, cx, cy, s=1.0, a=1.0, color=ACCENT):
    w, h = 150 * s, 46 * s
    d.rounded_rectangle((cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), int(10 * s),
                        fill=fade_color((40, 60, 88), a), outline=fade_color(color, a), width=3)
    for wx in (-w / 3, w / 3):
        d.ellipse((cx + wx - 18 * s, cy + h / 2 - 12 * s, cx + wx + 18 * s, cy + h / 2 + 24 * s),
                  fill=fade_color((25, 30, 40), a), outline=fade_color(MUTED, a), width=2)
    d.ellipse((cx - 10 * s, cy - h / 2 - 16 * s, cx + 10 * s, cy - h / 2 + 4 * s),
              fill=fade_color(BLUE, a))  # LiDAR


# ------------------------------------------------------------------ scènes
def s_title(fr, d, t, T):
    a = appear(t, 0.2, 1.0)
    robot_icon(d, W / 2, 190, 1.2, a)
    text_c(d, (W / 2, 305), "AMR-X : commander un robot autonome", F_TITLE, fade_color(TEXT, a))
    text_c(d, (W / 2, 362), "depuis une page web", F_TITLE, fade_color(ACCENT, a))
    b = appear(t, 1.4, 1.0)
    text_c(d, (W / 2, 450), "Stage d'été 2026  —  Linda Ouaghlani", F_B, fade_color(TEXT, b))
    text_c(d, (W / 2, 492), "CyberMech Systems · département R&D / Robotique", F_B, fade_color(MUTED, b))
    text_c(d, (W / 2, 560), "Projet : Design, Development, Simulation, and Validation of a Modular Autonomous Robotic System",
           F_S, fade_color(MUTED, b))


def s_modular(fr, d, t, T):
    header(d, "L'idée : un robot modulaire", appear(t, 0), "1 / 10")
    a = appear(t, 0.4)
    robot_icon(d, W / 2, 420, 2.0, a)
    text_c(d, (W / 2, 548), "base commune : roues, capteurs, navigation", F_S, fade_color(MUTED, a))
    modules = [("Module transport", ORANGE), ("Module hôpital", BLUE), ("Module entrepôt", GREEN)]
    k = int(clamp((t - 1.5) / 3.2, 0, 2.999))
    local = (t - 1.5) - 3.2 * k
    if t > 1.5:
        drop = ease(local / 0.9)
        lift = ease((local - 2.5) / 0.6) if k < 2 else 0
        y = 190 + (325 - 190) * drop - 150 * lift
        name, col = modules[k]
        al = a * (1 - lift)
        d.rounded_rectangle((W / 2 - 130, y - 40, W / 2 + 130, y + 40), 12,
                            fill=fade_color(PANEL, al), outline=fade_color(col, al), width=4)
        text_c(d, (W / 2, y), name, F_BB, fade_color(TEXT, al))
    caption(d, "CyberMech Systems développe AMR-X : une même base robotique qui reçoit des "
               "modules interchangeables selon le besoin (entrepôt, hôpital, transport…).",
            appear(t, 0.8))


def s_environment(fr, d, t, T):
    header(d, "Tout un environnement autonome", appear(t, 0), "2 / 10")
    items = [("Robot AMR-X", "base + modules", GREEN, (90, 170, 410, 290)),
             ("Simulation", "Gazebo : monde virtuel", ORANGE, (870, 170, 1190, 290)),
             ("Navigation", "Nav2 : se déplacer seul", BLUE, (90, 360, 410, 480)),
             ("Supervision", "dashboard web", ACCENT, (870, 360, 1190, 480))]
    for i, (lbl, sub, col, xy) in enumerate(items):
        box(d, xy, lbl, sub, col, appear(t, 0.5 + 1.2 * i))
    a = appear(t, 5.5)
    robot_icon(d, W / 2, 320, 1.1, a)
    for (x, y) in ((410, 230), (870, 230), (410, 420), (870, 420)):
        arrow(d, (W / 2 + (-90 if x < W / 2 else 90), 320), (x, y), MUTED, a, 3)
    caption(d, "Autour du robot, l'entreprise construit un environnement complet : on peut le "
               "simuler, il navigue seul, et un opérateur le supervise depuis un navigateur.",
            appear(t, 1.0))


def s_gazebo(fr, d, t, T):
    header(d, "Le robot vit dans une simulation", appear(t, 0), "3 / 10")
    paste_fit(fr, IMG['gazebo'], (160, 110, W - 160, 560), zoom=1.0 + 0.12 * t / T,
              alpha=appear(t, 0.3))
    caption(d, "Gazebo simule un entrepôt et le robot AMR-X, avec ses capteurs (deux LiDAR, une "
               "caméra, une centrale inertielle). On peut tester la navigation sans robot physique.",
            appear(t, 0.8))


def s_problem(fr, d, t, T):
    header(d, "Le point de départ", appear(t, 0), "4 / 10")
    a = appear(t, 0.4)
    box(d, (110, 220, 470, 400), "Dashboard web", "l'opérateur", ACCENT, a)
    box(d, (810, 220, 1170, 400), "Robot + Nav2", "dans Gazebo", BLUE, a)
    b = appear(t, 1.6)
    for x in range(480, 800, 28):
        d.line((x, 310, x + 14, 310), fill=fade_color(RED, b), width=4)
    cx, cy, r = W / 2, 310, 34 * b
    d.line((cx - r, cy - r, cx + r, cy + r), fill=fade_color(RED, b), width=8)
    d.line((cx - r, cy + r, cx + r, cy - r), fill=fade_color(RED, b), width=8)
    c = appear(t, 3.0)
    text_c(d, (290, 440), "affiche un plan…", F_S, fade_color(MUTED, c))
    text_c(d, (290, 470), "mais pas le vrai robot", F_SB, fade_color(RED, c))
    text_c(d, (990, 440), "se commande seulement", F_S, fade_color(MUTED, c))
    text_c(d, (990, 470), "depuis les outils ROS", F_SB, fade_color(RED, c))
    caption(d, "Au début du stage, les deux mondes n'étaient pas reliés : la page web ne "
               "voyait pas le robot et ne pouvait pas lui envoyer de destination.", appear(t, 1.0))


CHAIN = [("Navigateur", "Live map", ACCENT), ("rosbridge", "WebSocket", MUTED),
         ("Passerelle", "nouveau nœud", RED), ("Nav2", "navigation", BLUE),
         ("Robot", "Gazebo", GREEN)]


def chain_boxes(d, a, y0=250, y1=370):
    xs = []
    bw, gap = 196, 50
    x = (W - (5 * bw + 4 * gap)) / 2
    for i, (lbl, sub, col) in enumerate(CHAIN):
        box(d, (x, y0, x + bw, y1), lbl, sub, col, appear(a, 0.3 + 0.5 * i),
            width=5 if lbl == "Passerelle" else 3)
        xs.append((x, x + bw))
        x += bw + gap
    return xs


def s_solution(fr, d, t, T):
    header(d, "La solution : une passerelle", appear(t, 0), "5 / 10")
    xs = chain_boxes(d, t)
    a = appear(t, 2.8)
    for i in range(4):
        arrow(d, (xs[i][1] + 4, 295), (xs[i + 1][0] - 4, 295), MUTED, a, 3)
        arrow(d, (xs[i + 1][0] - 4, 325), (xs[i][1] + 4, 325), MUTED, a, 3)
    # paquet aller : destination
    if 3.5 < t < 9.5:
        p = ease((t - 3.5) / 5.0)
        x = xs[0][1] + (xs[4][0] - xs[0][1]) * p
        d.ellipse((x - 11, 214, x + 11, 236), fill=ORANGE)
        text_c(d, (x, 190), "destination", F_SB, ORANGE)
    # paquet retour : position + état
    if 10.0 < t < 16.5:
        p = ease((t - 10.0) / 5.5)
        x = xs[4][0] + (xs[0][1] - xs[4][0]) * p
        d.ellipse((x - 11, 384, x + 11, 406), fill=ACCENT)
        text_c(d, (x, 432), "position + état", F_SB, ACCENT)
    if t < 9.8:
        cap = ("Le travail du stage : un nouveau programme ROS 2, la « passerelle ». Quand "
               "l'opérateur choisit une destination, elle vérifie la demande puis la transmet à Nav2.")
    else:
        cap = ("En retour, la passerelle envoie au navigateur, 4 fois par seconde, la position "
               "du robot et l'état de la navigation : en route, arrivée, annulée…")
    caption(d, cap, appear(t, 1.0))


def s_operator(fr, d, t, T):
    header(d, "Ce que fait l'opérateur", appear(t, 0), "6 / 10")
    paste_fit(fr, IMG['livemap'], (70, 110, 800, 560), zoom=1.0, alpha=appear(t, 0.3))
    steps = [("1", "Choisir un point sur la carte", "ou saisir X, Y et le cap"),
             ("2", "Cliquer « Go to destination »", "la demande est acquittée"),
             ("3", "Suivre le robot en direct", "distance restante, résultat"),
             ("4", "Annuler si besoin", "« Cancel navigation »")]
    for i, (n, l1, l2) in enumerate(steps):
        a = appear(t, 1.5 + 2.2 * i)
        y = 150 + 100 * i
        d.ellipse((840, y, 890, y + 50), fill=fade_color(ACCENT, a))
        text_c(d, (865, y + 25), n, F_BB, fade_color(BG, a) if a > 0.5 else fade_color(PANEL, a))
        text_c(d, (910, y + 13), l1, F_SB, fade_color(TEXT, a), anchor='lm')
        text_c(d, (910, y + 40), l2, F_S, fade_color(MUTED, a), anchor='lm')
    caption(d, "Sur la page « Live map » du dashboard, le robot apparaît à sa vraie position "
               "sur le plan de l'entrepôt.", appear(t, 0.8))


def s_safety(fr, d, t, T):
    header(d, "Des garde-fous", appear(t, 0), "7 / 10")
    items = [("Un seul trajet à la fois", "un deuxième ordre est refusé tant que le premier n'est pas fini"),
             ("Destinations vérifiées", "obstacle, hors de la carte, mauvais monde : refus avec explication"),
             ("Données trop vieilles = commandes bloquées", "plus de 2,5 s sans nouvelles du robot"),
             ("Jamais de faux succès", "« arrivé » s'affiche seulement si Nav2 le confirme")]
    for i, (l1, l2) in enumerate(items):
        a = appear(t, 0.6 + 2.0 * i)
        y = 140 + 105 * i
        d.rounded_rectangle((110, y, W - 110, y + 86), 14, fill=fade_color(PANEL, a))
        d.rectangle((110, y, 118, y + 86), fill=fade_color(ACCENT, a))
        text_c(d, (150, y + 28), l1, F_BB, fade_color(TEXT, a), anchor='lm')
        text_c(d, (150, y + 60), l2, F_S, fade_color(MUTED, a), anchor='lm')
    caption(d, "Commander un robot à distance demande de la prudence : l'interface ne doit jamais "
               "tromper l'opérateur.", appear(t, 0.8) * (1 - appear(t, T - 0.2)))


def s_calibration(fr, d, t, T):
    header(d, "Aligner la carte et le monde", appear(t, 0), "8 / 10")
    # plan de l'entrepôt
    ox, oy, sc = 470, 330, 26
    a = appear(t, 0.3)
    d.rectangle((ox - 7 * sc, oy - 10 * sc + 60, ox + 6.3 * sc, oy + 10 * sc - 60),
                outline=fade_color(MUTED, a), width=2)
    real = (ox - 1.26 * sc, oy + 3.9 * sc - 60)
    # le robot réel
    d.ellipse((real[0] - 13, real[1] - 13, real[0] + 13, real[1] + 13), fill=fade_color(GREEN, a))
    text_c(d, (real[0], real[1] + 30), "robot réel (Gazebo)", F_S, fade_color(GREEN, a))
    # le robot affiché : décalé puis recalé
    fix = ease((t - 7.0) / 2.5)
    shown = (real[0] + 1.26 * sc * (1 - fix), real[1] - 3.9 * sc * (1 - fix))
    b = appear(t, 1.5)
    d.ellipse((shown[0] - 13, shown[1] - 13, shown[0] + 13, shown[1] + 13),
              outline=fade_color(ORANGE, b), width=4)
    text_c(d, (shown[0] + 20, shown[1] - 26), "affiché sur la page", F_S, fade_color(ORANGE, b), anchor='lm')
    if fix < 0.3 and t > 2.5:
        c = appear(t, 2.5)
        d.line((real[0], real[1], shown[0], shown[1]), fill=fade_color(RED, c), width=3)
        text_c(d, ((real[0] + shown[0]) / 2 - 16, (real[1] + shown[1]) / 2), "4,1 m", F_BB,
               fade_color(RED, c), anchor='rm')
    # explication à droite
    lines = [(3.0, "La carte de Nav2 a été", TEXT), (3.0, "enregistrée depuis le point", TEXT),
             (3.0, "de départ du robot :", TEXT), (4.5, "son origine n'est pas", ORANGE),
             (4.5, "celle du monde Gazebo.", ORANGE), (9.5, "Après calibration :", GREEN),
             (9.5, "moins de 6 cm d'écart", GREEN)]
    for i, (st, s, col) in enumerate(lines):
        text_c(d, (780, 170 + 42 * i + (20 if i >= 5 else 0)), s, F_BB if i >= 5 else F_B,
               fade_color(col, appear(t, st)), anchor='lm')
    caption(d, "Pour que le robot s'affiche au bon endroit, il a fallu mesurer le décalage "
               "entre la carte de navigation et le monde simulé, puis le corriger.", appear(t, 0.8))


def s_demo(fr, d, t, T):
    header(d, "Un essai réel dans la simulation", appear(t, 0), "9 / 10")
    after = ease((t - 6.0) / 1.2)
    lbl = "AVANT" if after < 0.5 else "APRÈS"
    text_c(d, (W / 2, 125), lbl, F_BB, ORANGE if after < 0.5 else GREEN)
    for key_b, key_a, xy in (('web_b', 'web_a', (80, 150, 420, 560)),
                             ('gz_b', 'gz_a', (450, 150, 1200, 560))):
        img = IMG[key_a] if after >= 0.5 else IMG[key_b]
        paste_fit(fr, img, xy, alpha=appear(t, 0.3))
    text_c(d, (250, 578), "dashboard (navigateur)", F_S, MUTED)
    text_c(d, (825, 578), "Gazebo (le robot simulé)", F_S, MUTED)
    if t > 8.0:
        paste_fit(fr, IMG['status'], (360, 480, 920, 540), alpha=appear(t, 8.0), border=GREEN)
    cap = ("Une destination est envoyée : le robot se déplace dans Gazebo et, en même temps, "
           "sur la page web." if t < 8.0 else
           "Résultat : destination atteinte en 10,8 s, à 0,9 cm près, et la page affiche « succeeded ».")
    caption(d, cap, appear(t, 0.8))


def s_results(fr, d, t, T):
    header(d, "Les résultats mesurés", appear(t, 0), "10 / 10")
    cards = [("< 6 cm", "écart entre la position affichée", "et la position réelle"),
             ("5,75 s", "pour atteindre une destination", "à 3 m, précision 5,6 cm"),
             ("0,03 s", "pour confirmer une annulation", "le robot s'arrête"),
             ("Toutes", "les demandes invalides refusées", "le robot ne bouge pas")]
    for i, (big, l1, l2) in enumerate(cards):
        a = appear(t, 0.5 + 1.3 * i)
        x0 = 90 + (i % 2) * 560
        y0 = 130 + (i // 2) * 210
        d.rounded_rectangle((x0, y0, x0 + 520, y0 + 180), 16, fill=fade_color(PANEL, a))
        text_c(d, (x0 + 260, y0 + 60), big, F_BIG, fade_color(ACCENT, a))
        text_c(d, (x0 + 260, y0 + 118), l1, F_S, fade_color(TEXT, a))
        text_c(d, (x0 + 260, y0 + 146), l2, F_S, fade_color(MUTED, a))
    caption(d, "Chaque chiffre a été mesuré en comparant l'affichage du dashboard à la position "
               "réelle du robot dans Gazebo.", appear(t, 0.8))


def s_end(fr, d, t, T):
    a = appear(t, 0.2)
    text_c(d, (W / 2, 150), "En résumé", F_TITLE, fade_color(TEXT, a))
    lines = ["Depuis une simple page web, un opérateur peut maintenant",
             "choisir une destination, envoyer le robot AMR-X, le suivre",
             "en direct et l'arrêter — avec des informations fiables."]
    for i, s in enumerate(lines):
        text_c(d, (W / 2, 240 + 44 * i), s, F_B, fade_color(TEXT, appear(t, 0.8 + 0.4 * i)))
    b = appear(t, 3.5)
    text_c(d, (W / 2, 420), "Et ensuite ?", F_BB, fade_color(ACCENT, b))
    nxt = "plusieurs robots  ·  enregistrement des trajets  ·  passage au robot physique"
    text_c(d, (W / 2, 465), nxt, F_B, fade_color(MUTED, b))
    c = appear(t, 5.5)
    text_c(d, (W / 2, 600), "Linda Ouaghlani — CyberMech Systems — Stage d'été 2026", F_S,
           fade_color(MUTED, c))


SCENES = [(s_title, 7), (s_modular, 12), (s_environment, 13), (s_gazebo, 10),
          (s_problem, 11), (s_solution, 17), (s_operator, 13), (s_safety, 11),
          (s_calibration, 15), (s_demo, 14), (s_results, 11), (s_end, 9)]
FADE = 0.5

# Texte lu par la voix off, une entrée par scène. Certains mots sont écrits
# phonétiquement pour la synthèse vocale (A M R X, Saïbeur Mèk, Ross).
NARRATION = [
    "Bonjour. Cette vidéo présente le stage d'été de Linda Ouaghlani chez Saïbeur Mèk "
    "Systèmes : comment commander un robot autonome depuis une simple page web.",
    "Saïbeur Mèk Systèmes développe A M R X, un robot autonome et modulaire. L'idée est "
    "simple : une même base robotique, avec ses roues et ses capteurs, sur laquelle on fixe "
    "différents modules selon le besoin : transport, hôpital, ou entrepôt.",
    "Autour de ce robot, l'entreprise construit tout un environnement autonome. Une "
    "simulation, pour tester sans robot physique. Un système de navigation, qui permet au "
    "robot de se déplacer seul. Et un tableau de bord web, pour que l'opérateur supervise "
    "les robots.",
    "Voici le robot dans la simulation Gazebo. Il se trouve dans un entrepôt virtuel, avec "
    "des étagères et des obstacles. Il possède deux lidars, une caméra et une centrale "
    "inertielle, comme un vrai robot.",
    "Au début du stage, il manquait un lien. La page web affichait le plan de l'entrepôt, "
    "mais pas le vrai robot. Et pour lui donner une destination, il fallait passer par les "
    "outils de développement de Ross.",
    "Le travail du stage a été de créer ce lien : un nouveau programme, appelé la "
    "passerelle. Quand l'opérateur choisit une destination, la passerelle vérifie la "
    "demande, puis la transmet au système de navigation, qui fait bouger le robot. En "
    "retour, quatre fois par seconde, la passerelle renvoie à la page web la position du "
    "robot et l'état du trajet : en route, arrivé, ou annulé.",
    "Pour l'opérateur, c'est très simple. Il clique sur un point de la carte, ou saisit des "
    "coordonnées. Il appuie sur le bouton pour lancer le trajet. Il suit le robot en direct, "
    "avec la distance restante. Et il peut annuler à tout moment.",
    "Commander un robot à distance demande de la prudence. Un seul trajet est accepté à la "
    "fois. Les destinations impossibles, par exemple sur un obstacle, sont refusées avec une "
    "explication. Si les informations du robot ont plus de deux secondes et demie, les "
    "commandes sont bloquées. Et l'interface n'annonce jamais un succès que le robot n'a pas "
    "confirmé.",
    "Une étape importante a été d'aligner la carte et le monde simulé. La carte de "
    "navigation a été enregistrée à partir du point de départ du robot : son origine n'est "
    "donc pas celle du monde Gazebo. Sans calibration, le robot s'affichait à quatre mètres "
    "de sa vraie position. Après avoir mesuré et corrigé ce décalage, l'écart est de moins "
    "de six centimètres.",
    "Voici un essai réel. Une destination est envoyée au robot. On le voit se déplacer dans "
    "Gazebo, et en même temps sur la page web, avec la trace de son trajet. Il arrive à "
    "destination en moins de onze secondes, à moins d'un centimètre près, et la page "
    "affiche le succès.",
    "Tous ces résultats ont été mesurés en comparant la page web à la position réelle du "
    "robot. La position affichée est juste à six centimètres près. Une annulation est "
    "confirmée en trois centièmes de seconde. Et toutes les demandes invalides sont "
    "refusées, sans que le robot ne bouge.",
    "En résumé : depuis une simple page web, un opérateur peut maintenant envoyer le robot "
    "A M R X vers une destination, le suivre en direct et l'arrêter, avec des informations "
    "fiables. Prochaines étapes : gérer plusieurs robots, et passer au robot physique. "
    "Merci de votre attention.",
]
TOOLS = os.path.expanduser('~/.local/share/amrx-tools')
PIPER = os.environ.get('PIPER', os.path.join(TOOLS, 'piper-venv', 'bin', 'piper'))
VOICE = os.environ.get('PIPER_VOICE', os.path.join(TOOLS, 'piper-voices', 'fr_FR-siwis-medium.onnx'))
LEAD, TAIL = 0.6, 1.0   # silence avant / après la voix dans chaque scène (s)


def build_audio(workdir):
    """Synthétise la voix off et allonge chaque scène pour qu'elle couvre sa narration.
    Retourne (chemin du wav complet, durées des scènes) ou (None, durées de base)."""
    import wave
    base = [T for _, T in SCENES]
    if not (os.path.exists(PIPER) and os.path.exists(VOICE)):
        print('Piper introuvable : vidéo sans son.')
        return None, base
    clips, rate, width = [], None, None
    for i, text in enumerate(NARRATION):
        path = os.path.join(workdir, f'voix_{i:02d}.wav')
        subprocess.run([PIPER, '-m', VOICE, '-f', path], input=text.encode(), check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with wave.open(path) as w:
            rate, width = w.getframerate(), w.getsampwidth()
            clips.append(w.readframes(w.getnframes()))
    durations = []
    track = bytearray()
    for T, clip in zip(base, clips):
        voice = len(clip) / (rate * width)
        T = max(T, LEAD + voice + TAIL)
        T = math.ceil(T * FPS) / FPS
        durations.append(T)
        silence_after = int(round((T - LEAD - voice) * rate)) * width
        track += bytes(int(LEAD * rate) * width) + clip + bytes(max(0, silence_after))
    out = os.path.join(workdir, 'voix_off.wav')
    with wave.open(out, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(bytes(track))
    return out, durations


def frames(durations):
    for (fn, Tb), T in zip(SCENES, durations):
        n = int(round(T * FPS))
        for i in range(n):
            t = i / FPS
            fr = Image.new('RGB', (W, H), BG)
            d = ImageDraw.Draw(fr)
            # les animations sont étirées sur la durée réelle de la scène
            fn(fr, d, t * Tb / T, Tb)
            k = min(clamp(t / FADE), clamp((T - t) / FADE))
            if k < 1:
                fr = Image.blend(Image.new('RGB', (W, H), BG), fr, k)
            yield fr


def encode(out):
    import tempfile
    work = tempfile.mkdtemp(prefix='amrx_video_')
    audio, durations = build_audio(work)
    total = sum(durations)
    print(f'{total:.1f} s, {int(total * FPS)} images, son : {"oui" if audio else "non"} -> {out}')
    ff = shutil.which('ffmpeg')
    if ff:
        cmd = [ff, '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
               '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-']
        if audio:
            cmd += ['-i', audio, '-c:a', 'aac', '-b:a', '128k']
        cmd += ['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '20',
                '-movflags', '+faststart', '-shortest', out]
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        for fr in frames(durations):
            p.stdin.write(fr.tobytes())
        p.stdin.close()
        code = p.wait()
        shutil.rmtree(work, ignore_errors=True)
        return code
    import cv2
    import numpy as np
    vw = cv2.VideoWriter(out, cv2.VideoWriter_fourcc(*'mp4v'), FPS, (W, H))
    for fr in frames(durations):
        vw.write(cv2.cvtColor(np.asarray(fr), cv2.COLOR_RGB2BGR))
    vw.release()
    print('ffmpeg absent : vidéo encodée sans son.')
    return 0


if __name__ == '__main__':
    if len(sys.argv) > 2 and sys.argv[1] == '--still':
        # --still <secondes> : exporte une image pour vérification
        target, acc = float(sys.argv[2]), 0
        for fn, T in SCENES:
            if target < acc + T:
                fr = Image.new('RGB', (W, H), BG)
                fn(fr, ImageDraw.Draw(fr), target - acc, T)
                fr.save(sys.argv[3] if len(sys.argv) > 3 else 'still.png')
                break
            acc += T
    else:
        sys.exit(encode(sys.argv[1] if len(sys.argv) > 1 else
                        os.path.join(HERE, 'presentation_amrx.mp4')))
