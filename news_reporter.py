"""
M&A & Company Intelligence Reporter  v3
Markets: US · GB · CN  |  Python 3.8+, no pip needed
"""
import html as _html, re, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

REPORTS_DIR    = Path(__file__).parent / "reports"
MAX_PER_QUERY  = 12
TIMEOUT        = 15
PAUSE          = 0.5
GNEWS_URL      = "https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"
SINA_RSS       = "http://rss.sina.com.cn/finance/globalfinance/financenews.xml"
BAIDU_URL      = "https://news.baidu.com/ns?word={q}&tn=news&from=news&cl=2&pn=0&rn=20"

# Company → domain lookup. Logos fetched live from Clearbit when report opens in browser.
COMPANY_DOMAINS = {
    "microsoft":"microsoft.com","apple":"apple.com","alphabet":"abc.xyz",
    "google":"google.com","amazon":"amazon.com","meta":"meta.com",
    "facebook":"facebook.com","netflix":"netflix.com","nvidia":"nvidia.com",
    "intel":"intel.com","ibm":"ibm.com","oracle":"oracle.com",
    "salesforce":"salesforce.com","adobe":"adobe.com","qualcomm":"qualcomm.com",
    "amd":"amd.com","uber":"uber.com","airbnb":"airbnb.com",
    "twitter":"twitter.com","x corp":"x.com","snap":"snap.com",
    "spotify":"spotify.com","paypal":"paypal.com","stripe":"stripe.com",
    "crowdstrike":"crowdstrike.com","palantir":"palantir.com",
    "openai":"openai.com","anthropic":"anthropic.com",
    "goldman sachs":"goldmansachs.com","jpmorgan":"jpmorgan.com",
    "morgan stanley":"morganstanley.com","citigroup":"citigroup.com",
    "bank of america":"bankofamerica.com","wells fargo":"wellsfargo.com",
    "blackrock":"blackrock.com","pfizer":"pfizer.com","merck":"merck.com",
    "exxonmobil":"exxonmobil.com","chevron":"chevron.com","boeing":"boeing.com",
    "tesla":"tesla.com","ford":"ford.com","general motors":"gm.com",
    "walmart":"walmart.com","disney":"disney.com","comcast":"comcast.com",
    "verizon":"verizon.com","at&t":"att.com",
    "shell":"shell.com","bp":"bp.com","hsbc":"hsbc.com",
    "barclays":"barclays.com","lloyds":"lloydsbankinggroup.com",
    "astrazeneca":"astrazeneca.com","gsk":"gsk.com","unilever":"unilever.com",
    "diageo":"diageo.com","vodafone":"vodafone.com","arm":"arm.com",
    "rio tinto":"riotinto.com","standard chartered":"sc.com",
    "alibaba":"alibaba.com","tencent":"tencent.com","baidu":"baidu.com",
    "meituan":"meituan.com","bytedance":"bytedance.com","tiktok":"tiktok.com",
    "xiaomi":"mi.com","huawei":"huawei.com","byd":"byd.com",
    "sinopec":"sinopec.com","ping an":"pingan.com","ant group":"antgroup.com",
    "netease":"163.com","bilibili":"bilibili.com",
    "reuters":"reuters.com","bloomberg":"bloomberg.com",
    "financial times":"ft.com","bbc":"bbc.co.uk","caixin":"caixinglobal.com",
}

_CPAT = [re.compile(p, re.IGNORECASE) for p in [
    r'^([A-Z][A-Za-z0-9&\.\-\' ]{2,35}?)\s+(?:acqui|merger|buys|to buy|takeover)',
    r'^([A-Z][A-Za-z0-9&\.\-\' ]{2,35}?)\s+(?:reports|posts|earnings|revenue|profit)',
    r'^([A-Z][A-Za-z0-9&\.\-\' ]{2,35}?)\s+(?:IPO|to list|goes public)',
    r'^([A-Z][A-Za-z0-9&\.\-\' ]{2,35}?)\s+(?:fined|probe|regulat)',
    r'(?:acquire|buy|takeover of|merger with)\s+([A-Z][A-Za-z0-9&\.\-\' ]{2,30})',
]]
_AVCOLS = ["#1D4ED8","#7C3AED","#059669","#DC2626","#D97706","#0891B2","#9333EA","#DB2777"]
def _avcol(n): return _AVCOLS[sum(ord(c) for c in n) % len(_AVCOLS)]
def _init(n):
    w=[x for x in n.strip().split() if x and x[0].isupper()][:2]
    return ("".join(x[0] for x in w).upper() or n[:2].upper() or "?")

