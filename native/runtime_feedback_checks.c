/* Authored shutdown/lazy-I/O harness: no original game code or ROM. */
#include "runtime_feedback.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc,char **argv) {
    rr_feedback_start(argc<2 || strcmp(argv[1],"disabled"));
    unsigned n=argc>2?(unsigned)atoi(argv[2]):1;
    unsigned base=argc>3?(unsigned)atoi(argv[3]):0;
    if(argc>1 && !strcmp(argv[1],"toggle-on"))rr_feedback_toggle();
    if(argc<2 || strcmp(argv[1],"none"))for(unsigned i=0;i<n;++i) {
        uint8_t bytes[4]={0x3e,0xa5,0x76,0};
        rr_feedback_note(1,base+i,0,bytes,4);
        rr_feedback_note(1,base+i,0,bytes,4);
    }
    if(argc>1 && !strcmp(argv[1],"hold-off"))rr_feedback_toggle();
    puts("buffered");fflush(stdout);
    if(argc>1 && !strncmp(argv[1],"hold",4))getchar();
    return 0;
}
