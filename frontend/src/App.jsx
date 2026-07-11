import { useState, useEffect, useCallback, useRef } from "react";

// Works locally (localhost:8000) AND when hosted on Render/Railway
// To deploy: set VITE_API_URL env variable in your hosting dashboard
const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

// Fetch with timeout — prevents infinite loading on Render cold start
function fetchTimeout(url, opts={}, ms=25000){
  const ctrl = new AbortController();
  const id = setTimeout(()=>ctrl.abort(), ms);
  return fetch(url, {...opts, signal: ctrl.signal})
    .then(r=>{ clearTimeout(id); if(!r.ok) throw new Error(r.status); return r.json(); })
    .catch(e=>{ clearTimeout(id); throw e; });
}
const get  = (p) => fetchTimeout(`${API}${p}`);
const post = (p,b) => fetchTimeout(`${API}${p}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)});
const del  = (p) => fetchTimeout(`${API}${p}`,{method:"DELETE"});

// ── dericBI colour palette ─────────────────────────────────────────────────
const C = {
  green:    "#49A078", greenDk: "#3D8069", greenDkr:"#3e8865",
  greenLt:  "#d1fae5", greenBg: "#e8f6ed", bg: "#f0fdfa",
  gold:     "#facc15", goldDk: "#f59e0b",
  blue:     "#2563EB", blueLt: "#dbeafe",
  red:      "#ef4444", redLt: "#fee2e2",
  orange:   "#f97316", orangeLt: "#ffedd5",
  yellow:   "#facc15", yellowLt: "#fef9c3",
  surface:  "#ffffff", borderGray:"#e5e7eb", border:"#d1fae5",
  text:     "#1f2937", textMid:"#374151", muted:"#6b7280", dim:"#9ca3af",
  foot:     "#DFF3EA",
};

// 60-point score helpers
const sc60 = s => s>=50?C.green : s>=40?"#86efac" : s>=30?C.yellow : s>=20?C.orange : C.red;
const sl60 = s => s>=50?"Strong Buy" : s>=40?"Buy" : s>=30?"Hold" : s>=20?"Weak" : "Avoid";
const sc60bg = s => s>=50?C.greenLt : s>=40?"#dcfce7" : s>=30?C.yellowLt : s>=20?C.orangeLt : C.redLt;

const fmt = {
  kes: v => v==null?"—":`KES ${Number(v).toLocaleString("en-KE",{minimumFractionDigits:2,maximumFractionDigits:2})}`,
  pct: v => v==null?"—":`${(v*100).toFixed(1)}%`,
  num: (v,d=2) => v==null?"—":Number(v).toFixed(d),
  bil: v => v==null?"—":v>=1e9?`${(v/1e9).toFixed(1)}B`:v>=1e6?`${(v/1e6).toFixed(1)}M`:Number(v).toFixed(0),
};

// ── Mini sparkline ────────────────────────────────────────────────────────
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

// ── Score ring (60-point) ─────────────────────────────────────────────────
function Ring60({score,size=64}){
  const max60=60, r=size/2-4, circ=2*Math.PI*r;
  const dash=(score/max60)*circ, c=sc60(score);
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

// ── Simple line chart ─────────────────────────────────────────────────────
function LineChart({data=[],height=200,color}){
  if(!data.length)return<div style={{height,display:"flex",alignItems:"center",justifyContent:"center",color:C.muted,fontSize:13}}>No data</div>;
  const vals=data.map(d=>d.value),mn=Math.min(...vals),mx=Math.max(...vals),rng=mx-mn||1;
  const col=color||C.green;
  const pts=data.map((d,i)=>`${(i/(data.length-1))*100},${100-((d.value-mn)/rng)*88-4}`).join(" ");
  return(
    <div>
      <div style={{display:"flex",justifyContent:"space-between",fontSize:10,color:C.muted,marginBottom:4}}>
        <span>{fmt.kes(mn)}</span><span>{fmt.kes(mx)}</span>
      </div>
      <svg viewBox="0 0 100 100" style={{width:"100%",height}} preserveAspectRatio="none">
        <defs><linearGradient id="lcg" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={col} stopOpacity="0.2"/><stop offset="100%" stopColor={col} stopOpacity="0"/></linearGradient></defs>
        <polygon points={`${pts} 100,100 0,100`} fill="url(#lcg)"/>
        <polyline points={pts} fill="none" stroke={col} strokeWidth="1.2" strokeLinejoin="round"/>
      </svg>
    </div>
  );
}

// ── Bar chart ─────────────────────────────────────────────────────────────
function BarChart({data=[],height=160,labelKey="label",valueKey="value",color}){
  if(!data.length)return null;
  const maxA=Math.max(...data.map(d=>Math.abs(d[valueKey]||0)),0.01);
  return(
    <div style={{display:"flex",alignItems:"flex-end",gap:3,height,paddingTop:12}}>
      {data.map((d,i)=>{
        const val=d[valueKey]||0,up=val>=0,bh=Math.abs(val/maxA)*(height*0.75);
        const col=color||(up?C.green:C.red);
        return(
          <div key={i} style={{flex:1,display:"flex",flexDirection:"column",alignItems:"center",gap:2}}>
            <span style={{fontSize:7,color:col,fontWeight:700}}>{typeof val==="number"&&Math.abs(val)<10?val.toFixed(1):Math.round(val)}</span>
            <div style={{width:"100%",height:bh,background:col,borderRadius:"3px 3px 0 0"}}/>
            <span style={{fontSize:7,color:C.muted,textAlign:"center",wordBreak:"break-all"}}>{String(d[labelKey]||"").slice(0,5)}</span>
          </div>
        );
      })}
    </div>
  );
}

// ── Stat card ─────────────────────────────────────────────────────────────
function Stat({label,value,sub,accent=C.green,topBorder,icon,span=1}){
  return(
    <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:12,padding:"14px 16px",gridColumn:"span "+span,borderTop:"4px solid "+(topBorder||accent),boxShadow:"0 1px 4px #0000000D"}}>
      <div style={{display:"flex",alignItems:"center",gap:6,marginBottom:5}}>
        {icon&&<span style={{fontSize:16}}>{icon}</span>}
        <span style={{fontSize:10,color:C.muted,textTransform:"uppercase",letterSpacing:"0.08em",fontWeight:600}}>{label}</span>
      </div>
      <div style={{fontSize:20,fontWeight:800,color:C.text,lineHeight:1.1}}>{value}</div>
      {sub&&<div style={{fontSize:11,color:C.muted,marginTop:4}}>{sub}</div>}
    </div>
  );
}

// ── Score pill ────────────────────────────────────────────────────────────
function ScorePill({score,size="md"}){
  if(score==null)return<span style={{color:C.dim,fontSize:11}}>—</span>;
  const c=sc60(score),bg=sc60bg(score);
  const fs=size==="lg"?16:13,pad=size==="lg"?"6px 14px":"4px 10px";
  return(
    <span style={{display:"inline-block",padding:pad,borderRadius:20,background:bg,border:"1.5px solid "+c,color:c,fontWeight:800,fontSize:fs,whiteSpace:"nowrap"}}>
      {score}<span style={{fontSize:fs-3,fontWeight:600,marginLeft:3}}>/60</span>
    </span>
  );
}

// ── Trade button ──────────────────────────────────────────────────────────
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

// ── Trade Modal ───────────────────────────────────────────────────────────
function TradeModal({tickers=[],preselect="",defaultType="BUY",onClose,onSubmit,stocks=[]}){
  const getPrice=(ticker)=>{
    const t=stocks.find(s=>s.ticker===ticker||s.ticker===ticker.split(".")[0]);
    return t?.metrics?.price||"";
  };
  const initPrice = preselect ? getPrice(preselect) : "";
  const [form,setForm]=useState({ticker:preselect||"",trade_type:defaultType,quantity:"",price:initPrice,date:new Date().toISOString().slice(0,10)});
  const [search,setSearch]=useState(preselect||"");
  const [showDrop,setShowDrop]=useState(false);
  const set=(k,v)=>setForm(f=>({...f,[k]:v}));
  const filtered=tickers.filter(t=>!search||t.ticker.includes(search.toUpperCase())||t.name.toLowerCase().includes(search.toLowerCase())).slice(0,8);
  const selectTicker=(t)=>{
    const autoPrice=getPrice(t.ticker);
    setForm(f=>({...f,ticker:t.ticker,price:autoPrice}));
    setSearch(t.ticker+" — "+t.name);
    setShowDrop(false);
  };
  const inp={width:"100%",background:"#f9fafb",border:"1px solid "+C.borderGray,borderRadius:8,padding:"10px 13px",color:C.text,fontSize:14,outline:"none",boxSizing:"border-box",fontFamily:"inherit"};
  return(
    <div style={{position:"fixed",inset:0,background:"#00000066",zIndex:1000,display:"flex",alignItems:"center",justifyContent:"center",padding:16}} onClick={onClose}>
      <div onClick={e=>e.stopPropagation()} style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:16,padding:"24px 24px 28px",width:"min(440px, 92vw)",boxShadow:"0 20px 60px #00000022",borderTop:"4px solid "+C.green,maxHeight:"90vh",overflowY:"auto"}}>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:18}}>
          <span style={{fontSize:17,fontWeight:800,color:C.text}}>Log Trade</span>
          <button onClick={onClose} style={{background:"none",border:"none",color:C.muted,fontSize:22,cursor:"pointer",lineHeight:1}}>×</button>
        </div>
        <div style={{display:"flex",gap:8,marginBottom:16}}>
          {["BUY","SELL","DIVIDEND"].map(t=>(
            <button key={t} onClick={()=>set("trade_type",t)} style={{flex:1,padding:9,borderRadius:9,
              border:"2px solid "+(form.trade_type===t?(t==="BUY"?C.green:t==="SELL"?C.red:C.blue):C.borderGray),
              background:form.trade_type===t?(t==="BUY"?C.greenLt:t==="SELL"?C.redLt:C.blueLt):"transparent",
              color:form.trade_type===t?(t==="BUY"?C.greenDk:t==="SELL"?C.red:C.blue):C.muted,
              fontWeight:800,fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>{t}</button>
          ))}
        </div>
        <div style={{marginBottom:14,position:"relative"}}>
          <div style={{fontSize:10,color:C.muted,marginBottom:4,textTransform:"uppercase",letterSpacing:"0.08em",fontWeight:600}}>Stock</div>
          <input value={search} onChange={e=>{setSearch(e.target.value);setShowDrop(true);set("ticker","");}} onFocus={()=>setShowDrop(true)} placeholder="Search ticker or company..." style={inp}/>
          {showDrop&&filtered.length>0&&(
            <div style={{position:"absolute",top:"100%",left:0,right:0,background:C.surface,border:"1px solid "+C.borderGray,borderRadius:8,boxShadow:"0 8px 24px #00000018",zIndex:100,maxHeight:220,overflowY:"auto",marginTop:2}}>
              {filtered.map(t=>(
                <div key={t.ticker} onClick={()=>selectTicker(t)} style={{padding:"9px 13px",cursor:"pointer",borderBottom:"1px solid "+C.borderGray,display:"flex",justifyContent:"space-between",alignItems:"center"}}
                  onMouseEnter={e=>e.currentTarget.style.background=C.greenLt} onMouseLeave={e=>e.currentTarget.style.background="transparent"}>
                  <div><span style={{fontWeight:700,fontSize:13,color:C.text}}>{t.ticker}</span><span style={{fontSize:11,color:C.muted,marginLeft:8}}>{t.name}</span></div>
                  <span style={{fontSize:10,background:C.greenLt,color:C.greenDk,borderRadius:20,padding:"2px 8px",fontWeight:600}}>{t.sector}</span>
                </div>
              ))}
            </div>
          )}
          {form.ticker&&<div style={{fontSize:11,color:C.green,marginTop:4,fontWeight:600}}>✓ {form.ticker}</div>}
        </div>
        <div style={{marginBottom:13}}>
          <div style={{fontSize:10,color:C.muted,marginBottom:4,textTransform:"uppercase",letterSpacing:"0.08em",fontWeight:600}}>{form.trade_type==="DIVIDEND"?"Shares Held":"Quantity"}</div>
          <input type="number" value={form.quantity} onChange={e=>set("quantity",e.target.value)} placeholder="e.g. 500" style={inp}/>
        </div>
        <div style={{marginBottom:13}}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:4}}>
            <div style={{fontSize:10,color:C.muted,textTransform:"uppercase",letterSpacing:"0.08em",fontWeight:600}}>{form.trade_type==="DIVIDEND"?"Dividend per Share (KES)":"Price per Share (KES)"}</div>
            {form.price&&form.ticker&&<div style={{fontSize:10,color:C.green,fontWeight:600}}>↑ auto-filled · editable</div>}
          </div>
          <input type="number" value={form.price} onChange={e=>set("price",e.target.value)} placeholder="e.g. 45.50" style={inp}/>
          {form.trade_type!=="DIVIDEND"&&<div style={{fontSize:10,color:C.muted,marginTop:3}}>Price is from the latest data in the system. You can edit if needed.</div>}
        </div>
        {form.quantity&&form.price&&(
          <div style={{background:C.greenLt,border:"1px solid "+C.border,borderRadius:8,padding:"10px 12px",marginBottom:13,fontSize:13,color:C.greenDk,fontWeight:700}}>
            Total: {fmt.kes(parseFloat(form.quantity)*parseFloat(form.price))}
          </div>
        )}
        <div style={{marginBottom:16}}>
          <div style={{fontSize:10,color:C.muted,marginBottom:4,textTransform:"uppercase",letterSpacing:"0.08em",fontWeight:600}}>Date</div>
          <input type="date" value={form.date} onChange={e=>set("date",e.target.value)} style={inp}/>
        </div>
        <button disabled={!form.ticker||!form.quantity||!form.price} onClick={()=>form.ticker&&form.quantity&&form.price&&onSubmit(form)}
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

// ── Toast ─────────────────────────────────────────────────────────────────
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

// ── OFFLINE BANNER ────────────────────────────────────────────────────────
function OfflineBanner(){
  return(
    <div style={{background:"#fef3c7",border:"1px solid "+C.gold,borderRadius:8,padding:"8px 16px",fontSize:12,color:"#92400e",fontWeight:600,display:"flex",alignItems:"center",gap:8,marginBottom:12}}>
      📡 Offline — using last cached data. Will sync when back online.
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// DASHBOARD
// ══════════════════════════════════════════════════════════════════════════
function Dashboard({stocks,portfolio,onSelect,onTrade}){
  if(!stocks.length)return<Loader text="Fetching live NSE data..."/>;
  const best=[...stocks].sort((a,b)=>(b.scores.total_score||0)-(a.scores.total_score||0))[0];
  const topScore=[...stocks].sort((a,b)=>(b.scores.total_score||0)-(a.scores.total_score||0)).slice(0,5);
  const topYield=[...stocks].sort((a,b)=>(b.metrics?.dividend_yield||0)-(a.metrics?.dividend_yield||0)).slice(0,5);
  const topValue=[...stocks].sort((a,b)=>(a.metrics?.pb||99)-(b.metrics?.pb||99)).slice(0,5);
  const s=portfolio.summary,plPos=(s.unrealized_pl||0)>=0;

  const MiniList=({list,labelKey,labelFn})=>list.map((stk,i)=>(
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
          <div style={{fontSize:12,fontWeight:700,color:C.text}}>KES {stk.metrics?.price||"—"}</div>
          <div style={{fontSize:11,fontWeight:800,color:sc60(stk.scores.total_score||0)}}>{labelFn?labelFn(stk):stk.scores.total_score||"—"}</div>
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
      {/* KPI row */}
      <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"repeat(5,1fr)",gap:14,marginBottom:24}}>
        <Stat icon="🏆" label="Top Pick Today"   value={best?.ticker||"—"}       sub={"Score "+(best?.scores?.total_score||"—")+"/60 · KES "+(best?.metrics?.price||"—")} accent={C.green} topBorder={C.gold}/>
        <Stat icon="💼" label="Portfolio Value"  value={fmt.kes(s.current_value)} sub={"Invested "+fmt.kes(s.total_invested)} accent={C.blue}/>
        <Stat icon={plPos?"📈":"📉"} label="Unrealised P/L" value={fmt.kes(s.unrealized_pl)} sub={fmt.pct(s.return_pct)+" return"} accent={plPos?C.green:C.red}/>
        <Stat icon="💰" label="Dividends YTD"    value={fmt.kes(s.dividends_ytd)} accent={C.green}/>
        <Stat icon="📊" label="Stocks Tracked"   value={stocks.length} sub="NSE equities" accent={C.muted} topBorder={C.borderGray}/>
      </div>

      {/* Hero + top scored */}
      <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"1.2fr 0.8fr",gap:18,marginBottom:18}}>
        {best&&(
          <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:14,padding:24,boxShadow:"0 2px 12px #0000000A",position:"relative",overflow:"hidden"}}>
            <div style={{position:"absolute",top:0,left:0,right:0,height:4,background:"linear-gradient(90deg,"+C.gold+","+C.green+","+C.blue+")"}}/>
            <div style={{fontSize:10,color:C.green,letterSpacing:"0.15em",textTransform:"uppercase",fontWeight:700,marginBottom:12,marginTop:4}}>⚡ Top Scoring Stock</div>
            <div style={{display:"flex",alignItems:"flex-start",gap:16,marginBottom:16}}>
              <Ring60 score={best.scores.total_score||0} size={76}/>
              <div style={{flex:1}}>
                <div style={{fontSize:28,fontWeight:900,color:C.text,lineHeight:1}}>{best.ticker}</div>
                <div style={{fontSize:13,color:C.muted,margin:"4px 0 6px"}}>{best.name} · {best.sector}</div>
                <div style={{fontSize:24,fontWeight:900,color:C.green}}>KES {best.metrics?.price||"—"}</div>
              </div>
              <Spark data={best.sparkline||[]} w={110} h={44}/>
            </div>
            <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:8,marginBottom:14}}>
              {[["Profitability",best.scores.profitability_score],["Value",best.scores.value_score],["Dividends",best.scores.dividend_score],["Growth",best.scores.growth_score],["Asset Safety",best.scores.asset_safety_score],["Debt Safety",best.scores.debt_safety_score]].map(([l,sv])=>(
                <div key={l} style={{background:C.greenBg,borderRadius:8,padding:"8px 6px",textAlign:"center",border:"1px solid "+C.border}}>
                  <div style={{fontSize:9,color:C.muted,marginBottom:2,fontWeight:600}}>{l}</div>
                  <div style={{fontSize:18,fontWeight:900,color:sc60((sv||0)*6)}}>{sv||0}<span style={{fontSize:10,color:C.muted}}>/10</span></div>
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
          <div style={{fontSize:11,color:C.green,letterSpacing:"0.12em",textTransform:"uppercase",fontWeight:700,marginBottom:12}}>🎯 Top by Score</div>
          <MiniList list={topScore} labelFn={s=>s.scores.total_score+"/60"}/>
        </div>
      </div>

      <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:18}}>
        <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:14,padding:20,boxShadow:"0 2px 12px #0000000A"}}>
          <div style={{fontSize:11,color:C.green,letterSpacing:"0.12em",textTransform:"uppercase",fontWeight:700,marginBottom:12}}>💰 Highest Dividend Yield</div>
          <MiniList list={topYield} labelFn={s=>fmt.pct(s.metrics?.dividend_yield)}/>
        </div>
        <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:14,padding:20,boxShadow:"0 2px 12px #0000000A"}}>
          <div style={{fontSize:11,color:C.green,letterSpacing:"0.12em",textTransform:"uppercase",fontWeight:700,marginBottom:12}}>📈 Best Value (Low P/B)</div>
          <MiniList list={topValue} labelFn={s=>"P/B "+fmt.num(s.metrics?.pb)}/>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// SCREENER
// ══════════════════════════════════════════════════════════════════════════
function Screener({stocks,sectors,onSelect,onTrade}){
  const [q,setQ]=useState("");
  const [sector,setSector]=useState("");
  const [sort,setSort]=useState("score");
  const [scoreMin,setScoreMin]=useState(0);
  const [scoreMax,setScoreMax]=useState(60);

  const list=[...stocks]
    .filter(s=>{
      const ts=s.scores.total_score||0;
      if(ts<scoreMin||ts>scoreMax)return false;
      if(sector&&s.sector!==sector)return false;
      if(q&&!s.ticker.includes(q.toUpperCase())&&!s.name.toLowerCase().includes(q.toLowerCase())&&!s.sector?.toLowerCase().includes(q.toLowerCase()))return false;
      return true;
    })
    .sort((a,b)=>{
      if(sort==="price")return(b.metrics?.price||0)-(a.metrics?.price||0);
      if(sort==="pe")return(a.metrics?.pe||9999)-(b.metrics?.pe||9999);
      if(sort==="pb")return(a.metrics?.pb||9999)-(b.metrics?.pb||9999);
      if(sort==="yield")return(b.metrics?.dividend_yield||0)-(a.metrics?.dividend_yield||0);
      return(b.scores.total_score||0)-(a.scores.total_score||0);
    });

  return(
    <div>
      {/* Filter bar */}
      <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:12,padding:"14px 16px",marginBottom:16,display:"flex",flexWrap:"wrap",gap:12,alignItems:"center"}}>
        <input value={q} onChange={e=>setQ(e.target.value)} placeholder="Search ticker, company or sector..."
          style={{flex:"1 1 200px",background:"#f9fafb",border:"1px solid "+C.borderGray,borderRadius:9,padding:"9px 13px",color:C.text,fontSize:14,outline:"none",fontFamily:"inherit"}}/>
        <select value={sector} onChange={e=>setSector(e.target.value)}
          style={{padding:"9px 12px",borderRadius:8,border:"1px solid "+C.borderGray,background:"#f9fafb",color:C.text,fontSize:13,cursor:"pointer",outline:"none",fontFamily:"inherit"}}>
          <option value="">All Sectors</option>
          {sectors.map(s=><option key={s} value={s}>{s}</option>)}
        </select>
        <div style={{display:"flex",alignItems:"center",gap:8,fontSize:12,color:C.muted}}>
          <span>Score:</span>
          <input type="range" min={0} max={60} value={scoreMin} onChange={e=>setScoreMin(+e.target.value)} style={{width:80}}/>
          <span style={{fontWeight:700,color:C.text}}>{scoreMin}</span>
          <span>—</span>
          <input type="range" min={0} max={60} value={scoreMax} onChange={e=>setScoreMax(+e.target.value)} style={{width:80}}/>
          <span style={{fontWeight:700,color:C.text}}>{scoreMax}</span>
        </div>
        <div style={{display:"flex",gap:6}}>
          {[{id:"score",l:"Score"},{id:"price",l:"Price"},{id:"pe",l:"P/E"},{id:"pb",l:"P/B"},{id:"yield",l:"Yield"}].map(t=>(
            <button key={t.id} onClick={()=>setSort(t.id)} style={{padding:"7px 13px",borderRadius:8,border:"2px solid",borderColor:sort===t.id?C.green:C.borderGray,background:sort===t.id?C.greenLt:"transparent",color:sort===t.id?C.greenDk:C.muted,fontWeight:700,fontSize:12,cursor:"pointer",fontFamily:"inherit",transition:"all 0.15s"}}>{t.l}</button>
          ))}
        </div>
      </div>

      <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,overflow:"hidden",boxShadow:"0 2px 12px #0000000A"}}>
      <div className="resp-table-wrap" style={{overflowX:"auto"}}>
        <table style={{width:"100%",borderCollapse:"collapse"}}>
          <thead>
            <tr style={{background:C.greenBg,borderBottom:"2px solid "+C.border}}>
              {["#","Stock","Sector","Score","P/E","P/B","Div Yield","Price","Asset Cov","Trend","Action"].map((h,i)=>(
                <th key={h} style={{padding:"10px 12px",textAlign:i>=4?i<=8?"right":"left":"left",fontSize:10,color:C.muted,fontWeight:700,letterSpacing:"0.1em",textTransform:"uppercase",whiteSpace:"nowrap"}}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {!list.length
              ?<tr><td colSpan={11} style={{padding:40,textAlign:"center",color:C.muted}}>No stocks match your filters</td></tr>
              :list.map((s,i)=>{
                const score=s.scores.total_score||0, c=sc60(score);
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
                    <td style={{padding:"10px 8px"}}>
                      <div style={{display:"inline-flex",flexDirection:"column",alignItems:"center",gap:1}}>
                        <ScorePill score={score}/>
                        <span style={{fontSize:9,color:sc60(score),fontWeight:700}}>{sl60(score)}</span>
                      </div>
                    </td>
                    <td style={{padding:"10px 8px",color:C.textMid,fontSize:13,textAlign:"right",fontVariantNumeric:"tabular-nums"}}>{fmt.num(s.metrics?.pe)}</td>
                    <td style={{padding:"10px 8px",color:C.textMid,fontSize:13,textAlign:"right",fontVariantNumeric:"tabular-nums"}}>{fmt.num(s.metrics?.pb)}</td>
                    <td style={{padding:"10px 8px",color:C.green,fontSize:13,textAlign:"right",fontWeight:700}}>{fmt.pct(s.metrics?.dividend_yield)}</td>
                    <td style={{padding:"10px 12px",textAlign:"right"}}>
                      <div style={{fontSize:13,fontWeight:700,color:C.text}}>KES {s.metrics?.price||"—"}</div>
                      <div style={{fontSize:11,fontWeight:700,color:up?C.green:C.red}}>{up?"▲":"▼"}</div>
                    </td>
                    <td style={{padding:"10px 8px",color:C.textMid,fontSize:13,textAlign:"right"}}>{fmt.num(s.metrics?.asset_coverage)}</td>
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
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// STOCK DETAIL
// ══════════════════════════════════════════════════════════════════════════
function StockDetail({ticker,onBack,onTrade,tickers,onToast}){
  const [d,setD]=useState(null);
  const [tab,setTab]=useState("overview");
  const [rng,setRng]=useState("1M");
  const [loading,setLoading]=useState(true);
  const [inWl,setInWl]=useState(false);
  const [missingForm,setMissingForm]=useState({});
  const [saving,setSaving]=useState(false);
  const [rec,setRec]=useState(null);
  const [recLoading,setRecLoading]=useState(false);
  const [logging,setLogging]=useState(false);

  useEffect(()=>{
    setLoading(true);setD(null);setRec(null);
    get("/api/stock/"+encodeURIComponent(ticker)).then(data=>{setD(data);setInWl(data.in_watchlist||false);}).catch(()=>setD(null)).finally(()=>setLoading(false));
  },[ticker]);

  useEffect(()=>{
    if(tab==="recommendation"&&!rec&&!recLoading){
      setRecLoading(true);
      get("/api/stock/"+encodeURIComponent(ticker)+"/recommendation").then(setRec).catch(()=>setRec({available:false,reason:"Could not reach the backend."})).finally(()=>setRecLoading(false));
    }
  },[tab,ticker]);

  const logRecommendation=async()=>{
    setLogging(true);
    try{
      await post("/api/recommendations/log?ticker="+encodeURIComponent(ticker),{});
      onToast("Logged to track record — outcome can be checked later","success");
    }catch(e){onToast("Failed to log recommendation","error");}
    setLogging(false);
  };

  const toggleWatchlist=async()=>{
    const ep=inWl?"/api/watchlist/remove":"/api/watchlist/add";
    await post(ep,{ticker}).catch(()=>{});
    setInWl(!inWl);
    onToast(inWl?"Removed from watchlist":"Added to watchlist","success");
  };

  const saveMissing=async(field)=>{
    const val=missingForm[field];
    if(!val)return;
    setSaving(true);
    try{
      const r=await post("/api/missing-data",{ticker,field_name:field,value:String(val),source:"manual"});
      setD(prev=>prev?({...prev,scores:{...prev.scores,...r.new_scores}}):prev);
      onToast("Data saved & score updated","success");
      setMissingForm(f=>({...f,[field]:""}));
    }catch(e){onToast("Save failed","error");}
    setSaving(false);
  };

  if(loading)return<Loader text="Loading stock data..."/>;
  if(!d)return(
    <div>
      <button onClick={onBack} style={{background:"none",border:"none",color:C.green,fontSize:13,cursor:"pointer",padding:0,marginBottom:16,fontWeight:700}}>← Back</button>
      <div style={{background:C.redLt,border:"1px solid "+C.red,borderRadius:12,padding:24,color:C.red,fontSize:14}}>Could not load data for {ticker}.</div>
    </div>
  );

  const {scores,fundamentals:f,my_position:pos,history_charts:hc,missing_fields:mf=[]}=d;
  const rMap={"1D":1,"1W":7,"1M":30,"3M":90,"1Y":365};
  const cd=(d.price_history||[]).slice(-rMap[rng]).map(x=>({date:x.date,value:x.close}));
  const cur=d.price_history?.[d.price_history.length-1]?.close;
  const prev=d.price_history?.[d.price_history.length-2]?.close;
  const chg=cur&&prev?cur-prev:0, pct=prev?chg/prev:0;

  const scoreBreakdown=[
    {key:"profitability_score",label:"Profitability",icon:"📈",desc:"Profit trend + ROE"},
    {key:"dividend_score",     label:"Dividends",    icon:"💰",desc:"Consistency + payout ratio"},
    {key:"growth_score",       label:"Growth",       icon:"🌱",desc:"Revenue & earnings CAGR"},
    {key:"value_score",        label:"Value",        icon:"🏷️", desc:"P/B + P/E ratios"},
    {key:"asset_safety_score", label:"Asset Safety", icon:"🛡️", desc:"Earnings yield + asset coverage"},
    {key:"debt_safety_score",  label:"Debt Safety",  icon:"⚖️", desc:"D/E ratio + interest coverage"},
  ];

  return(
    <div>
      {/* Back */}
      <button onClick={onBack} style={{background:"none",border:"none",color:C.green,fontSize:13,cursor:"pointer",padding:0,marginBottom:16,fontWeight:700}}>← Back to Screener</button>

      {/* Header */}
      <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:14,padding:24,marginBottom:18,boxShadow:"0 2px 12px #0000000A",position:"relative",overflow:"hidden"}}>
        <div style={{position:"absolute",top:0,left:0,right:0,height:4,background:"linear-gradient(90deg,"+sc60(scores.total_score||0)+","+C.greenDk+")"}}/>
        <div style={{display:"flex",alignItems:"flex-start",gap:20,marginTop:4}}>
          <Ring60 score={scores.total_score||0} size={80}/>
          <div style={{flex:1}}>
            <div style={{display:"flex",alignItems:"center",gap:12,flexWrap:"wrap"}}>
              <span style={{fontSize:30,fontWeight:900,color:C.text}}>{d.ticker}</span>
              <span style={{fontSize:14,color:C.muted}}>{d.name}</span>
              <span style={{fontSize:11,background:C.greenLt,color:C.greenDk,borderRadius:20,padding:"3px 10px",fontWeight:700}}>{d.sector}</span>
              <span style={{fontSize:13,fontWeight:800,color:sc60(scores.total_score||0),background:sc60bg(scores.total_score||0),borderRadius:8,padding:"4px 12px",border:"1.5px solid "+sc60(scores.total_score||0)}}>{scores.label||sl60(scores.total_score||0)}</span>
            </div>
            <div style={{display:"flex",alignItems:"baseline",gap:10,margin:"8px 0"}}>
              <span style={{fontSize:28,fontWeight:900,color:C.text}}>KES {fmt.num(cur,2)}</span>
              <span style={{fontSize:14,fontWeight:700,color:chg>=0?C.green:C.red}}>{chg>=0?"+":""}{fmt.num(chg,2)} ({chg>=0?"+":""}{(pct*100).toFixed(2)}%)</span>
            </div>
          </div>
          <div style={{display:"flex",gap:8,flexShrink:0,flexWrap:"wrap"}}>
            <TradeBtn ticker={d.ticker} type="BUY"  onTrade={onTrade}/>
            <TradeBtn ticker={d.ticker} type="SELL" onTrade={onTrade}/>
            <button onClick={toggleWatchlist} style={{padding:"8px 16px",borderRadius:8,border:"2px solid "+(inWl?C.gold:C.borderGray),background:inWl?"#fef3c7":"transparent",color:inWl?C.goldDk:C.muted,fontWeight:700,fontSize:12,cursor:"pointer",fontFamily:"inherit"}}>
              {inWl?"★ Watching":"☆ Watch"}
            </button>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div style={{display:"flex",gap:6,marginBottom:18,flexWrap:"wrap"}}>
        {["overview","recommendation","technical","valuation","capital flow","charts","my position","missing data"].map(t=>(
          <button key={t} onClick={()=>setTab(t)} style={{padding:"8px 18px",borderRadius:8,border:"2px solid",borderColor:tab===t?C.green:C.borderGray,background:tab===t?C.greenLt:"transparent",color:tab===t?C.greenDk:C.muted,fontWeight:700,fontSize:13,cursor:"pointer",fontFamily:"inherit",textTransform:"capitalize",position:"relative"}}>
            {t}{t==="missing data"&&mf.length>0&&<span style={{position:"absolute",top:-6,right:-6,background:C.red,color:"#fff",borderRadius:"50%",width:16,height:16,fontSize:9,fontWeight:800,display:"flex",alignItems:"center",justifyContent:"center"}}>{mf.length}</span>}
          </button>
        ))}
      </div>

      {/* Overview tab */}
      {tab==="overview"&&(
        <div>
          {/* Score breakdown */}
          <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:12,marginBottom:18}}>
            {scoreBreakdown.map(({key,label,icon,desc})=>{
              const val=scores[key]||0,c=sc60(val*6);
              const barW=(val/10)*100;
              return(
                <div key={key} style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:12,padding:"14px 16px",borderTop:"3px solid "+c}}>
                  <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:6}}>
                    <div style={{display:"flex",alignItems:"center",gap:6}}>
                      <span>{icon}</span>
                      <span style={{fontSize:12,fontWeight:700,color:C.text}}>{label}</span>
                    </div>
                    <span style={{fontSize:18,fontWeight:900,color:c}}>{val}<span style={{fontSize:10,color:C.muted}}>/10</span></span>
                  </div>
                  <div style={{background:C.greenLt,borderRadius:4,height:6,marginBottom:6}}>
                    <div style={{width:barW+"%",height:"100%",background:c,borderRadius:4,transition:"width 0.5s"}}/>
                  </div>
                  <div style={{fontSize:10,color:C.muted}}>{desc}</div>
                </div>
              );
            })}
          </div>
          {/* Ratios */}
          <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:12}}>
            <Stat icon="💰" label="EPS"             value={fmt.num(f.eps)}              accent={C.green}/>
            <Stat icon="📚" label="Book Value/Share" value={"KES "+fmt.num(f.bvps)}      accent={C.green}/>
            <Stat icon="📊" label="P/E Ratio"        value={fmt.num(f.pe)}               accent={C.blue}/>
            <Stat icon="📖" label="P/B Ratio"        value={fmt.num(f.pb)}               accent={C.blue}/>
            <Stat icon="📈" label="ROE"              value={fmt.pct(f.roe)}              accent={C.green}/>
            <Stat icon="🎯" label="Profit Margin"    value={fmt.pct(f.margin)}           accent={C.blue}/>
            <Stat icon="⚖️" label="Debt/Equity"      value={fmt.num(f.debt_to_equity)}   accent={C.orange} topBorder={C.orange}/>
            <Stat icon="🛡️" label="Interest Cover"   value={fmt.num(f.interest_coverage)} accent={C.green}/>
            <Stat icon="💵" label="Annual Dividend"  value={"KES "+fmt.num(f.dividends)} accent={C.green}/>
            <Stat icon="📉" label="Div Yield"        value={fmt.pct(f.dividend_yield)}   accent={C.green}/>
            <Stat icon="🏦" label="Total Assets"     value={fmt.bil(f.total_assets)}     accent={C.blue}/>
            <Stat icon="🔖" label="Market Cap"       value={fmt.bil(f.market_cap)}       accent={C.blue}/>
          </div>
        </div>
      )}

      {/* Technical tab — Layer 8 */}
      {tab==="technical"&&(()=>{
        const t=d.technical;
        if(!t||!t.available){
          return <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:12,padding:32,textAlign:"center",color:C.muted,fontSize:14}}>
            {t?.reason||"No technical data available yet — needs more price history."}
          </div>;
        }
        const tsColor = ts=>ts==null?C.muted:ts>=70?C.green:ts>=50?"#86efac":ts>=30?C.yellow:C.red;
        return(
          <div>
            <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:12,marginBottom:18}}>
              <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:12,padding:18,borderTop:"3px solid "+tsColor(t.technical_score?.score)}}>
                <div style={{fontSize:11,color:C.muted,fontWeight:700,marginBottom:6}}>TECHNICAL SCORE</div>
                <div style={{fontSize:28,fontWeight:900,color:tsColor(t.technical_score?.score)}}>{t.technical_score?.score??"—"}<span style={{fontSize:12,color:C.muted}}>/100</span></div>
                <div style={{fontSize:12,color:C.muted,marginTop:4}}>{t.technical_score?.label} · {t.technical_score?.confidence} confidence</div>
              </div>
              <Stat icon="📐" label="Trend" value={t.trend?.direction||"—"} accent={C.blue} sub={t.trend?.sma20?`SMA20: ${fmt.num(t.trend.sma20)}`:undefined}/>
              <Stat icon="📊" label="RSI (14)" value={t.rsi!=null?t.rsi.toFixed(1):"—"} accent={t.rsi>70?C.red:t.rsi<30?C.green:C.blue}/>
            </div>
            <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:12}}>
              <Stat icon="〰️" label="SMA 20"  value={t.trend?.sma20!=null?fmt.num(t.trend.sma20):"—"} accent={C.blue}/>
              <Stat icon="〰️" label="SMA 50"  value={t.trend?.sma50!=null?fmt.num(t.trend.sma50):"—"} accent={C.blue}/>
              <Stat icon="〰️" label="SMA 200" value={t.trend?.sma200!=null?fmt.num(t.trend.sma200):"—"} accent={C.blue}/>
              <Stat icon="🎯" label="ADX (14)" value={t.adx!=null?t.adx.toFixed(1):"—"} accent={C.blue}/>
              <Stat icon="📉" label="MACD" value={t.macd?.macd!=null?t.macd.macd.toFixed(3):"—"} accent={t.macd?.histogram>0?C.green:C.red}/>
              <Stat icon="📐" label="MACD Signal" value={t.macd?.signal!=null?t.macd.signal.toFixed(3):"—"} accent={C.blue}/>
              <Stat icon="📶" label="ATR (14)" value={t.atr!=null?fmt.num(t.atr):"—"} accent={C.orange} sub={t.atr_pct!=null?t.atr_pct.toFixed(1)+"% of price":undefined}/>
              <Stat icon="🧭" label="Support / Resistance" value={t.support_resistance?.support!=null?`${fmt.num(t.support_resistance.support)} / ${fmt.num(t.support_resistance.resistance)}`:"—"} accent={C.muted} topBorder={C.borderGray}/>
            </div>
            {(t.macd?.bullish_cross||t.macd?.bearish_cross)&&(
              <div style={{marginTop:14,padding:"10px 16px",borderRadius:10,fontSize:13,fontWeight:700,
                background:t.macd.bullish_cross?C.greenLt:C.redLt,color:t.macd.bullish_cross?C.greenDk:C.red}}>
                {t.macd.bullish_cross?"🟢 MACD bullish crossover detected":"🔴 MACD bearish crossover detected"}
              </div>
            )}
          </div>
        );
      })()}

      {/* Valuation tab — Layer 6 ext (DCF / DDM / margin of safety) */}
      {tab==="valuation"&&(()=>{
        const v=d.valuation||{};
        const Model=({title,m})=>{
          if(!m||!m.available)return(
            <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:12,padding:18}}>
              <div style={{fontSize:13,fontWeight:700,color:C.text,marginBottom:8}}>{title}</div>
              <div style={{fontSize:12,color:C.muted}}>{m?.reason||"Not available"}</div>
            </div>
          );
          const verdictColor=m.verdict==="Undervalued"?C.green:m.verdict==="Overvalued"?C.red:C.yellow;
          return(
            <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:12,padding:18,borderTop:"3px solid "+(m.verdict?verdictColor:C.borderGray)}}>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:10}}>
                <div style={{fontSize:13,fontWeight:700,color:C.text}}>{title}</div>
                {m.verdict&&<span style={{fontSize:11,fontWeight:800,color:verdictColor,background:verdictColor+"22",borderRadius:8,padding:"3px 10px"}}>{m.verdict}</span>}
              </div>
              <div style={{fontSize:24,fontWeight:900,color:C.text,marginBottom:4}}>KES {fmt.num(m.fair_value_per_share)}</div>
              <div style={{fontSize:12,color:C.muted,marginBottom:10}}>Fair value estimate {m.current_price!=null&&`vs current KES ${fmt.num(m.current_price)}`}</div>
              {m.upside_pct!=null&&<div style={{fontSize:13,fontWeight:700,color:m.upside_pct>=0?C.green:C.red,marginBottom:10}}>{m.upside_pct>=0?"+":""}{m.upside_pct}% {m.upside_pct>=0?"upside":"downside"}</div>}
              {m.assumptions&&(
                <div style={{fontSize:10,color:C.muted,borderTop:"1px solid "+C.borderGray,paddingTop:8,marginTop:8}}>
                  {Object.entries(m.assumptions).map(([k,val])=>(
                    <div key={k}>{k.replace(/_/g," ")}: <b>{typeof val==="number"?val:String(val)}</b></div>
                  ))}
                </div>
              )}
            </div>
          );
        };
        return(
          <div>
            {v.margin_of_safety?.available&&(
              <div style={{background:C.greenBg,border:"1px solid "+C.border,borderRadius:12,padding:18,marginBottom:18,display:"flex",justifyContent:"space-between",alignItems:"center"}}>
                <div>
                  <div style={{fontSize:12,color:C.muted,fontWeight:700}}>MARGIN OF SAFETY (avg of {v.margin_of_safety.models_used} model{v.margin_of_safety.models_used>1?"s":""})</div>
                  <div style={{fontSize:26,fontWeight:900,color:v.margin_of_safety.margin_of_safety_pct>=0?C.green:C.red}}>{v.margin_of_safety.margin_of_safety_pct>=0?"+":""}{v.margin_of_safety.margin_of_safety_pct}%</div>
                </div>
                <div style={{textAlign:"right",fontSize:12,color:C.muted}}>
                  Avg fair value: <b style={{color:C.text}}>KES {fmt.num(v.margin_of_safety.average_fair_value)}</b><br/>
                  Confidence: <b style={{color:C.text}}>{v.margin_of_safety.confidence}</b>
                </div>
              </div>
            )}
            <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"repeat(2,1fr)",gap:18}}>
              <Model title="📐 DCF (Discounted Cash Flow)" m={v.dcf}/>
              <Model title="💵 DDM (Dividend Discount Model)" m={v.ddm}/>
            </div>
            {v.valuation_bands?.available&&(
              <div style={{marginTop:18,background:C.surface,border:"1px solid "+C.borderGray,borderRadius:12,padding:18}}>
                <div style={{fontSize:13,fontWeight:700,color:C.text,marginBottom:10}}>Current Multiples</div>
                <div style={{display:"flex",gap:24,marginBottom:8}}>
                  <div><span style={{fontSize:11,color:C.muted}}>P/E</span><div style={{fontSize:18,fontWeight:800,color:C.text}}>{v.valuation_bands.current_pe??"—"}</div></div>
                  <div><span style={{fontSize:11,color:C.muted}}>P/B</span><div style={{fontSize:18,fontWeight:800,color:C.text}}>{v.valuation_bands.current_pb??"—"}</div></div>
                </div>
                <div style={{fontSize:11,color:C.muted,fontStyle:"italic"}}>{v.valuation_bands.note}</div>
              </div>
            )}
          </div>
        );
      })()}

      {/* Recommendation tab — Layer 10, confidence-first design */}
      {tab==="recommendation"&&(()=>{
        if(recLoading)return<Loader text="Synthesizing recommendation..."/>;
        if(!rec||!rec.available){
          return <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:12,padding:32,textAlign:"center",color:C.muted,fontSize:14}}>
            {rec?.reason||"Not enough data across layers to synthesize a recommendation yet."}
          </div>;
        }
        // Confidence dictates visual weight — a Low-confidence "Strong Buy"
        // must never look as convincing as a High-confidence one. This is
        // a deliberate design constraint, not decoration.
        const confStyle = {
          High:   {bg:C.greenLt, border:C.green, text:C.greenDk, opacity:1,    label:"High confidence"},
          Medium: {bg:"#fef3c7", border:C.gold,  text:C.goldDk,  opacity:0.92, label:"Medium confidence"},
          Low:    {bg:"#f3f4f6", border:C.borderGray, text:C.muted, opacity:0.75, label:"Low confidence — treat as a starting point, not a signal"},
        }[rec.confidence] || {bg:C.surface,border:C.borderGray,text:C.muted,opacity:0.75,label:"Unknown confidence"};

        const verdictColor = rec.recommendation.includes("Buy")?C.green:rec.recommendation==="Hold"?C.yellow:C.red;

        return(
          <div>
            <div style={{background:confStyle.bg,border:"2px solid "+confStyle.border,borderRadius:14,padding:22,marginBottom:18,opacity:confStyle.opacity}}>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:12,flexWrap:"wrap",gap:10}}>
                <div>
                  <div style={{fontSize:26,fontWeight:900,color:verdictColor}}>{rec.recommendation}</div>
                  <div style={{fontSize:13,color:confStyle.text,fontWeight:700,marginTop:2}}>{confStyle.label}</div>
                </div>
                <div style={{textAlign:"right"}}>
                  <div style={{fontSize:24,fontWeight:900,color:C.text}}>{rec.overall_score}/100</div>
                  <div style={{fontSize:11,color:C.muted}}>overall score</div>
                </div>
              </div>

              {/* Coverage bar — always visible, never fine print */}
              <div style={{marginBottom:4}}>
                <div style={{display:"flex",justifyContent:"space-between",fontSize:11,color:C.muted,marginBottom:4}}>
                  <span>Data coverage</span><span>{rec.coverage_pct}% of layers available</span>
                </div>
                <div style={{height:8,borderRadius:4,background:"#e5e7eb",overflow:"hidden"}}>
                  <div style={{height:"100%",width:rec.coverage_pct+"%",background:rec.coverage_pct>=80?C.green:rec.coverage_pct>=50?C.gold:C.red,borderRadius:4}}/>
                </div>
              </div>
              {rec.coverage_pct<80&&(
                <div style={{fontSize:11,color:C.muted,marginTop:8,fontStyle:"italic"}}>
                  ⚠️ This recommendation is missing {Object.entries(rec.component_scores).filter(([k,v])=>v==null).map(([k])=>k).join(", ")} — coverage gap, not a negative signal, but treat this score with proportionally less weight.
                </div>
              )}
            </div>

            {/* Component breakdown */}
            <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"repeat(5,1fr)",gap:10,marginBottom:18}}>
              {Object.entries(rec.component_scores).map(([key,val])=>(
                <div key={key} style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:10,padding:"12px 10px",textAlign:"center"}}>
                  <div style={{fontSize:10,color:C.muted,fontWeight:700,textTransform:"uppercase",marginBottom:4}}>{key.replace("_"," ")}</div>
                  <div style={{fontSize:18,fontWeight:800,color:val==null?C.muted:val>=60?C.green:val>=40?C.gold:C.red}}>{val??"—"}</div>
                  <div style={{fontSize:9,color:C.muted,marginTop:2}}>weight {(rec.component_weights[key]*100).toFixed(0)}%</div>
                </div>
              ))}
            </div>

            {/* Thesis */}
            <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:12,padding:18,marginBottom:14}}>
              <div style={{fontSize:13,fontWeight:700,color:C.text,marginBottom:12}}>Investment Thesis</div>
              {rec.thesis.supporting_evidence?.length>0&&(
                <div style={{marginBottom:12}}>
                  <div style={{fontSize:11,fontWeight:700,color:C.green,marginBottom:6}}>SUPPORTING EVIDENCE</div>
                  {rec.thesis.supporting_evidence.map((s,i)=><div key={i} style={{fontSize:13,color:C.text,marginBottom:4}}>✓ {s}</div>)}
                </div>
              )}
              {rec.thesis.primary_risks?.length>0&&(
                <div style={{marginBottom:12}}>
                  <div style={{fontSize:11,fontWeight:700,color:C.red,marginBottom:6}}>PRIMARY RISKS</div>
                  {rec.thesis.primary_risks.map((s,i)=><div key={i} style={{fontSize:13,color:C.text,marginBottom:4}}>⚠ {s}</div>)}
                </div>
              )}
              {rec.thesis.what_could_invalidate_this?.length>0&&(
                <div>
                  <div style={{fontSize:11,fontWeight:700,color:C.muted,marginBottom:6}}>WHAT COULD INVALIDATE THIS</div>
                  {rec.thesis.what_could_invalidate_this.map((s,i)=><div key={i} style={{fontSize:12,color:C.muted,marginBottom:4,fontStyle:"italic"}}>{s}</div>)}
                </div>
              )}
            </div>

            <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",gap:10,flexWrap:"wrap"}}>
              <div style={{fontSize:10,color:C.muted,fontStyle:"italic",maxWidth:420}}>{rec.methodology_note}</div>
              <button onClick={logRecommendation} disabled={logging} style={{padding:"8px 16px",borderRadius:8,border:"1px solid "+C.green,background:"transparent",color:C.green,fontWeight:700,fontSize:12,cursor:logging?"default":"pointer",fontFamily:"inherit",opacity:logging?0.6:1}}>
                {logging?"Logging...":"📋 Log to Track Record"}
              </button>
            </div>
            <div style={{fontSize:11,color:C.red,marginTop:10,fontWeight:600}}>
              ⚠️ This is a research aid, not financial advice. Verify independently before acting with real capital.
            </div>
          </div>
        );
      })()}

      {/* Capital Flow tab — Layer 7 */}
      {tab==="capital flow"&&(()=>{
        const cf=d.capital_flow;
        if(!cf||!cf.available){
          return(
            <div>
              <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:12,padding:32,textAlign:"center",color:C.muted,fontSize:14,marginBottom:14}}>
                {cf?.reason||"Not available."}
              </div>
              {cf?.unavailable_note&&<div style={{fontSize:12,color:C.muted,fontStyle:"italic",textAlign:"center"}}>{cf.unavailable_note}</div>}
            </div>
          );
        }
        const flowColor=cf.capital_flow_score>=70?C.green:cf.capital_flow_score>=45?C.gold:C.red;
        return(
          <div>
            <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:12,padding:18,marginBottom:18,borderTop:"3px solid "+flowColor}}>
              <div style={{fontSize:11,color:C.muted,fontWeight:700,marginBottom:6}}>CAPITAL FLOW SCORE</div>
              <div style={{fontSize:28,fontWeight:900,color:flowColor}}>{cf.capital_flow_score}<span style={{fontSize:12,color:C.muted}}>/100</span></div>
              <div style={{fontSize:13,color:C.muted,marginTop:4}}>{cf.capital_flow_label}</div>
            </div>
            <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"repeat(2,1fr)",gap:12,marginBottom:14}}>
              <Stat icon="📊" label="OBV Trend" value={cf.obv_trend} accent={cf.obv_trend==="Accumulation"?C.green:C.red} sub={cf.obv_slope_pct_20d!=null?`${cf.obv_slope_pct_20d>=0?"+":""}${cf.obv_slope_pct_20d}% (20d)`:undefined}/>
              <Stat icon="📈" label="A/D Line Trend" value={cf.ad_line_trend} accent={cf.ad_line_trend==="Accumulation"?C.green:C.red}/>
              <Stat icon="🔊" label="Relative Volume" value={cf.relative_volume!=null?cf.relative_volume+"x":"—"} accent={cf.relative_volume>1.2?C.gold:C.blue} sub={cf.relative_volume_note}/>
              <Stat icon={cf.signals_agree?"✅":"⚠️"} label="Signal Agreement" value={cf.signals_agree?"Confirmed":"Mixed"} accent={cf.signals_agree?C.green:C.gold}/>
            </div>
            <div style={{fontSize:11,color:C.muted,fontStyle:"italic",background:"#f9fafb",borderRadius:8,padding:12}}>{cf.unavailable_note}</div>
          </div>
        );
      })()}

      {/* Charts tab */}
      {tab==="charts"&&(
        <div>
          {/* Price chart */}
          <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,padding:22,marginBottom:18,boxShadow:"0 2px 12px #0000000A"}}>
            <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:14}}>
              <div style={{fontSize:13,fontWeight:700,color:C.text}}>Price History</div>
              <div style={{display:"flex",gap:6}}>
                {["1D","1W","1M","3M","1Y"].map(r=>(
                  <button key={r} onClick={()=>setRng(r)} style={{padding:"5px 10px",borderRadius:6,border:"1.5px solid",borderColor:rng===r?C.green:C.borderGray,background:rng===r?C.greenLt:"transparent",color:rng===r?C.greenDk:C.muted,fontWeight:700,fontSize:11,cursor:"pointer",fontFamily:"inherit"}}>{r}</button>
                ))}
              </div>
            </div>
            <LineChart data={cd} height={240}/>
          </div>
          {/* 5-year charts */}
          {hc&&hc.years?.length>0&&(
            <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:18}}>
              {[
                {title:"5-Year Revenue",data:hc.revenue,color:C.blue},
                {title:"5-Year Net Income",data:hc.net_income,color:C.green},
                {title:"5-Year Dividends (DPS)",data:hc.dividends,color:C.gold},
              ].map(({title,data,color})=>(
                <div key={title} style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,padding:18,boxShadow:"0 2px 12px #0000000A"}}>
                  <div style={{fontSize:12,fontWeight:700,color:C.text,marginBottom:10}}>{title}</div>
                  {data&&data.length>0
                    ?<BarChart data={(data||[]).map((v,i)=>({label:hc.years[i]||"",value:v||0}))} height={120} labelKey="label" valueKey="value" color={color}/>
                    :<div style={{height:120,display:"flex",alignItems:"center",justifyContent:"center",color:C.muted,fontSize:12}}>No historical data</div>
                  }
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* My position tab */}
      {tab==="my position"&&(
        <div>
          {pos?(
            <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:12,marginBottom:16}}>
              <Stat icon="🧾" label="Shares Held"   value={pos.quantity?.toLocaleString()} accent={C.green}/>
              <Stat icon="💳" label="Avg Cost"       value={"KES "+fmt.num(pos.avg_cost)}   accent={C.green}/>
              <Stat icon="📍" label="Current Price"  value={"KES "+fmt.num(cur,2)}           accent={C.text} topBorder={C.borderGray}/>
              <Stat icon={pos.realized_pl>=0?"🟢":"🔴"} label="Realised P/L" value={fmt.kes(pos.realized_pl)} accent={pos.realized_pl>=0?C.green:C.red}/>
              <Stat icon="📅" label="Holding Period" value={(pos.holding_days||0)+" days"} accent={C.muted} topBorder={C.borderGray} span={2}/>
              <Stat icon="💰" label="Dividends Received" value={fmt.kes(pos.dividends_received||0)} accent={C.green} span={2}/>
            </div>
          ):(
            <div style={{background:C.greenBg,border:"1px solid "+C.border,borderRadius:12,padding:32,textAlign:"center",color:C.muted,marginBottom:16,fontSize:14}}>No position in {ticker} yet.</div>
          )}
          <div style={{display:"flex",gap:12}}>
            <button onClick={()=>onTrade(d.ticker,"BUY")}  style={{flex:1,padding:14,borderRadius:10,border:"2px solid "+C.green,background:C.greenLt,color:C.greenDk,fontWeight:800,fontSize:15,cursor:"pointer",fontFamily:"inherit"}}>＋ Buy {d.ticker}</button>
            <button onClick={()=>onTrade(d.ticker,"SELL")} style={{flex:1,padding:14,borderRadius:10,border:"2px solid "+C.red,background:C.redLt,color:C.red,fontWeight:800,fontSize:15,cursor:"pointer",fontFamily:"inherit"}}>− Sell {d.ticker}</button>
            <button onClick={()=>onTrade(d.ticker,"DIVIDEND")} style={{flex:1,padding:14,borderRadius:10,border:"2px solid "+C.blue,background:C.blueLt,color:C.blue,fontWeight:800,fontSize:15,cursor:"pointer",fontFamily:"inherit"}}>💰 Log Dividend</button>
          </div>
        </div>
      )}

      {/* Missing data tab */}
      {tab==="missing data"&&(
        <div>
          {mf.length===0?(
            <div style={{background:C.greenLt,border:"1px solid "+C.green,borderRadius:12,padding:24,textAlign:"center",color:C.greenDk,fontSize:14,fontWeight:600}}>✅ All key data fields are present for {ticker}!</div>
          ):(
            <div>
              <div style={{fontSize:13,color:C.muted,marginBottom:16}}>The following fields are missing. Enter values manually to improve the score accuracy.</div>
              <div style={{display:"flex",flexDirection:"column",gap:10}}>
                {mf.map(({field,label})=>(
                  <div key={field} style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:10,padding:"14px 16px",display:"flex",alignItems:"center",gap:12}}>
                    <div style={{flex:1}}>
                      <div style={{fontSize:13,fontWeight:700,color:C.text}}>{label}</div>
                      <div style={{fontSize:11,color:C.muted,marginTop:2}}>Field: <code style={{fontSize:10,background:"#f3f4f6",padding:"1px 5px",borderRadius:4}}>{field}</code></div>
                    </div>
                    <input value={missingForm[field]||""} onChange={e=>setMissingForm(f=>({...f,[field]:e.target.value}))}
                      placeholder="Enter value..." style={{width:160,padding:"8px 10px",borderRadius:7,border:"1px solid "+C.borderGray,fontSize:13,outline:"none",fontFamily:"inherit"}}/>
                    <button onClick={()=>saveMissing(field)} disabled={saving||!missingForm[field]}
                      style={{padding:"8px 16px",borderRadius:7,border:"none",background:missingForm[field]?C.green:"#d1d5db",color:"#fff",fontWeight:700,fontSize:12,cursor:missingForm[field]?"pointer":"not-allowed",fontFamily:"inherit"}}>
                      {saving?"…":"Save"}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// PORTFOLIO
// ══════════════════════════════════════════════════════════════════════════
function Portfolio({portfolio,onAdd,onTrade,onDeletePosition,stocks}){
  const s=portfolio.summary,plPos=(s.unrealized_pl||0)>=0;
  const [risk,setRisk]=useState(null);
  const [riskLoading,setRiskLoading]=useState(true);
  const scoreMap={};
  stocks.forEach(st=>{scoreMap[st.ticker]=st.scores?.total_score||null;});

  useEffect(()=>{
    setRiskLoading(true);
    get("/api/portfolio/risk").then(setRisk).catch(()=>setRisk(null)).finally(()=>setRiskLoading(false));
  },[]);

  // Sector allocation
  const sectorAlloc={};
  portfolio.holdings?.forEach(h=>{
    const st=stocks.find(s=>s.ticker===h.ticker);
    const sec=st?.sector||"Other";
    sectorAlloc[sec]=(sectorAlloc[sec]||0)+h.current_price*h.quantity;
  });
  const totalVal=Object.values(sectorAlloc).reduce((a,b)=>a+b,0)||1;

  return(
    <div>
      {/* Summary */}
      <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"repeat(5,1fr)",gap:14,marginBottom:24}}>
        <Stat icon="💼" label="Total Invested"    value={fmt.kes(s.total_invested)}   accent={C.muted} topBorder={C.borderGray}/>
        <Stat icon="💹" label="Current Value"      value={fmt.kes(s.current_value)}    accent={C.blue}/>
        <Stat icon="📈" label="Unrealised P/L"     value={fmt.kes(s.unrealized_pl)}    accent={plPos?C.green:C.red}/>
        <Stat icon="✅" label="Realised P/L"       value={fmt.kes(s.realized_pl)}      accent={C.green}/>
        <Stat icon="🎯" label="Total Return"       value={fmt.pct(s.return_pct)}       accent={plPos?C.green:C.red}/>
        <Stat icon="📊" label="Annualised Return"  value={fmt.pct(s.annualized_return)} accent={C.blue} topBorder={C.blue}/>
        <Stat icon="💰" label="Dividends YTD"      value={fmt.kes(s.dividends_ytd)}    accent={C.green}/>
        <Stat icon="⭐" label="Avg Portfolio Score" value={s.avg_score!=null?s.avg_score+"/60":"—"} accent={s.avg_score>=40?C.green:s.avg_score>=30?C.yellow:C.orange} topBorder={s.avg_score!=null?sc60(s.avg_score):C.borderGray}/>
        <Stat icon="📁" label="Positions"          value={portfolio.holdings?.length||0} accent={C.muted} topBorder={C.borderGray} span={2}/>
      </div>

      {/* Sector allocation mini chart */}
      {Object.keys(sectorAlloc).length>0&&(
        <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,padding:18,marginBottom:18,boxShadow:"0 2px 12px #0000000A"}}>
          <div style={{fontSize:12,fontWeight:700,color:C.text,marginBottom:12}}>Allocation by Sector</div>
          <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
            {Object.entries(sectorAlloc).map(([sec,val])=>{
              const pct=val/totalVal*100;
              return(
                <div key={sec} style={{flex:"1 1 100px",minWidth:80}}>
                  <div style={{display:"flex",justifyContent:"space-between",fontSize:11,marginBottom:3}}>
                    <span style={{color:C.text,fontWeight:600}}>{sec}</span>
                    <span style={{color:C.muted}}>{pct.toFixed(1)}%</span>
                  </div>
                  <div style={{background:C.greenLt,borderRadius:4,height:6}}>
                    <div style={{width:pct+"%",height:"100%",background:C.green,borderRadius:4}}/>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Risk metrics — Layer 9 / Layer 11 */}
      {!riskLoading&&risk&&(
        <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,padding:18,marginBottom:18,boxShadow:"0 2px 12px #0000000A"}}>
          <div style={{fontSize:12,fontWeight:700,color:C.text,marginBottom:12}}>Risk Metrics</div>
          <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:12,marginBottom:risk.correlation_matrix?.available?16:0}}>
            <Stat icon="📐" label="Sharpe Ratio"
              value={risk.sharpe_ratio?.available?risk.sharpe_ratio.value:"—"}
              sub={risk.sharpe_ratio?.available?risk.sharpe_ratio.interpretation:risk.sharpe_ratio?.reason}
              accent={risk.sharpe_ratio?.value>0.5?C.green:risk.sharpe_ratio?.value>0?C.yellow:C.red}/>
            <Stat icon="📉" label="Sortino Ratio"
              value={risk.sortino_ratio?.available?risk.sortino_ratio.value:"—"}
              sub={risk.sortino_ratio?.available?risk.sortino_ratio.interpretation:risk.sortino_ratio?.reason}
              accent={risk.sortino_ratio?.value>0.75?C.green:risk.sortino_ratio?.value>0?C.yellow:C.red}/>
            <Stat icon="📊" label="Max Drawdown"
              value={risk.max_drawdown?.available?risk.max_drawdown.max_drawdown_pct+"%":"—"}
              sub={risk.max_drawdown?.available?`Current: ${risk.max_drawdown.current_drawdown_pct}%`:risk.max_drawdown?.reason}
              accent={C.red} topBorder={C.red}/>
            <Stat icon="🌐" label="Beta (vs NSE basket)"
              value={(()=>{
                const betas=Object.values(risk.beta_by_holding||{}).filter(b=>b?.available);
                if(!betas.length)return"—";
                const avg=betas.reduce((a,b)=>a+b.value,0)/betas.length;
                return avg.toFixed(2);
              })()}
              sub="Equal-weighted NSE basket proxy — not true NASI beta"
              accent={C.blue}/>
          </div>
          {risk.correlation_matrix?.available&&(
            <div style={{marginTop:8}}>
              <div style={{fontSize:11,color:C.muted,fontWeight:700,marginBottom:8}}>CORRELATION MATRIX</div>
              <div style={{overflowX:"auto"}}>
                <table style={{borderCollapse:"collapse",fontSize:11}}>
                  <thead>
                    <tr>
                      <th style={{padding:"4px 8px"}}></th>
                      {risk.correlation_matrix.tickers.map(t=>(
                        <th key={t} style={{padding:"4px 8px",color:C.muted,fontWeight:700}}>{t.replace(".NR","").replace(".NRO","")}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {risk.correlation_matrix.matrix.map((row,i)=>(
                      <tr key={i}>
                        <td style={{padding:"4px 8px",color:C.muted,fontWeight:700}}>{risk.correlation_matrix.tickers[i].replace(".NR","").replace(".NRO","")}</td>
                        {row.map((val,j)=>{
                          const v=val==null?null:val;
                          const bg=v==null?"transparent":v>=0.7?C.redLt:v>=0.3?"#fef3c7":v>=-0.3?C.greenLt:C.blueLt;
                          return <td key={j} style={{padding:"4px 8px",textAlign:"center",background:bg,borderRadius:4}}>{v!=null?v.toFixed(2):"—"}</td>;
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Holdings table */}
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:12}}>
        <span style={{fontSize:16,fontWeight:700,color:C.text}}>Holdings</span>
        <button onClick={onAdd} style={{padding:"8px 20px",borderRadius:8,border:"2px solid "+C.green,background:C.greenLt,color:C.greenDk,fontWeight:700,fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>+ Add Trade</button>
      </div>
      <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,overflow:"hidden",boxShadow:"0 2px 12px #0000000A"}}>
      <div className="resp-table-wrap" style={{overflowX:"auto"}}>
        <table style={{width:"100%",borderCollapse:"collapse"}}>
          <thead>
            <tr style={{background:C.greenBg,borderBottom:"2px solid "+C.border}}>
              {["Ticker","Qty","Avg Cost","Current Price","Unrealised P/L","Realised P/L","Dividends","Score","Alloc %","Action"].map(h=>(
                <th key={h} style={{padding:"10px 14px",textAlign:"left",fontSize:10,color:C.muted,fontWeight:700,letterSpacing:"0.1em",textTransform:"uppercase",whiteSpace:"nowrap"}}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {!portfolio.holdings?.length
              ?<tr><td colSpan={10} style={{padding:40,textAlign:"center",color:C.muted}}>No holdings yet. Use "+ Add Trade" to log your first position.</td></tr>
              :portfolio.holdings.map(h=>{
                const plH=(h.unrealized_pl||0)>=0;
                const bp=scoreMap[h.ticker]??h.total_score;
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
                    <td style={{padding:"12px 14px",fontWeight:700,fontSize:13,color:C.green}}>{fmt.kes(h.dividends_received)}</td>
                    <td style={{padding:"12px 14px"}}>{bp!=null&&<ScorePill score={Math.round(bp)}/>}</td>
                    <td style={{padding:"12px 14px",color:C.textMid,fontSize:13,fontWeight:600}}>{h.allocation_pct||"—"}%</td>
                    <td style={{padding:"12px 14px"}}>
                      <div style={{display:"flex",gap:4}}>
                        <TradeBtn ticker={h.ticker} type="BUY"  onTrade={onTrade} small/>
                        <TradeBtn ticker={h.ticker} type="SELL" onTrade={onTrade} small/>
                        <button onClick={()=>onDeletePosition(h.ticker)} title="Delete all trades for this ticker"
                          style={{padding:"6px 10px",borderRadius:6,border:"1px solid "+C.red,background:"transparent",color:C.red,fontSize:12,cursor:"pointer",fontFamily:"inherit"}}>
                          🗑
                        </button>
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
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// ANALYTICS
// ══════════════════════════════════════════════════════════════════════════
function Analytics({analytics,stocks}){
  const [accuracy,setAccuracy]=useState(null);
  const [effectiveness,setEffectiveness]=useState(null);
  useEffect(()=>{
    get("/api/recommendations/accuracy").then(setAccuracy).catch(()=>setAccuracy(null));
    get("/api/recommendations/effectiveness").then(setEffectiveness).catch(()=>setEffectiveness(null));
  },[]);
  if(!analytics)return<Loader text="Loading analytics..."/>;
  const {equity_curve:ec,monthly_performance:mp,best_picks:bp,worst_picks:wp,avg_holding_days:ahd,projections:pj}=analytics;

  // Top 5 by score from universe
  const top5Score=[...stocks].sort((a,b)=>(b.scores.total_score||0)-(a.scores.total_score||0)).slice(0,5);

  // Risk distribution by sector
  const sectorScores={};
  stocks.forEach(s=>{
    const sec=s.sector||"Other";
    if(!sectorScores[sec])sectorScores[sec]={total:0,count:0};
    sectorScores[sec].total+=s.scores.total_score||0;
    sectorScores[sec].count++;
  });

  const dl=(data,name)=>{
    if(!data?.length)return;
    const k=Object.keys(data[0]);
    const csv=[k.join(","),...data.map(r=>k.map(x=>r[x]).join(","))].join("\n");
    const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([csv],{type:"text/csv"}));a.download=name;a.click();
  };

  return(
    <div>
      {/* Projections */}
      <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:14,marginBottom:24}}>
        {(pj||[]).map(p=><Stat key={p.years} icon="🔮" label={p.years+"-Year Projection"} value={fmt.kes(p.projected_value)} sub={"@ "+fmt.pct(p.assumed_rate)+" p.a."} accent={C.green} topBorder={C.gold}/>)}
      </div>

      {/* Equity + monthly */}
      <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"2fr 1fr",gap:18,marginBottom:18}}>
        <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,padding:22,boxShadow:"0 2px 12px #0000000A"}}>
          <div style={{fontSize:13,fontWeight:700,color:C.text,marginBottom:14}}>Portfolio Equity Curve</div>
          <LineChart data={(ec||[]).map(x=>({date:x.date,value:x.value}))} height={240}/>
        </div>
        <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,padding:22,boxShadow:"0 2px 12px #0000000A"}}>
          <div style={{fontSize:13,fontWeight:700,color:C.text,marginBottom:4}}>Monthly Returns</div>
          <BarChart data={(mp||[]).map(d=>({label:d.month,value:d.return_pct*100}))} height={240} labelKey="label" valueKey="value"/>
        </div>
      </div>

      {/* Best/worst + top5 + sector risk */}
      <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr 1fr",gap:18,marginBottom:18}}>
        {[{title:"🏆 Best Picks",col:C.green,data:bp,sign:"+"},{title:"📉 Worst Picks",col:C.red,data:wp,sign:""}].map(({title,col,data,sign})=>(
          <div key={title} style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,padding:22,boxShadow:"0 2px 12px #0000000A"}}>
            <div style={{fontSize:10,color:col,textTransform:"uppercase",letterSpacing:"0.1em",fontWeight:700,marginBottom:13}}>{title}</div>
            {(data||[]).map(p=><div key={p.ticker} style={{display:"flex",justifyContent:"space-between",padding:"9px 0",borderBottom:"1px solid "+C.borderGray}}><span style={{color:C.text,fontWeight:700,fontSize:13}}>{p.ticker}</span><span style={{color:col,fontWeight:700,fontSize:13}}>{sign}{fmt.pct(p.return_pct)}</span></div>)}
            {!(data||[]).length&&<div style={{color:C.muted,fontSize:12,padding:"12px 0"}}>No data yet</div>}
          </div>
        ))}
        <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,padding:22,boxShadow:"0 2px 12px #0000000A"}}>
          <div style={{fontSize:10,color:C.green,textTransform:"uppercase",letterSpacing:"0.1em",fontWeight:700,marginBottom:13}}>⭐ Top 5 by Score</div>
          {top5Score.map(s=>(
            <div key={s.ticker} style={{display:"flex",justifyContent:"space-between",padding:"7px 0",borderBottom:"1px solid "+C.borderGray}}>
              <span style={{color:C.text,fontWeight:700,fontSize:13}}>{s.ticker}</span>
              <ScorePill score={s.scores.total_score||0}/>
            </div>
          ))}
        </div>
        <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,padding:22,boxShadow:"0 2px 12px #0000000A"}}>
          <div style={{fontSize:10,color:C.green,textTransform:"uppercase",letterSpacing:"0.1em",fontWeight:700,marginBottom:13}}>🗂 Risk by Sector</div>
          {Object.entries(sectorScores).sort((a,b)=>b[1].total/b[1].count-a[1].total/a[1].count).slice(0,6).map(([sec,v])=>{
            const avg=Math.round(v.total/v.count);
            return(
              <div key={sec} style={{padding:"6px 0",borderBottom:"1px solid "+C.borderGray}}>
                <div style={{display:"flex",justifyContent:"space-between",fontSize:11,marginBottom:3}}>
                  <span style={{color:C.text,fontWeight:600}}>{sec}</span>
                  <span style={{color:sc60(avg),fontWeight:700}}>{avg}/60</span>
                </div>
                <div style={{background:C.greenLt,borderRadius:3,height:4}}>
                  <div style={{width:(avg/60*100)+"%",height:"100%",background:sc60(avg),borderRadius:3}}/>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Exports */}
      <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,padding:22,boxShadow:"0 2px 12px #0000000A"}}>
        <div style={{fontSize:10,color:C.green,textTransform:"uppercase",letterSpacing:"0.1em",fontWeight:700,marginBottom:13}}>⚙️ Stats & Exports</div>
        <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:16}}>
          <div>
            <div style={{display:"flex",justifyContent:"space-between",padding:"9px 0",borderBottom:"1px solid "+C.borderGray,marginBottom:14}}><span style={{color:C.muted}}>Avg Holding Period</span><span style={{color:C.text,fontWeight:700}}>{ahd||"—"} days</span></div>
          </div>
          <div style={{display:"flex",gap:8,flexDirection:"column",gridColumn:"span 2"}}>
            <button onClick={()=>dl(ec,"equity_curve.csv")} style={{padding:"9px 12px",borderRadius:8,border:"1px solid "+C.borderGray,background:C.greenBg,color:C.textMid,fontSize:12,cursor:"pointer",fontFamily:"inherit",textAlign:"left",fontWeight:600}}>↓ Export Equity CSV</button>
            <button onClick={()=>dl(mp,"monthly_returns.csv")} style={{padding:"9px 12px",borderRadius:8,border:"1px solid "+C.borderGray,background:C.greenBg,color:C.textMid,fontSize:12,cursor:"pointer",fontFamily:"inherit",textAlign:"left",fontWeight:600}}>↓ Export Monthly CSV</button>
          </div>
        </div>
      </div>

      {/* Track Record — Layer 12, Continuous Learning */}
      <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,padding:20,boxShadow:"0 2px 12px #0000000A",marginTop:20}}>
        <div style={{fontSize:10,color:C.green,textTransform:"uppercase",letterSpacing:"0.1em",fontWeight:700,marginBottom:13}}>📋 Track Record — Recommendation Accuracy</div>
        {!accuracy?.available?(
          <div style={{color:C.muted,fontSize:13,padding:"12px 0"}}>
            {accuracy?.reason||"No recommendations logged yet."} Use the "Log to Track Record" button on a stock's Recommendation tab to start building history.
            {accuracy?.total_recommendations_logged>0&&<div style={{marginTop:6}}>{accuracy.total_recommendations_logged} recommendation(s) logged, awaiting outcome data.</div>}
          </div>
        ):(
          <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:12,marginBottom:16}}>
            <Stat icon="🎯" label="Buy Hit Rate" value={accuracy.buy_recommendation_hit_rate_pct!=null?accuracy.buy_recommendation_hit_rate_pct+"%":"—"} accent={accuracy.buy_recommendation_hit_rate_pct>50?C.green:C.red}/>
            <Stat icon="📊" label="Avg Return" value={accuracy.avg_return_pct+"%"} accent={accuracy.avg_return_pct>=0?C.green:C.red}/>
            <Stat icon="📈" label="Evaluated" value={accuracy.total_with_outcomes} accent={C.blue} sub={`of ${accuracy.total_recommendations_logged} logged`}/>
            <Stat icon="📐" label="Median Return" value={accuracy.median_return_pct+"%"} accent={accuracy.median_return_pct>=0?C.green:C.red}/>
          </div>
        )}

        {effectiveness&&(
          <div style={{marginTop:8}}>
            <div style={{fontSize:11,fontWeight:700,color:C.muted,marginBottom:8}}>COMPONENT EFFECTIVENESS (feeds adaptive weighting)</div>
            <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"repeat(5,1fr)",gap:8}}>
              {Object.entries(effectiveness.components||{}).map(([key,c])=>(
                <div key={key} style={{border:"1px solid "+C.borderGray,borderRadius:8,padding:"10px 8px",textAlign:"center",opacity:c.reliable?1:0.55}}>
                  <div style={{fontSize:9,color:C.muted,fontWeight:700,textTransform:"uppercase",marginBottom:4}}>{key.replace("_score","").replace("_"," ")}</div>
                  <div style={{fontSize:16,fontWeight:800,color:c.correlation>0.25?C.green:c.correlation<-0.25?C.red:C.muted}}>{c.correlation!=null?c.correlation.toFixed(2):"—"}</div>
                  <div style={{fontSize:9,color:C.muted,marginTop:2}}>{c.reliable?`n=${c.sample_size}`:`need ${c.min_samples_required}+`}</div>
                </div>
              ))}
            </div>
            <div style={{fontSize:10,color:C.muted,marginTop:8,fontStyle:"italic"}}>
              Correlation between each component's score and actual outcome return. Grayed-out components don't have enough evaluated recommendations (min {effectiveness.min_samples_required}) yet to trust — this is intentional, not a bug.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// WATCHLIST PAGE
// ══════════════════════════════════════════════════════════════════════════
function Watchlist({stocks,watchlist,onSelect,onTrade}){
  const watched=stocks.filter(s=>watchlist.includes(s.ticker));
  return(
    <div>
      <div style={{fontSize:16,fontWeight:700,color:C.text,marginBottom:16}}>★ Your Watchlist ({watched.length})</div>
      {!watched.length?(
        <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,padding:48,textAlign:"center",color:C.muted,fontSize:14}}>
          No stocks on watchlist yet.<br/>Open any stock and click "☆ Watch" to add it.
        </div>
      ):(
        <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:14}}>
          {watched.map(s=>{
            const score=s.scores.total_score||0,c=sc60(score);
            const up=s.sparkline?.length>1&&s.sparkline[s.sparkline.length-1]>=s.sparkline[0];
            return(
              <div key={s.ticker} style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,padding:18,boxShadow:"0 2px 12px #0000000A",borderTop:"3px solid "+c}}>
                <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:10}}>
                  <div>
                    <div style={{fontSize:16,fontWeight:800,color:C.text,cursor:"pointer"}} onClick={()=>onSelect(s)}>{s.ticker}</div>
                    <div style={{fontSize:11,color:C.muted}}>{s.name}</div>
                    <div style={{fontSize:10,background:c+"18",color:c,borderRadius:20,padding:"2px 8px",fontWeight:700,marginTop:3,display:"inline-block"}}>{s.sector}</div>
                  </div>
                  <ScorePill score={score}/>
                </div>
                <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:10}}>
                  <div>
                    <div style={{fontSize:18,fontWeight:800,color:C.text}}>KES {s.metrics?.price||"—"}</div>
                    <div style={{fontSize:11,fontWeight:700,color:up?C.green:C.red}}>{up?"▲ Up":"▼ Down"}</div>
                  </div>
                  <Spark data={s.sparkline||[]} w={80} h={32}/>
                </div>
                <div style={{display:"flex",gap:6,fontSize:11,color:C.muted,marginBottom:10}}>
                  <span>P/E {fmt.num(s.metrics?.pe)}</span>
                  <span>·</span>
                  <span>P/B {fmt.num(s.metrics?.pb)}</span>
                  <span>·</span>
                  <span style={{color:C.green,fontWeight:700}}>{fmt.pct(s.metrics?.dividend_yield)} yield</span>
                </div>
                <div style={{display:"flex",gap:6}}>
                  <TradeBtn ticker={s.ticker} type="BUY"  onTrade={onTrade} small/>
                  <TradeBtn ticker={s.ticker} type="SELL" onTrade={onTrade} small/>
                  <button onClick={()=>onSelect(s)} style={{flex:1,padding:"5px 8px",borderRadius:7,border:"1px solid "+C.borderGray,background:"transparent",color:C.muted,fontSize:11,cursor:"pointer",fontFamily:"inherit"}}>Details →</button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}


// ── Data Freshness Screen ───────────────────────────────────────────────────
// ── Data Freshness Screen (CSV Upload) ----------------------------------------
function DataFreshness({onToast, focusTicker=null, focusField=null}){
  const [data, setData]           = useState([]);
  const [loading, setLoading]     = useState(true);
  const [uploadStatus, setUploadStatus] = useState(null);
  const [editRow, setEditRow]     = useState(null);
  const [editVal, setEditVal]     = useState("");
  const [saving, setSaving]       = useState(false);
  const [filter, setFilter]       = useState("all");
  const [uploadingPrice, setUploadingPrice]   = useState(false);
  const [uploadingFund, setUploadingFund]     = useState(false);
  const [uploadResult, setUploadResult]       = useState(null);
  const [updatingAll, setUpdatingAll]         = useState(false);
  const [updateAllResult, setUpdateAllResult] = useState(null);
  const rowRefs = useRef({});

  const handleUpdateAllData = async () => {
    setUpdatingAll(true); setUpdateAllResult(null);
    try{
      const r = await post("/api/data/update-all", {});
      setUpdateAllResult(r);
      const improved = r.fundamentals?.tickers_improved || 0;
      const derived = r.fundamentals?.fields_derived || 0;
      const pricesAdded = r.prices?.total_added || 0;
      onToast(`Update complete: ${pricesAdded} prices refreshed, ${improved} tickers improved, ${derived} fields derived`, "success");
      load();
    }catch(e){
      onToast("Update failed: "+e.message, "error");
    }
    setUpdatingAll(false);
  };


  const load = () => {
    setLoading(true);
    Promise.all([
      get("/api/data-freshness"),
      get("/api/upload/status"),
    ]).then(([d, s]) => {
      setData(d.freshness||[]);
      setUploadStatus(s);
      setLoading(false);
    }).catch(()=>setLoading(false));
  };

  useEffect(()=>{ load(); const iv=setInterval(load,60000); return()=>clearInterval(iv); },[]);

  useEffect(()=>{
    if(focusTicker && data.length>0){
      setTimeout(()=>{
        const el = rowRefs.current[focusTicker];
        if(el){ el.scrollIntoView({behavior:"smooth",block:"center"}); el.style.outline="2px solid "+C.green; setTimeout(()=>{ el.style.outline=""; },2000); }
      }, 200);
    }
  },[focusTicker, data]);

  const downloadTemplate = async (type) => {
    try{
      const a = document.createElement("a");
      a.href = `${API}/api/template/${type}`;
      a.download = `nse_${type}_template.csv`;
      a.click();
    }catch(e){ onToast("Download failed","error"); }
  };

  const handleUploadPrices = async (formData) => {
    setUploadingPrice(true); setUploadResult(null);
    try{
      const r = await fetch(`${API}/api/upload/prices`,{method:"POST",body:formData});
      const d = await r.json();
      if(!r.ok) throw new Error(d.detail||"Upload failed");
      onToast(`Prices uploaded: ${d.updated} tickers updated`,"info");
      setUploadResult({type:"prices",...d});
      load();
    }catch(e){
      onToast(`Price upload failed: ${e.message}`,"error");
      setUploadResult({error:e.message});
    }finally{
      setUploadingPrice(false);
    }
  };

  const handleUploadFundamentals = async (formData) => {
    setUploadingFund(true); setUploadResult(null);
    try{
      const r = await fetch(`${API}/api/upload/fundamentals`,{method:"POST",body:formData});
      const d = await r.json();
      if(!r.ok) throw new Error(d.detail||"Upload failed");
      onToast(`Fundamentals uploaded: ${d.updated} tickers updated`,"info");
      setUploadResult({type:"fundamentals",...d});
      load();
    }catch(e){
      onToast(`Fundamentals upload failed: ${e.message}`,"error");
      setUploadResult({error:e.message});
    }finally{
      setUploadingFund(false);
    }
  };

  const openEdit = (ticker, field, currentVal="") => {
    setEditRow({ticker, field});
    setEditVal(currentVal!=null?String(currentVal):"");
  };

  const saveEdit = async () => {
    if(!editRow || !editVal.trim()) return;
    setSaving(true);
    try{
      const {ticker, field} = editRow;
      if(field==="PRICE"){
        await post("/api/manual-price",{ticker, price: parseFloat(editVal)});
        onToast(`${ticker} price set to KES ${editVal}`,"info");
      } else {
        await post("/api/manual-fundamental",{ticker, field:field.toLowerCase(), value: parseFloat(editVal)});
        onToast(`${ticker} ${field} saved`,"info");
      }
      setEditRow(null); setEditVal(""); load();
    }catch(e){ onToast(`Save failed: ${e.message}`,"error"); }
    setSaving(false);
  };

  const ps = uploadStatus?.prices;
  const fs = uploadStatus?.fundamentals;

  const summary = {
    fresh:  data.filter(d=>d.freshness==="fresh"||d.freshness==="recent").length,
    stale:  data.filter(d=>d.freshness==="stale"||d.freshness==="old").length,
    noData: data.filter(d=>!d.price||d.freshness==="no_data").length,
    issues: data.filter(d=>d.issue_count>0).length,
  };

  const filtered = data.filter(d=>{
    if(filter==="issues") return d.issue_count>0;
    if(filter==="nodata") return !d.price||d.freshness==="no_data";
    if(filter==="no_fund") return !d.has_eps||!d.has_pe||!d.has_roe;
    return true;
  });

  const card = {background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,padding:20,boxShadow:"0 2px 12px #0000000A"};
  const inp  = {padding:"8px 12px",borderRadius:8,border:"1.5px solid "+C.green,fontSize:13,fontFamily:"inherit",outline:"none"};

  return(
    <div>
      {/* ── Update Data button ── */}
      <div style={{...card,marginBottom:20,display:"flex",justifyContent:"space-between",alignItems:"center",flexWrap:"wrap",gap:12}}>
        <div>
          <div style={{fontSize:14,fontWeight:800,color:C.text}}>Update Data</div>
          <div style={{fontSize:11,color:C.muted,marginTop:2,maxWidth:480}}>
            Pulls fresh prices and fundamentals from live sources for every tracked stock, keeps your existing good data wherever live sources have nothing, and fills remaining gaps using safe arithmetic (e.g. margin from net income ÷ revenue) — never invents a number that can't be traced back to something real. Can take up to a minute.
          </div>
        </div>
        <button onClick={handleUpdateAllData} disabled={updatingAll}
          style={{padding:"12px 24px",borderRadius:10,border:"2px solid "+C.green,background:updatingAll?C.greenLt:C.green,color:updatingAll?C.greenDk:"#fff",fontWeight:800,fontSize:13,cursor:updatingAll?"default":"pointer",fontFamily:"inherit",whiteSpace:"nowrap",opacity:updatingAll?0.7:1}}>
          {updatingAll?"⏳ Updating...":"🔄 Update Data"}
        </button>
      </div>
      {updateAllResult&&(
        <div style={{...card,marginBottom:20,fontSize:12,color:C.textMid}}>
          <div style={{fontWeight:700,marginBottom:6,color:C.text}}>Last update result</div>
          <div>Prices: {updateAllResult.prices?.total_added ?? 0} tickers refreshed today, {updateAllResult.prices?.skipped_duplicate?.length ?? 0} already up to date</div>
          <div>Fundamentals: {updateAllResult.fundamentals?.tickers_improved ?? 0} tickers improved, {updateAllResult.fundamentals?.fields_derived ?? 0} fields filled via derivation</div>
          {updateAllResult.fundamentals?.errors?.length>0&&<div style={{color:C.orange,marginTop:4}}>{updateAllResult.fundamentals.errors.length} tickers had a live-fetch issue (existing data preserved, nothing lost)</div>}
        </div>
      )}

      {/* ── Two upload panels ── */}
      <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16,marginBottom:20}}>

        {/* Prices */}
        <div style={{...card,border:"1.5px solid "+C.borderGray}}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:12}}>
            <div>
              <div style={{fontSize:14,fontWeight:800,color:C.text}}>Upload Prices</div>
              <div style={{fontSize:11,color:C.muted,marginTop:2}}>Two columns only: <strong>ticker</strong> and <strong>price</strong>. That is it.</div>
            </div>
            {ps&&(
              <div style={{textAlign:"right",flexShrink:0}}>
                <div style={{fontSize:11,fontWeight:700,color:ps.status==="ok"?C.green:ps.status==="stale"?C.orange:C.red}}>
                  {ps.status==="ok"?"Fresh":ps.status==="stale"?"Stale":"Outdated"}
                </div>
                <div style={{fontSize:10,color:C.muted}}>{ps.ticker_count} stocks, {ps.age_days}d old</div>
              </div>
            )}
          </div>
          <button onClick={()=>downloadTemplate("prices")}
            style={{width:"100%",padding:"8px 0",borderRadius:8,border:"1.5px solid "+C.green,background:"transparent",
              color:C.green,fontWeight:700,fontSize:12,cursor:"pointer",fontFamily:"inherit",marginBottom:10}}>
            Download Template (all stocks pre-loaded, just fill price)
          </button>
          <div
            onDragOver={e=>{e.preventDefault();e.currentTarget.style.background=C.greenBg;}}
            onDragLeave={e=>{e.currentTarget.style.background="#fafafa";}}
            onDrop={e=>{e.preventDefault();e.currentTarget.style.background="#fafafa";
              const fd=new FormData();fd.append("file",e.dataTransfer.files[0]);handleUploadPrices(fd);}}
            onClick={()=>document.getElementById("price-inp").click()}
            style={{border:"2px dashed "+C.borderGray,borderRadius:10,padding:"18px",textAlign:"center",
              cursor:"pointer",background:"#fafafa",transition:"background .15s"}}>
            <div style={{fontSize:12,color:uploadingPrice?C.green:C.muted,fontWeight:600}}>
              {uploadingPrice?"Uploading...":"Drop CSV here or click to browse"}
            </div>
            <input id="price-inp" type="file" accept=".csv" style={{display:"none"}}
              onChange={e=>{const fd=new FormData();fd.append("file",e.target.files[0]);handleUploadPrices(fd);e.target.value="";}}/>
          </div>
          {ps?.last_upload&&ps.last_upload!=="never"&&(
            <div style={{fontSize:10,color:C.dim,marginTop:8}}>
              Last upload: {new Date(ps.last_upload).toLocaleString("en-KE")}
            </div>
          )}
        </div>

        {/* Fundamentals */}
        <div style={{...card,border:"1.5px solid "+C.borderGray}}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:12}}>
            <div>
              <div style={{fontSize:14,fontWeight:800,color:C.text}}>Upload Fundamentals</div>
              <div style={{fontSize:11,color:C.muted,marginTop:2}}>Update quarterly. EPS, PE, ROE, dividends, history.</div>
            </div>
            {fs&&(
              <div style={{textAlign:"right",flexShrink:0}}>
                <div style={{fontSize:11,fontWeight:700,color:fs.status==="ok"?C.green:C.orange}}>
                  {fs.status==="ok"?"Current":"Check age"}
                </div>
                <div style={{fontSize:10,color:C.muted}}>{fs.ticker_count} stocks, {fs.age_days}d old</div>
              </div>
            )}
          </div>
          <button onClick={()=>downloadTemplate("fundamentals")}
            style={{width:"100%",padding:"8px 0",borderRadius:8,border:"1.5px dashed "+C.blue,background:"transparent",
              color:C.blue,fontWeight:700,fontSize:12,cursor:"pointer",fontFamily:"inherit",marginBottom:10}}>
            Download Fundamentals Template (pre-filled)
          </button>
          <div
            onDragOver={e=>{e.preventDefault();e.currentTarget.style.background=C.blueLt;}}
            onDragLeave={e=>{e.currentTarget.style.background="#fafafa";}}
            onDrop={e=>{e.preventDefault();e.currentTarget.style.background="#fafafa";
              const fd=new FormData();fd.append("file",e.dataTransfer.files[0]);handleUploadFundamentals(fd);}}
            onClick={()=>document.getElementById("fund-inp").click()}
            style={{border:"2px dashed "+C.borderGray,borderRadius:10,padding:"18px",textAlign:"center",
              cursor:uploadingFund?"wait":"pointer",background:"#fafafa",transition:"background .15s"}}>
            <div style={{fontSize:20,marginBottom:4}}>{uploadingFund?"...":"+"}</div>
            <div style={{fontSize:12,color:C.muted,fontWeight:600}}>
              {uploadingFund?"Uploading & validating...":"Drop CSV or click to upload"}
            </div>
            <input id="fund-inp" type="file" accept=".csv" style={{display:"none"}}
              onChange={e=>{const fd=new FormData();fd.append("file",e.target.files[0]);handleUploadFundamentals(fd);e.target.value="";}}/>
          </div>
          {fs?.last_upload&&fs.last_upload!=="never"&&(
            <div style={{fontSize:10,color:C.dim,marginTop:8}}>
              Last upload: {new Date(fs.last_upload).toLocaleString("en-KE")}
            </div>
          )}
        </div>
      </div>

      {/* Upload result */}
      {uploadResult&&(
        <div style={{...card,marginBottom:16,background:uploadResult.error?C.redLt:C.greenLt,
          border:"1.5px solid "+(uploadResult.error?C.red:C.green)}}>
          {uploadResult.error?(
            <div style={{color:C.red,fontSize:13,fontWeight:700}}>Upload Error: {uploadResult.error}</div>
          ):(
            <div>
              <div style={{fontSize:13,fontWeight:700,color:C.greenDk,marginBottom:6}}>
                {uploadResult.type==="prices"?"Prices":"Fundamentals"} uploaded: {uploadResult.updated} tickers updated
              </div>
              {uploadResult.errors?.length>0&&(
                <div style={{fontSize:11,color:C.orange,marginBottom:4}}>
                  {uploadResult.errors.length} warnings:
                  {uploadResult.errors.slice(0,5).map((e,i)=><div key={i} style={{marginLeft:8}}>- {e}</div>)}
                  {uploadResult.errors.length>5&&<div style={{marginLeft:8}}>...and {uploadResult.errors.length-5} more</div>}
                </div>
              )}
              <div style={{fontSize:11,color:C.muted}}>Skipped: {uploadResult.skipped||0} | Total in system: {uploadResult.total}</div>
            </div>
          )}
          <button onClick={()=>setUploadResult(null)}
            style={{marginTop:8,fontSize:11,color:C.muted,background:"none",border:"none",cursor:"pointer"}}>dismiss</button>
        </div>
      )}

      {/* Summary cards */}
      <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:12,marginBottom:20}}>
        {[
          {l:"Fresh (< 7d)",  v:summary.fresh,  c:C.green,  f:"all"},
          {l:"Stale (7-14d)", v:summary.stale,  c:C.orange, f:"nodata"},
          {l:"No Price",      v:summary.noData, c:C.red,    f:"nodata"},
          {l:"Has Issues",    v:summary.issues, c:C.red,    f:"issues"},
        ].map(({l,v,c,f})=>(
          <div key={l} onClick={()=>setFilter(f===filter?"all":f)} style={{...card,borderTop:"3px solid "+c,cursor:"pointer",opacity:filter!=="all"&&filter!==f?0.5:1,transition:"opacity .15s"}}>
            <div style={{fontSize:10,color:C.muted,fontWeight:600,textTransform:"uppercase",marginBottom:3}}>{l}</div>
            <div style={{fontSize:28,fontWeight:900,color:c}}>{v}</div>
            <div style={{fontSize:10,color:C.muted}}>click to filter</div>
          </div>
        ))}
      </div>

      {/* Inline edit */}
      {editRow&&(
        <div style={{...card,marginBottom:16,background:"#f0fdf4",border:"2px solid "+C.green}}>
          <div style={{fontSize:13,fontWeight:700,color:C.text,marginBottom:10}}>
            Edit {editRow.field} for <span style={{color:C.green}}>{editRow.ticker}</span>
          </div>
          <div style={{display:"flex",gap:8,alignItems:"center",flexWrap:"wrap"}}>
            <input value={editVal} onChange={e=>setEditVal(e.target.value)}
              onKeyDown={e=>e.key==="Enter"&&saveEdit()}
              placeholder={editRow.field==="PRICE"?"e.g. 75.50":"e.g. 8.5"}
              style={{...inp,width:160}} autoFocus/>
            <div style={{fontSize:11,color:C.muted,flex:1}}>
              {editRow.field==="PRICE"?"Current market price in KES":
               editRow.field==="ROE"?"Decimal e.g. 0.18 = 18%":
               editRow.field==="DIVIDEND_YIELD"?"Decimal e.g. 0.05 = 5%":
               "Value from company annual report"}
            </div>
            <button onClick={saveEdit} disabled={saving||!editVal.trim()}
              style={{padding:"8px 20px",borderRadius:8,border:"none",background:C.green,color:"#fff",fontWeight:700,fontSize:13,cursor:"pointer",fontFamily:"inherit",opacity:saving||!editVal.trim()?0.5:1}}>
              {saving?"Saving...":"Save"}
            </button>
            <button onClick={()=>{setEditRow(null);setEditVal("");}}
              style={{padding:"8px 14px",borderRadius:8,border:"1px solid "+C.borderGray,background:"transparent",color:C.muted,fontSize:12,cursor:"pointer",fontFamily:"inherit"}}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Filter tabs */}
      <div style={{display:"flex",gap:8,marginBottom:14,flexWrap:"wrap"}}>
        {[["all","All Stocks"],["issues","Has Issues"],["nodata","No Price"],["no_fund","Missing Fundamentals"]].map(([v,l])=>(
          <button key={v} onClick={()=>setFilter(v)}
            style={{padding:"6px 14px",borderRadius:20,border:"1.5px solid "+(filter===v?C.green:C.borderGray),background:filter===v?C.greenLt:"transparent",color:filter===v?C.greenDk:C.muted,fontSize:11,fontWeight:filter===v?700:400,cursor:"pointer",fontFamily:"inherit"}}>
            {l}
          </button>
        ))}
        <div style={{flex:1}}/>
        <div style={{fontSize:11,color:C.muted,alignSelf:"center"}}>Showing {filtered.length} of {data.length}</div>
      </div>

      {/* Table */}
      <div style={card}>
        {loading?<Loader text="Loading data status..."/>:(
          <div style={{overflowX:"auto"}}>
            <table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
              <thead>
                <tr style={{background:C.greenBg,borderBottom:"2px solid "+C.border}}>
                  {["Stock","Price","Price Date","Fundamentals","Fund Age","Issues","Quick Edit"].map(h=>(
                    <th key={h} style={{padding:"9px 12px",textAlign:"left",fontSize:10,color:C.muted,fontWeight:700,textTransform:"uppercase",whiteSpace:"nowrap"}}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map(d=>{
                  const hasIssues = d.issue_count>0;
                  const noPrice   = !d.price || d.freshness==="no_data";
                  const freshCol  = d.freshness==="fresh"?C.green:d.freshness==="recent"?"#86efac":d.freshness==="stale"?C.orange:C.red;
                  return(
                    <tr key={d.ticker} ref={el=>rowRefs.current[d.ticker]=el}
                      style={{borderBottom:"1px solid "+C.borderGray,background:noPrice?"#fff1f2":hasIssues?"#fffbeb":C.surface,transition:"background .2s"}}>
                      <td style={{padding:"10px 12px"}}>
                        <div style={{fontWeight:700,color:C.text,fontSize:13}}>{d.ticker}</div>
                        <div style={{fontSize:10,color:C.muted}}>{d.name}</div>
                        <div style={{fontSize:9,color:C.dim}}>{d.sector}</div>
                      </td>
                      <td style={{padding:"10px 12px"}}>
                        <div style={{fontWeight:700,color:noPrice?C.red:C.text,fontSize:13}}>
                          {d.price>0?"KES "+Number(d.price).toLocaleString("en-KE",{minimumFractionDigits:2,maximumFractionDigits:2}):"no data"}
                        </div>
                        <div style={{display:"flex",alignItems:"center",gap:4,marginTop:3}}>
                          <span style={{width:7,height:7,borderRadius:"50%",background:freshCol,display:"inline-block",flexShrink:0}}/>
                          <span style={{fontSize:9,color:freshCol,fontWeight:700}}>{d.freshness||"no_data"}</span>
                        </div>
                      </td>
                      <td style={{padding:"10px 12px"}}>
                        <div style={{fontSize:11,color:d.price_date?C.text:C.dim}}>{d.price_date||"never"}</div>
                        <div style={{fontSize:9,color:C.muted,marginTop:2}}>
                          {d.price_age_h>=9990?"":d.price_age_h<24?d.price_age_h.toFixed(1)+"h ago":(d.price_age_h/24).toFixed(1)+"d ago"}
                        </div>
                      </td>
                      <td style={{padding:"10px 12px"}}>
                        <div style={{display:"flex",gap:4,flexWrap:"wrap"}}>
                          {[["PE",d.has_pe],["EPS",d.has_eps],["ROE",d.has_roe],["BVPS",d.has_bvps],["DIV",d.has_div]].map(([f,ok])=>(
                            <span key={f} onClick={!ok?()=>openEdit(d.ticker,f):undefined}
                              style={{fontSize:9,fontWeight:700,padding:"2px 5px",borderRadius:5,
                                background:ok?C.greenLt:C.redLt,color:ok?C.greenDk:C.red,
                                cursor:ok?"default":"pointer",border:"1px solid "+(ok?C.green+"44":C.red+"44")}}>
                              {ok?"ok":"+"} {f}
                            </span>
                          ))}
                        </div>
                        <div style={{fontSize:9,color:C.muted,marginTop:3}}>
                          {d.fund_source==="manual_csv"?"CSV upload":
                           d.fund_source&&d.fund_source.includes("annual")?"Annual report":
                           d.fund_source&&d.fund_source.includes("seed")?"FY2024 seed":
                           d.fund_source&&d.fund_source.includes("manual")?"Manual entry":
                           d.fund_source||""}
                          {d.fiscal_year?" FY"+d.fiscal_year:""}
                        </div>
                      </td>
                      <td style={{padding:"10px 12px"}}>
                        <span style={{fontSize:11,fontWeight:600,color:d.fund_age_days<90?C.green:d.fund_age_days<180?C.orange:C.red}}>
                          {d.fund_age_days>=9990?"no data":Math.round(d.fund_age_days)+"d old"}
                        </span>
                      </td>
                      <td style={{padding:"10px 12px",maxWidth:200}}>
                        {hasIssues?(
                          <div>
                            {d.issues.slice(0,3).map((iss,i)=>(
                              <div key={i} onClick={()=>openEdit(d.ticker,iss.field)}
                                style={{fontSize:10,color:iss.severity==="critical"?C.red:"#92400e",marginBottom:3,cursor:"pointer",display:"flex",alignItems:"center",gap:4}}>
                                <span>{iss.severity==="critical"?"[!]":"[w]"}</span>
                                <span style={{textDecoration:"underline"}}>{iss.message}</span>
                              </div>
                            ))}
                            {d.issues.length>3&&<div style={{fontSize:9,color:C.muted}}>+{d.issues.length-3} more</div>}
                          </div>
                        ):(
                          <span style={{fontSize:11,color:C.green,fontWeight:600}}>All good</span>
                        )}
                      </td>
                      <td style={{padding:"10px 12px",whiteSpace:"nowrap"}}>
                        <button onClick={()=>openEdit(d.ticker,"PRICE",d.price)}
                          style={{padding:"4px 10px",borderRadius:6,border:"1.5px solid "+C.green,background:"transparent",color:C.green,fontWeight:700,fontSize:10,cursor:"pointer",fontFamily:"inherit",display:"block",marginBottom:4}}>
                          Edit Price
                        </button>
                        <button onClick={()=>openEdit(d.ticker,"PE","")}
                          style={{padding:"4px 10px",borderRadius:6,border:"1.5px solid "+C.blue,background:"transparent",color:C.blue,fontWeight:700,fontSize:10,cursor:"pointer",fontFamily:"inherit",display:"block"}}>
                          Edit P/E
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* How-to */}
      <div style={{...card,marginTop:16,background:"#f8faff",border:"1px solid "+C.blueLt}}>
        <div style={{fontSize:12,fontWeight:700,color:C.blue,marginBottom:10}}>How to update your data</div>
        <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16,fontSize:11,color:C.textMid}}>
          <div style={{background:"#fff",borderRadius:9,padding:14,border:"1px solid "+C.borderGray}}>
            <div style={{fontWeight:700,color:C.green,marginBottom:6}}>Prices — update weekly</div>
            <div style={{marginBottom:3}}>1. Click <strong>Download Price Template</strong> above</div>
            <div style={{marginBottom:3}}>2. Fill in the <em>close</em> column for each stock</div>
            <div style={{marginBottom:3}}>3. open/high/low/volume are optional</div>
            <div style={{marginBottom:6}}>4. Save CSV and upload via drag-drop or click</div>
            <div style={{color:C.muted,fontSize:10}}>Date format: YYYY-MM-DD. Existing history is preserved — no data lost.</div>
          </div>
          <div style={{background:"#fff",borderRadius:9,padding:14,border:"1px solid "+C.borderGray}}>
            <div style={{fontWeight:700,color:C.blue,marginBottom:6}}>Fundamentals — update quarterly</div>
            <div style={{marginBottom:3}}>1. Click <strong>Download Fundamentals Template</strong> above</div>
            <div style={{marginBottom:3}}>2. Template is pre-filled with existing values</div>
            <div style={{marginBottom:3}}>3. Update only the values that have changed</div>
            <div style={{marginBottom:6}}>4. History: semicolon-separated oldest to newest e.g. 50B;60B;70B</div>
            <div style={{color:C.muted,fontSize:10}}>ROE/margin/yield as decimals: 0.18 = 18%. Existing fields preserved if left blank.</div>
          </div>
        </div>
      </div>
    </div>
  );
}


// ══════════════════════════════════════════════════════════════════════════
// MACRO INTELLIGENCE — Layers 1-4 (Global / Country / Sector / Industry)
// ══════════════════════════════════════════════════════════════════════════

function IntelCard({title,children}){
  return(
    <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,padding:18,boxShadow:"0 2px 12px #0000000A"}}>
      <div style={{fontSize:13,fontWeight:700,color:C.text,marginBottom:12}}>{title}</div>
      {children}
    </div>
  );
}

function Unavailable({reason}){
  return <div style={{padding:"16px 0",color:C.muted,fontSize:12,fontStyle:"italic"}}>{reason||"Not available."}</div>;
}

function MacroIntelligence({onToast}){
  const [tab,setTab]=useState("global");
  const [global_,setGlobal]=useState(null);
  const [country,setCountry]=useState(null);
  const [sector,setSector]=useState(null);
  const [loading,setLoading]=useState(true);

  useEffect(()=>{
    setLoading(true);
    Promise.all([
      get("/api/intelligence/global").catch(()=>null),
      get("/api/intelligence/country").catch(()=>null),
      get("/api/intelligence/sector").catch(()=>null),
    ]).then(([g,c,s])=>{setGlobal(g);setCountry(c);setSector(s);}).finally(()=>setLoading(false));
  },[]);

  if(loading)return<Loader text="Loading macro intelligence..."/>;

  return(
    <div>
      <div style={{display:"flex",gap:6,marginBottom:18,flexWrap:"wrap"}}>
        {["global","country","sector"].map(t=>(
          <button key={t} onClick={()=>setTab(t)} style={{padding:"8px 18px",borderRadius:8,border:"2px solid",borderColor:tab===t?C.green:C.borderGray,background:tab===t?C.greenLt:"transparent",color:tab===t?C.greenDk:C.muted,fontWeight:700,fontSize:13,cursor:"pointer",fontFamily:"inherit",textTransform:"capitalize"}}>
            {t==="global"?"🌍 Global":t==="country"?"🏛️ Country":"🏭 Sector"}
          </button>
        ))}
      </div>

      {/* GLOBAL — Layer 1 */}
      {tab==="global"&&(()=>{
        const g=global_;
        if(!g)return <IntelCard title="Global Intelligence"><Unavailable reason="Could not reach the backend."/></IntelCard>;
        return(
          <div>
            {g.data_quality_warning&&(
              <div style={{background:"#fef3c7",border:"1px solid "+C.gold,borderRadius:10,padding:"12px 16px",marginBottom:16,fontSize:12,color:C.goldDk,fontWeight:600}}>
                ⚠️ {g.data_quality_warning}
              </div>
            )}
            <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:12,marginBottom:18}}>
              <Stat icon="📐" label="Economic Regime" value={g.economic_regime} accent={C.blue} span={2}/>
              <Stat icon="⚠️" label="Global Risk Score" value={g.global_risk_score!=null?g.global_risk_score+"/100":"—"}
                accent={g.global_risk_score>60?C.red:g.global_risk_score>35?C.yellow:C.green}
                sub={g.global_risk_score_note} topBorder={g.global_risk_score>60?C.red:undefined}/>
            </div>

            <IntelCard title="FRED Macro Indicators">
              {!g.fred_configured?<Unavailable reason="FRED_API_KEY not set on the server — set it as an environment variable to enable rates/inflation/GDP/PMI data."/>:(
                <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:12}}>
                  {Object.entries(g.indicators||{}).map(([code,ind])=>(
                    <Stat key={code} icon="📊" label={ind.label||code}
                      value={ind.value!=null?ind.value+(ind.units?.includes("%")?"%":""):"—"}
                      sub={ind.yoy_change_pct!=null?`YoY: ${ind.yoy_change_pct>=0?"+":""}${ind.yoy_change_pct}%`:ind.note}
                      accent={C.blue}/>
                  ))}
                </div>
              )}
            </IntelCard>

            <div style={{height:18}}/>
            <IntelCard title="Market Signals (Commodities / VIX / DXY)">
              <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:12}}>
                {Object.entries(g.market_signals||{}).map(([key,m])=>(
                  <Stat key={key} icon="📈" label={key.replace(/_/g," ").toUpperCase()}
                    value={m.value!=null?fmt.num(m.value):"—"}
                    sub={m.change_30d_pct!=null?`30d: ${m.change_30d_pct>=0?"+":""}${m.change_30d_pct}%`:m.note}
                    accent={m.change_30d_pct>=0?C.green:C.red}/>
                ))}
              </div>
            </IntelCard>
          </div>
        );
      })()}

      {/* COUNTRY — Layer 2 */}
      {tab==="country"&&(()=>{
        const c=country;
        if(!c||!c.available)return <IntelCard title="Country Intelligence"><Unavailable reason="Could not reach World Bank data."/></IntelCard>;
        return(
          <div>
            <IntelCard title="Country Ranking">
              <div style={{display:"flex",flexDirection:"column",gap:8}}>
                {c.ranked_by_score?.map((r,i)=>(
                  <div key={r.country_code} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"8px 12px",background:i===0?C.greenLt:"transparent",borderRadius:8}}>
                    <span style={{fontSize:13,fontWeight:700,color:C.text}}>{i+1}. {r.country_name}</span>
                    <span style={{fontSize:14,fontWeight:800,color:sc60(r.score)}}>{r.score}/100</span>
                  </div>
                ))}
              </div>
            </IntelCard>
            <div style={{height:18}}/>
            <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"repeat(2,1fr)",gap:18}}>
              {Object.values(c.countries||{}).map(p=>(
                <IntelCard key={p.country_code} title={`${p.country_name} — ${p.outlook}`}>
                  <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"repeat(2,1fr)",gap:10,marginBottom:10}}>
                    {Object.values(p.indicators||{}).map((ind,i)=>(
                      <div key={i}>
                        <div style={{fontSize:10,color:C.muted}}>{ind.label}</div>
                        <div style={{fontSize:14,fontWeight:700,color:C.text}}>{ind.value!=null?ind.value+"%":"—"}</div>
                      </div>
                    ))}
                  </div>
                  <div style={{fontSize:11,color:C.muted,fontStyle:"italic"}}>{p.note}</div>
                </IntelCard>
              ))}
            </div>
          </div>
        );
      })()}

      {/* SECTOR — Layers 3+4 */}
      {tab==="sector"&&(()=>{
        const s=sector;
        if(!s)return <IntelCard title="Sector Intelligence"><Unavailable reason="Could not reach the backend."/></IntelCard>;
        const gsr=s.global_sector_rotation||{};
        const nse=s.nse_sectors||{};
        return(
          <div>
            <IntelCard title="🌍 Global Sector Rotation (US SPDR ETF proxy)">
              {!gsr.available?<Unavailable reason={gsr.note}/>:(
                <div>
                  <div style={{display:"flex",gap:20,marginBottom:14,fontSize:12}}>
                    <div><b style={{color:C.green}}>Preferred:</b> {gsr.preferred_sectors?.join(", ")}</div>
                    <div><b style={{color:C.red}}>Avoided:</b> {gsr.avoided_sectors?.join(", ")}</div>
                  </div>
                  <div className="stat-grid" style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:10}}>
                    {Object.entries(gsr.sectors||{}).map(([name,d])=>(
                      <div key={name} style={{padding:"10px 12px",border:"1px solid "+C.borderGray,borderRadius:8}}>
                        <div style={{fontSize:11,fontWeight:700,color:C.text}}>{name}</div>
                        {d.available?(
                          <div style={{fontSize:13,fontWeight:800,color:d.momentum_3m_pct>=0?C.green:C.red,marginTop:4}}>
                            {d.momentum_3m_pct>=0?"+":""}{d.momentum_3m_pct}% (3m)
                          </div>
                        ):<div style={{fontSize:11,color:C.muted,marginTop:4}}>No data</div>}
                      </div>
                    ))}
                  </div>
                  <div style={{fontSize:10,color:C.muted,marginTop:10,fontStyle:"italic"}}>{gsr.note}</div>
                </div>
              )}
            </IntelCard>

            <div style={{height:18}}/>
            <IntelCard title="🇰🇪 NSE Sector Momentum (your tracked tickers)">
              {!nse.available?<Unavailable reason={nse.note}/>:(
                <div>
                  <div style={{display:"flex",gap:20,marginBottom:14,fontSize:12}}>
                    <div><b style={{color:C.green}}>Preferred:</b> {nse.preferred_sectors?.join(", ")}</div>
                    <div><b style={{color:C.red}}>Avoided:</b> {nse.avoided_sectors?.join(", ")}</div>
                  </div>
                  <div style={{display:"flex",flexDirection:"column",gap:8}}>
                    {Object.entries(nse.sectors||{}).map(([name,d])=>(
                      <div key={name} style={{padding:"10px 12px",border:"1px solid "+C.borderGray,borderRadius:8}}>
                        <div style={{display:"flex",justifyContent:"space-between"}}>
                          <span style={{fontSize:12,fontWeight:700,color:C.text}}>{name}</span>
                          {d.available?<span style={{fontSize:13,fontWeight:800,color:d.avg_momentum_1m_pct>=0?C.green:C.red}}>{d.avg_momentum_1m_pct>=0?"+":""}{d.avg_momentum_1m_pct}%</span>:<span style={{fontSize:11,color:C.muted}}>No data</span>}
                        </div>
                        {d.available&&d.leaders?.length>0&&(
                          <div style={{fontSize:11,color:C.muted,marginTop:4}}>
                            Leaders: {d.leaders.map(l=>`${l.ticker} (${l.momentum_1m_pct>=0?"+":""}${l.momentum_1m_pct}%)`).join(", ")}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                  <div style={{fontSize:10,color:C.muted,marginTop:10,fontStyle:"italic"}}>{nse.note}</div>
                </div>
              )}
            </IntelCard>
          </div>
        );
      })()}
    </div>
  );
}


// ══════════════════════════════════════════════════════════════════════════
// ROOT APP
// ══════════════════════════════════════════════════════════════════════════
export default function App(){
  const [page,setPage]           = useState("dashboard");
  const [sidebarOpen,setSidebarOpen] = useState(false);
  const [healthAlerts,setHealthAlerts] = useState([]);
  const [showAlerts,setShowAlerts] = useState(false);
  const [focusTicker,setFocusTicker] = useState(null);
  const [focusField,setFocusField]   = useState(null);
  const [stocks,setStocks]       = useState([]);
  const [stocksLoading,setStocksLoading] = useState(true);
  const [sectors,setSectors]     = useState([]);
  const [tickers,setTickers]     = useState([]);
  const [portfolio,setPortfolio] = useState({summary:{total_invested:0,current_value:0,unrealized_pl:0,realized_pl:0,return_pct:0,annualized_return:0,dividends_ytd:0,avg_score:null},holdings:[]});
  const [analytics,setAnalytics] = useState(null);
  const [selected,setSelected]   = useState(null);
  const [modal,setModal]         = useState(null);
  const [toast,setToast]         = useState(null);
  const [live,setLive]           = useState(null);
  const [offline,setOffline]     = useState(false);
  const [watchlist,setWatchlist] = useState([]);

  const showToast=(msg,type="info")=>setToast({msg,type});

  useEffect(()=>{
    get("/api/tickers").then(d=>setTickers(d.tickers||[])).catch(()=>{});
    get("/api/sectors").then(d=>setSectors(d.sectors||[])).catch(()=>{});
    get("/api/watchlist").then(d=>setWatchlist(d.watchlist||[])).catch(()=>{});
    // Load data health alerts
    get("/api/data-health").then(d=>setHealthAlerts(d.alerts||[])).catch(()=>{});
  },[]);

  useEffect(()=>{
    setStocksLoading(true);
    get("/api/stocks")
      .then(d=>{
        if(d.stocks?.length){setStocks(d.stocks);setLive(true);setOffline(false);}
        else{setStocks([]);setLive(false);}
      })
      .catch(()=>{setLive(false);setOffline(true);showToast("Cannot reach backend — check CMD window","error");})
      .finally(()=>setStocksLoading(false));
  },[]);

  useEffect(()=>{
    get("/api/portfolio").then(setPortfolio).catch(()=>{});
  },[]);

  useEffect(()=>{
    if(page==="analytics"&&!analytics)
      get("/api/analytics").then(setAnalytics).catch(()=>{});
  },[page]);

  // Refresh watchlist when navigating to it
  useEffect(()=>{
    if(page==="watchlist")
      get("/api/watchlist").then(d=>setWatchlist(d.watchlist||[])).catch(()=>{});
  },[page]);

  const handleTrade=async(form)=>{
    try{
      const r=await post("/api/trades",{ticker:form.ticker,trade_type:form.trade_type,quantity:parseFloat(form.quantity),price:parseFloat(form.price),date:form.date});
      setPortfolio(r);
      showToast(form.trade_type+" "+form.quantity+" × "+form.ticker+" logged","success");
    }catch(e){showToast("Trade failed: "+e.message,"error");}
    setModal(null);
  };

  const handleDeletePosition=async(ticker)=>{
    if(!window.confirm(`Delete ALL trades for ${ticker}? This cannot be undone.`))return;
    try{
      const r=await del("/api/trades/ticker/"+encodeURIComponent(ticker));
      setPortfolio(r);
      showToast(ticker+" position deleted","success");
    }catch(e){showToast("Delete failed: "+e.message,"error");}
  };

  const goTo=(id)=>{setPage(id);setSelected(null);setSidebarOpen(false);};
  const openStock=useCallback((s)=>{setSelected(s.ticker);setPage("detail");},[]);
  const openTrade=(ticker,type)=>setModal({ticker,type});

  const navItems=[
    {id:"dashboard", icon:"⊞", l:"Dashboard"},
    {id:"screener",  icon:"⟳", l:"Screener"},
    {id:"watchlist", icon:"★", l:"Watchlist"},
    {id:"portfolio", icon:"◈", l:"Portfolio"},
    {id:"analytics", icon:"≋", l:"Analytics"},
    {id:"macro",      icon:"🌍", l:"Macro Intelligence"},
    {id:"freshness",  icon:"📡", l:"Data Status"},
  ];
  const titles={dashboard:"Dashboard",screener:"Stock Screener",watchlist:"Watchlist",portfolio:"My Portfolio",detail:"Stock Detail",analytics:"Analytics",macro:"Macro Intelligence — Global · Country · Sector",freshness:"NSE Data Status & Freshness"};

  return(
    <div style={{display:"flex",minHeight:"100vh",background:C.bg,fontFamily:"'Segoe UI','Inter',system-ui,sans-serif",color:C.text}}>
      <style>{`
        *{box-sizing:border-box;margin:0;padding:0;}
        body{background:${C.bg};overflow-x:hidden;}
        ::-webkit-scrollbar{width:5px;height:5px;}
        ::-webkit-scrollbar-thumb{background:${C.greenLt};border-radius:4px;}
        input,button,select{font-family:inherit;}
        @keyframes spin{to{transform:rotate(360deg);}}
        .sidebar-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:40;}
        @media(max-width:768px){
          .sidebar-desktop{display:none!important;}
          .sidebar-overlay.open{display:block;}
          .sidebar-mobile{display:flex!important;}
          .mobile-topbar-hamburger{display:flex!important;}
          .main-padding{padding:16px 14px!important;}
          .topbar-title{font-size:15px!important;}
          .topbar-pad{padding:10px 14px!important;}
          .log-trade-btn{padding:8px 12px!important;font-size:11px!important;}
          .stat-grid{grid-template-columns:repeat(2,1fr)!important;}
          .resp-table-wrap{overflow-x:auto!important;-webkit-overflow-scrolling:touch;}
        }
        @media(max-width:480px){
          .stat-grid{grid-template-columns:1fr!important;}
        }
        @media(min-width:769px){
          .sidebar-mobile{display:none!important;}
          .mobile-topbar-hamburger{display:none!important;}
          .sidebar-desktop{display:flex!important;}
        }
      `}</style>

      {/* MOBILE OVERLAY — tap to close */}
      <div className={"sidebar-overlay"+(sidebarOpen?" open":"")} onClick={()=>setSidebarOpen(false)}/>

      {/* SIDEBAR — desktop always visible, mobile slides in */}
      <div className="sidebar-desktop" style={{width:234,flexShrink:0,background:"linear-gradient(180deg,"+C.green+","+C.greenDk+")",display:"flex",flexDirection:"column",position:"sticky",top:0,height:"100vh",boxShadow:"2px 0 12px #0000001C"}}>
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

      {/* MOBILE SIDEBAR — slides in from left */}
      <div className="sidebar-mobile" style={{position:"fixed",top:0,left:sidebarOpen?0:"-260px",width:234,height:"100vh",background:"linear-gradient(180deg,"+C.green+","+C.greenDk+")",display:"flex",flexDirection:"column",zIndex:50,transition:"left 0.25s ease",boxShadow:"2px 0 20px #00000030"}}>
        <div style={{padding:"18px 18px 14px",borderBottom:"1px solid #ffffff22",display:"flex",alignItems:"center",justifyContent:"space-between"}}>
          <div style={{display:"flex",alignItems:"center",gap:10}}>
            <img src="/logo.png" alt="" style={{width:38,height:38,borderRadius:"50%",objectFit:"cover",border:"2px solid "+C.gold}} onError={e=>e.target.style.display="none"}/>
            <div>
              <div style={{fontSize:16,fontWeight:900,color:"#fff",lineHeight:1}}>Stock<span style={{color:C.gold}}>Intel</span></div>
              <div style={{fontSize:9,color:"#ffffff90",letterSpacing:"0.1em",textTransform:"uppercase",marginTop:2,fontStyle:"italic"}}>Cut Through Noise</div>
            </div>
          </div>
          <button onClick={()=>setSidebarOpen(false)} style={{background:"none",border:"none",color:"#fff",fontSize:20,cursor:"pointer",padding:"4px 8px",lineHeight:1}}>✕</button>
        </div>
        <nav style={{padding:"12px 10px",flex:1}}>
          {navItems.map(n=>{
            const active=page===n.id||(page==="detail"&&n.id==="screener");
            return(
              <button key={n.id} onClick={()=>goTo(n.id)} style={{width:"100%",display:"flex",alignItems:"center",gap:10,padding:"12px 13px",borderRadius:9,border:"none",background:active?"#ffffff22":"transparent",color:active?C.gold:"#ffffffCC",fontWeight:active?700:400,fontSize:14,cursor:"pointer",marginBottom:2,textAlign:"left",borderLeft:"3px solid "+(active?C.gold:"transparent")}}>
                <span style={{fontSize:17,width:22,textAlign:"center",flexShrink:0}}>{n.icon}</span>{n.l}
              </button>
            );
          })}
        </nav>
        <div style={{padding:"13px 16px",borderTop:"1px solid #ffffff22"}}>
          <div style={{display:"flex",alignItems:"center",gap:8}}>
            <div style={{width:8,height:8,borderRadius:"50%",background:live===null?C.gold:live?"#4ade80":C.red}}/>
            <span style={{fontSize:11,color:"#ffffffBB"}}>{live===null?"Connecting…":live?"🟢 Live":"🔴 Offline"}</span>
          </div>
        </div>
      </div>

      {/* MAIN */}
      <div style={{flex:1,display:"flex",flexDirection:"column",minWidth:0,overflow:"hidden"}}>
        {/* Top bar */}
        <div className="topbar-pad" style={{padding:"13px 28px",borderBottom:"2px solid "+C.border,background:C.surface,display:"flex",alignItems:"center",justifyContent:"space-between",position:"sticky",top:0,zIndex:10,flexShrink:0,boxShadow:"0 1px 6px #0000000C"}}>
          <div style={{display:"flex",alignItems:"center",gap:10}}>
            {/* Hamburger — mobile only */}
            <button className="mobile-topbar-hamburger" onClick={()=>setSidebarOpen(true)} style={{display:"none",background:"none",border:"none",cursor:"pointer",padding:"4px 6px",flexDirection:"column",gap:4,marginRight:4}}>
              <span style={{display:"block",width:20,height:2,background:C.text,borderRadius:2}}/>
              <span style={{display:"block",width:20,height:2,background:C.text,borderRadius:2}}/>
              <span style={{display:"block",width:20,height:2,background:C.text,borderRadius:2}}/>
            </button>
            <div>
              <div className="topbar-title" style={{fontSize:19,fontWeight:800,color:C.text}}>{titles[page]||"Stock Intel"}</div>
              <div style={{fontSize:11,color:C.muted,marginTop:1}}>{new Date().toLocaleDateString("en-KE",{weekday:"long",year:"numeric",month:"long",day:"numeric"})} · NSE</div>
            </div>
          </div>
          <div style={{display:"flex",alignItems:"center",gap:8}}>
            {/* Data health bell */}
            <div style={{position:"relative"}}>
              <button onClick={()=>setShowAlerts(a=>!a)} title="Data Health Alerts"
                style={{padding:"9px 12px",borderRadius:9,border:"1px solid "+C.borderGray,background:C.surface,cursor:"pointer",fontSize:16,position:"relative",display:"flex",alignItems:"center",gap:4}}>
                🔔
                {healthAlerts.filter(a=>a.severity==="critical").length>0&&(
                  <span style={{position:"absolute",top:-4,right:-4,background:C.red,color:"#fff",borderRadius:"50%",width:16,height:16,fontSize:9,fontWeight:900,display:"flex",alignItems:"center",justifyContent:"center"}}>
                    {healthAlerts.filter(a=>a.severity==="critical").length}
                  </span>
                )}
                {healthAlerts.filter(a=>a.severity==="critical").length===0&&healthAlerts.filter(a=>a.severity==="warning").length>0&&(
                  <span style={{position:"absolute",top:-4,right:-4,background:C.orange,color:"#fff",borderRadius:"50%",width:16,height:16,fontSize:9,fontWeight:900,display:"flex",alignItems:"center",justifyContent:"center"}}>
                    {healthAlerts.filter(a=>a.severity==="warning").length}
                  </span>
                )}
              </button>
              {showAlerts&&(
                <div style={{position:"absolute",right:0,top:"110%",width:"min(320px, 88vw)",background:C.surface,border:"1px solid "+C.borderGray,borderRadius:12,boxShadow:"0 8px 32px #00000018",zIndex:100,maxHeight:400,overflowY:"auto"}}>
                  <div style={{padding:"12px 16px",borderBottom:"1px solid "+C.borderGray,display:"flex",justifyContent:"space-between",alignItems:"center"}}>
                    <span style={{fontWeight:700,fontSize:13,color:C.text}}>Data Health Alerts</span>
                    <button onClick={()=>setShowAlerts(false)} style={{background:"none",border:"none",cursor:"pointer",fontSize:16,color:C.muted}}>✕</button>
                  </div>
                  {healthAlerts.length===0?(
                    <div style={{padding:16,fontSize:12,color:C.muted,textAlign:"center"}}>✅ All data looks good</div>
                  ):(
                    healthAlerts.slice(0,20).map((a,i)=>(
                      <div key={i}
                        onClick={()=>{setShowAlerts(false);setFocusTicker(a.ticker);setFocusField(a.field);setPage("freshness");}}
                        style={{padding:"10px 16px",borderBottom:"1px solid "+C.borderGray+"88",
                          background:a.severity==="critical"?C.redLt:a.severity==="warning"?"#fffbeb":C.surface,
                          cursor:"pointer",transition:"filter .1s"}}
                        onMouseEnter={e=>e.currentTarget.style.filter="brightness(0.96)"}
                        onMouseLeave={e=>e.currentTarget.style.filter=""}>
                        <div style={{fontSize:11,fontWeight:700,color:a.severity==="critical"?C.red:a.severity==="warning"?"#92400e":C.text}}>
                          {a.severity==="critical"?"🔴":"🟡"} <strong>{a.ticker}</strong> — {a.message}
                        </div>
                        <div style={{fontSize:10,color:C.muted,marginTop:2}}>→ {a.action} &nbsp;<span style={{color:C.green,fontWeight:700}}>Click to fix ↗</span></div>
                      </div>
                    ))
                  )}
                  <div style={{padding:"10px 16px",borderTop:"1px solid "+C.borderGray}}>
                    <button onClick={()=>{setShowAlerts(false);setFocusTicker(null);setPage("freshness");}} style={{fontSize:11,color:C.green,background:"none",border:"none",cursor:"pointer",fontWeight:700}}>
                      View all on Data Status Page →
                    </button>
                  </div>
                </div>
              )}
            </div>
            <button className="log-trade-btn" onClick={()=>setModal({ticker:"",type:"BUY"})} style={{padding:"10px 22px",borderRadius:9,border:"none",background:"linear-gradient(135deg,"+C.green+","+C.greenDk+")",color:"#fff",fontWeight:800,fontSize:13,cursor:"pointer",letterSpacing:"0.03em",boxShadow:"0 4px 14px "+C.green+"44"}}>
              + Log Trade
            </button>
          </div>
        </div>

        {/* Page content */}
        <div className="main-padding" style={{flex:1,padding:"24px 28px",overflowY:"auto",background:C.bg}}>
          {offline&&<OfflineBanner/>}
          {stocksLoading && (page==="dashboard"||page==="screener"||page==="watchlist") ? (
            <div style={{display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",padding:80,gap:20}}>
              <div style={{width:48,height:48,border:"4px solid "+C.greenLt,borderTopColor:C.green,borderRadius:"50%",animation:"spin 0.8s linear infinite"}}/>
              <div style={{textAlign:"center"}}>
                <div style={{fontSize:15,fontWeight:700,color:C.text,marginBottom:6}}>Loading NSE stocks…</div>
                <div style={{fontSize:12,color:C.muted,maxWidth:280}}>Fetching all 55 tickers. This takes 10–30 seconds on first load.</div>
              </div>
            </div>
          ) : (
            <>
              {page==="dashboard" && <Dashboard  stocks={stocks} portfolio={portfolio} onSelect={openStock} onTrade={openTrade}/>}
              {page==="screener"  && <Screener   stocks={stocks} sectors={sectors}     onSelect={openStock} onTrade={openTrade}/>}
              {page==="watchlist" && <Watchlist  stocks={stocks} watchlist={watchlist}  onSelect={openStock} onTrade={openTrade}/>}
              {page==="portfolio" && <Portfolio  portfolio={portfolio} onAdd={()=>setModal({ticker:"",type:"BUY"})} onTrade={openTrade} onDeletePosition={handleDeletePosition} stocks={stocks}/>}
              {page==="analytics" && <Analytics  analytics={analytics} stocks={stocks}/>}
              {page==="macro"     && <MacroIntelligence onToast={showToast}/>}
              {page==="detail"&&selected && <StockDetail ticker={selected} onBack={()=>setPage("screener")} onTrade={openTrade} tickers={tickers} onToast={showToast}/>}
              {page==="freshness" && <DataFreshness onToast={showToast} focusTicker={focusTicker} focusField={focusField}/>}
            </>
          )}
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
          stocks={stocks}
        />
      )}
      {toast&&<Toast msg={toast.msg} type={toast.type} onClose={()=>setToast(null)}/>}
    </div>
  );
}
