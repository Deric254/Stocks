import { useState, useEffect, useCallback } from "react";

const API = "http://localhost:8000";

const get  = (p) => fetch(`${API}${p}`).then(r => { if(!r.ok) throw new Error(r.status); return r.json(); });
const post = (p,b) => fetch(`${API}${p}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)}).then(r=>{ if(!r.ok) throw new Error(r.status); return r.json(); });

// ── dericBI exact colours ──────────────────────────────────────────────────
const C = {
  green:    "#49A078", greenDk: "#3D8069", greenDkr:"#3e8865",
  greenLt:  "#d1fae5", greenBg: "#e8f6ed", bg: "#f0fdfa",
  gold:     "#facc15", goldDk: "#f59e0b",
  blue:     "#2563EB", blueLt: "#dbeafe",
  red:      "#ef4444", redLt: "#fee2e2",
  orange:   "#f97316",
  surface:  "#ffffff", borderGray:"#e5e7eb", border:"#d1fae5",
  text:     "#1f2937", textMid:"#374151", muted:"#6b7280", dim:"#9ca3af",
  foot:     "#DFF3EA",
};

const sc = s => s>=80?C.green : s>=60?C.blue : s>=40?C.goldDk : C.red;
const sl = s => s>=80?"Strong" : s>=60?"Good" : s>=40?"Fair" : "Weak";

const fmt = {
  kes: v => v==null?"—":`KES ${Number(v).toLocaleString("en-KE",{minimumFractionDigits:2,maximumFractionDigits:2})}`,
  pct: v => v==null?"—":`${(v*100).toFixed(1)}%`,
  num: (v,d=2) => v==null?"—":Number(v).toFixed(d),
};

// ── COMPONENTS ─────────────────────────────────────────────────────────────

function Spark({data=[],w=90,h=32}){
  if(data.length<2)return<svg width={w} height={h}/>;
  const mn=Math.min(...data),mx=Math.max(...data),rng=mx-mn||1;
  const pts=data.map((v,i)=>`${(i/(data.length-1))*w},${h-((v-mn)/rng)*(h-4)-2}`).join(" ");
  const up=data[data.length-1]>=data[0],col=up?C.green:C.red;
  return(
    <svg width={w} height={h} style={{display:"block"}}>
      <defs><linearGradient id={"sg"+w} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={col} stopOpacity="0.3"/><stop offset="100%" stopColor={col} stopOpacity="0"/></linearGradient></defs>
      <polygon points={`${pts} ${w},${h} 0,${h}`} fill={`url(#sg${w})`}/>
      <polyline points={pts} fill="none" stroke={col} strokeWidth="2" strokeLinejoin="round"/>
    </svg>
  );
}

function Ring({score,size=60}){
  const r=size/2-4, circ=2*Math.PI*r, dash=(score/100)*circ, c=sc(score);
  return(
    <svg width={size} height={size} style={{transform:"rotate(-90deg)",flexShrink:0}}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={C.greenLt} strokeWidth="4"/>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={c} strokeWidth="4"
        strokeDasharray={`${dash} ${circ-dash}`} strokeLinecap="round"/>
      <text x={size/2} y={size/2} textAnchor="middle" dominantBaseline="central"
        style={{transform:`rotate(90deg)`,transformOrigin:`${size/2}px ${size/2}px`,
        fontSize:size>50?13:10,fontWeight:800,fill:c,fontFamily:"inherit"}}>{score}</text>
    </svg>
  );
}

function LineChart({data=[],height=220}){
  if(!data.length)return<div style={{height,display:"flex",alignItems:"center",justifyContent:"center",color:C.muted,fontSize:13}}>No data</div>;
  const vals=data.map(d=>d.value),mn=Math.min(...vals),mx=Math.max(...vals),rng=mx-mn||1;
  const pts=data.map((d,i)=>`${(i/(data.length-1))*100},${100-((d.value-mn)/rng)*88-4}`).join(" ");
  return(
    <div>
      <div style={{display:"flex",justifyContent:"space-between",fontSize:10,color:C.muted,marginBottom:4}}>
        <span>{fmt.kes(mn)}</span><span>{fmt.kes(mx)}</span>
      </div>
      <svg viewBox="0 0 100 100" style={{width:"100%",height}} preserveAspectRatio="none">
        <defs><linearGradient id="lcg" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={C.green} stopOpacity="0.2"/><stop offset="100%" stopColor={C.green} stopOpacity="0"/></linearGradient></defs>
        <polygon points={`${pts} 100,100 0,100`} fill="url(#lcg)"/>
        <polyline points={pts} fill="none" stroke={C.green} strokeWidth="1.2" strokeLinejoin="round"/>
      </svg>
    </div>
  );
}

function Bars({data=[],height=160}){
  if(!data.length)return null;
  const maxA=Math.max(...data.map(d=>Math.abs(d.return_pct)),0.01);
  return(
    <div style={{display:"flex",alignItems:"flex-end",gap:3,height,paddingTop:12}}>
      {data.map((d,i)=>{
        const up=d.return_pct>=0,bh=Math.abs(d.return_pct/maxA)*(height*0.75);
        return(
          <div key={i} style={{flex:1,display:"flex",flexDirection:"column",alignItems:"center",gap:2}}>
            <span style={{fontSize:7,color:up?C.green:C.red,fontWeight:700}}>{(d.return_pct*100).toFixed(1)}%</span>
            <div style={{width:"100%",height:bh,background:up?C.green:C.red,borderRadius:"3px 3px 0 0"}}/>
            <span style={{fontSize:7,color:C.muted}}>{d.month?.slice(5)}</span>
          </div>
        );
      })}
    </div>
  );
}

function Stat({label,value,sub,accent=C.green,topBorder,icon,span=1}){
  return(
    <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:12,padding:"14px 16px",gridColumn:"span "+span,borderTop:"4px solid "+(topBorder||accent),boxShadow:"0 1px 4px #0000000D"}}>
      <div style={{display:"flex",alignItems:"center",gap:6,marginBottom:5}}>
        {icon&&<span style={{fontSize:14}}>{icon}</span>}
        <span style={{fontSize:10,color:C.muted,textTransform:"uppercase",letterSpacing:"0.1em",fontWeight:600}}>{label}</span>
      </div>
      <div style={{fontSize:20,fontWeight:800,color:accent,lineHeight:1,fontVariantNumeric:"tabular-nums"}}>{value}</div>
      {sub&&<div style={{fontSize:11,color:C.muted,marginTop:4}}>{sub}</div>}
    </div>
  );
}

