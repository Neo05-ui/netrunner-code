print ("ho! ho! ho! bitch your resuslt is here")
score = int(input("what did you score? "))
if 90 <= score <= 100:
    print ("you're a god, you scored A")
elif 80 <= score < 90:
    print ("you did good, you scored B")
elif 70 <= score < 80:
    print ("nah you can do better son, you scored a C")
elif 60 <= score < 70:
    print ("you fucking suck, you score a Dih")
else:
    print ("you failed nigga, kill yourself")

# we dont use if repeatedly after elif because once one condition is met the rest are ignored
# also we use <= and < to avoid overlap between conditions