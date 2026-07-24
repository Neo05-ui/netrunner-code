def meow(n):
    for _ in range(n):
        print("meow")

# (:) the colon means next indented (spaced forward) block is part of the function

def get_number():
    while True:
        n = int(input("what's n? "))
        if n > 0:
            return n

def main():
    number = get_number()
    meow (number)

main()
# we call the main function to start the program
# the def main function is the last thing in the file. we define all other functions above it.