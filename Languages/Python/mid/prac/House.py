print ("what's your name? ")
name = input()

animals = {"owl":4, "lion":3, "deer" :2, "snake":1}
colours = {"white":4, "red":3, "violet":2, "green":1}
traits = {"curiosity":4, "bravery":3, "honour":2, "ambition":1}

total = 0

print ("what's your favourite animal?")
animal = input("Choose animal (owl, lion, deer, snake): ").lower()

print ("what's your favourite colour?")
colour = input("Choose colour (red, white, violet, green): ").lower()

print ("what's your best trait?")
trait = input("Choose trait (curiosity, bravery, honour, ambition): ").lower()

print ("Based on your choices, we will now determine what house you should be a part of.")

total += animals.get(animal, 0)
total += colours.get(colour,0)
total += traits.get(trait,0)

print ("your total points =", total)

if 3 <= total <= 5:
    print (name + "," + "you are in Slytherin!!")
elif 6 <= total <= 8:
    print (name + "," + "you are in Gryffindor!!")
elif 9 <= total <= 11:
    print (name + "," + "you are in Ravenclow!!")
elif total >= 12:
    print (name + "," + "you are in Hufflepuff!!")