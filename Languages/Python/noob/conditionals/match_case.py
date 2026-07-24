name = input("what's your name? ")

match name:
    case "Neo"|"Trinity"|"Morpheus":
        print ("The scientist")
   
        # '|' is used to denote 'or' in match case statements
   
    case "Paradox"| "Batman"| "Jotaro":
        print ("The enigma")
    case _:
        print("Database under construction. Come back later.")
                   