#make a calculator that can add, subtract, multiply, and divide two numbers and also compare them.

def add (x,y):
    return x + y

def subtract (x,y):
    return x - y

def multiply (x,y):
    return x*y

def divide (x,y):
    if y == 0:
        print ("error, cannot divide by zero")
    else: 
        return x / y

def compare (x,y):
   if x >y:
      print ("x is greater than y")
   elif y>x:
      print ("y is greater than x")
   else:
      print ("x is equal to y")
      
num1 = int(input("Enter first number: "))
num2 = int(input("Enter second number: "))

operation = input("Enter operation (+, -, *, /, compare): ")

if operation == "+":
    print (add(num1,num2))  
elif operation == "-":
    print (subtract(num1,num2))
elif operation == "*":
       print (multiply(num1,num2))
elif operation == "/":
       print (divide(num1,num2))
elif operation == "compare":
       compare(num1,num2)
else:
    print ("Invalid operation")
      
   