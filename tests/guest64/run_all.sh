#!/bin/bash
# Full regression for the 64-bit guest. Usage: tests/run_all.sh [x86|arm]
# Uses fresh copies of the roots, so nothing here changes alpine64-clean/-dev.
cd ${ROOTS:-~/src/ish64-roots}
which=${1:-x86}
if [ $which = arm ]; then ISHBIN="qemu-aarch64 $HOME/src/ish64/build64arm/ish"; else ISHBIN="${ISHBIN:-$HOME/src/ish64/build64r/ish}"; fi
D=$PWD/alpine64-dev
fails=0
ok() { echo "PASS  $1"; }
bad() { echo "FAIL  $1"; fails=$((fails+1)); }
# 1. shell checks on a fresh copy of the clean root
W=$PWD/regress-clean-$$; cp -a alpine64-clean $W
r=$(ISH="$ISHBIN" ROOT=$W ./run_checks.sh | tail -1); [ "$r" = "64-bit checks: 15 passed, 0 failed" ] && ok "shell checks ($r)" || bad "shell checks ($r)"
# 2. programs whose output must equal the native run of the same binary
for t in torture_O0 torture_O2 simd nan notify; do
    n=tests/$t.native; [ -f $n ] || n=tests/native_${t#torture_}.txt
    b=${t}; [ -f tests/$t.bin ] || b=$t
    timeout -s KILL 900 $ISHBIN -f $D /root/$b > tests/$t.$which.out 2>&1
    cmp -s $n tests/$t.$which.out && ok "$t identical to native" || bad "$t differs from native"
done
# 3. programs that print OK/FAIL lines
for t in sys as64 ptrace smc; do
    timeout -s KILL 300 $ISHBIN -f $D /root/$t > tests/$t.$which.out 2>&1
    n=$(grep -c "OK$" tests/$t.$which.out); f=$(grep -Evc "OK$|refused \(ish limit" tests/$t.$which.out)
    [ $f = 0 ] && [ $n -gt 5 ] && ok "$t ($n checks)" || bad "$t ($f not OK of $((n+f)))"
done
r=$(timeout -s KILL 300 $ISHBIN -f $D /root/execthr 2>&1 | tail -1); [ "$r" = "exec with 9 other threads: 20 of 20 ok" ] && ok "execve from a threaded process" || bad "execthr: $r"
r=$(timeout -s KILL 120 $ISHBIN -f $D /root/sig 2>&1); [ "$r" = "signals delivered: yes, long double equal: 1, double equal: 1" ] && ok "signal handler keeps FP state" || bad "sig: $r"
# 4. Python
P=$PWD/regress-py-$$; cp -a alpine64-python $P
r=$(timeout -s KILL 300 $ISHBIN -f $P /bin/sh -c "$(cat py_only.sh)" 2>&1 | md5sum | cut -c1-8)
[ "$r" = "$(cat tests/py_only.md5 2>/dev/null)" ] && ok "python script" || bad "python script (md5 $r)"
# 5. system behaviors that Python's own OS tests exposed
n=$(timeout -s KILL 120 $ISHBIN -f $P /usr/bin/python3 - < tests/py/os_misc.py 2>&1 | grep -c "True$")
[ "$n" = 33 ] && ok "OS behaviors ($n checks)" || bad "OS behaviors ($n of 33)"
# 6. JIT compilers: Node running generated code, alone and in six threads (needs a root with node)
if [ -d alpine64-big ]; then
    N=$PWD/regress-node-$$; cp -a alpine64-big $N
    T=$HOME/src/ish64/tests/guest64
    r=$(timeout -s KILL 2400 $ISHBIN -f $N /bin/sh -c 'export PATH=/usr/local/bin:/usr/bin:/bin; cat > /tmp/t.js; node /tmp/t.js' < $T/jitstress.js 2>&1 | tail -1)
    [ "$r" = "2233830945" ] && ok "node JIT stress" || bad "node JIT stress: $r"
    r=$(timeout -s KILL 2400 $ISHBIN -f $N /bin/sh -c 'export PATH=/usr/local/bin:/usr/bin:/bin; cat > /tmp/t.js; node /tmp/t.js' < $T/workers.js 2>&1 | tail -1)
    [ "$r" = "2748341649,300941309,3196927470,1192551412,1616053237,1416627574 9600" ] && ok "node JIT in six threads" || bad "node workers: $r"
else
    N=
fi
echo "$which: $fails failed"
echo "temporary roots left behind (delete them): $W $P $N"