// ── TRADE MODAL — with ticker dropdown ────────────────────────────────────
function TradeModal({tickers=[],preselect="",defaultType="BUY",onClose,onSubmit}){
  const [form,setForm]=useState({
    ticker: preselect||"",
    trade_type: defaultType,
    quantity:"",
    price:"",
    date: new Date().toISOString().slice(0,10),
  });
  const [search,setSearch]=useState(preselect||"");
  const [showDrop,setShowDrop]=useState(false);

  const set=(k,v)=>setForm(f=>({...f,[k]:v}));

  const filtered=tickers.filter(t=>
    !search || t.ticker.includes(search.toUpperCase()) || t.name.toLowerCase().includes(search.toLowerCase())
  ).slice(0,8);

  const selectTicker=(t)=>{
    set("ticker",t.ticker);
    setSearch(t.ticker+" — "+t.name);
    setShowDrop(false);
  };

  const inp={width:"100%",background:"#f9fafb",border:"1px solid "+C.borderGray,borderRadius:8,
    padding:"10px 13px",color:C.text,fontSize:14,outline:"none",boxSizing:"border-box",fontFamily:"inherit"};

  return(
    <div style={{position:"fixed",inset:0,background:"#00000066",zIndex:1000,display:"flex",alignItems:"center",justifyContent:"center",padding:16}} onClick={onClose}>
      <div onClick={e=>e.stopPropagation()} style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:16,padding:"24px 24px 28px",width:440,boxShadow:"0 20px 60px #00000022",borderTop:"4px solid "+C.green,maxHeight:"90vh",overflowY:"auto"}}>

        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:18}}>
          <span style={{fontSize:17,fontWeight:800,color:C.text}}>Log Trade</span>
          <button onClick={onClose} style={{background:"none",border:"none",color:C.muted,fontSize:22,cursor:"pointer",lineHeight:1}}>×</button>
        </div>

        {/* BUY / SELL toggle */}
        <div style={{display:"flex",gap:8,marginBottom:16}}>
          {["BUY","SELL"].map(t=>(
            <button key={t} onClick={()=>set("trade_type",t)} style={{flex:1,padding:10,borderRadius:9,
              border:"2px solid "+(form.trade_type===t?(t==="BUY"?C.green:C.red):C.borderGray),
              background:form.trade_type===t?(t==="BUY"?C.greenLt:C.redLt):"transparent",
              color:form.trade_type===t?(t==="BUY"?C.greenDk:C.red):C.muted,
              fontWeight:800,fontSize:14,cursor:"pointer",fontFamily:"inherit"}}>{t}</button>
          ))}
        </div>

        {/* Ticker search + dropdown */}
        <div style={{marginBottom:14,position:"relative"}}>
          <div style={{fontSize:10,color:C.muted,marginBottom:4,textTransform:"uppercase",letterSpacing:"0.08em",fontWeight:600}}>Stock</div>
          <input value={search} onChange={e=>{setSearch(e.target.value);setShowDrop(true);set("ticker","");}}
            onFocus={()=>setShowDrop(true)} placeholder="Search ticker or company..."
            style={inp}/>
          {showDrop&&filtered.length>0&&(
            <div style={{position:"absolute",top:"100%",left:0,right:0,background:C.surface,border:"1px solid "+C.borderGray,borderRadius:8,boxShadow:"0 8px 24px #00000018",zIndex:100,maxHeight:220,overflowY:"auto",marginTop:2}}>
              {filtered.map(t=>(
                <div key={t.ticker} onClick={()=>selectTicker(t)}
                  style={{padding:"9px 13px",cursor:"pointer",borderBottom:"1px solid "+C.borderGray,display:"flex",justifyContent:"space-between",alignItems:"center"}}
                  onMouseEnter={e=>e.currentTarget.style.background=C.greenLt}
                  onMouseLeave={e=>e.currentTarget.style.background="transparent"}>
                  <div>
                    <span style={{fontWeight:700,fontSize:13,color:C.text}}>{t.ticker}</span>
                    <span style={{fontSize:11,color:C.muted,marginLeft:8}}>{t.name}</span>
                  </div>
                  <span style={{fontSize:10,background:C.greenLt,color:C.greenDk,borderRadius:20,padding:"2px 8px",fontWeight:600}}>{t.sector}</span>
                </div>
              ))}
            </div>
          )}
          {form.ticker&&<div style={{fontSize:11,color:C.green,marginTop:4,fontWeight:600}}>✓ Selected: {form.ticker}</div>}
        </div>

        {/* Quantity */}
        <div style={{marginBottom:13}}>
          <div style={{fontSize:10,color:C.muted,marginBottom:4,textTransform:"uppercase",letterSpacing:"0.08em",fontWeight:600}}>Quantity (shares)</div>
          <input type="number" value={form.quantity} onChange={e=>set("quantity",e.target.value)} placeholder="e.g. 500" style={inp}/>
        </div>

        {/* Price */}
        <div style={{marginBottom:13}}>
          <div style={{fontSize:10,color:C.muted,marginBottom:4,textTransform:"uppercase",letterSpacing:"0.08em",fontWeight:600}}>Price per share (KES)</div>
          <input type="number" value={form.price} onChange={e=>set("price",e.target.value)} placeholder="e.g. 45.50" style={inp}/>
        </div>

        {/* Total preview */}
        {form.quantity&&form.price&&(
          <div style={{background:C.greenLt,border:"1px solid "+C.border,borderRadius:8,padding:"10px 12px",marginBottom:13,fontSize:13,color:C.greenDk,fontWeight:700}}>
            Total: {fmt.kes(parseFloat(form.quantity)*parseFloat(form.price))}
          </div>
        )}

        {/* Date */}
        <div style={{marginBottom:16}}>
          <div style={{fontSize:10,color:C.muted,marginBottom:4,textTransform:"uppercase",letterSpacing:"0.08em",fontWeight:600}}>Date</div>
          <input type="date" value={form.date} onChange={e=>set("date",e.target.value)} style={inp}/>
        </div>

        <button
          disabled={!form.ticker||!form.quantity||!form.price}
          onClick={()=>form.ticker&&form.quantity&&form.price&&onSubmit(form)}
          style={{width:"100%",padding:13,borderRadius:9,border:"none",
            background:form.ticker&&form.quantity&&form.price?"linear-gradient(135deg,"+C.green+","+C.greenDk+")":"#d1d5db",
            color:"#fff",fontWeight:800,fontSize:15,cursor:form.ticker&&form.quantity&&form.price?"pointer":"not-allowed",
            letterSpacing:"0.03em",boxShadow:form.ticker?"0 4px 14px "+C.green+"44":"none"}}>
          Confirm {form.trade_type}
        </button>
      </div>
    </div>
  );
}

function Toast({msg,type="info",onClose}){
  useEffect(()=>{const t=setTimeout(onClose,4000);return()=>clearTimeout(t);},[]);
  const col={info:C.blue,success:C.green,error:C.red}[type];
  const bg={info:C.blueLt,success:C.greenLt,error:C.redLt}[type];
  return(
    <div style={{position:"fixed",top:22,right:22,background:bg,border:"1px solid "+col,borderRadius:10,padding:"11px 18px",color:C.text,fontSize:13,zIndex:9999,boxShadow:"0 6px 24px #00000018",display:"flex",gap:9,alignItems:"center",maxWidth:340,fontWeight:600}}>
      <div style={{width:8,height:8,borderRadius:"50%",background:col,flexShrink:0}}/>{msg}
    </div>
  );
}

