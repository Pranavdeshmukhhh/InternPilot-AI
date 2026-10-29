import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile, mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import ts from 'typescript';
import { QueryClient } from '@tanstack/react-query';

// Exercise the actual transport code, including its generation and CSRF checks.
const directory = await mkdtemp(join(tmpdir(), 'internpilot-query-'));
const source = await readFile(new URL('../src/lib/api-client.ts', import.meta.url), 'utf8');
const output = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } });
const moduleFile = join(directory, 'api.mjs');
await writeFile(moduleFile, output.outputText);
const { api, setApiSession, ApiError } = await import(pathToFileURL(moduleFile));
const originalFetch = globalThis.fetch;
try {
  await test('a response begun under the old account cannot populate the next session', async () => {
    let complete;
    globalThis.fetch = () => new Promise(resolve => { complete = resolve; });
    setApiSession('old-session-csrf');
    const previous = api('/profile');
    setApiSession('new-session-csrf');
    complete(new Response(JSON.stringify({ name: 'Private old account' }), { status: 200 }));
    await assert.rejects(previous, error => error instanceof ApiError && error.status === 409);
  });
  await test('identical concurrent queries coalesce; account partitions do not reuse private data', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000, retry: false } } });
    let calls = 0;
    globalThis.fetch = async () => { calls += 1; return Response.json({ version: calls }); };
    const queryFn = ({ signal }) => api('/documents', 'GET', undefined, false, signal);
    const options = { queryKey: ['private', 'one', 1, '/documents'], queryFn };
    const [first, duplicate] = await Promise.all([client.fetchQuery(options), client.fetchQuery(options)]);
    assert.equal(calls, 1); assert.deepEqual(first, duplicate);
    const second = await client.fetchQuery({ ...options, queryKey: ['private', 'two', 2, '/documents'] });
    assert.equal(calls, 2); assert.notDeepEqual(first, second);
    client.clear(); assert.equal(client.getQueryData(options.queryKey), undefined);
  });
  await test('exact action CSRF header and abort signal are forwarded, without automatic mutation retries', async () => {
    let calls = 0; const controller = new AbortController();
    setApiSession('synthetic-action-token');
    globalThis.fetch = async (url, options) => {
      calls += 1; assert.equal(options.headers['X-CSRF-Token'], 'synthetic-action-token');
      assert.equal(options.signal, controller.signal); assert.equal(options.credentials, 'same-origin');
      return Response.json({ detail: 'Approval was revoked' }, { status: 403 });
    };
    await assert.rejects(api('/applications/id/approve', 'POST', { consent: true }, false, controller.signal), error => error.status === 403 && error.message === 'Approval was revoked');
    assert.equal(calls, 1);
  });
  await test('successful empty deletion is distinguishable from a failed action sentinel', async () => {
    globalThis.fetch = async () => new Response(null, { status: 204 });
    assert.equal(await api('/sources/id', 'DELETE'), undefined);
  });
  await test('validation and temporary outage errors preserve actionable server messages', async () => {
    globalThis.fetch = async () => Response.json({ detail: [{ msg: 'Graduation year must be valid' }] }, { status: 422 });
    await assert.rejects(api('/profile', 'PUT', {}), /Graduation year must be valid/);
    globalThis.fetch = async () => Response.json({ detail: 'Queue capacity reached' }, { status: 503 });
    await assert.rejects(api('/discovery/run', 'POST', {}), error => error.status === 503 && error.message === 'Queue capacity reached');
  });
} finally {
  globalThis.fetch = originalFetch;
  await rm(directory, { recursive: true, force: true });
}
