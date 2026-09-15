const fs = require('fs');
const { execFileSync } = require('child_process');

const sourcePath = 'rubyclips/muffin_story_resolve.js';
const tempPath = 'rubyclips/muffin_story_resolve.recovery.cjs';
let source = fs.readFileSync(sourcePath, 'utf8');

const wrong = "39: '7680667081213234450'";
const correct = "39: '7682997046713781518'";
if (source.includes(wrong)) {
  source = source.replace(wrong, correct);
} else if (!source.includes(correct)) {
  throw new Error('Episode 39 mapping was not found in the original MuffinDrama resolver.');
}

fs.writeFileSync(tempPath, source);
console.log('Running original MuffinDrama resolver with corrected Episode 39 canonical ID.');
execFileSync('node', [tempPath], { stdio: 'inherit' });
