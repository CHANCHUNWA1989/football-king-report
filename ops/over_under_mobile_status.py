"""Render evidence-gated OU2.5 status in the iPhone homepage."""
import argparse
import html
import json
from pathlib import Path

MARKER='<section id="fk-ou25">'
END='</section>'

def publish(site):
    site=Path(site)
    data=json.loads((site/"over_under_25.json").read_text(encoding="utf-8"))
    count=data.get("candidate_count",0)
    if type(count) is not int or count<0:
        raise ValueError("INVALID_CANDIDATE_COUNT")
    status=html.escape(str(data.get("input_status","UNKNOWN"))[:100])
    updated=html.escape(str(data.get("generated_at_utc","UNKNOWN"))[:60])
    notice="目前未有已核實大細球候選，唔代表系統推薦細球或大球。" if count==0 else "研究候選未經獨立驗證，不屬正式投注推薦。"
    section=(MARKER+"<h2>大／細 2.5 每日研究</h2>"
        +"<p>研究候選："+str(count)+"；正式投注推薦：停用</p>"
        +"<p>輸入狀態："+status+"；更新："+updated+"</p>"
        +"<p>"+notice+"</p>"
        +'<p><a href="over_under_25.json">查看大細球資料及缺失條件</a></p>'+END)
    index=site/"index.html"
    body=index.read_text(encoding="utf-8")
    if MARKER in body:
        start=body.index(MARKER)
        end=body.find(END,start)
        if end<0:
            raise ValueError("BROKEN_OU25_SECTION")
        body=body[:start]+section+body[end+len(END):]
    elif "</main>" in body:
        body=body.replace("</main>",section+"</main>",1)
    elif "</body>" in body:
        body=body.replace("</body>",section+"</body>",1)
    else:
        raise ValueError("NO_HTML_INSERTION_POINT")
    index.write_text(body,encoding="utf-8")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--site",required=True)
    publish(parser.parse_args().site)
