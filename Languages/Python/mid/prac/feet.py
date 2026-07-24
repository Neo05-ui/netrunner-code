def height():
    h = int(input("what's the height? "))
    return h
def width():
    w = int(input("what's the width? "))
    return w
def sq_ft():
    area = height() * width()
#only height() and width() is defined
#only those functions which are defined can be multiplied
    area = int(area)
    print (f"the total area in square ft is {area}")

sq_ft()

#OR a more effecient way i learnt from the video

def area(w,h):
    area_sqft = w * h
    print(f"the total sqft is:{area_sqft}")

wid = int(input("enter the width of the room: "))
hite = int(input("enter the height of the room: "))

area(wid, hite)