function Loader({text="Loading..."}){
  return(
    <div style={{display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",padding:80,gap:16}}>
      <div style={{width:40,height:40,border:"3px solid "+C.greenLt,borderTopColor:C.green,borderRadius:"50%",animation:"spin 0.8s linear infinite"}}/>
      <span style={{color:C.muted,fontSize:13}}>{text}</span>
    </div>
  );
}

// ── BUY/SELL QUICK BUTTON — used everywhere ───────────────────────────────
function TradeBtn({ticker,type,onTrade,small}){
  const isBuy=type==="BUY";
  return(
    <button onClick={e=>{e.stopPropagation();onTrade(ticker,type);}} style={{
      padding:small?"5px 10px":"8px 16px",borderRadius:7,border:"2px solid "+(isBuy?C.green:C.red),
      background:isBuy?C.greenLt:C.redLt,color:isBuy?C.greenDk:C.red,
      fontWeight:700,fontSize:small?11:12,cursor:"pointer",fontFamily:"inherit",whiteSpace:"nowrap",
    }}>{isBuy?"＋ Buy":"− Sell"}</button>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// PAGES
// ══════════════════════════════════════════════════════════════════════════

function Dashboard({stocks,portfolio,onSelect,onTrade}){
  if(!stocks.length)return<Loader text="Fetching live NSE data..."/>;
  const best=[...stocks].sort((a,b)=>(b.scores.best_pick||0)-(a.scores.best_pick||0))[0];
  const topD=[...stocks].sort((a,b)=>(b.scores.daily||0)-(a.scores.daily||0)).slice(0,5);
  const topM=[...stocks].sort((a,b)=>(b.scores.monthly||0)-(a.scores.monthly||0)).slice(0,5);
  const topL=[...stocks].sort((a,b)=>(b.scores.long_term||0)-(a.scores.long_term||0)).slice(0,5);
  const s=portfolio.summary, plPos=(s.unrealized_pl||0)>=0;

  const MiniList=({list,sk})=>list.map((stk,i)=>(
    <div key={stk.ticker} style={{display:"flex",alignItems:"center",gap:10,padding:"9px 10px",borderRadius:9,cursor:"pointer",marginBottom:4,border:"1px solid transparent",transition:"all 0.12s"}}
      onMouseEnter={e=>{e.currentTarget.style.background=C.greenLt;e.currentTarget.style.borderColor=C.border;}}
      onMouseLeave={e=>{e.currentTarget.style.background="transparent";e.currentTarget.style.borderColor="transparent";}}>
      <div onClick={()=>onSelect(stk)} style={{display:"flex",alignItems:"center",gap:10,flex:1,minWidth:0}}>
        <div style={{width:24,height:24,borderRadius:"50%",background:"linear-gradient(135deg,"+C.green+","+C.greenDk+")",color:"#fff",fontSize:11,fontWeight:800,display:"flex",alignItems:"center",justifyContent:"center",flexShrink:0}}>{i+1}</div>
        <div style={{flex:1,minWidth:0}}>
          <span style={{fontSize:13,fontWeight:700,color:C.text}}>{stk.ticker}</span>
          <span style={{fontSize:11,color:C.muted,marginLeft:6}}>{stk.name}</span>
        </div>
        <div style={{textAlign:"right",flexShrink:0,marginRight:8}}>
          <div style={{fontSize:13,fontWeight:700,color:C.text}}>KES {stk.metrics?.price||"—"}</div>
          <div style={{fontSize:12,fontWeight:800,color:sc(stk.scores[sk]||0)}}>{stk.scores[sk]||"—"}</div>
        </div>
      </div>
      <div style={{display:"flex",gap:4,flexShrink:0}}>
        <TradeBtn ticker={stk.ticker} type="BUY"  onTrade={onTrade} small/>
        <TradeBtn ticker={stk.ticker} type="SELL" onTrade={onTrade} small/>
      </div>
    </div>
  ));

  return(
    <div>
      <div style={{display:"grid",gridTemplateColumns:"repeat(5,1fr)",gap:14,marginBottom:24}}>
        <Stat icon="🏆" label="Best Pick Today" value={best?.ticker||"—"}   sub={"Score "+(best?.scores?.best_pick||"—")+" · KES "+(best?.metrics?.price||"—")} accent={C.green} topBorder={C.gold}/>
        <Stat icon="💼" label="Portfolio Value"  value={fmt.kes(s.current_value)}  sub={"Invested "+fmt.kes(s.total_invested)} accent={C.blue}/>
        <Stat icon={plPos?"📈":"📉"} label="Unrealised P/L" value={fmt.kes(s.unrealized_pl)} sub={fmt.pct(s.return_pct)+" return"} accent={plPos?C.green:C.red}/>
        <Stat icon="✅" label="Realised P/L"    value={fmt.kes(s.realized_pl)}   accent={C.green}/>
        <Stat icon="📊" label="Stocks Tracked"  value={stocks.length}             sub="NSE equities" accent={C.muted} topBorder={C.borderGray}/>
      </div>

      <div style={{display:"grid",gridTemplateColumns:"1.2fr 0.8fr",gap:18,marginBottom:18}}>
        {/* Hero card */}
        {best&&(
          <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:14,padding:24,boxShadow:"0 2px 12px #0000000A",position:"relative",overflow:"hidden"}}>
            <div style={{position:"absolute",top:0,left:0,right:0,height:4,background:"linear-gradient(90deg,"+C.gold+","+C.green+","+C.blue+")"}}/>
            <div style={{fontSize:10,color:C.green,letterSpacing:"0.15em",textTransform:"uppercase",fontWeight:700,marginBottom:12,marginTop:4}}>⚡ Best Pick of the Day</div>
            <div style={{display:"flex",alignItems:"flex-start",gap:16,marginBottom:16}}>
              <Ring score={best.scores.best_pick||0} size={76}/>
              <div style={{flex:1}}>
                <div style={{fontSize:28,fontWeight:900,color:C.text,lineHeight:1}}>{best.ticker}</div>
                <div style={{fontSize:13,color:C.muted,margin:"4px 0 6px"}}>{best.name} · {best.sector}</div>
                <div style={{fontSize:24,fontWeight:900,color:C.green}}>KES {best.metrics?.price||"—"}</div>
              </div>
              <Spark data={best.sparkline||[]} w={110} h={44}/>
            </div>
            <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:8,marginBottom:14}}>
              {[["Daily",best.scores.daily],["Monthly",best.scores.monthly],["Long-Term",best.scores.long_term],["Best Pick",best.scores.best_pick]].map(([l,sv])=>(
                <div key={l} style={{background:C.greenBg,borderRadius:8,padding:"8px 6px",textAlign:"center",border:"1px solid "+C.border}}>
                  <div style={{fontSize:10,color:C.muted,marginBottom:2,fontWeight:600}}>{l}</div>
                  <div style={{fontSize:20,fontWeight:900,color:sc(sv||0)}}>{sv||"—"}</div>
                  <div style={{fontSize:9,color:sc(sv||0),marginTop:1,fontWeight:600}}>{sl(sv||0)}</div>
                </div>
              ))}
            </div>
            <div style={{display:"flex",gap:8}}>
              {[["P/E",fmt.num(best.metrics?.pe),C.text],["P/B",fmt.num(best.metrics?.pb),C.text],["Div",fmt.pct(best.metrics?.dividend_yield),C.green]].map(([lbl,val,clr])=>(
                <div key={lbl} style={{flex:1,background:C.greenBg,borderRadius:8,padding:"8px 10px",border:"1px solid "+C.border}}>
                  <div style={{fontSize:10,color:C.muted,fontWeight:600}}>{lbl}</div>
                  <div style={{fontSize:14,fontWeight:700,color:clr}}>{val}</div>
                </div>
              ))}
              <TradeBtn ticker={best.ticker} type="BUY"  onTrade={onTrade}/>
              <TradeBtn ticker={best.ticker} type="SELL" onTrade={onTrade}/>
              <button onClick={()=>onSelect(best)} style={{flex:1,padding:"8px 10px",borderRadius:8,border:"2px solid "+C.green,background:C.greenLt,color:C.greenDk,fontWeight:700,fontSize:12,cursor:"pointer",fontFamily:"inherit"}}>Full →</button>
            </div>
          </div>
        )}

        <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:14,padding:20,boxShadow:"0 2px 12px #0000000A"}}>
          <div style={{fontSize:11,color:C.green,letterSpacing:"0.12em",textTransform:"uppercase",fontWeight:700,marginBottom:12}}>🎯 Most Undervalued Today</div>
          <MiniList list={topD} sk="daily"/>
        </div>
      </div>

      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:18}}>
        {[{t:"📊 Fundamentally Strong",list:topM,sk:"monthly"},{t:"🌱 Long-Term Value",list:topL,sk:"long_term"}].map(({t,list,sk})=>(
          <div key={sk} style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:14,padding:20,boxShadow:"0 2px 12px #0000000A"}}>
            <div style={{fontSize:11,color:C.green,letterSpacing:"0.12em",textTransform:"uppercase",fontWeight:700,marginBottom:12}}>{t}</div>
            <MiniList list={list} sk={sk}/>
          </div>
        ))}
      </div>
    </div>
  );
}

