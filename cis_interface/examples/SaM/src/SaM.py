#!/usr/bin/python
import sys
from cis_interface.interface.PsiInterface import PsiInput, PsiOutput


if __name__ == '__main__':

    # Get input and output channels matching yaml
    in1 = PsiInput('input1')
    in2 = PsiInput('static')
    out1 = PsiOutput('output')
    print('SaM(P): Set up I/O channels')

    # Get input from input1 channel
    ret, adata = in1.recv()
    if not ret:
        print('SaM(P): ERROR RECV from input1')
        sys.exit(-1)
    a = int(adata[0])
    print('SaM(P): Received %d from input1' % a)

    # Get input from static channel
    ret, bdata = in2.recv()
    if not ret:
        print('SaM(P): ERROR RECV from static')
        sys.exit(-1)
    b = int(bdata[0])
    print('SaM(P): Received %d from static' % b)

    # Compute sum and send message to output channel
    sum = a + b
    outdata = 'Sum = %d\n' % sum
    ret = out1.send(outdata)
    if not ret:
        print('SaM(P): ERROR SEND to output')
        sys.exit(-1)
    print('SaM(P): Sent to output')