def extract_company(title):
    cname=""
    for pat in _CPAT:
        m=pat.search(title)
        if m: cname=m.group(1).strip().rstrip(" ,"); break
    domain=""; best=0; tl=title.lower()
    for frag,dom in COMPANY_DOMAINS.items():
        if frag in tl and len(frag)>best:
            best=len(frag); domain=dom
            if not cname: cname=frag.title()
    if not cname:
        w=re.findall(r'\b[A-Z][A-Za-z0-9&]+\b',title)
        cname=" ".join(w[:2]) if w else "Company"
    return dict(name=cname,domain=domain,
                logo_url=f"https://logo.clearbit.com/{domain}" if domain else "",
                initials=_init(cname),color=_avcol(cname))

ACTIVITY_RULES=[
    ("M&A","#7C3AED","🤝",["acqui","merger","takeover","buyout","bid","divest","consolidat","并购","收购","兼并","合并","重组"]),
    ("IPO","#059669","🚀",["ipo","listing","float","public offering","debut","goes public","上市","首发","新股"]),
    ("Earnings","#0891B2","📊",["earnings","revenue","profit","quarterly","forecast","dividend","财报","业绩","利润","营收"]),
    ("Regulatory","#DC2626","⚖️",["regulat","fine","penalty","investigat","antitrust","probe","监管","罚款","调查"]),
]
DEAL_RE=re.compile(r'(?:\$|£|€|US\$)?[\d,.]+\s*(?:billion|million|bn|m|亿)\b|(?:\$|£|€)[\d,.]+[BMK]',re.I)
def _act(ti,su):
    t=(ti+" "+su).lower()
    for lbl,col,ico,kws in ACTIVITY_RULES:
        if any(k in t for k in kws): return lbl,col,ico
    return "Company News","#64748B","📰"
def _deal(ti,su):
    for t in (ti,su):
        m=DEAL_RE.search(t)
        if m: return m.group(0).strip()
    return ""

MARKETS=[
    {"id":"us","flag":"🇺🇸","name":"United States","color":"#1D4ED8","sources":[
        {"type":"gnews","label":"Google News","hl":"en-US","gl":"US","ceid":"US:en",
         "queries":["US company merger acquisition deal billion",
                    "US corporate takeover buyout bid",
                    "NYSE NASDAQ company earnings quarterly results",
                    "US company IPO stock listing announcement"]},
        {"type":"rss","label":"Reuters","url":"https://feeds.reuters.com/reuters/businessNews"},
    ]},
    {"id":"gb","flag":"🇬🇧","name":"Great Britain","color":"#B91C1C","sources":[
        {"type":"gnews","label":"Google News","hl":"en-GB","gl":"GB","ceid":"GB:en",
         "queries":["UK company merger acquisition takeover deal",
                    "British corporate buyout bid acquisition",
                    "FTSE London Stock Exchange earnings results",
                    "UK company IPO listing shares announcement"]},
        {"type":"rss","label":"BBC Business","url":"http://feeds.bbci.co.uk/news/business/rss.xml"},
    ]},
    {"id":"cn","flag":"🇨🇳","name":"China","color":"#B45309","sources":[
        {"type":"gnews","label":"Google (EN)","hl":"en-US","gl":"US","ceid":"US:en",
         "queries":["China company merger acquisition deal",
                    "Chinese corporate takeover buyout billion",
                    "China listed company earnings results stock",
                    "Shanghai Shenzhen Hong Kong company IPO listing"]},
        {"type":"gnews","label":"Google (CN)","hl":"zh-CN","gl":"CN","ceid":"CN:zh-Hans",
         "queries":["中国上市公司并购收购交易","企业兼并重组上市公司业绩"]},
        {"type":"rss","label":"Caixin","url":"https://www.caixinglobal.com/rss_en.xml"},
        {"type":"sina","label":"Sina Finance"},
        {"type":"baidu","label":"Baidu News","queries":["上市公司并购收购","企业重组兼并交易"]},
    ]},
]

def _get(url,enc="utf-8"):
    req=urllib.request.Request(url,headers={
        "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
        "Accept-Language":"en-US,en;q=0.9,zh-CN;q=0.8"})
    with urllib.request.urlopen(req,timeout=TIMEOUT) as r:
        return r.read().decode(enc,errors="replace")

def _strip(s): return re.sub(r"<[^>]+>","",s or "").strip()
def _ct(t): return re.sub(r"\s+-\s+[^-]+$","",t or "").strip()
def _src(raw,el):
    if el is not None and el.text: return el.text.strip()
    m=re.search(r"\s+-\s+([^-]+)$",raw or ""); return m.group(1).strip() if m else "—"
