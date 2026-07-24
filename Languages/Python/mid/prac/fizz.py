num = int(input ("gimme a number son "))

if num % 15 == 0:
    print ("fizzbuzz")

elif num % 5 == 0:
    print ("buzz")

elif num % 3 == 0:
    print ("fizz")
else:
    print ("nah uh") 
#or we can do it this way
# elif num % 3 == 0 and num % 5 ==0: print fizzbuzz
