import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const source=await readFile(new URL('../src/lib/application-status.ts',import.meta.url),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText;
const {applicationStage,applicationMatches}=await import('data:text/javascript;base64,'+Buffer.from(compiled).toString('base64'));
test('all known and future application states retain a board column',()=>{
  for(const status of ['queued','preparing','ready','approved','submitting'])assert.equal(applicationStage(status),'Preparing');
  for(const status of ['awaiting_review','needs_input','uncertain','failed','new-server-state'])assert.equal(applicationStage(status),'Review');
  for(const status of ['submitted','assessment','interview'])assert.equal(applicationStage(status),'Follow-up');
  for(const status of ['offer','rejected','withdrawn'])assert.equal(applicationStage(status),'Closed');
});
test('filters keep pending submission and failed work visible without claiming submission',()=>{
  assert.ok(applicationMatches('approved','progress'));
  assert.ok(applicationMatches('submitting','progress'));
  assert.ok(applicationMatches('failed','attention'));
  assert.ok(applicationMatches('new-server-state','attention'));
  assert.equal(applicationMatches('submitting','submitted'),false);
  assert.equal(applicationMatches('ready','submitted'),false);
  assert.ok(applicationMatches('submitted','submitted'));
});
