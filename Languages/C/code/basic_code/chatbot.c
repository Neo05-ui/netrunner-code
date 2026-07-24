#include <cs50.h>
#include <stdio.h>
#include<string.h>
int main(void)

{
    string answer = get_string("what is your name? ");
    printf("hello, %s\n", answer);
     string shi = get_string("how are you? ");

    if (strcmp(shi, "im good") == 0)
    {
        printf("type shi son\n");
    }
    else if (strcmp(shi, "not good") == 0)
    {
        printf("nah you're cooked\n");
    }
}
