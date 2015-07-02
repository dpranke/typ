#include <stdio.h>
#include <string.h>

int main(int argc, const char **argv) {
  const char *greeting = "Hello";
  const char *noun = "world";

  if (((argc > 1) && (!strcmp(argv[0], "-h") || !strcmp(argv[0], "--help"))) ||
      (argc > 3)) {
    printf("Usage: hello [greeting] [noun]\n");
    return 0;
  }
  if (argc > 1) {
    greeting = argv[1];
  }
  if (argc > 2) {
    noun = argv[2];
  }
  printf("%s, %s.\n", greeting, noun);
  return 0;
}
