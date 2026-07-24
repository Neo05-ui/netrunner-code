#gonna build a coffee shop together using python ofc
#let build a robot barista
print ("hello! welcome to neo's coffee shop!!!")
print ("what's your name??")
name = input ()

print ("here's a menu that you can choose from " +name)
print ("Burger, " "Pizza, " "Coffee, " "Latte, " "Dih")

order = input()

print ("is there anything else? yes/no")
reply = input()
if reply == ("yes"):
   print ("what else?")
   order_2 = input ()
if reply ==("no"):
     print ("okiee")

price = {
   "Pizza": 7,
   "Burger": 5,
   "Coffee": 14,
   "Latte": 10,
   "Dih": 28,
}

cost_1 = price.get(order, 0)
cost_2 = price.get(order_2, 0)
#get functions gets the price from the dictionary of the particular item, and 0 in front just makes it 0 by default)
#figure out a way to make this work if there is NO order_2
print ("how old are you pookie? ")
age = int(input())

if 0 <= age <18:
   print ("Here's your "+ order + " "+ "and " + order_2 + ", " +name + "!!! there aint no diddling involved here.")

if age>= 18:
   print ("Here's your "+ order +" " + "and " + order_2 + ", "+ name + "!!!! Now lets have seggs")

print ("what quantity of "+ order + " "+ "would you like?")
#make a way to get seperate quantities for each order
quantity = int(input())

print ("what quantity of "+ order_2 +" "+ "would you like?" )
quantity_2 = int(input())

total = (quantity * cost_1) + (quantity_2 * cost_2)

print ("did you like the "+ order +" "+ "and " + order_2 + "?")
answer = input().lower()
#i put the lower() there to take the answer in lower case
if answer == ('yes'):
   print ("type shi son i know this shi peak ")
elif answer == ('no'):
   print ("nigga disappear before i clock yo shi")

print ("here's your total "+ name + ": "+ "$"+ str(total))
#str() makes stuff into string like int() makes stuff into integer so that we can use + sign
print ("have a nice day byeei byeiii")



