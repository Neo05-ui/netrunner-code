def is_even(n):
    if n % 2 == 0:
       return True
    else:
       return False
    
def main():
    x = float(input("what's x? "))
    if is_even (x):
        print("x is even")
    else:
        print ("x is odd")
    
main ()