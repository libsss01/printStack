from PIL import Image
img = Image.open('assets/images/printstack_logo.png')
img.save('assets/images/icon.ico', format='ICO', sizes=[(32, 32), (64, 64), (128, 128), (256, 256)])
print("icon.ico created")
