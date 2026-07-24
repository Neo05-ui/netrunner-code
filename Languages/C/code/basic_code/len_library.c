#include <stdio.h>
#include <cs50.h>
#include <string.h>

int main(void)
{
    string name = get_string("Name ");
    int length = strlen(name);
    printf("%i\n", length);
}
// this program is shorter then 'length' code because of the use of string.h library