function Screener({stocks,onSelect,onTrade}){
  const [timing,setTiming]=useState("best_pick");
  const [q,setQ]=useState("");
  const list=[...stocks]
    .filter(s=>!q||s.ticker.includes(q.toUpperCase())||s.name.toLowerCase().includes(q.toLowerCase())||s.sector?.toLowerCase().includes(q.toLowerCase()))
    .sort((a,b)=>(b.scores[timing]||0)-(a.scores[timing]||0));

  return(
    <div>
      <div style={{display:"flex",gap:12,marginBottom:16,alignItems:"center"}}>
        <input value={q} onChange={e=>setQ(e.target.value)} placeholder="Search ticker, company or sector..."
          style={{flex:1,background:C.surface,border:"1px solid "+C.borderGray,borderRadius:9,padding:"10px 14px",color:C.text,fontSize:14,outline:"none",fontFamily:"inherit"}}/>
        <div style={{display:"flex",gap:6}}>
          {[{id:"best_pick",l:"Best Pick"},{id:"daily",l:"Daily"},{id:"monthly",l:"Monthly"},{id:"long_term",l:"Long-Term"}].map(t=>(
            <button key={t.id} onClick={()=>setTiming(t.id)} style={{padding:"8px 14px",borderRadius:8,border:"2px solid",borderColor:timing===t.id?C.green:C.borderGray,background:timing===t.id?C.greenLt:"transparent",color:timing===t.id?C.greenDk:C.muted,fontWeight:700,fontSize:12,cursor:"pointer",fontFamily:"inherit",transition:"all 0.15s"}}>{t.l}</button>
          ))}
        </div>
      </div>
      <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,overflow:"hidden",boxShadow:"0 2px 12px #0000000A"}}>
        <table style={{width:"100%",borderCollapse:"collapse"}}>
          <thead>
            <tr style={{background:C.greenBg,borderBottom:"2px solid "+C.border}}>
              {["#","Stock","Sector","Score","P/E","P/B","Div Yield","Price","Trend","Action"].map((h,i)=>(
                <th key={h} style={{padding:"10px 12px",textAlign:i>=4&&i<=8?"right":"left",fontSize:10,color:C.muted,fontWeight:700,letterSpacing:"0.1em",textTransform:"uppercase",whiteSpace:"nowrap"}}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {!list.length
              ?<tr><td colSpan={10} style={{padding:40,textAlign:"center",color:C.muted}}>No stocks found</td></tr>
              :list.map((s,i)=>{
                const score=s.scores[timing]||s.scores.best_pick||0, c=sc(score);
                const up=s.sparkline?.length>1&&s.sparkline[s.sparkline.length-1]>=s.sparkline[0];
                return(
                  <tr key={s.ticker} style={{borderBottom:"1px solid "+C.borderGray,transition:"background 0.12s"}}
                    onMouseEnter={e=>e.currentTarget.style.background=C.greenLt}
                    onMouseLeave={e=>e.currentTarget.style.background="transparent"}>
                    <td style={{padding:"10px 12px",color:C.dim,fontSize:12,fontWeight:600}}>{i+1}</td>
                    <td style={{padding:"10px 8px",cursor:"pointer"}} onClick={()=>onSelect(s)}>
                      <div style={{fontWeight:800,color:C.text,fontSize:14}}>{s.ticker}</div>
                      <div style={{fontSize:11,color:C.muted}}>{s.name}</div>
                    </td>
                    <td style={{padding:"10px 8px"}}>
                      <span style={{fontSize:10,background:c+"18",color:c,border:"1px solid "+c+"40",borderRadius:20,padding:"3px 9px",fontWeight:700,whiteSpace:"nowrap"}}>{s.sector}</span>
                    </td>
                    <td style={{padding:"10px 8px",textAlign:"right"}}>
                      <div style={{display:"inline-flex",alignItems:"center",justifyContent:"center",width:40,height:40,borderRadius:20,background:c+"15",border:"2px solid "+c+"50"}}>
                        <span style={{fontSize:13,fontWeight:900,color:c}}>{score}</span>
                      </div>
                    </td>
                    <td style={{padding:"10px 8px",color:C.textMid,fontSize:13,textAlign:"right",fontVariantNumeric:"tabular-nums"}}>{fmt.num(s.metrics?.pe)}</td>
                    <td style={{padding:"10px 8px",color:C.textMid,fontSize:13,textAlign:"right",fontVariantNumeric:"tabular-nums"}}>{fmt.num(s.metrics?.pb)}</td>
                    <td style={{padding:"10px 8px",color:C.green,fontSize:13,textAlign:"right",fontWeight:700}}>{fmt.pct(s.metrics?.dividend_yield)}</td>
                    <td style={{padding:"10px 12px",textAlign:"right"}}>
                      <div style={{fontSize:13,fontWeight:700,color:C.text}}>KES {s.metrics?.price||"—"}</div>
                      <div style={{fontSize:11,fontWeight:700,color:up?C.green:C.red}}>{up?"▲":"▼"}</div>
                    </td>
                    <td style={{padding:"10px 12px"}}><Spark data={s.sparkline||[]} w={80} h={28}/></td>
                    <td style={{padding:"10px 12px"}}>
                      <div style={{display:"flex",gap:4}}>
                        <TradeBtn ticker={s.ticker} type="BUY"  onTrade={onTrade} small/>
                        <TradeBtn ticker={s.ticker} type="SELL" onTrade={onTrade} small/>
                      </div>
                    </td>
                  </tr>
                );
              })
            }
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StockDetail({ticker,onBack,onTrade,tickers}){
  const [d,setD]=useState(null);
  const [tab,setTab]=useState("overview");
  const [rng,setRng]=useState("1M");
  const [loading,setLoading]=useState(true);

  useEffect(()=>{
    setLoading(true);setD(null);
    get("/api/stock/"+encodeURIComponent(ticker)).then(setD).catch(()=>setD(null)).finally(()=>setLoading(false));
  },[ticker]);

  if(loading)return<Loader text="Loading stock data..."/>;
  if(!d)return(
    <div>
      <button onClick={onBack} style={{background:"none",border:"none",color:C.green,fontSize:13,cursor:"pointer",padding:0,marginBottom:16,fontWeight:700}}>← Back</button>
      <div style={{background:C.redLt,border:"1px solid "+C.red,borderRadius:12,padding:24,color:C.red,fontSize:14}}>Could not load data for {ticker}. The stock may not be available on Yahoo Finance.</div>
    </div>
  );

  const {scores,fundamentals:f,my_position:pos}=d;
  const rMap={"1D":1,"1W":7,"1M":30,"1Y":365,"5Y":1825};
  const cd=(d.price_history||[]).slice(-rMap[rng]).map(x=>({date:x.date,value:x.close}));
  const cur=d.price_history?.[d.price_history.length-1]?.close;
  const prev=d.price_history?.[d.price_history.length-2]?.close;
  const chg=cur&&prev?cur-prev:0, pct=prev?chg/prev:0;

  return(
    <div>
      <button onClick={onBack} style={{background:"none",border:"none",color:C.green,fontSize:13,cursor:"pointer",padding:0,marginBottom:14,display:"flex",alignItems:"center",gap:6,fontWeight:700}}>← Back to Screener</button>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:18}}>
        <div>
          <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:4}}>
            <span style={{fontSize:30,fontWeight:900,color:C.text}}>{d.ticker}</span>
            <span style={{fontSize:11,background:C.greenLt,color:C.greenDk,border:"1px solid "+C.border,borderRadius:20,padding:"3px 11px",fontWeight:700}}>{d.sector}</span>
          </div>
          <div style={{fontSize:13,color:C.muted}}>{d.name}</div>
        </div>
        <div style={{textAlign:"right"}}>
          <div style={{fontSize:32,fontWeight:900,color:C.text}}>KES {fmt.num(cur,2)}</div>
          <div style={{fontSize:13,fontWeight:700,color:chg>=0?C.green:C.red}}>{chg>=0?"+":""}{fmt.num(chg,2)} ({fmt.pct(pct)})</div>
          <div style={{display:"flex",gap:8,marginTop:8,justifyContent:"flex-end"}}>
            <TradeBtn ticker={d.ticker} type="BUY"  onTrade={onTrade}/>
            <TradeBtn ticker={d.ticker} type="SELL" onTrade={onTrade}/>
          </div>
        </div>
      </div>

      <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:12,marginBottom:20}}>
        {[["Daily",scores?.daily],["Monthly",scores?.monthly],["Long-Term",scores?.long_term],["Best Pick",scores?.best_pick]].map(([l,sv])=>(
          <div key={l} style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:12,padding:"13px 12px",textAlign:"center",borderTop:"3px solid "+sc(sv||0),boxShadow:"0 1px 4px #0000000A"}}>
            <div style={{fontSize:10,color:C.muted,textTransform:"uppercase",letterSpacing:"0.1em",marginBottom:4,fontWeight:600}}>{l}</div>
            <div style={{fontSize:32,fontWeight:900,color:sc(sv||0),lineHeight:1}}>{sv||"—"}</div>
            <div style={{fontSize:11,color:sc(sv||0),marginTop:4,fontWeight:600}}>{sl(sv||0)}</div>
          </div>
        ))}
      </div>

      <div style={{display:"flex",borderBottom:"2px solid "+C.borderGray,marginBottom:16}}>
        {["overview","fundamentals","my position"].map(t=>(
          <button key={t} onClick={()=>setTab(t)} style={{padding:"10px 18px",background:"none",border:"none",borderBottom:"3px solid "+(tab===t?C.green:"transparent"),color:tab===t?C.green:C.muted,fontWeight:700,fontSize:13,cursor:"pointer",textTransform:"capitalize",fontFamily:"inherit",marginBottom:-2,transition:"all 0.15s"}}>{t}</button>
        ))}
      </div>

      {tab==="overview"&&(
        <div>
          <div style={{display:"flex",gap:6,marginBottom:12}}>
            {["1D","1W","1M","1Y","5Y"].map(r=>(
              <button key={r} onClick={()=>setRng(r)} style={{padding:"6px 13px",borderRadius:7,border:"2px solid",borderColor:rng===r?C.green:C.borderGray,background:rng===r?C.greenLt:"transparent",color:rng===r?C.greenDk:C.muted,fontSize:12,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>{r}</button>
            ))}
          </div>
          <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:12,padding:"16px 16px 10px",boxShadow:"0 2px 12px #0000000A"}}>
            {cd.length?<LineChart data={cd} height={270}/>:<div style={{padding:40,textAlign:"center",color:C.muted}}>No price history available</div>}
          </div>
        </div>
      )}

      {tab==="fundamentals"&&f&&(
        <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:12}}>
          <Stat icon="💰" label="EPS"             value={fmt.num(f.eps)}              accent={C.green}/>
          <Stat icon="📚" label="Book Value/Share" value={"KES "+fmt.num(f.bvps)}      accent={C.green}/>
          <Stat icon="📊" label="Revenue"          value={f.revenue?((f.revenue/1e9).toFixed(1)+"B"):"—"} accent={C.blue}/>
          <Stat icon="⚠️" label="Total Debt"       value={f.debt?((f.debt/1e9).toFixed(1)+"B"):"—"}      accent={C.orange} topBorder={C.orange}/>
          <Stat icon="💵" label="Annual Dividend"  value={"KES "+fmt.num(f.dividends)} accent={C.green}/>
          <Stat icon="📈" label="ROE"              value={fmt.pct(f.roe)}              accent={C.green}/>
          <Stat icon="🎯" label="Profit Margin"    value={fmt.pct(f.margin)}           accent={C.blue}/>
        </div>
      )}

      {tab==="my position"&&(
        <div>
          {pos?(
            <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:12,marginBottom:16}}>
              <Stat icon="🧾" label="Shares Held"   value={pos.quantity?.toLocaleString()} accent={C.green}/>
              <Stat icon="💳" label="Avg Cost"       value={"KES "+fmt.num(pos.avg_cost)}   accent={C.green}/>
              <Stat icon="📍" label="Current Price"  value={"KES "+fmt.num(cur,2)}           accent={C.text} topBorder={C.borderGray}/>
              <Stat icon={pos.realized_pl>=0?"🟢":"🔴"} label="Realised P/L" value={fmt.kes(pos.realized_pl)} accent={pos.realized_pl>=0?C.green:C.red}/>
              <Stat icon="📅" label="Holding Period" value={(pos.holding_days||0)+" days"} accent={C.muted} topBorder={C.borderGray} span={4}/>
            </div>
          ):(
            <div style={{background:C.greenBg,border:"1px solid "+C.border,borderRadius:12,padding:32,textAlign:"center",color:C.muted,marginBottom:16,fontSize:14}}>No position in {ticker} yet. Buy to get started.</div>
          )}
          <div style={{display:"flex",gap:12}}>
            <button onClick={()=>onTrade(d.ticker,"BUY")}  style={{flex:1,padding:14,borderRadius:10,border:"2px solid "+C.green,background:C.greenLt,color:C.greenDk,fontWeight:800,fontSize:15,cursor:"pointer",fontFamily:"inherit"}}>＋ Buy {d.ticker}</button>
            <button onClick={()=>onTrade(d.ticker,"SELL")} style={{flex:1,padding:14,borderRadius:10,border:"2px solid "+C.red,background:C.redLt,color:C.red,fontWeight:800,fontSize:15,cursor:"pointer",fontFamily:"inherit"}}>− Sell {d.ticker}</button>
          </div>
        </div>
      )}
    </div>
  );
}

