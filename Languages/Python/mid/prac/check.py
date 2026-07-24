print ("what's your name? ")
first_name = input()

print ("and the name of your clan? ")
clan_name = input()
#we can also remove one more step (print step) here by doing this
age = int(input ("and how old are you? ")) 
# we removed the print step by directly adding that line in the input

#print ("ahh yes, so it is you..." + first_name + " of the " + last_name + " clan! You are aged " + str(age))
#fstrings make it shorter and much more easier to handle variables
print (f"ahh yes, so it is you...{first_name} of the {clan_name} clan! you are aged {age}")
#fstring helps us do stuff with string holding variables and cruly braces

print ("whats your ip? ")
ip = input()
print ("You are currently targetting " + str(ip))

#OR a more effective way of donig this would be
print ("he is currently targetting " + input("what is his ip? "))