def _pd(s):
    try:
        dt=parsedate_to_datetime(s).astimezone(timezone.utc)
        return dt.strftime("%d %b %Y"),dt.timestamp()
    except:
        now=datetime.now(timezone.utc); return now.strftime("%d %b %Y"),now.timestamp()
def _mk(ti,li,so,sl,da,ts,su,mid):
    ti=ti.strip(); su=_strip(su)[:420]; act,acol,aico=_act(ti,su)
    return dict(title=ti,link=li,source=so,src_label=sl,date=da,ts=ts,summary=su,
                activity=act,act_color=acol,act_icon=aico,deal=_deal(ti,su),
                company=extract_company(ti),market_id=mid)
def _prss(xml,mid,sl):
    out=[]
    try: root=ET.fromstring(xml)
    except ET.ParseError: return out
    for item in root.findall(".//item"):
        raw=item.findtext("title") or ""; ti=_ct(raw); li=(item.findtext("link") or "").strip()
        if not ti: continue
        da,ts=_pd(item.findtext("pubDate") or "")
        out.append(_mk(ti,li,_src(raw,item.find("source")),sl,da,ts,item.findtext("description") or "",mid))
    return out
def _baidu(q,mid):
    out=[]
    try:
        h=_get(BAIDU_URL.format(q=urllib.parse.quote(q)))
        pairs=re.findall(r'<h3[^>]*>\s*<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',h,re.DOTALL)
        sums=re.findall(r'<p[^>]*class=["\'][^"\']*abs[^"\']*["\'][^>]*>(.*?)</p>',h,re.DOTALL)
        now=datetime.now(timezone.utc)
        for i,(li,rt) in enumerate(pairs[:MAX_PER_QUERY]):
            ti=_strip(rt).strip()
            if not ti: continue
            su=_strip(sums[i]) if i<len(sums) else ""
            if li.startswith("/"): li="https://news.baidu.com"+li
            out.append(_mk(ti,li,"Baidu News","Baidu News",now.strftime("%d %b %Y"),now.timestamp(),su,mid))
    except Exception as e: print(f"    ⚠ Baidu: {e}")
    return out

def fetch_market(mkt):
    arts,seen=[],set()
    def add(new):
        for a in new:
            k=a["title"].lower().strip()
            if k not in seen: seen.add(k); arts.append(a)
    for src in mkt["sources"]:
        t,lbl=src["type"],src["label"]
        if t=="gnews":
            for q in src.get("queries",[]):
                url=GNEWS_URL.format(q=urllib.parse.quote_plus(q),hl=src["hl"],gl=src["gl"],ceid=urllib.parse.quote(src["ceid"]))
                print(f"    [{lbl}] {q[:55]}")
                try: add(_prss(_get(url),mkt["id"],lbl)[:MAX_PER_QUERY])
                except Exception as e: print(f"    ⚠ {e}")
                time.sleep(PAUSE)
        elif t=="rss":
            print(f"    [{lbl}]")
            try: add(_prss(_get(src["url"]),mkt["id"],lbl)[:MAX_PER_QUERY])
            except Exception as e: print(f"    ⚠ {e}")
            time.sleep(PAUSE)
        elif t=="sina":
            print(f"    [{lbl}]")
            try: add(_prss(_get(SINA_RSS,enc="gbk"),mkt["id"],lbl)[:MAX_PER_QUERY])
            except Exception as e: print(f"    ⚠ {e}")
            time.sleep(PAUSE)
        elif t=="baidu":
            for q in src.get("queries",[]):
                print(f"    [{lbl}] {q}")
                add(_baidu(q,mkt["id"])); time.sleep(PAUSE)
    arts.sort(key=lambda a:a["ts"],reverse=True)
    return dict(id=mkt["id"],flag=mkt["flag"],name=mkt["name"],color=mkt["color"],articles=arts,count=len(arts))

def fetch_all():
    now=datetime.now(timezone.utc)
    res=dict(generated_at=now.strftime("%d %b %Y, %H:%M UTC"),date_slug=now.strftime("%Y-%m-%d"),markets=[],total=0)
    for mkt in MARKETS:
        print(f"\n{'─'*55}\n  {mkt['flag']}  {mkt['name']}\n{'─'*55}")
        m=fetch_market(mkt); res["markets"].append(m); res["total"]+=m["count"]
        print(f"  → {m['count']} articles")
    print(f"\n✓ Total: {res['total']} articles")
    return res

