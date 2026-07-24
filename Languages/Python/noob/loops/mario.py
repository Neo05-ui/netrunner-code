def print_row(width):
     print("?" * width)
#there is no newline after print_row

def print_columns(height):
    for h in range(height):
        print("#\n" * height, end="")
#there are newlines after each column (that's why we use \n in the print statement)

def main():
    print_row(4)
    print_columns(2)

main()