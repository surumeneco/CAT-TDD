/** Bounded source inspection. Never evaluates the inspected TypeScript. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';

const fail = message => { throw new Error(message); };
const requireThat = (condition, message) => { if (!condition) fail(message); };
const digest = name => crypto.createHash('sha256').update(fs.readFileSync(name)).digest('hex');
const read = name => JSON.parse(fs.readFileSync(name, 'utf8'));
const inside = (root, name) => { const p = path.relative(root, name); return p !== '..' && !p.startsWith('..'+path.sep) && !path.isAbsolute(p); };
const repo = fs.realpathSync(process.argv[2]);
const files = process.argv.slice(3).map(p => fs.realpathSync(p));
const scope = 'typed data arguments and unmodified standard intrinsics; explicit locale for collation; excludes callers, accessor/proxy behavior, loader and build transforms';
try {
  requireThat(files.length && files.every(p => inside(repo,p) && p.endsWith('.ts')), 'exact TypeScript source files required');
  const pkg = fs.realpathSync(path.join(repo, 'node_modules/typescript'));
  requireThat(inside(repo,pkg), 'compiler outside repository');
  const meta = read(path.join(pkg,'package.json'));
  const lock = read(path.join(repo,'package-lock.json'));
  requireThat(meta.name === 'typescript' && meta.version === lock.packages?.['node_modules/typescript']?.version, 'installed TypeScript differs from lockfile');
  const compiler = path.join(pkg,'lib/typescript.js');
  const ts = createRequire(import.meta.url)(compiler);
  requireThat(ts.version === meta.version, 'compiler version mismatch');
  const program = ts.createProgram(files, {target:ts.ScriptTarget.ES2022, module:ts.ModuleKind.NodeNext,
    moduleResolution:ts.ModuleResolutionKind.NodeNext, strict:true, noUncheckedIndexedAccess:true,
    noEmit:true, skipLibCheck:true, types:[]});
  const checker = program.getTypeChecker();
  const sources = files.map(file => program.getSourceFile(file));
  requireThat(sources.every(Boolean), 'source not loaded');
  const diagnostics = ts.getPreEmitDiagnostics(program).filter(d => d.category === ts.DiagnosticCategory.Error);
  requireThat(!diagnostics.length, diagnostics.length ? ts.flattenDiagnosticMessageText(diagnostics[0].messageText,' ') : 'compiler diagnostics');
  const funcs = new Map(), publicNames = new Set(), graph = new Map();
  const typeFiles = new Set(program.getSourceFiles().filter(f=>!program.isSourceFileDefaultLibrary(f)).map(f=>{const file=fs.realpathSync(f.fileName); requireThat(inside(repo,file) && !file.includes(path.sep+'node_modules'+path.sep), 'nonlocal data type dependency'); requireThat(!/@ts-(?:nocheck|ignore|expect-error)\b/.test(f.text),'typecheck suppression in dependency'); return file;}));
  const symbol = node => checker.getSymbolAtLocation(node);
  const nameOf = node => ts.isIdentifier(node) ? node.text : '';
  const modifiers = node => node.modifiers?.map(m=>m.kind) ?? [];
  const primitive = (type, flags) => !!(type.flags & flags) || !!type.isUnion?.() && type.types.every(t=>primitive(t,flags));
  const numeric = type => primitive(type,ts.TypeFlags.NumberLike);
  const text = type => primitive(type,ts.TypeFlags.StringLike);
  const array = type => checker.isArrayType(type) || checker.isTupleType(type);
  const libSymbol = (node, name) => { const s=symbol(node); return s?.name===name && !!s.declarations?.length && s.declarations.every(d => program.isSourceFileDefaultLibrary(d.getSourceFile())); };
  const remember = node => { const f=node.getSourceFile(); if (!program.isSourceFileDefaultLibrary(f)) { requireThat(inside(repo,f.fileName), 'data type outside repository'); typeFiles.add(f.fileName); } };
  const data = (type, opaque, visited=new Set()) => {
    if (type.flags & (ts.TypeFlags.Any|ts.TypeFlags.Unknown|ts.TypeFlags.ESSymbolLike|ts.TypeFlags.BigIntLike)) return false;
    if (type.flags & (ts.TypeFlags.BooleanLike|ts.TypeFlags.StringLike|ts.TypeFlags.NumberLike|ts.TypeFlags.Null|ts.TypeFlags.Undefined|ts.TypeFlags.Never)) return true;
    if (type.flags & ts.TypeFlags.TypeParameter) return opaque.has(type.symbol);
    if (type.isUnion?.()) return type.types.every(t=>data(t,opaque,visited));
    if (visited.has(type) || visited.size>=16) return false;
    const next=new Set(visited);next.add(type);
    if(array(type)) return checker.getTypeArguments(type).length>0 && checker.getTypeArguments(type).every(t=>data(t,opaque,next));
    if(!(type.flags & ts.TypeFlags.Object) || type.getCallSignatures().length || type.getConstructSignatures().length || checker.getIndexInfosOfType(type).length) return false;
    const props=checker.getPropertiesOfType(type);
    return props.length>0 && props.length<=64 && props.every(prop => {
      if (!prop.declarations?.length || !prop.declarations.every(d=>ts.isPropertySignature(d)&&!ts.isComputedPropertyName(d.name))) return false;
      prop.declarations.forEach(remember);
      return data(checker.getTypeOfSymbolAtLocation(prop,prop.declarations[0]),opaque,next);
    });
  };
  for(const sf of sources){
    requireThat(!sf.referencedFiles.length&&!sf.typeReferenceDirectives.length&&!sf.libReferenceDirectives.length,'reference directives unsupported');
    requireThat(!/@ts-(?:nocheck|ignore|expect-error)\b/.test(sf.text),'typecheck suppression unsupported');
    for(const statement of sf.statements){
      if(ts.isImportDeclaration(statement)){
        requireThat(statement.importClause?.isTypeOnly && ts.isStringLiteral(statement.moduleSpecifier) && statement.moduleSpecifier.text.startsWith('.'), 'runtime or external import unsupported');
        continue;
      }
      // Only actual exported function implementations: no module initialization.
      requireThat(ts.isFunctionDeclaration(statement)&&statement.name&&statement.body&&!statement.asteriskToken&&
        modifiers(statement).length===1&&modifiers(statement)[0]===ts.SyntaxKind.ExportKeyword,'unsupported top-level declaration');
      const id=symbol(statement.name), name=statement.name.text;
      requireThat(id&&!publicNames.has(name),'duplicate public function');
      publicNames.add(name);funcs.set(id,statement);graph.set(id,new Set());
    }
  }
  requireThat(funcs.size>0 && funcs.size<=32,'empty or excessive function scope');
  const typeOf = node => checker.getTypeAtLocation(node);
  const magic = new Set(['__proto__','prototype','constructor','caller','callee','arguments']);
  const K=ts.SyntaxKind;
  const comparisons = new Set([K.LessThanToken,K.LessThanEqualsToken,K.GreaterThanToken,K.GreaterThanEqualsToken]);
  const logical = new Set([K.AmpersandAmpersandToken,K.BarBarToken,K.EqualsEqualsEqualsToken,K.ExclamationEqualsEqualsToken]);
  for(const [functionId,fn] of funcs){
    const locals=new Set(), ownedArrays=new Set(), opaque=new Set();
    for(const tp of fn.typeParameters??[]){
      requireThat(!tp.constraint&&!tp.default&&!tp.modifiers?.length,'only opaque unconstrained type parameters supported');
      opaque.add(symbol(tp.name));
    }
    function parameter(p, target){
      requireThat(ts.isIdentifier(p.name)&&!p.initializer&&!p.dotDotDotToken&&!p.questionToken&&!p.modifiers?.length,'unsupported parameter');
      requireThat(data(typeOf(p),opaque),'non-data parameter: '+p.name.text);
      target.add(symbol(p.name));
    }
    for(const p of fn.parameters){ requireThat(!!p.type,'explicit parameter type required'); parameter(p,locals); }
    const seen = node => node.getText().slice(0,100);
    function expression(n, env=locals){
      requireThat(!!n,'expression missing');
      if(ts.isIdentifier(n)){requireThat(env.has(symbol(n)),'ambient or unresolved identifier: '+n.text);return;}
      if(ts.isStringLiteral(n)||ts.isNumericLiteral(n)||[K.TrueKeyword,K.FalseKeyword,K.NullKeyword].includes(n.kind))return;
      if(ts.isParenthesizedExpression(n)||ts.isNonNullExpression(n)){expression(n.expression,env);return;}
      if(ts.isPrefixUnaryExpression(n)){requireThat(n.operator===K.ExclamationToken||(n.operator===K.MinusToken&&numeric(typeOf(n.operand))),'unsupported unary operator');expression(n.operand,env);return;}
      if(ts.isConditionalExpression(n)){expression(n.condition,env);expression(n.whenTrue,env);expression(n.whenFalse,env);return;}
      if(ts.isPropertyAccessExpression(n)){
        expression(n.expression,env);const base=checker.getNonNullableType(typeOf(n.expression));
        requireThat(!n.questionDotToken&&!magic.has(n.name.text)&&data(base,opaque),'unsupported property access: '+seen(n));
        if(array(base)){requireThat(n.name.text==='length','array properties other than length unsupported');return;}
        requireThat(!(base.flags&ts.TypeFlags.TypeParameter)&&!(base.flags&(ts.TypeFlags.StringLike|ts.TypeFlags.NumberLike|ts.TypeFlags.BooleanLike)), 'non-record property access');
        const prop=checker.getPropertyOfType(base,n.name.text);
        requireThat(prop?.declarations?.every(d=>ts.isPropertySignature(d)&&!ts.isComputedPropertyName(d.name)),'not a declared data property');return;
      }
      if(ts.isElementAccessExpression(n)){
        requireThat(!n.questionDotToken&&array(typeOf(n.expression))&&numeric(typeOf(n.argumentExpression)),'only typed array indexing allowed');
        expression(n.expression,env);expression(n.argumentExpression,env);return;
      }
      if(ts.isArrayLiteralExpression(n)){
        for(const el of n.elements){if(ts.isSpreadElement(el)){requireThat(array(typeOf(el.expression)),'non-array spread');expression(el.expression,env);}else expression(el,env);}return;
      }
      if(ts.isObjectLiteralExpression(n)){
        const keys=new Set();for(const prop of n.properties){requireThat(ts.isPropertyAssignment(prop)&&(ts.isIdentifier(prop.name)||ts.isStringLiteral(prop.name))&&!magic.has(prop.name.text)&&!keys.has(prop.name.text),'unsupported object property');keys.add(prop.name.text);expression(prop.initializer,env);}return;
      }
      if(ts.isBinaryExpression(n)){
        const op=n.operatorToken.kind;
        requireThat(logical.has(op)||(comparisons.has(op)&&((numeric(typeOf(n.left))&&numeric(typeOf(n.right)))||(text(typeOf(n.left))&&text(typeOf(n.right)))))||
          ([K.PlusToken,K.MinusToken].includes(op)&&numeric(typeOf(n.left))&&numeric(typeOf(n.right))), 'unsupported binary operator: '+seen(n));
        expression(n.left,env);expression(n.right,env);return;
      }
      if(ts.isCallExpression(n)){
        requireThat(!n.questionDotToken&&!n.typeArguments?.length&&!n.arguments.some(ts.isSpreadElement),'unsupported call shape');
        const callee=n.expression;
        if(ts.isIdentifier(callee)){
          const target=symbol(callee);
          if(funcs.has(target)){graph.get(functionId).add(target);}
          else requireThat(libSymbol(callee,'Boolean')&&n.arguments.length===1,'unapproved direct call: '+seen(n));
          n.arguments.forEach(arg=>expression(arg,env));return;
        }
        requireThat(ts.isPropertyAccessExpression(callee)&&!callee.questionDotToken,'unsupported indirect call');
        const base=callee.expression, member=callee.name.text;
        if(ts.isIdentifier(base)&&libSymbol(base,'Number')&&['isFinite','isInteger'].includes(member)){
          requireThat(n.arguments.length===1&&numeric(typeOf(n.arguments[0])),'numeric intrinsic argument invalid');expression(n.arguments[0],env);return;
        }
        if(member==='localeCompare'&&text(typeOf(base))){
          requireThat(n.arguments.length===2&&text(typeOf(n.arguments[0]))&&ts.isStringLiteral(n.arguments[1])&&/^[a-z]{2,3}(?:-[A-Z]{2})?$/.test(n.arguments[1].text),'collation needs explicit fixed locale');
          expression(base,env);expression(n.arguments[0],env);return;
        }
        requireThat(array(typeOf(base))&&['find','every'].includes(member)&&n.arguments.length===1&&ts.isArrowFunction(n.arguments[0]),'unapproved member call: '+seen(n));
        expression(base,env);const callback=n.arguments[0];requireThat(!callback.modifiers?.length&&!callback.typeParameters?.length&&!ts.isBlock(callback.body)&&callback.parameters.length===1,'unsupported array predicate');
        const child=new Set(env);parameter(callback.parameters[0],child);expression(callback.body,child);return;
      }
      fail('unsupported expression: '+seen(n));
    }
    function statement(n){
      if(ts.isBlock(n)){n.statements.forEach(statement);return;}
      if(ts.isReturnStatement(n)){expression(n.expression);return;}
      if(ts.isIfStatement(n)){expression(n.expression);statement(n.thenStatement);if(n.elseStatement)statement(n.elseStatement);return;}
      if(ts.isVariableStatement(n)){
        requireThat(!n.modifiers?.length&&(n.declarationList.flags&ts.NodeFlags.Const),'only const locals allowed');
        for(const d of n.declarationList.declarations){requireThat(ts.isIdentifier(d.name)&&d.initializer,'unsupported local binding');expression(d.initializer);requireThat(data(typeOf(d),opaque),'non-data local');const id=symbol(d.name);locals.add(id);if(ts.isArrayLiteralExpression(d.initializer))ownedArrays.add(id);}return;
      }
      // Destructuring swap of freshly allocated local arrays; never write inputs.
      if(ts.isExpressionStatement(n)&&ts.isBinaryExpression(n.expression)&&n.expression.operatorToken.kind===K.EqualsToken){
        const {left,right}=n.expression;
        requireThat(ts.isArrayLiteralExpression(left)&&ts.isArrayLiteralExpression(right)&&left.elements.length===right.elements.length&&left.elements.length>0,'only local array destructuring assignment allowed');
        for(const el of left.elements){requireThat(ts.isElementAccessExpression(el)&&ts.isIdentifier(el.expression)&&ownedArrays.has(symbol(el.expression)),'write to non-owned array');expression(el);}
        expression(right);return;
      }
      fail('unsupported statement: '+seen(n));
    }
    statement(fn.body);
  }
  const visiting=new Set(), visited=new Set();
  function walk(id){requireThat(!visiting.has(id),'recursive call graph unsupported');if(visited.has(id))return;visiting.add(id);graph.get(id).forEach(walk);visiting.delete(id);visited.add(id);}
  funcs.forEach((_,id)=>walk(id));
  const source_sha256=Object.fromEntries([...new Set([...files,...typeFiles])].sort().map(f=>[path.relative(repo,f).split(path.sep).join('/'),digest(f)]));
  console.log(JSON.stringify({status:'passed',scope,source_sha256,public_symbols:[...publicNames].sort(),compiler:{version:ts.version,sha256:digest(compiler)}}));
}catch(e){console.log(JSON.stringify({status:'inconclusive',scope,reason:String(e.message??e)}));process.exitCode=3;}
