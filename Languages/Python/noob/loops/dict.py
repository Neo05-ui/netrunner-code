students = [
    {"name": "Harry", "house": "Gryffindor", "patronus": "Stag"},
    {"name": "Hermione", "house": "Gryffindor", "patronus": "Otter"},
    {"name": "Ron", "house": "Gryffindor", "patronus": "Jack Russell terrier"},
    {"name": "Draco", "house": "Slytherin", "patronus": None},
] 
# [] creates a list and {} creates a dictionary. here we have a list of dictionaries.

for student in students:
 print (student ["name"] + " from " + student ["house"] + " has the following patronous - " + str(student ["patronus"]))

# we put str around student["patronus"] because it can be None, and we need to convert it to a string to concatenate it with other strings
# we access dictionary values using square brackets and the key name, e.g. student["name