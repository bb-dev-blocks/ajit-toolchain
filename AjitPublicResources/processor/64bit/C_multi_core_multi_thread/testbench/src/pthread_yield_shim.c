#include <sched.h>

/* glibc 2.34 dropped pthread_yield; ahir's pipe handler still calls it. */
int pthread_yield(void)
{
	return sched_yield();
}
