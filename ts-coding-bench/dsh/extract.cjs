// Only copy a bounded regular file. Never follow agent-created symbolic links.
const fs=require('node:fs');
const fd=fs.openSync('/workspace/solution.ts',fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW|fs.constants.O_NONBLOCK);
const stat=fs.fstatSync(fd);
if(!stat.isFile()||stat.size>262144)throw Error('solution.ts must be a regular file <=256 KiB');
const bytes=Buffer.alloc(262145);
const n=fs.readSync(fd,bytes,0,bytes.length,0);
fs.closeSync(fd);
if(n>262144)throw Error('solution.ts exceeds 256 KiB');
process.stdout.write(bytes.subarray(0,n));
