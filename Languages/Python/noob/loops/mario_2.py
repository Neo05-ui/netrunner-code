def print_square(size):
     for i in range(size):
      # for each row
       for j in range(size):
        # for each column
         print ("#", end="")
        #print a block with a newline after each
       print()
def main():
    print_square (4)

main()
# python is very serious about indentation
# print is always indented ahead of the for loops, this makes it a part of the inner loop
# indentations is how we differentiate between layers of code.