def _e(s): return _html.escape(str(s),quote=True)
def _logo(co):
    i=_e(co["initials"]); c=_e(co["color"]); n=_e(co["name"])
    av=f'<div class="avatar" style="background:{c}" title="{n}">{i}</div>'
    if not co["logo_url"]: return f'<div class="lw">{av}</div>'
    return (f'<div class="lw" title="{n}"><img src="{_e(co["logo_url"])}" alt="{n}" width="52" height="52" '
            f'style="border-radius:10px;object-fit:contain;display:block" '
            f'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'">'
            f'<div class="avatar" style="background:{c};display:none">{i}</div></div>')

def _card(a,mc):
    logo=_logo(a["company"])
    deal=(f'<div class="deal-tag"><span class="deal-icon">$</span>{_e(a["deal"])}</div>') if a["deal"] else ""
    summ=(f'<p class="card-sum">{_e(a["summary"])}</p>') if a["summary"] else ""
    ac=_e(a["act_color"]); aico=a["act_icon"]; albl=_e(a["activity"])
    txt=_e((a["title"]+" "+a["company"]["name"]+" "+a["summary"]).lower())
    return f"""<div class="card" data-activity="{albl}" data-text="{txt}">
  <div class="card-side">
    {logo}
    <span class="act-dot" style="background:{ac}" title="{albl}"></span>
  </div>
  <div class="card-body">
    <div class="card-meta">
      <span class="act-badge" style="background:{ac}1a;color:{ac};border-color:{ac}44">{aico} {albl}</span>
      <span class="card-date">{_e(a["date"])}</span>
    </div>
    <a class="card-title" href="{_e(a["link"])}" target="_blank" rel="noopener">{_e(a["title"])}</a>
    {deal}{summ}
    <div class="card-foot">
      <span class="co-tag">{_e(a["company"]["name"])}</span>
      <span class="src-tag" style="color:{mc}">{_e(a["src_label"])}</span>
    </div>
  </div>
</div>"""

def _panel(mkt,first):
    col=mkt["color"]; arts=mkt["articles"]; mid=mkt["id"]
    disp="block" if first else "none"
    seen_acts,act_counts=[],{}
    for a in arts:
        act_counts[a["activity"]]=act_counts.get(a["activity"],0)+1
        if a["activity"] not in seen_acts: seen_acts.append(a["activity"])
    flts=f'<button class="flt on" data-act="all" onclick="flt(this,\'all\',\'{mid}\')">All <span>{len(arts)}</span></button>'
    for act in seen_acts:
        flts+=f'<button class="flt" data-act="{_e(act)}" onclick="flt(this,\'{_e(act)}\',\'{mid}\')">{_e(act)} <span>{act_counts[act]}</span></button>'
    cards="\n".join(_card(a,col) for a in arts) if arts else '<div class="empty-state"><p>No articles found for today.</p></div>'
    return f"""<div id="panel-{mid}" class="panel" style="display:{disp}">
  <div class="panel-hdr" style="--mc:{col}">
    <div class="panel-hdr-left">
      <span class="panel-flag">{mkt["flag"]}</span>
      <div><div class="panel-name">{_e(mkt["name"])}</div><div class="panel-count">{mkt["count"]} articles today</div></div>
    </div>
    <div class="flt-bar">{flts}</div>
  </div>
  <div class="grid" id="grid-{mid}">{cards}</div>
  <div class="empty-filter" id="empty-{mid}" style="display:none">No articles match this filter.</div>
</div>"""

