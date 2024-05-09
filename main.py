#!/bin/env python3

from PIL import Image, ImageDraw, ImageFont
import discordrpc as rpc
import subprocess
import json
import time
import sys
import os

if not os.path.isfile("data.json"):
    json.dump({}, open("data.json", "w"))

data = json.load(open("data.json"))

def parse_time(time_secs):
    s = time_secs % 60
    m = time_secs // 60 % 60
    h = time_secs // 60 ** 2 % 60 ** 2
    return f"{h:0>2}:{m:0>2}:{s:0>2}"

def parse_time_minutes(time_secs):
    m = time_secs // 60 % 60
    h = time_secs // 60 ** 2 % 60 ** 2
    if h == 0:
        return f"{m} minutes"
    else:
        return f"{h} hours {m} minutes"

def start_timer(game, set_func, drpc, process):
    global data
    old_min = -1
    session_time = 0
    while True:
        stime = time.perf_counter()
        new_min = data[game]["timer"] // 60
        if new_min != old_min and drpc is not None: set_func(drpc, session_time)
        if process.poll() is not None: return
        data[game]["timer"] += 1
        session_time += 1
        print(f"total {data[game]['name']} time: {parse_time(data[game]['timer'])}, session time: {parse_time(session_time)}", end="\r")
        old_min = new_min
        time.sleep(1 - (time.perf_counter() - stime))

def print_help(program):
    print(f"usage: {program} <subcommand> [game] [options]")
    print("\tsubcommands:")
    print("\t\thelp - get help")
    print("\t\tadd - add a game")
    print("\t\tinfo - get elapsed time at the game")
    print("\t\ttime - start timer for selected game")
    print("\t\timg - generate image for selected game")
    print("\toptions:")
    print("\t\t--no-rpc - forcefully disable discord rpc")

def hash_name(name):
    hsh = 0
    for k, i in enumerate(name):
        hsh += (k+1)*ord(i)
    return hsh

def print_all_games():
    size = os.get_terminal_size().columns - 5

    full = sum(map(lambda x: x["timer"], data.values()))
    sizes = {}
    for k, i in sorted(data.items(), key=lambda x: -x[1]["timer"]):
        sizes[k] = round(i["timer"]/full*size)
    
    perc = {}
    for k, i in sorted(data.items(), key=lambda x: -x[1]["timer"]):
        perc[k] = i["timer"]/full

    char = "#@$%&"

    for k, i in sorted(data.items(), key=lambda x: -x[1]["timer"]):
        print(f"{char[hash_name(k)%len(char)]} ({perc[k]*100:0.2f}%) {i['name']}: {parse_time(i['timer'])}")

    print("\n  ", end="")
    for k, i in sizes.items():
        name = data[k]["name"]
        if i < len(name):
            if i < 3:
                print("." * i, end="")
            else: print("..." + " " * (i-3), end="")
        else:
            print(name + (" " * (i - len(name))), end="")
    
    print("\n[ ", end="")

    for k, i in sizes.items():
        print(char[hash_name(k)%len(char)] * i, end="")
    
    print(" ]")

def error(string):
    print("error:", string)
    sys.exit(1)

def parse_args(args):
    program = args.pop(0)
    if len(args) == 0:
        print_all_games()
        return None, None, set()

    operation = args.pop(0)
    if operation not in ("time", "info", "help", "add", "img"):
        print_help(program)
        error(f"unknown operation: {operation}")

    if operation == "help":
        print_help(program)
        sys.exit()

    if len(args) == 0:
        print_help(program)
        error(f"operation {operation} expects a game slug")

    game = args.pop(0)

    opts = set()
    for i in args:
        if i == "--no-rpc":
            opts.add("norpc")
        else:
            print_help(program)
            error(f"unknown option {i}")
    
    return operation, game, opts

lerp = lambda a, b, t: a + (b-a)*t
lerp2d = lambda a, b, t: [lerp(a[0], b[0], t), lerp(a[1], b[1], t)]
lerp3d = lambda a, b, t: [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)]

in_circle = lambda c, x, y, r: (x-c[0])**2 + (y-c[1])**2 < r**2

def make_round(image):
    new_image = image.copy()
    for i in range(new_image.width):
        for j in range(new_image.height):
            if not in_circle((new_image.width/2, new_image.height/2), i, j, new_image.width/2):
                new_image.putpixel((i, j), (0, 0, 0, 0))
    return new_image

def paste_blend(image, topaste, box):
    for i in range(topaste.width):
        for j in range(topaste.height):
            orig = image.getpixel((i+box[0], j+box[1]))
            new = topaste.getpixel((i, j))
            col = lerp3d(orig, new[:3], new[3]/255) + [255]
            image.putpixel((i+box[0], j+box[1]), tuple(map(int, col)))

def get_hours(time):
    return f"Play time: {time//60**2} hours"

avg = lambda x: sum(x)/len(x)

def avg2d(xs):
    items_0 = list(map(lambda x: x[0], xs))
    items_1 = list(map(lambda x: x[1], xs))
    return avg(items_0), avg(items_1)

def avg3d(xs):
    items_0 = list(map(lambda x: x[0], xs))
    items_1 = list(map(lambda x: x[1], xs))
    items_2 = list(map(lambda x: x[2], xs))
    return avg(items_0), avg(items_1), avg(items_2)

