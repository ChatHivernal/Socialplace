import os
import requests
from PIL import Image
from io import BytesIO

def create_default_avatar():

    from PIL import Image, ImageDraw
    

    img = Image.new('RGB', (200, 200), color=(255, 107, 53))
    draw = ImageDraw.Draw(img)
    

    draw.ellipse([50, 50, 150, 150], fill=(255, 209, 102))
    

    draw.ellipse([80, 80, 95, 95], fill=(0, 0, 0))
    draw.ellipse([105, 80, 120, 95], fill=(0, 0, 0))
    

    draw.arc([75, 100, 125, 130], 0, 180, fill=(0, 0, 0), width=3)
    

    os.makedirs('static/images/default', exist_ok=True)
    img.save('static/images/default/default_avatar.png')
    print("Default avatar created!")
    

    os.makedirs('static/uploads/profiles', exist_ok=True)
    img.save('static/uploads/profiles/default.png')

if __name__ == '__main__':
    create_default_avatar()
