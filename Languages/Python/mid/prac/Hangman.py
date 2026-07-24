import random
#this library helps us pick random words
print ("hello, let us play hangman!!")

words = ["sakai", "penis", "zebra", "cobra"]

secret_word = random.choice(words)
print ("you get 5 guesses")
display_word = []
#this display_word will help us create the underscore word
for letter in (secret_word):
    display_word += "_"
print (display_word)
#it will look like this "_","_","_" for a three letter word
num = 0
#this is the integer of number of guesses
game_over = False
while not game_over:
#so that the game continues even after if we guess a letter

    guess = input ("guess a letter buddy ").lower()
#lower is for the lower case input  
    for position in range(len(secret_word)):
#basically, this loop will help us match our guess with every letter of the random word
        letter = secret_word[position]
        if letter == guess:
           display_word[position] = letter
#in the underscore word, we will see our guessed letter at the right spot
    if guess not in secret_word:
        num += 1
#this is the number of wrong guesses
        guesses_left = 5-num
        print (f"guesses left = {guesses_left}")
        if num >= 5:
            print ("you're cooked")
            game_over = True
    print(display_word)

    if "_" not in display_word:
        print ("You are hangman!")
        game_over = True