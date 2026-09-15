/** Allocate memory and communicate via queue.
*/
#include<math.h>
#include "cortos.h"

#define SIZE 80

int *i0 = SHARED_INT_ADDR_0;
int *i1 = SHARED_INT_ADDR_1;
int queueId = -1;

CortosMessage msg1;
CortosMessage msg2;


void main() {} // important, but keep empty.

void cortos_entry_func_001() {
  // allocate memory and write data
  CORTOS_DEBUG("Acquiring Memory!\n");
  int *a = (int*)cortos_bget(sizeof(int) * 20);
  a[0] = 10;
  a[19] = 11;

  CORTOS_TRACE("This will not get logged.");

  // send message
  msg1.a_code = 1;
  msg1.a_ptr = a;
  CORTOS_DEBUG("Sending Message!\n");
  queueId = cortos_reserveQueue();
  cortos_writeMessage(queueId, &msg1);

  cortos_exit(0); //safely exit
}

void cortos_entry_func_010() {
  return;
}

void cortos_entry_func_101() {
  while (queueId == -1)
    ;
  while (!cortos_readMessage(queueId, &msg2))
    ;

  CORTOS_DEBUG("Received Message!\n");

  // process the message
  int *arr = (int*)msg2.a_ptr;
  *i0 = arr[0];
  *i1 = arr[19];

  CORTOS_DEBUG("Releasing Memory!\n");
  // release the memory
  cortos_brel(msg2.a_ptr);

  cortos_exit(0); //safely exit
}

void cortos_entry_func_110() {
  return;
}