def avg_col(img):
    cols = []
    for i in range(img.width):
        for j in range(img.height):
            cols.append(img.getpixel((i, j)))
    return avg3d(cols)

def rgb2hsv(col):
    r, g, b = col
    r, g, b = r/255, g/255, b/255
    cmax = max(r, g, b)
    cmin = min(r, g, b)
    cdelta = cmax - cmin
    hue = 0
    if cdelta == 0: hue = 0
    elif cmax == r: hue = 60 * (((g - b)/cdelta) % 6)
    elif cmax == g: hue = 60 * (((b - r)/cdelta) + 2)
    elif cmax == b: hue = 60 * (((r - g)/cdelta) + 4)
    saturation = 0
    if cmax == 0: saturation = 0
    else: saturation: cdelta/cmax
    value = cmax
    return hue, saturation, value

def hsv2rgb(col):
    h, s, v = col
    c = v * s
    x = c * (1 - abs((h/60) % 2 - 1))
    m = v - c
    if 0 <= h < 60: rgb = (c, x, 0)
    if 60 <= h < 120: rgb = (x, c, 0)
    if 120 <= h < 180: rgb = (0, c, x)
    if 180 <= h < 240: rgb = (0, x, c)
    if 240 <= h < 300: rgb = (x, 0, c)
    if 300 <= h < 360: rgb = (c, 0, x)
    return rgb

def generate_image(name):
    banner_path = os.path.join("assets", "imgs", name, "banner.png")
    icon_path = os.path.join("assets", "imgs", name, "icon.png")
    if not os.path.isfile(banner_path):
        error(f"no banner image")
    if not os.path.isfile(icon_path):
        error(f"no icon image")
    
    banner = Image.open(banner_path).convert("RGB")
    icon = Image.open(icon_path).convert("RGBA")

    # banner resize
    if banner.width < banner.height:
        h = 100
        w = banner.width/banner.height*h
    else:
        w = 300
        h = banner.height/banner.width*w
    
    banner = banner.resize((int(w), int(h))) \
                   .crop((0, 0, 300, 100))

    #b = (36, 54, 148)
    b = avg_col(Image.open(banner_path))
    grad_start = 0.6
    grad_end = 1.0
    for i in range(banner.height):
        for j in range(banner.width):
            a = banner.getpixel((j, i))
            newcol = lerp3d(a, b, lerp(grad_start, grad_end, i/banner.height))
            banner.putpixel((j, i), tuple(map(int, newcol)))

    image = Image.new("RGBA", (300, 100))
    image.paste(banner)
    
    icon = make_round(icon).resize((64, 64))
    
    paste_blend(image, icon, (18, 18))

    # text

    draw = ImageDraw.Draw(image)
    
    font_tiny = ImageFont.truetype("assets/Montserrat-Italic.ttf", 20)
    font_huge = ImageFont.truetype("assets/Montserrat-SemiBoldItalic.ttf", 30)

    draw.text((94, 23), data[name]["name"], font=font_huge)
    draw.text((94, 54), get_hours(data[name]["timer"]), font=font_tiny)

    return image

if __name__ == "__main__":
    version = "1.0-dev"
    print(f"antimony v{version}; made by aciddev")
    operation, game, opts = parse_args(sys.argv)

    if operation == "time":
        if game not in data:
            print("no such game; add with `add` subcommand")
            sys.exit(1)
        
        if "process" not in data[game]:
            print("specify game executable to run")
            a = input("$ ")
            while not os.path.isfile(a):
                a = input("$ ")
            data[game]["process"] = a

        discord_opened = "norpc" not in opts
        if discord_opened:
            try: drpc = rpc.RPC(app_id=1219360949086064671, output=False)
            except rpc.exceptions.DiscordNotOpened: discord_opened = False

        if discord_opened:
            print("discord is opened, rpc started")
            set_act = lambda rpc, st: rpc.set_activity(
                details=f"{data[game]['name']} for {parse_time_minutes(data[game]['timer'])}",
                state=f"Played for {parse_time_minutes(st)} in this session",
                large_image=game,
                large_text=data[game]['name'],
            )
        elif "norpc" in opts:
            print("no rpc option is selected, running localy")
            set_act = None
        else:
            print("discord is not opened, running localy")
            set_act = None
        
        proc = subprocess.Popen([data[game]["process"]])

        try: start_timer(game, set_act, drpc if discord_opened else None, proc)
        except KeyboardInterrupt: pass

        print(f"\ntimer for {data[game]['name']} is interrupted")
        
        json.dump(data, open("data.json", "w"))
        
        if discord_opened:
            drpc.disconnect()

    elif operation == "img":
        generate_image(game).save(f"{game}.png")

    elif operation == "info":
        if game not in data:
            print("no such game; add with `add` subcommand")
            sys.exit(1)
        print(f"{data[game]['name']} info:")
        print(f"elapsed time: {parse_time(data[game]['timer'])}")
    elif operation == "add":
        name = input("full game name: ")
        execpath = input("game executable path: ")
        if game not in data: data[game] = {}
        data[game]["name"] = name
        data[game]["process"] = execpath
        if "timer" not in data[game].keys(): data[game]["timer"] = 0
        json.dump(data, open("data.json", "w"))