def build_html(data):
    # ── Tabs
    tabs="".join(
        f'<button class="tab {"active" if i==0 else ""}" onclick="showTab(\'{_e(m["id"])}\',this)">'
        f'{m["flag"]} {_e(m["name"])} <span class="tab-cnt">{m["count"]}</span></button>'
        for i,m in enumerate(data["markets"]))
    # ── Activity totals
    all_acts={}
    for m in data["markets"]:
        for a in m["articles"]:
            all_acts[a["activity"]]=all_acts.get(a["activity"],0)+1
    # ── KPI strip (values embedded as data-target for countUp)
    kpi_defs=[
        ("M&A","#7C3AED","#F5F3FF","🤝"),
        ("IPO","#059669","#ECFDF5","🚀"),
        ("Earnings","#0891B2","#E0F2FE","📊"),
        ("Regulatory","#DC2626","#FEF2F2","⚖️"),
        ("Company News","#64748B","#F8FAFC","📰"),
    ]
    kpi_cards="".join(
        f'<button class="kpi" style="--kc:{col};--kb:{bg}" data-lbl="{_e(lbl)}" onclick="kpiClick(\'{_e(lbl)}\',this)">'
        f'<span class="kpi-ico">{ico}</span>'
        f'<span class="kpi-num" data-target="{all_acts.get(lbl,0)}">0</span>'
        f'<span class="kpi-lbl">{_e(lbl)}</span>'
        f'<span class="kpi-bar-fill" style="width:{min(100,round(all_acts.get(lbl,0)/max(sum(all_acts.values()),1)*100))}%"></span>'
        f'</button>'
        for lbl,col,bg,ico in kpi_defs)
    # ── Market pills
    mktpills="".join(
        f'<span class="mkt-pill" style="--mc:{m["color"]}">{m["flag"]} {_e(m["name"])} <b>{m["count"]}</b></span>'
        for m in data["markets"])
    panels="".join(_panel(m,i==0) for i,m in enumerate(data["markets"]))
    # ── CSS stagger for card entrance (up to 24 cards)
    stagger="".join(f".grid .card:nth-child({i}){{animation-delay:{i*0.04:.2f}s}}" for i in range(1,25))
    CSS="""
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{--navy:#0F172A;--ink:#1E293B;--muted:#64748B;--line:#E2E8F0;--bg:#F1F5F9;--white:#fff;--radius:12px}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;background:var(--bg);color:var(--ink);font-size:14px;line-height:1.6;scroll-behavior:smooth}}
/* ── Keyframes ── */
@keyframes fadeUp{{from{{opacity:0;transform:translateY(18px)}}to{{opacity:1;transform:translateY(0)}}}}
@keyframes slideIn{{from{{opacity:0;transform:translateX(-8px)}}to{{opacity:1;transform:translateX(0)}}}}
@keyframes pulse{{0%,100%{{box-shadow:0 0 0 0 rgba(99,102,241,.35)}}50%{{box-shadow:0 0 0 6px rgba(99,102,241,0)}}}}
@keyframes barGrow{{from{{width:0}}to{{width:var(--w,0%)}}}}
/* ── Sticky header ── */
.hdr{{position:sticky;top:0;z-index:100;background:var(--navy);color:#fff;padding:14px 40px;display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:1px solid rgba(255,255,255,.08)}}
.hdr-brand{{display:flex;align-items:center;gap:10px}}
.hdr-dot{{width:8px;height:8px;border-radius:50%;background:#6366F1;box-shadow:0 0 8px #6366F199}}
.hdr h1{{font-size:1.05rem;font-weight:700;letter-spacing:-.01em}}
.hdr-sub{{font-size:.68rem;opacity:.4;margin-top:1px;letter-spacing:.01em}}
.hdr-right{{display:flex;align-items:center;gap:8px}}
.hdr-time{{font-size:.68rem;opacity:.4;border-right:1px solid rgba(255,255,255,.15);padding-right:12px;margin-right:4px}}
.save-btn{{display:flex;align-items:center;gap:5px;padding:6px 14px;border-radius:8px;font-size:.75rem;font-weight:600;cursor:pointer;border:1px solid rgba(255,255,255,.2);color:#fff;background:rgba(255,255,255,.07);transition:all .2s}}
.save-btn:hover{{background:rgba(255,255,255,.16);border-color:rgba(255,255,255,.4);transform:translateY(-1px)}}
/* ── KPI strip ── */
.kpi-strip{{background:var(--white);border-bottom:1px solid var(--line);padding:16px 40px;display:flex;gap:10px}}
.kpi{{flex:1;position:relative;display:flex;flex-direction:column;gap:3px;padding:14px 16px 12px;border-radius:var(--radius);border:1.5px solid var(--line);background:var(--white);cursor:pointer;overflow:hidden;transition:border-color .2s,box-shadow .2s,transform .15s;user-select:none}}
.kpi:hover{{border-color:var(--kc);box-shadow:0 4px 16px rgba(0,0,0,.07);transform:translateY(-2px)}}
.kpi.active-kpi{{border-color:var(--kc);background:var(--kb);animation:pulse .6s ease}}
.kpi-top{{display:flex;align-items:center;justify-content:space-between}}
.kpi-ico{{font-size:1.1rem;line-height:1}}
.kpi-chg{{font-size:.62rem;font-weight:600;color:var(--muted)}}
.kpi-num{{font-size:1.9rem;font-weight:800;color:var(--navy);line-height:1;letter-spacing:-.03em}}
.kpi-lbl{{font-size:.65rem;font-weight:600;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}}
.kpi-track{{position:absolute;bottom:0;left:0;right:0;height:3px;background:var(--line)}}
.kpi-bar-fill{{position:absolute;bottom:0;left:0;height:3px;background:var(--kc);border-radius:0 2px 2px 0;animation:barGrow .8s .3s cubic-bezier(.4,0,.2,1) both}}
/* ── Search / ctrl bar ── */
.ctrl{{background:var(--white);border-bottom:1px solid var(--line);padding:10px 40px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}}
.search-box{{flex:1;min-width:180px;display:flex;align-items:center;gap:7px;background:var(--bg);border:1.5px solid var(--line);border-radius:8px;padding:6px 12px;transition:border-color .2s}}
.search-box:focus-within{{border-color:#6366F1;background:var(--white)}}
.search-box svg{{flex-shrink:0;opacity:.4}}
.search-box input{{border:none;background:none;font-size:.82rem;color:var(--ink);outline:none;width:100%}}
.mkt-pills{{display:flex;gap:6px;flex-wrap:wrap}}
.mkt-pill{{display:flex;align-items:center;gap:4px;padding:4px 10px;border-radius:99px;border:1.5px solid var(--mc);background:var(--white);font-size:.72rem;font-weight:600;color:var(--mc)}}
.mkt-pill b{{font-size:.8rem}}
.total-tag{{margin-left:auto;background:var(--navy);color:#fff;border-radius:7px;padding:5px 12px;font-size:.75rem;font-weight:700;letter-spacing:.01em}}
/* ── Tabs ── */
.tabs{{position:sticky;top:49px;z-index:90;background:var(--white);border-bottom:2px solid var(--line);padding:0 40px;display:flex;gap:0}}
.tab{{padding:10px 18px;border:none;background:none;border-bottom:2.5px solid transparent;margin-bottom:-2px;font-size:.82rem;font-weight:600;color:var(--muted);cursor:pointer;white-space:nowrap;transition:color .15s,border-color .2s;display:flex;align-items:center;gap:6px}}
.tab:hover{{color:var(--ink)}}.tab.active{{color:#1D4ED8;border-bottom-color:#1D4ED8}}
.tab-cnt{{font-size:.63rem;background:#EFF6FF;color:#3B82F6;border-radius:99px;padding:1px 6px;transition:background .2s}}
.tab.active .tab-cnt{{background:#1D4ED8;color:#fff}}
/* ── Panel ── */
.main{{padding:20px 40px 60px}}
.panel-hdr{{display:flex;align-items:center;gap:14px;flex-wrap:wrap;padding:12px 16px;background:var(--white);border-radius:var(--radius);border-left:4px solid var(--mc);margin-bottom:14px;box-shadow:0 1px 3px rgba(0,0,0,.05);animation:slideIn .3s ease both}}
.panel-flag{{font-size:1.9rem;line-height:1}}
.panel-name{{font-size:.95rem;font-weight:700;color:var(--navy)}}
.panel-count{{font-size:.68rem;color:var(--muted);margin-top:1px}}
.flt-bar{{display:flex;gap:5px;flex-wrap:wrap;margin-left:auto}}
.flt{{padding:4px 12px;border-radius:99px;border:1.5px solid var(--line);background:var(--white);font-size:.7rem;font-weight:600;color:var(--muted);cursor:pointer;transition:all .18s;display:flex;align-items:center;gap:4px}}
.flt span{{min-width:14px;text-align:center}}.flt:hover{{border-color:#94A3B8;color:var(--ink)}}
.flt.on{{background:#1D4ED8;border-color:#1D4ED8;color:#fff}}
/* ── Grid & Cards ── */
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:10px}}
.card{{background:var(--white);border:1.5px solid var(--line);border-radius:var(--radius);padding:14px;display:flex;gap:12px;transition:box-shadow .2s,border-color .2s,transform .2s;animation:fadeUp .45s ease both;opacity:0}}
.card:hover{{box-shadow:0 8px 24px rgba(0,0,0,.1);border-color:#CBD5E1;transform:translateY(-2px)}}
.card.hidden{{display:none}}
.card-side{{display:flex;flex-direction:column;align-items:center;gap:8px;flex-shrink:0}}
.lw{{width:46px}}.avatar{{width:46px;height:46px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:.9rem;font-weight:700;color:#fff}}
.act-dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0}}
.card-body{{flex:1;min-width:0;display:flex;flex-direction:column;gap:5px}}
.card-meta{{display:flex;align-items:center;justify-content:space-between;gap:6px}}
.act-badge{{font-size:.63rem;font-weight:700;padding:2px 8px;border-radius:99px;border:1px solid;white-space:nowrap}}
.card-date{{font-size:.63rem;color:#94A3B8;white-space:nowrap}}
.card-title{{font-size:.88rem;font-weight:700;color:var(--navy);text-decoration:none;line-height:1.45;transition:color .15s}}
.card-title:hover{{color:#1D4ED8}}
.deal-tag{{display:inline-flex;align-items:center;gap:4px;background:#FFFBEB;border:1px solid #FDE68A;border-radius:6px;padding:3px 8px;font-size:.72rem;color:#92400E;margin-top:1px}}
.deal-icon{{font-weight:800;color:#D97706}}
.card-sum{{font-size:.76rem;color:#475569;line-height:1.55;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.card-foot{{display:flex;align-items:center;justify-content:space-between;gap:8px;padding-top:6px;border-top:1px solid #F1F5F9;margin-top:auto}}
.co-tag{{font-size:.66rem;color:var(--muted);font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.src-tag{{font-size:.63rem;font-weight:600;white-space:nowrap}}
/* ── Empty states ── */
.empty-state,.empty-filter{{background:var(--white);border:1.5px dashed var(--line);border-radius:var(--radius);padding:36px;text-align:center;color:#94A3B8;grid-column:1/-1;font-size:.82rem}}
/* ── Scroll to top ── */
#topbtn{{position:fixed;bottom:28px;right:28px;width:38px;height:38px;border-radius:50%;background:var(--navy);color:#fff;border:none;cursor:pointer;font-size:1rem;display:flex;align-items:center;justify-content:center;opacity:0;transform:translateY(10px);transition:opacity .2s,transform .2s;z-index:200}}
#topbtn.vis{{opacity:1;transform:translateY(0)}}
#topbtn:hover{{background:#1D4ED8}}
/* ── Footer ── */
.footer{{background:var(--white);border-top:1px solid var(--line);text-align:center;padding:14px;font-size:.67rem;color:#94A3B8}}
/* ── Responsive ── */
@media(max-width:680px){{.hdr,.kpi-strip,.ctrl,.tabs,.main{{padding-left:14px;padding-right:14px}}.grid{{grid-template-columns:1fr}}.kpi-strip{{flex-wrap:wrap}}.kpi{{min-width:calc(50% - 5px)}}.panel-hdr{{flex-direction:column;align-items:flex-start}}.flt-bar{{margin-left:0}}}}"""

    JS="""
var _kf=null,_sq='';
/* ── KPI count-up ── */
function countUp(el,target){{
  var start=0,dur=700,t0=null;
  function step(ts){{
    if(!t0) t0=ts;
    var p=Math.min((ts-t0)/dur,1);
    el.textContent=Math.round(p*p*(3-2*p)*target);
    if(p<1) requestAnimationFrame(step);
  }}
  requestAnimationFrame(step);
}}
window.addEventListener('load',function(){{
  document.querySelectorAll('.kpi-num[data-target]').forEach(function(el){{
    var t=parseInt(el.dataset.target)||0;
    setTimeout(function(){{countUp(el,t);}},200);
  }});
  observeCards();
}});
/* ── Card entrance via IntersectionObserver ── */
function observeCards(){{
  if(!window.IntersectionObserver) {{
    document.querySelectorAll('.card').forEach(function(c){{c.style.opacity='1';}});return;
  }}
  var io=new IntersectionObserver(function(entries){{
    entries.forEach(function(e){{if(e.isIntersecting) e.target.classList.add('visible');}});
  }},{{threshold:.08}});
  document.querySelectorAll('.card').forEach(function(c){{io.observe(c);}});
}}
/* ── Tabs ── */
function showTab(id,el){{
  document.querySelectorAll('.panel').forEach(function(p){{p.style.display='none';}});
  document.querySelectorAll('.tab').forEach(function(t){{t.classList.remove('active');}});
  var panel=document.getElementById('panel-'+id);
  panel.style.display='block';
  el.classList.add('active');
  observeCards();
  applyFilters();
}}
/* ── KPI global filter ── */
function kpiClick(lbl,el){{
  _kf=(_kf===lbl)?null:lbl;
  document.querySelectorAll('.kpi').forEach(function(k){{k.classList.remove('active-kpi');}});
  if(_kf) el.classList.add('active-kpi');
  document.querySelectorAll('.flt.on').forEach(function(b){{
    b.classList.remove('on');
    var first=b.closest('.flt-bar').querySelector('.flt');
    if(first) first.classList.add('on');
  }});
  applyFilters();
}}
/* ── Per-market filter ── */
function flt(btn,activity,mid){{
  btn.closest('.flt-bar').querySelectorAll('.flt').forEach(function(b){{b.classList.remove('on');}});
  btn.classList.add('on');
  _kf=null;
  document.querySelectorAll('.kpi').forEach(function(k){{k.classList.remove('active-kpi');}});
  applyFilters();
}}
/* ── Apply all filters ── */
function applyFilters(){{
  var sq=_sq.toLowerCase();
  document.querySelectorAll('.panel').forEach(function(panel){{
    if(panel.style.display==='none') return;
    var mid=panel.id.replace('panel-','');
    var onBtn=panel.querySelector('.flt.on');
    var fltAct=onBtn?onBtn.dataset.act:'all';
    var shown=0;
    panel.querySelectorAll('.card').forEach(function(c){{
      var am=_kf?c.dataset.activity===_kf:(fltAct==='all'||c.dataset.activity===fltAct);
      var tm=!sq||(c.dataset.text||'').includes(sq);
      c.classList.toggle('hidden',!am||!tm);
      if(am&&tm) shown++;
    }});
    var ef=document.getElementById('empty-'+mid);
    if(ef) ef.style.display=shown?'none':'block';
  }});
}}
function doSearch(v){{_sq=v;applyFilters();}}
/* ── Save ── */
function saveReport(){{
  var h=document.documentElement.outerHTML;
  var b=new Blob([h],{{type:'text/html'}});
  var a=document.createElement('a');
  a.href=URL.createObjectURL(b);
  var d=new Date(),ds=d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
  a.download='ma_report_'+ds+'.html';a.click();URL.revokeObjectURL(a.href);
}}
/* ── Scroll to top ── */
var topBtn=document.getElementById('topbtn');
window.addEventListener('scroll',function(){{topBtn.classList.toggle('vis',window.scrollY>300);}});
topBtn.onclick=function(){{window.scrollTo({{top:0,behavior:'smooth'}});}};"""

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>M&amp;A Intelligence — {_e(data['date_slug'])}</title>
<style>{CSS}
.card.visible{{opacity:1}}
{stagger}
</style></head><body>
<header class="hdr">
  <div class="hdr-brand">
    <div class="hdr-dot"></div>
    <div><div class="hdr h1" style="font-size:1.05rem;font-weight:700">M&amp;A &amp; Company Intelligence</div>
    <div class="hdr-sub">US · GB · CN &nbsp;·&nbsp; Google · Reuters · BBC · Baidu · Sina · Caixin</div></div>
  </div>
  <div class="hdr-right">
    <span class="hdr-time">{_e(data['generated_at'])}</span>
    <button class="save-btn" onclick="saveReport()">&#8595; Save Report</button>
  </div>