function Portfolio({portfolio,onAdd,onTrade,stocks}){
  const s=portfolio.summary, plPos=(s.unrealized_pl||0)>=0;
  // Build a lookup of score from live stocks
  const scoreMap={};
  stocks.forEach(st=>{scoreMap[st.ticker]=st.scores?.best_pick||null;});

  return(
    <div>
      <div style={{display:"grid",gridTemplateColumns:"repeat(5,1fr)",gap:14,marginBottom:24}}>
        <Stat icon="💼" label="Total Invested"  value={fmt.kes(s.total_invested)}  accent={C.muted} topBorder={C.borderGray}/>
        <Stat icon="💹" label="Current Value"   value={fmt.kes(s.current_value)}   accent={C.blue}/>
        <Stat icon="📈" label="Unrealised P/L"  value={fmt.kes(s.unrealized_pl)}   accent={plPos?C.green:C.red}/>
        <Stat icon="✅" label="Realised P/L"    value={fmt.kes(s.realized_pl)}     accent={C.green}/>
        <Stat icon="🎯" label="Total Return"    value={fmt.pct(s.return_pct)}      accent={plPos?C.green:C.red}/>
      </div>

      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:12}}>
        <span style={{fontSize:16,fontWeight:700,color:C.text}}>Holdings</span>
        <button onClick={onAdd} style={{padding:"8px 20px",borderRadius:8,border:"2px solid "+C.green,background:C.greenLt,color:C.greenDk,fontWeight:700,fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>+ Add Trade</button>
      </div>

      <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,overflow:"hidden",boxShadow:"0 2px 12px #0000000A"}}>
        <table style={{width:"100%",borderCollapse:"collapse"}}>
          <thead>
            <tr style={{background:C.greenBg,borderBottom:"2px solid "+C.border}}>
              {["Ticker","Qty","Avg Cost","Current Price","Unrealised P/L","Realised P/L","Score","Action"].map(h=>(
                <th key={h} style={{padding:"10px 14px",textAlign:"left",fontSize:10,color:C.muted,fontWeight:700,letterSpacing:"0.1em",textTransform:"uppercase",whiteSpace:"nowrap"}}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {!portfolio.holdings?.length
              ?<tr><td colSpan={8} style={{padding:40,textAlign:"center",color:C.muted}}>No holdings yet. Use "+ Add Trade" to log your first position.</td></tr>
              :portfolio.holdings.map(h=>{
                const plH=(h.unrealized_pl||0)>=0;
                // Use score from live stocks data for consistency
                const bp=scoreMap[h.ticker]??h.best_pick_score;
                return(
                  <tr key={h.ticker} style={{borderBottom:"1px solid "+C.borderGray,transition:"background 0.12s"}}
                    onMouseEnter={e=>e.currentTarget.style.background=C.greenLt}
                    onMouseLeave={e=>e.currentTarget.style.background="transparent"}>
                    <td style={{padding:"12px 14px",fontWeight:800,color:C.text,fontSize:14}}>{h.ticker}</td>
                    <td style={{padding:"12px 14px",color:C.textMid,fontSize:13}}>{h.quantity?.toLocaleString()}</td>
                    <td style={{padding:"12px 14px",color:C.textMid,fontSize:13}}>KES {fmt.num(h.avg_cost)}</td>
                    <td style={{padding:"12px 14px",color:C.text,fontSize:13,fontWeight:600}}>KES {fmt.num(h.current_price)}</td>
                    <td style={{padding:"12px 14px",fontWeight:700,fontSize:13,color:plH?C.green:C.red}}>{plH?"+":""}{fmt.kes(h.unrealized_pl)}</td>
                    <td style={{padding:"12px 14px",fontWeight:700,fontSize:13,color:(h.realized_pl||0)>=0?C.green:C.red}}>{fmt.kes(h.realized_pl)}</td>
                    <td style={{padding:"12px 14px"}}>
                      {bp!=null&&<div style={{display:"inline-flex",alignItems:"center",justifyContent:"center",width:36,height:36,borderRadius:18,background:sc(bp)+"15",border:"2px solid "+sc(bp)+"50"}}><span style={{fontSize:13,fontWeight:900,color:sc(bp)}}>{Math.round(bp)}</span></div>}
                    </td>
                    <td style={{padding:"12px 14px"}}>
                      <div style={{display:"flex",gap:4}}>
                        <TradeBtn ticker={h.ticker} type="BUY"  onTrade={onTrade} small/>
                        <TradeBtn ticker={h.ticker} type="SELL" onTrade={onTrade} small/>
                      </div>
                    </td>
                  </tr>
                );
              })
            }
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Analytics({analytics}){
  if(!analytics)return<Loader text="Loading analytics..."/>;
  const {equity_curve:ec,monthly_performance:mp,best_picks:bp,worst_picks:wp,avg_holding_days:ahd,projections:pj}=analytics;
  const dl=(data,name)=>{
    if(!data?.length)return;
    const k=Object.keys(data[0]);
    const csv=[k.join(","),...data.map(r=>k.map(x=>r[x]).join(","))].join("\n");
    const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([csv],{type:"text/csv"}));a.download=name;a.click();
  };
  return(
    <div>
      <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:14,marginBottom:24}}>
        {(pj||[]).map(p=><Stat key={p.years} icon="🔮" label={p.years+"-Year Projection"} value={fmt.kes(p.projected_value)} sub={"@ "+fmt.pct(p.assumed_rate)+" p.a."} accent={C.green} topBorder={C.gold}/>)}
      </div>
      <div style={{display:"grid",gridTemplateColumns:"2fr 1fr",gap:18,marginBottom:18}}>
        <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,padding:22,boxShadow:"0 2px 12px #0000000A"}}>
          <div style={{fontSize:13,fontWeight:700,color:C.text,marginBottom:14}}>Equity Curve</div>
          <LineChart data={(ec||[]).map(x=>({date:x.date,value:x.value}))} height={240}/>
        </div>
        <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,padding:22,boxShadow:"0 2px 12px #0000000A"}}>
          <div style={{fontSize:13,fontWeight:700,color:C.text,marginBottom:4}}>Monthly Returns</div>
          <Bars data={mp||[]} height={240}/>
        </div>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:18}}>
        {[{title:"🏆 Best Picks",col:C.green,data:bp,sign:"+"},{title:"📉 Worst Picks",col:C.red,data:wp,sign:""}].map(({title,col,data,sign})=>(
          <div key={title} style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,padding:22,boxShadow:"0 2px 12px #0000000A"}}>
            <div style={{fontSize:10,color:col,textTransform:"uppercase",letterSpacing:"0.1em",fontWeight:700,marginBottom:13}}>{title}</div>
            {(data||[]).map(p=><div key={p.ticker} style={{display:"flex",justifyContent:"space-between",padding:"9px 0",borderBottom:"1px solid "+C.borderGray}}><span style={{color:C.text,fontWeight:700}}>{p.ticker}</span><span style={{color:col,fontWeight:700}}>{sign}{fmt.pct(p.return_pct)}</span></div>)}
          </div>
        ))}
        <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,padding:22,boxShadow:"0 2px 12px #0000000A"}}>
          <div style={{fontSize:10,color:C.green,textTransform:"uppercase",letterSpacing:"0.1em",fontWeight:700,marginBottom:13}}>⚙️ Stats & Exports</div>
          <div style={{display:"flex",justifyContent:"space-between",padding:"9px 0",borderBottom:"1px solid "+C.borderGray,marginBottom:14}}><span style={{color:C.muted}}>Avg Holding</span><span style={{color:C.text,fontWeight:700}}>{ahd||"—"} days</span></div>
          <div style={{display:"flex",flexDirection:"column",gap:8}}>
            <button onClick={()=>dl(ec,"equity_curve.csv")} style={{padding:"9px 12px",borderRadius:8,border:"1px solid "+C.borderGray,background:C.greenBg,color:C.textMid,fontSize:12,cursor:"pointer",fontFamily:"inherit",textAlign:"left",fontWeight:600}}>↓ Export Equity CSV</button>
            <button onClick={()=>dl(mp,"monthly_returns.csv")} style={{padding:"9px 12px",borderRadius:8,border:"1px solid "+C.borderGray,background:C.greenBg,color:C.textMid,fontSize:12,cursor:"pointer",fontFamily:"inherit",textAlign:"left",fontWeight:600}}>↓ Export Monthly CSV</button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// ROOT APP
