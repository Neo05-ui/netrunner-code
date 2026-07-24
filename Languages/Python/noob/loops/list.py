students = ["Harry", "Hermione", "Ron", "Draco"]
houses = ["Gryffindor", "Gryffindor", "Gryffindor", "Slytherin"]
for i in range(len(students)):
    print (f"{i + 1}. {students[i]} - {houses[i]}")


# prints each student in the list, more readable than using indexes
# [] can also be used to index the lists, e.g. students[0] is the first student and so on.
# len(students) gives the length of the list
# range(len(students)) gives a range of numbers from 0 to length-1
# enumerate gives both the index and the value at that index in the list
# f" {} " is an f-string, which allows putting expressions inside string literals