</header>
<div class="kpi-strip">{kpi_cards}</div>
<div class="ctrl">
  <div class="search-box">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
    <input type="text" placeholder="Search by company, keyword or deal size…" oninput="doSearch(this.value)"/>
  </div>
  <div class="mkt-pills">{mktpills}</div>
  <span class="total-tag">{data['total']} articles today</span>
</div>
<nav class="tabs">{tabs}</nav>
<main class="main">{panels}</main>
<div class="footer">M&amp;A Intelligence Reporter &nbsp;·&nbsp; {_e(data['date_slug'])} &nbsp;·&nbsp; Logos via Clearbit</div>
<button id="topbtn" title="Back to top">&#8593;</button>
<script>{JS}</script>
</body></html>"""

CI_MODE = "--ci" in sys.argv  # True when running inside GitHub Actions

def save_report(data):
    html = build_html(data)
    # Always save a dated copy locally
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"ma_report_{data['date_slug']}.html"
    path.write_text(html, encoding="utf-8")
    print(f"Report saved: {path.resolve()}")
    # In CI mode also write docs/index.html for GitHub Pages
    if CI_MODE:
        docs = Path(__file__).parent / "docs"
        docs.mkdir(exist_ok=True)
        (docs / "index.html").write_text(html, encoding="utf-8")
        print("CI: written to docs/index.html")
    return path

if __name__=="__main__":
    print("="*55+"\n  M&A & Company Intelligence Reporter\n  US  GB  CN\n"+"="*55)
    if CI_MODE: print("  Running in CI mode (GitHub Actions)\n")
    try:
        data=fetch_all(); path=save_report(data)
        if not CI_MODE:
            import webbrowser; webbrowser.open(path.resolve().as_uri())
        print(f"\n  Done. Saved: {path.resolve()}\n")
    except KeyboardInterrupt: print("\nCancelled.")
    except Exception as e:
        import traceback; traceback.print_exc(); input("\nPress Enter to close…"); sys.exit(1)
