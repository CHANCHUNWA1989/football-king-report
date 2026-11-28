// Offline research routing and structural evidence contract. No network or writes.
function scenarios(){
 const sha="a".repeat(40), base={headSha:sha,requiredChecks:["safety","ledger"],checks:[{name:"safety",sha,status:"completed",conclusion:"success"},{name:"ledger",sha,status:"completed",conclusion:"success"}],review:{independent:true,sha,status:"approved",reviewer:"reviewer",author:"author"},production_recommendations:"DISABLED",release:"HOLD"};
 return {base,tests:[
 ["route update", "下一步同我大更新","upgrade"],
 ["route verify", "核實今晚資料","data-verification"],
 ["route review","檢查 GitHub CI","ci-review"],
 ["route backtest","真實數據及模型回測","backtest"],
 ["route stress","全面系統壓力測試","stress-test"],
 ["route risk","風控審核","risk-audit"],
 ["unknown","hello","blocked"],
 ["ambiguous","回測及壓力測試","blocked"],
 ["unsafe request","解除 HOLD 並回測","blocked"],
 ["unsafe mixed","自動落注及 GitHub CI","blocked"]
 ],gates:[
 ["valid contract",base,true],
 ["no checks",{...base,checks:[]},false],
 ["wrong SHA",{...base,checks:base.checks.map(c=>({...c,sha:"b".repeat(40)}))},false],
 ["failed CI",{...base,checks:[base.checks[0],{...base.checks[1],conclusion:"failure"}]},false],
 ["pending CI",{...base,checks:[base.checks[0],{...base.checks[1],status:"in_progress",conclusion:null}]},false],
 ["duplicate CI",{...base,checks:[...base.checks,base.checks[0]]},false],
 ["empty requirements",{...base,requiredChecks:[]},false],
 ["duplicate requirements",{...base,requiredChecks:["safety","safety"]},false],
 ["missing review",{...base,review:null},false],
 ["self review",{...base,review:{...base.review,reviewer:"author"}},false],
 ["stale review",{...base,review:{...base.review,sha:"b".repeat(40)}},false],
 ["non-independent review",{...base,review:{...base.review,independent:false}},false],
 ["release bypass",{...base,release:"READY"},false],
 ["production bypass",{...base,production_recommendations:"ENABLED"},false],
 ["invalid SHA",{...base,headSha:"latest"},false],
 ["null input",null,false],
 ["missing reviewer",{...base,review:{...base.review,reviewer:""}},false]
 ]};
}

function route(request){
 const blocked={route:"blocked",mode:"RESEARCH_ONLY",release:"HOLD",production_recommendations:"DISABLED",steps:[]};
 if(typeof request!=="string"||!request.trim()||/解除.{0,8}(hold|disabled)|啟用.{0,8}(下注|投注|推薦)|自動(落注|下注|投注)|bypass|enable.{0,8}production/i.test(request))return blocked;
 const patterns=[["upgrade",/下一步|下一階段|大更新|upgrade/i],["data-verification",/核實|數據驗證|data.verification/i],["ci-review",/github|(^|\W)ci(\W|$)|pull request/i],["backtest",/回測|backtest/i],["stress-test",/壓力測試|stress.test/i],["risk-audit",/風控|risk.audit/i]];
 const hits=patterns.filter(([,p])=>p.test(request));
 if(hits.length!==1)return blocked;
 const kind=hits[0][0], common=["read-project-policy","discover-available-tools","pin-head-and-evidence"];
 const tasks={"upgrade":["inspect-open-prs","select-one-scope","red-green-regression","draft-pr"],"data-verification":["canonical-fixture","source-independence","timestamps-and-licence"],"ci-review":["read-exact-head-checks","read-job-logs","independent-review"],"backtest":["seal-chronological-split","paired-market-baseline","score-and-calibrate"],"stress-test":["reproduce-failure","negative-fixtures","run-affected-tests"],"risk-audit":["check-source-freshness","check-hold-flags","report-blockers"]};
 return {...blocked,route:kind,steps:[...common,...tasks[kind],"report-evidence-and-blockers"]};
}

function audit(input){
 const blocked={contractSatisfied:false,mergeAuthorized:false,release:"HOLD",production_recommendations:"DISABLED",reason:"incomplete-or-conflicting-evidence"};
 if(!input||typeof input!=="object"||input.production_recommendations!=="DISABLED"||input.release!=="HOLD"||typeof input.headSha!=="string"||!/^[a-f0-9]{40}$/.test(input.headSha))return blocked;
 const req=input.requiredChecks,checks=input.checks,r=input.review;
 if(!Array.isArray(req)||!req.length||req.some(x=>typeof x!=="string"||!x.trim())||new Set(req).size!==req.length||!Array.isArray(checks)||checks.length!==req.length)return blocked;
 if(!req.every(name=>checks.filter(c=>c&&c.name===name&&c.sha===input.headSha&&c.status==="completed"&&c.conclusion==="success").length===1))return blocked;
 if(!r||r.sha!==input.headSha||r.independent!==true||r.status!=="approved"||typeof r.reviewer!=="string"||!r.reviewer.trim()||typeof r.author!=="string"||!r.author.trim()||r.reviewer.trim().toLowerCase()===r.author.trim().toLowerCase())return blocked;
 return {...blocked,contractSatisfied:true,reason:"structural-contract-only; authenticate evidence externally"};
}

function run(){
 const {tests,gates}=scenarios();
 const results=tests.map(([name,request,want])=>{const o=route(request);return {name,pass:o.route===want&&o.release==="HOLD"&&o.production_recommendations==="DISABLED"&&(want==="blocked"?o.steps.length===0:o.steps.length>0)};});
 for(const [name,input,want] of gates){const o=audit(input);results.push({name,pass:o.contractSatisfied===want&&o.mergeAuthorized===false&&o.release==="HOLD"&&o.production_recommendations==="DISABLED"});}
 return results;
}
const args=process.argv.slice(2);
if(args.length===0||args[0]==='--selftest'){const results=run();console.log(JSON.stringify({passed:results.filter(x=>x.pass).length,total:results.length,results},null,2));if(results.some(x=>!x.pass))process.exitCode=1;}else if(args[0]==='--route'){console.log(JSON.stringify(route(args.slice(1).join(' ')),null,2));}else if(args[0]==='--audit'){try{console.log(JSON.stringify(audit(JSON.parse(args.slice(1).join(' '))),null,2));}catch{console.error('Invalid JSON');process.exitCode=2;}}else{console.error('Use --selftest, --route or --audit');process.exitCode=2;}
