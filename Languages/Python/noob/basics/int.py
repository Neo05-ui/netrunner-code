x = float(input ("what's x? "))
y = float(input ("what's y? "))

#its better to make a third vaiable to hold the result of a calculation rather than putting the calculation directly into the print statement which is easier to edit
z = round(x/y)
#the 2 at the end suggests how many decimal places we want to round to
#the round off will always keep the decimal places even if they are zeros
print ("by dividing x by y we get: ")

print (f"{z:2f}")  
#formatted string literal (f-string) allows us to embed expressions inside string literals, using curly braces {}
