# ask questions and make a system to sort users into harry potter houses #
# ask for name, then ask a series of questions #
# based on answers, assign to a house #
# birds, animals, what would you do, etc. #
print ("what's your name? ")
name = input()

total = 0

print ("what's your favourite animal?")
animal = input("Choose animal (owl, lion, deer, snake): ")
if animal == "owl":
    total += 4
elif animal == "lion":
      total += 3
elif animal == "deer":
      total += 2
else:
      total += 1

print ("what's your favourite colour?")
colour = input("Choose colour (red, white, black, green): ")
if colour == "white":
 total += 4
elif colour == "red": 
 total += 3
elif colour == "green":
    total += 2
else:
    total += 1

print ("what's your best skill?")
skill = input("Choose skill (writing, singing, running, sleeping): ")
if skill == "writing":
 total += 4
if skill == "singing":
 total += 3
if skill == "running":
 total += 2
else: 
    total += 1

print ("Based on your choices, we will now determine what house you should be a part of.")

print ("your total points =", total)

if 3 <= total <= 5:
    print (name + "," + "you are in Slytherin!!")
elif 6 <= total <= 8:
    print (name + "," + "you are in Gryffindor!!")
elif 9 <= total <= 11:
    print (name + "," + "you are in Ravenclow!!")
elif total >= 12:
    print (name + "," + "you are in Hufflepuff!!")

