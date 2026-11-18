// Expected output: 2233830945 (same as native Node). Run in a root that has node:
//   ish -f ROOT /bin/sh -c 'node -' < tests/guest64/jitstress.js
// JIT churn: thousands of generated functions, type changes that force deoptimization, closures, regexps.
let h = 0;
function mix(x) { h = (Math.imul(h ^ (x | 0), 0x9e3779b1) + 0x7f4a7c15) | 0; }
for (let round = 0; round < 60; round++) {
  const fs = [];
  for (let k = 0; k < 120; k++)
    fs.push(new Function('a', 'b', `let s=${k}; for(let i=0;i<a;i++){ s = (s*${(k % 7) + 2} + (i ^ b)) % ${1000 + k}; } return s + ${round};`));
  for (let k = 0; k < fs.length; k++) mix(fs[k](200 + k, round));
  const poly = x => x + x;
  for (let i = 0; i < 4000; i++) mix(typeof poly(i % 3 == 0 ? i : i % 3 == 1 ? 'a' + i : i + 0.5) == 'string' ? i : 7);
  const o = {}; for (let i = 0; i < 300; i++) o['p' + (i * round % 97)] = i; mix(Object.keys(o).length);
  mix(('x'.repeat(round) + 'abc' + round).replace(/x+/g, m => m.length).length);
  mix(eval(`(function(){ let t=0; for(let i=0;i<${500 + round};i++) t+=i%${round + 2}; return t })()`));
  mix(Math.round(Math.sqrt(round * 1234.5) * 1000));
}
console.log(h >>> 0);
