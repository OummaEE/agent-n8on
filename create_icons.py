from PIL import Image, ImageDraw, ImageFont
import os

def create_icon(size):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    center = size // 2
    radius = size // 2 - 2

    for y in range(size):
        for x in range(size):
            dist = ((x - center)**2 + (y - center)**2) ** 0.5
            if dist < radius:
                t = dist / radius
                r = int(88 + t * 100)
                g = int(166 - t * 80)
                b = int(255 - t * 50)
                img.putpixel((x, y), (r, g, b, 255))

    try:
        font_size = size // 2
        font = ImageFont.truetype("arial.ttf", font_size)
    except:
        font = ImageFont.load_default()

    text = "n8"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = (size - text_width) // 2
    y = (size - text_height) // 2 - bbox[1]

    draw.text((x, y), text, fill='white', font=font)
    return img

os.makedirs('src-tauri/icons', exist_ok=True)

img32 = create_icon(32)
img32.save('src-tauri/icons/32x32.png')

img128 = create_icon(128)
img128.save('src-tauri/icons/128x128.png')

img256 = create_icon(256)
img256.save('src-tauri/icons/128x128@2x.png')
img256.save('src-tauri/icons/icon.png')

# ICO
img256.save('src-tauri/icons/icon.ico', format='ICO',
            sizes=[(256,256), (128,128), (64,64), (32,32), (16,16)])

# ICNS (just copy PNG for macOS - not needed when building on Windows)
img256.save('src-tauri/icons/icon.icns')

print("Icons created successfully!")
