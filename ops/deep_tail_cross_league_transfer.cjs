// Frozen #723 replay, expanded historical cohorts only.
const fs=require('node:fs'),crypto=require('node:crypto'),path=require('node:path');
const {replay,summarize}=require('./deep_tail_mixture_bootstrap.cjs');
const specs=[
  [
    "2023-24/es.1.json",
    "a9d391f61af872bb9f456951d2f71f10d9e10704",
    380,
    380
  ],
  [
    "2024-25/es.1.json",
    "ba4e9bc10b172d6413a92aeba0c04eb70961cd05",
    380,
    370
  ],
  [
    "2023-24/it.1.json",
    "674079696d1298ce45abab6a1f8953d0675b995f",
    380,
    380
  ],
  [
    "2024-25/it.1.json",
    "5c1cb89a7b676eee1db06d79b65773220b599e96",
    380,
    370
  ],
  [
    "2023-24/fr.1.json",
    "a5c5c479bd14c4581931219a41687d9938e4dc1e",
    306,
    306
  ],
  [
    "2024-25/fr.1.json",
    "8bc6ec90c62fa423386ec60473cfa6236419a636",
    306,
    306
  ]
];
function project(doc,spec){
 const [file,pin,scheduled,finished]=spec;
 if(!Array.isArray(doc.matches)||doc.matches.length!==scheduled)throw Error("schedule count");
 const year=Number(file.slice(0,4)),ids=new Set();
 for(const r of doc.matches){
  if(typeof r.date!=="string"||! /^\d{4}-\d{2}-\d{2}$/.test(r.date)||!Number.isFinite(Date.parse(r.date))||r.date<`${year}-07-01`||r.date>=`${year+1}-07-01`||typeof r.team1!=="string"||typeof r.team2!=="string"||!r.team1.trim()||!r.team2.trim()||r.team1===r.team2)throw Error("fixture scope");
  const key=JSON.stringify([r.team1,r.team2]);if(ids.has(key))throw Error("duplicate");ids.add(key);
  const v=r.score?.ft;if(v!=null&&(!Array.isArray(v)||v.length!==2||v.some(x=>!Number.isInteger(x)||x<0||x>30)))throw Error("invalid result");
 }
 const matches=doc.matches.filter(r=>r.score?.ft!=null);
 if(matches.length!==finished)throw Error("finished count");
 return {...doc,matches};
}
function run(root){const results={};for(const s of specs){const b=fs.readFileSync(path.join(root,s[0]));if(crypto.createHash('sha1').update('blob '+b.length+'\0').update(b).digest('hex')!==s[1])throw Error('pin');results[s[0]]=replay(project(JSON.parse(b),s),s[3]);}return {results,summary:summarize(results)};}
if(require.main===module){if(!process.argv[2])throw Error('archive directory required');console.log(JSON.stringify(run(process.argv[2]),null,2));}
module.exports={run,project,specs};
