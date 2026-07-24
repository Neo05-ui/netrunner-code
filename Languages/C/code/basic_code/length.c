#include <stdio.h>
#include <cs50.h>

int string_length (string s);
int main (void)
{
string name = get_string ("Name ");
int length = string_length (name);
printf ("%i\n", length);
}

// this is the function to calculate length of string

int string_length (string s)
{
    int n = 0;
    while (s[n] != '\0')

    // '\0' is used to indicate the end of string and != means not equal to
    
    {
        n++;
    }
    return n;
}
