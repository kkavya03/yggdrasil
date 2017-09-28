#include "PsiInterface.hpp"
#include <string>
#include <iostream>
using namespace std;

int main(int argc, char *argv[]) {
  int ret = 1;
  const int bufsiz0 = 512;
  char buf[bufsiz0];

  cout << "Hello from C++\n";
  
  /* Matching with the the model yaml */
  PsiInput inf("inFile"); 
  PsiOutput outf("outFile");
  PsiInput inq("helloParQueueIn");
  PsiOutput outq("helloParQueueOut");
  cout << "helloPar(CPP): Created I/O channels\n";

  // Receive input from the local file
  ret = inf.recv(buf, bufsiz0);
  if (ret < 0) {
    printf("helloPar(CPP): ERROR FILE RECV\n");
    return -1;
  }
  int bufsiz = ret;
  printf("helloPar(CPP): Received %d bytes from file: %s\n", bufsiz, buf);

  // Send output to queue
  ret = outq.send(buf, bufsiz);
  if (ret != 0) {
    printf("helloPar(CPP): ERROR QUEUE SEND\n");
    return -1;
  }
  printf("helloPar(CPP): Sent to outq\n");

  // Receive input from queue
  ret = inq.recv(buf, bufsiz0);
  if (ret < 0) {
    printf("helloPar(CPP): ERROR QUEUE RECV\n");
    return -1;
  }
  bufsiz = ret;
  printf("helloPar(CPP): Received %d bytes from queue: %s\n", bufsiz, buf);

  // Send output to local file
  ret = outf.send(buf, bufsiz);
  if (ret != 0) {
    printf("helloPar(CPP): ERROR FILE SEND\n");
    return -1;
  }
  printf("helloPar(CPP): Sent to outf\n");

  cout << "Goodbye from C++\n";
  return 0;
}