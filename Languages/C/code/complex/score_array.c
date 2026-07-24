#include <cs50.h>
#include <stdio.h>

int main (void)
{
    // N is a constant number

    const int N = 5;
    int scores[N];

    // [] is used for making arrays

    for (int i = 0; i < N; i++)
    {
        scores[i] = get_int("enter score %i: ", i + 1);
    }
    printf(" average: %f\n", (scores[0] + scores[1] + scores[2] +scores[3] + scores[4]) / (float) N);

    // float is used for decimal values

}
