import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve, join } from 'node:path';
import * as prettier from 'prettier';
const root=resolve('..');
const python=process.env.PYTHON || (existsSync(join(root,'backend/.venv/bin/python'))?join(root,'backend/.venv/bin/python'):existsSync(join(root,'backend/.venv/Scripts/python.exe'))?join(root,'backend/.venv/Scripts/python.exe'):'python');
const directory=mkdtempSync(join(tmpdir(),'internpilot-type-contract-'));
try {
  const schema=join(directory,'openapi.json'), target=join(directory,'types.ts');
  for(const [command,args] of [[python,[join(root,'scripts/export-openapi.py'),schema]],[process.execPath,['node_modules/openapi-typescript/bin/cli.js',schema,'-o',target]]]) {
    const result=spawnSync(command,args,{stdio:'inherit'});if(result.status!==0)process.exitCode=1;
    if(process.exitCode)break;
  }
  if(!process.exitCode) {
    const config=await prettier.resolveConfig('src/lib/generated-api-types.ts');
    const expected=await prettier.format(readFileSync(target,'utf8'),{...config,parser:'typescript'});
    if(expected!==readFileSync('src/lib/generated-api-types.ts','utf8'))throw new Error('API types drifted. Export schema, regenerate types, and format before committing.');
    console.log('Generated API request types match the current backend.');
  }
} finally {rmSync(directory,{recursive:true,force:true});}
