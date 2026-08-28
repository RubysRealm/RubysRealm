import fs from 'node:fs/promises';
import handler from '../api/story-video.js';

const output = process.argv[2] || '/tmp/rubys-realm-story-test.mp4';
const headers = new Map();

const req = {
  method:'GET',
  query:{ seed:'local-quality-check' }
};

let statusCode = 200;
const res = {
  setHeader(name,value) { headers.set(String(name).toLowerCase(),String(value)); },
  status(code) { statusCode = code; return this; },
  end() { return undefined; },
  json(value) { throw new Error(`Render returned ${statusCode}: ${JSON.stringify(value)}`); },
  async send(value) {
    if (statusCode !== 200) throw new Error(`Render returned ${statusCode}.`);
    await fs.writeFile(output,value);
  }
};

await handler(req,res);
console.log(JSON.stringify({ output,statusCode,headers:Object.fromEntries(headers) },null,2));