// ══════════════════════════════════════════════════════════════════════════
export default function App(){
  const [page,setPage]      = useState("dashboard");
  const [stocks,setStocks]  = useState([]);
  const [tickers,setTickers]= useState([]);
  const [portfolio,setPortfolio] = useState({summary:{total_invested:0,current_value:0,unrealized_pl:0,realized_pl:0,return_pct:0},holdings:[]});
  const [analytics,setAnalytics] = useState(null);
  const [selected,setSelected]   = useState(null);
  const [modal,setModal]         = useState(null);   // {ticker,type}
  const [toast,setToast]         = useState(null);
  const [live,setLive]           = useState(null);

  const showToast=(msg,type="info")=>setToast({msg,type});

  // Load tickers list for dropdown (never falls back — just empty array on fail)
  useEffect(()=>{
    get("/api/tickers").then(d=>setTickers(d.tickers||[])).catch(()=>{});
  },[]);

  // Load stocks — this determines live vs demo
  useEffect(()=>{
    get("/api/stocks?timing=best_pick")
      .then(d=>{
        if(d.stocks&&d.stocks.length){setStocks(d.stocks);setLive(true);}
        else{setStocks([]);setLive(false);showToast("Backend returned no stocks","info");}
      })
      .catch(()=>{setLive(false);showToast("Cannot reach backend — check CMD window","error");});
  },[]);

  // Load portfolio
  useEffect(()=>{
    get("/api/portfolio").then(setPortfolio).catch(()=>{});
  },[]);

  // Load analytics lazily
  useEffect(()=>{
    if(page==="analytics"&&!analytics)
      get("/api/analytics").then(setAnalytics).catch(()=>{});
  },[page]);

  const handleTrade=async(form)=>{
    try{
      const r=await post("/api/trades",{ticker:form.ticker,trade_type:form.trade_type,quantity:parseInt(form.quantity),price:parseFloat(form.price),date:form.date});
      setPortfolio(r);
      showToast(form.trade_type+" "+form.quantity+" × "+form.ticker+" logged","success");
    }catch(e){
      showToast("Trade failed: "+e.message,"error");
    }
    setModal(null);
  };

  const goTo=(id)=>{setPage(id);setSelected(null);};
  const openStock=useCallback((s)=>{setSelected(s.ticker);setPage("detail");},[]);
  const openTrade=(ticker,type)=>setModal({ticker,type});

  const navItems=[
    {id:"dashboard",icon:"⊞",l:"Dashboard"},
    {id:"screener", icon:"⟳",l:"Screener"},
    {id:"portfolio",icon:"◈",l:"Portfolio"},
    {id:"analytics",icon:"≋",l:"Analytics"},
  ];
  const titles={dashboard:"Dashboard",screener:"Stock Screener",portfolio:"My Portfolio",detail:"Stock Detail",analytics:"Analytics"};

  return(
    <div style={{display:"flex",minHeight:"100vh",background:C.bg,fontFamily:"'Segoe UI','Inter',system-ui,sans-serif",color:C.text}}>
      <style>{`
        *{box-sizing:border-box;margin:0;padding:0;}
        body{background:${C.bg};overflow-x:hidden;}
        ::-webkit-scrollbar{width:5px;height:5px;}
        ::-webkit-scrollbar-thumb{background:${C.greenLt};border-radius:4px;}
        input,button{font-family:inherit;}
        @keyframes spin{to{transform:rotate(360deg);}}
      `}</style>

      {/* SIDEBAR */}
      <div style={{width:234,flexShrink:0,background:"linear-gradient(180deg,"+C.green+","+C.greenDk+")",display:"flex",flexDirection:"column",position:"sticky",top:0,height:"100vh",boxShadow:"2px 0 12px #0000001C"}}>
        <div style={{padding:"18px 18px 14px",borderBottom:"1px solid #ffffff22",display:"flex",alignItems:"center",gap:10}}>
          <img src="/logo.png" alt="" style={{width:44,height:44,borderRadius:"50%",objectFit:"cover",border:"2px solid "+C.gold,boxShadow:"0 0 0 3px #ffffff25",flexShrink:0}} onError={e=>e.target.style.display="none"}/>
          <div>
            <div style={{fontSize:17,fontWeight:900,color:"#fff",lineHeight:1}}>Stock<span style={{color:C.gold}}>Intel</span></div>
            <div style={{fontSize:9,color:"#ffffff90",letterSpacing:"0.1em",textTransform:"uppercase",marginTop:2,fontStyle:"italic"}}>Cut Through Noise</div>
          </div>
        </div>

        <nav style={{padding:"12px 10px",flex:1}}>
          {navItems.map(n=>{
            const active=page===n.id||(page==="detail"&&n.id==="screener");
            return(
              <button key={n.id} onClick={()=>goTo(n.id)} style={{width:"100%",display:"flex",alignItems:"center",gap:10,padding:"11px 13px",borderRadius:9,border:"none",background:active?"#ffffff22":"transparent",color:active?C.gold:"#ffffffCC",fontWeight:active?700:400,fontSize:13,cursor:"pointer",marginBottom:2,textAlign:"left",borderLeft:"3px solid "+(active?C.gold:"transparent"),transition:"all 0.13s"}}
                onMouseEnter={e=>{if(!active){e.currentTarget.style.color=C.gold;}}}
                onMouseLeave={e=>{if(!active){e.currentTarget.style.color="#ffffffCC";}}}>
                <span style={{fontSize:16,width:20,textAlign:"center",flexShrink:0}}>{n.icon}</span>{n.l}
              </button>
            );
          })}
        </nav>

        <div style={{padding:"13px 16px",borderTop:"1px solid #ffffff22"}}>
          <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:8}}>
            <div style={{width:8,height:8,borderRadius:"50%",flexShrink:0,background:live===null?C.gold:live?"#4ade80":C.red,boxShadow:live?"0 0 6px #4ade80":"none"}}/>
            <span style={{fontSize:11,color:"#ffffffBB"}}>{live===null?"Connecting…":live?"🟢 Live NSE data":"🔴 No live data"}</span>
          </div>
          <a href="https://dericbi.vercel.app" target="_blank" rel="noreferrer" style={{fontSize:10,color:"#ffffff70",textDecoration:"none",lineHeight:1.7,display:"block"}}>dericbi.vercel.app →</a>
        </div>
      </div>

      {/* MAIN */}
      <div style={{flex:1,display:"flex",flexDirection:"column",minWidth:0,overflow:"hidden"}}>
        {/* Top bar */}
        <div style={{padding:"13px 28px",borderBottom:"2px solid "+C.border,background:C.surface,display:"flex",alignItems:"center",justifyContent:"space-between",position:"sticky",top:0,zIndex:10,flexShrink:0,boxShadow:"0 1px 6px #0000000C"}}>
          <div>
            <div style={{fontSize:19,fontWeight:800,color:C.text}}>{titles[page]||"Stock Intel"}</div>
            <div style={{fontSize:11,color:C.muted,marginTop:1}}>{new Date().toLocaleDateString("en-KE",{weekday:"long",year:"numeric",month:"long",day:"numeric"})} · NSE</div>
          </div>
          <button onClick={()=>setModal({ticker:"",type:"BUY"})} style={{padding:"10px 22px",borderRadius:9,border:"none",background:"linear-gradient(135deg,"+C.green+","+C.greenDk+")",color:"#fff",fontWeight:800,fontSize:13,cursor:"pointer",letterSpacing:"0.03em",boxShadow:"0 4px 14px "+C.green+"44"}}>
            + Log Trade
          </button>
        </div>

        {/* Page */}
        <div style={{flex:1,padding:"24px 28px",overflowY:"auto",background:C.bg}}>
          {page==="dashboard" && <Dashboard  stocks={stocks} portfolio={portfolio} onSelect={openStock} onTrade={openTrade}/>}
          {page==="screener"  && <Screener   stocks={stocks} onSelect={openStock}  onTrade={openTrade}/>}
          {page==="portfolio" && <Portfolio  portfolio={portfolio} onAdd={()=>setModal({ticker:"",type:"BUY"})} onTrade={openTrade} stocks={stocks}/>}
          {page==="analytics" && <Analytics  analytics={analytics}/>}
          {page==="detail"&&selected && <StockDetail ticker={selected} onBack={()=>setPage("screener")} onTrade={openTrade} tickers={tickers}/>}
        </div>

        {/* Footer */}
        <footer style={{background:"linear-gradient(180deg,#ffffff,"+C.foot+")",borderTop:"1px solid "+C.border,padding:"9px 28px",display:"flex",alignItems:"center",justifyContent:"space-between",flexShrink:0,flexWrap:"wrap",gap:8}}>
          <div style={{display:"flex",alignItems:"center",gap:8}}>
            <img src="/logo.png" alt="" style={{width:30,height:30,borderRadius:"50%",objectFit:"cover",border:"2px solid "+C.gold}} onError={e=>e.target.style.display="none"}/>
            <div style={{fontSize:13,fontWeight:900,color:C.text}}>Stock<span style={{color:C.gold}}>Intel</span></div>
          </div>
          <div style={{fontSize:10,color:C.muted}}>© 2025 StockIntel · Built on <a href="https://dericbi.vercel.app" target="_blank" rel="noreferrer" style={{color:C.green,fontWeight:700,textDecoration:"none"}}>dericBI</a></div>
          <div style={{fontSize:10,color:live?C.green:C.red,fontWeight:600}}>{live===null?"Connecting…":live?"Live NSE":"No live data — check backend"}</div>
        </footer>
      </div>

      {/* Trade modal */}
      {modal&&(
        <TradeModal
          tickers={tickers.length?tickers:stocks.map(s=>({ticker:s.ticker,name:s.name,sector:s.sector}))}
          preselect={modal.ticker}
          defaultType={modal.type||"BUY"}
          onClose={()=>setModal(null)}
          onSubmit={handleTrade}
        />
      )}
      {toast&&<Toast msg={toast.msg} type={toast.type} onClose={()=>setToast(null)}/>}
    </div>
  );
}
