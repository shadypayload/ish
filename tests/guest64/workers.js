// Expected output (same as native Node):
//   2748341649,300941309,3196927470,1192551412,1616053237,1416627574 9600
// Threads + JIT at once: 6 workers each compiling and running generated functions, sharing an atomic counter.
const { Worker, isMainThread, parentPort, workerData } = require('worker_threads');
if (isMainThread) {
  const sab = new SharedArrayBuffer(16);
  const ctr = new Int32Array(sab);
  let done = 0; const sums = [];
  for (let w = 0; w < 6; w++) {
    const wk = new Worker(__filename, { workerData: { w, sab } });
    wk.on('message', m => { sums[m.w] = m.h; if (++done == 6) console.log(sums.join(','), Atomics.load(ctr, 0)); });
    wk.on('error', e => { console.log('worker error', e.message); process.exit(1); });
  }
} else {
  const { w, sab } = workerData; const ctr = new Int32Array(sab);
  let h = w;
  for (let r = 0; r < 40; r++) {
    for (let k = 0; k < 40; k++) {
      const f = new Function('a', `let s=${k + w}; for(let i=0;i<a;i++){ s=(s*${(k % 5) + 3}+i)%${997 + k}; } return s;`);
      h = (Math.imul(h ^ f(300 + r), 0x9e3779b1) + r) | 0;
      Atomics.add(ctr, 0, 1);
    }
    const buf = Buffer.alloc(20000, r + w); h = (h + buf.reduce((a, b) => (a + b) | 0, 0)) | 0;
  }
  parentPort.postMessage({ w, h: h >>> 0 });
}
