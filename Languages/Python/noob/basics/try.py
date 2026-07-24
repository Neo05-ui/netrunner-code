try:
    #try basically just tries new code and hopes it runs without errors
    x = int(input("What's x? "))
    print (f"x is {x}")
except ValueError:
    #IF try fails and the code has a bug or an error, except runs instead, handling the error
    print ("you are fucking stupid")
    else:
        break

print (f"x is {x}")