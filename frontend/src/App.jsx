import { useState, useEffect, useCallback, useRef } from "react";

// Works locally (localhost:8000) AND when hosted on Render/Railway
// To deploy: set VITE_API_URL env variable in your hosting dashboard
const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
const get  = (p) => fetch(`${API}${p}`).then(r => { if(!r.ok) throw new Error(r.status); return r.json(); });
const post = (p,b) => fetch(`${API}${p}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)}).then(r=>{ if(!r.ok) throw new Error(r.status); return r.json(); });

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
function TradeModal({tickers=[],preselect="",defaultType="BUY",onClose,onSubmit}){
  const [form,setForm]=useState({ticker:preselect||"",trade_type:defaultType,quantity:"",price:"",date:new Date().toISOString().slice(0,10)});
  const [search,setSearch]=useState(preselect||"");
  const [showDrop,setShowDrop]=useState(false);
  const set=(k,v)=>setForm(f=>({...f,[k]:v}));
  const filtered=tickers.filter(t=>!search||t.ticker.includes(search.toUpperCase())||t.name.toLowerCase().includes(search.toLowerCase())).slice(0,8);
  const selectTicker=(t)=>{set("ticker",t.ticker);setSearch(t.ticker+" — "+t.name);setShowDrop(false);};
  const inp={width:"100%",background:"#f9fafb",border:"1px solid "+C.borderGray,borderRadius:8,padding:"10px 13px",color:C.text,fontSize:14,outline:"none",boxSizing:"border-box",fontFamily:"inherit"};
  return(
    <div style={{position:"fixed",inset:0,background:"#00000066",zIndex:1000,display:"flex",alignItems:"center",justifyContent:"center",padding:16}} onClick={onClose}>
      <div onClick={e=>e.stopPropagation()} style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:16,padding:"24px 24px 28px",width:440,boxShadow:"0 20px 60px #00000022",borderTop:"4px solid "+C.green,maxHeight:"90vh",overflowY:"auto"}}>
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
          <div style={{fontSize:10,color:C.muted,marginBottom:4,textTransform:"uppercase",letterSpacing:"0.08em",fontWeight:600}}>{form.trade_type==="DIVIDEND"?"Dividend per Share (KES)":"Price per Share (KES)"}</div>
          <input type="number" value={form.price} onChange={e=>set("price",e.target.value)} placeholder="e.g. 45.50" style={inp}/>
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
      <div style={{display:"grid",gridTemplateColumns:"repeat(5,1fr)",gap:14,marginBottom:24}}>
        <Stat icon="🏆" label="Top Pick Today"   value={best?.ticker||"—"}       sub={"Score "+(best?.scores?.total_score||"—")+"/60 · KES "+(best?.metrics?.price||"—")} accent={C.green} topBorder={C.gold}/>
        <Stat icon="💼" label="Portfolio Value"  value={fmt.kes(s.current_value)} sub={"Invested "+fmt.kes(s.total_invested)} accent={C.blue}/>
        <Stat icon={plPos?"📈":"📉"} label="Unrealised P/L" value={fmt.kes(s.unrealized_pl)} sub={fmt.pct(s.return_pct)+" return"} accent={plPos?C.green:C.red}/>
        <Stat icon="💰" label="Dividends YTD"    value={fmt.kes(s.dividends_ytd)} accent={C.green}/>
        <Stat icon="📊" label="Stocks Tracked"   value={stocks.length} sub="NSE equities" accent={C.muted} topBorder={C.borderGray}/>
      </div>

      {/* Hero + top scored */}
      <div style={{display:"grid",gridTemplateColumns:"1.2fr 0.8fr",gap:18,marginBottom:18}}>
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
            <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:8,marginBottom:14}}>
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

      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:18}}>
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

  useEffect(()=>{
    setLoading(true);setD(null);
    get("/api/stock/"+encodeURIComponent(ticker)).then(data=>{setD(data);setInWl(data.in_watchlist||false);}).catch(()=>setD(null)).finally(()=>setLoading(false));
  },[ticker]);

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
      <div style={{display:"flex",gap:6,marginBottom:18}}>
        {["overview","charts","my position","missing data"].map(t=>(
          <button key={t} onClick={()=>setTab(t)} style={{padding:"8px 18px",borderRadius:8,border:"2px solid",borderColor:tab===t?C.green:C.borderGray,background:tab===t?C.greenLt:"transparent",color:tab===t?C.greenDk:C.muted,fontWeight:700,fontSize:13,cursor:"pointer",fontFamily:"inherit",textTransform:"capitalize",position:"relative"}}>
            {t}{t==="missing data"&&mf.length>0&&<span style={{position:"absolute",top:-6,right:-6,background:C.red,color:"#fff",borderRadius:"50%",width:16,height:16,fontSize:9,fontWeight:800,display:"flex",alignItems:"center",justifyContent:"center"}}>{mf.length}</span>}
          </button>
        ))}
      </div>

      {/* Overview tab */}
      {tab==="overview"&&(
        <div>
          {/* Score breakdown */}
          <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:12,marginBottom:18}}>
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
          <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:12}}>
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
            <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:18}}>
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
            <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:12,marginBottom:16}}>
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
function Portfolio({portfolio,onAdd,onTrade,stocks}){
  const s=portfolio.summary,plPos=(s.unrealized_pl||0)>=0;
  const scoreMap={};
  stocks.forEach(st=>{scoreMap[st.ticker]=st.scores?.total_score||null;});

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
      <div style={{display:"grid",gridTemplateColumns:"repeat(5,1fr)",gap:14,marginBottom:24}}>
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

      {/* Holdings table */}
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:12}}>
        <span style={{fontSize:16,fontWeight:700,color:C.text}}>Holdings</span>
        <button onClick={onAdd} style={{padding:"8px 20px",borderRadius:8,border:"2px solid "+C.green,background:C.greenLt,color:C.greenDk,fontWeight:700,fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>+ Add Trade</button>
      </div>
      <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,overflow:"hidden",boxShadow:"0 2px 12px #0000000A"}}>
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

// ══════════════════════════════════════════════════════════════════════════
// ANALYTICS
// ══════════════════════════════════════════════════════════════════════════
function Analytics({analytics,stocks}){
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
      <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:14,marginBottom:24}}>
        {(pj||[]).map(p=><Stat key={p.years} icon="🔮" label={p.years+"-Year Projection"} value={fmt.kes(p.projected_value)} sub={"@ "+fmt.pct(p.assumed_rate)+" p.a."} accent={C.green} topBorder={C.gold}/>)}
      </div>

      {/* Equity + monthly */}
      <div style={{display:"grid",gridTemplateColumns:"2fr 1fr",gap:18,marginBottom:18}}>
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
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr 1fr",gap:18,marginBottom:18}}>
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
        <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:16}}>
          <div>
            <div style={{display:"flex",justifyContent:"space-between",padding:"9px 0",borderBottom:"1px solid "+C.borderGray,marginBottom:14}}><span style={{color:C.muted}}>Avg Holding Period</span><span style={{color:C.text,fontWeight:700}}>{ahd||"—"} days</span></div>
          </div>
          <div style={{display:"flex",gap:8,flexDirection:"column",gridColumn:"span 2"}}>
            <button onClick={()=>dl(ec,"equity_curve.csv")} style={{padding:"9px 12px",borderRadius:8,border:"1px solid "+C.borderGray,background:C.greenBg,color:C.textMid,fontSize:12,cursor:"pointer",fontFamily:"inherit",textAlign:"left",fontWeight:600}}>↓ Export Equity CSV</button>
            <button onClick={()=>dl(mp,"monthly_returns.csv")} style={{padding:"9px 12px",borderRadius:8,border:"1px solid "+C.borderGray,background:C.greenBg,color:C.textMid,fontSize:12,cursor:"pointer",fontFamily:"inherit",textAlign:"left",fontWeight:600}}>↓ Export Monthly CSV</button>
          </div>
        </div>
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
        <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:14}}>
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
  const rowRefs = useRef({});

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
    }catch(e){ onToast(`Price upload failed: ${e.message}`,"error"); setUploadResult({error:e.message}); }
    setUploadingPrice(false);
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
    }catch(e){ onToast(`Fundamentals upload failed: ${e.message}`,"error"); setUploadResult({error:e.message}); }
    setUploadingFund(false);
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
      {/* ── Two upload panels ── */}
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16,marginBottom:20}}>

        {/* Prices */}
        <div style={{...card,border:"1.5px solid "+C.borderGray}}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:12}}>
            <div>
              <div style={{fontSize:14,fontWeight:800,color:C.text}}>Upload Prices</div>
              <div style={{fontSize:11,color:C.muted,marginTop:2}}>Update weekly. Only close price is required.</div>
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
            Download Price Template (all stocks)
          </button>
          <div
            onDragOver={e=>{e.preventDefault();e.currentTarget.style.background=C.greenBg;}}
            onDragLeave={e=>{e.currentTarget.style.background="#fafafa";}}
            onDrop={e=>{e.preventDefault();e.currentTarget.style.background="#fafafa";
              const fd=new FormData();fd.append("file",e.dataTransfer.files[0]);handleUploadPrices(fd);}}
            onClick={()=>document.getElementById("price-inp").click()}
            style={{border:"2px dashed "+C.borderGray,borderRadius:10,padding:"18px",textAlign:"center",
              cursor:uploadingPrice?"wait":"pointer",background:"#fafafa",transition:"background .15s"}}>
            <div style={{fontSize:20,marginBottom:4}}>{uploadingPrice?"...":"+"}</div>
            <div style={{fontSize:12,color:C.muted,fontWeight:600}}>
              {uploadingPrice?"Uploading & validating...":"Drop CSV or click to upload"}
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
      <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:12,marginBottom:20}}>
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
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16,fontSize:11,color:C.textMid}}>
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
// GOLD TRADING MODULE
// ══════════════════════════════════════════════════════════════════════════

const GOLD_C = {
  gold:    "#f59e0b", goldLt: "#fef3c7", goldDk: "#d97706",
  bull:    "#49A078", bullLt: "#d1fae5",
  bear:    "#ef4444", bearLt: "#fee2e2",
  wait:    "#6b7280", waitLt: "#f3f4f6",
};

function QualityBadge({quality, color, score}){
  return(
    <span style={{display:"inline-flex",alignItems:"center",gap:6,padding:"4px 14px",borderRadius:20,
      background:color+"22",border:"1.5px solid "+color,color:color,fontWeight:800,fontSize:13}}>
      {quality} <span style={{fontSize:11,opacity:0.8}}>({score}/100)</span>
    </span>
  );
}

function DirectionBadge({direction}){
  const col = direction==="BUY"?GOLD_C.bull:direction==="SELL"?GOLD_C.bear:GOLD_C.wait;
  const bg  = direction==="BUY"?GOLD_C.bullLt:direction==="SELL"?GOLD_C.bearLt:GOLD_C.waitLt;
  const icon= direction==="BUY"?"▲ BUY":direction==="SELL"?"▼ SELL":"◆ WAIT";
  return(
    <span style={{display:"inline-block",padding:"6px 20px",borderRadius:8,background:bg,
      border:"2px solid "+col,color:col,fontWeight:900,fontSize:16,letterSpacing:"0.05em"}}>{icon}</span>
  );
}

function GoldPriceChart({candles=[], height=220}){
  if(candles.length < 2) return <div style={{height,display:"flex",alignItems:"center",justifyContent:"center",color:C.muted,fontSize:13}}>Loading chart…</div>;
  const closes = candles.map(c=>c.close);
  const mn=Math.min(...closes), mx=Math.max(...closes), rng=mx-mn||1;
  const pts=candles.map((c,i)=>`${(i/(candles.length-1))*100},${100-((c.close-mn)/rng)*88-4}`).join(" ");
  const last=closes[closes.length-1], first=closes[0];
  const up=last>=first, col=up?GOLD_C.bull:GOLD_C.bear;
  const ema9pts  = candles.filter(c=>c.ema9).map((c,i)=>`${(i/(candles.length-1))*100},${100-((c.ema9-mn)/rng)*88-4}`).join(" ");
  const ema21pts = candles.filter(c=>c.ema21).map((c,i)=>`${(i/(candles.length-1))*100},${100-((c.ema21-mn)/rng)*88-4}`).join(" ");
  return(
    <div style={{position:"relative"}}>
      <div style={{display:"flex",justifyContent:"space-between",fontSize:10,color:C.muted,marginBottom:4}}>
        <span>${mn.toFixed(2)}</span>
        <span style={{color:GOLD_C.gold,fontWeight:700}}>XAUUSD</span>
        <span>${mx.toFixed(2)}</span>
      </div>
      <svg viewBox="0 0 100 100" style={{width:"100%",height}} preserveAspectRatio="none">
        <defs>
          <linearGradient id="gcg" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={col} stopOpacity="0.25"/>
            <stop offset="100%" stopColor={col} stopOpacity="0"/>
          </linearGradient>
        </defs>
        <polygon points={`${pts} 100,100 0,100`} fill="url(#gcg)"/>
        <polyline points={pts} fill="none" stroke={col} strokeWidth="1.2" strokeLinejoin="round"/>
        {ema9pts&&<polyline points={ema9pts} fill="none" stroke="#3b82f6" strokeWidth="0.6" strokeDasharray="2,1"/>}
        {ema21pts&&<polyline points={ema21pts} fill="none" stroke="#f59e0b" strokeWidth="0.6" strokeDasharray="2,1"/>}
      </svg>
      <div style={{display:"flex",gap:14,fontSize:10,marginTop:4}}>
        <span style={{color:"#3b82f6"}}>— EMA9</span>
        <span style={{color:GOLD_C.gold}}>— EMA21</span>
      </div>
    </div>
  );
}

function BacktestChart({equity=[],height=180}){
  if(equity.length<2)return null;
  const vals=equity.map(e=>e.value);
  const mn=Math.min(...vals),mx=Math.max(...vals),rng=mx-mn||1;
  const pts=equity.map((e,i)=>`${(i/(equity.length-1))*100},${100-((e.value-mn)/rng)*88-4}`).join(" ");
  const up=vals[vals.length-1]>=vals[0];
  const col=up?GOLD_C.bull:GOLD_C.bear;
  return(
    <svg viewBox="0 0 100 100" style={{width:"100%",height}} preserveAspectRatio="none">
      <defs><linearGradient id="btg" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={col} stopOpacity="0.2"/><stop offset="100%" stopColor={col} stopOpacity="0"/></linearGradient></defs>
      <polygon points={`${pts} 100,100 0,100`} fill="url(#btg)"/>
      <polyline points={pts} fill="none" stroke={col} strokeWidth="1.5" strokeLinejoin="round"/>
    </svg>
  );
}

function GoldTrading({onToast}){
  const [tab, setTab]         = useState("signal");
  const [signal, setSignal]   = useState(null);
  const [price, setPrice]     = useState(null);
  const [candles, setCandles] = useState([]);
  const [interval, setInterval] = useState("1h");
  const [loading, setLoading] = useState(true);
  const [sigLoading, setSigLoading] = useState(false);
  const [demoData, setDemoData] = useState({trades:[],performance:{}});
  const [btResult, setBtResult] = useState(null);
  const [btRunning, setBtRunning] = useState(false);
  const [btParams, setBtParams] = useState({
    interval:"1h", start_date:"", end_date:"",
    atr_sl_mult:1.5, atr_tp_mult:4.5, min_score:35
  });
  const [lotSize, setLotSize] = useState("0.1");

  // Live price ticker
  useEffect(()=>{
    const fetchPrice=()=>get("/api/gold/price").then(d=>setPrice(d)).catch(()=>{});
    fetchPrice();
    const iv=setInterval(fetchPrice,15000);
    return()=>clearInterval(iv);
  },[]);

  // Load candles
  useEffect(()=>{
    setLoading(true);
    get(`/api/gold/candles?interval=${interval}&outputsize=200`)
      .then(d=>{setCandles(d.candles||[]);setLoading(false);})
      .catch(()=>setLoading(false));
  },[interval]);

  // Load signal
  const refreshSignal=()=>{
    setSigLoading(true);
    get("/api/gold/signal").then(d=>{setSignal(d);setSigLoading(false);}).catch(()=>setSigLoading(false));
  };
  useEffect(()=>{
    refreshSignal();
    const iv=setInterval(refreshSignal,60000);
    return()=>clearInterval(iv);
  },[]);

  // Load demo trades
  useEffect(()=>{
    if(tab==="demo") get("/api/gold/demo/trades").then(setDemoData).catch(()=>{});
  },[tab]);

  const openDemoTrade=async()=>{
    if(!signal||!signal.entry)return;
    try{
      const r=await post("/api/gold/demo/open",{
        direction:signal.direction, entry:signal.entry,
        sl:signal.sl, tp1:signal.tp1, tp2:signal.tp2,
        score:signal.score, lot_size:parseFloat(lotSize)||0.1,
      });
      setDemoData(r);
      onToast("Demo trade opened — "+signal.direction+" @ $"+signal.entry,"success");
    }catch(e){onToast("Failed to open trade","error");}
  };

  const closeDemoTrade=async(id,result)=>{
    const cp=price?.price||signal?.price||0;
    try{
      const r=await post("/api/gold/demo/close",{trade_id:id,close_price:cp,result});
      setDemoData(r);
      onToast("Trade closed — "+result,"info");
    }catch(e){onToast("Failed to close trade","error");}
  };

  const runBacktest=async()=>{
    setBtRunning(true); setBtResult(null);
    try{
      const r=await post("/api/gold/backtest",btParams);
      setBtResult(r);
      if(r.error) onToast(r.error,"error");
    }catch(e){onToast("Backtest failed","error");}
    setBtRunning(false);
  };

  const setBtp=(k,v)=>setBtParams(p=>({...p,[k]:v}));
  const inp={background:"#f9fafb",border:"1px solid "+C.borderGray,borderRadius:8,padding:"8px 11px",fontSize:13,color:C.text,outline:"none",fontFamily:"inherit",width:"100%",boxSizing:"border-box"};
  const cardStyle={background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,padding:20,boxShadow:"0 2px 12px #0000000A"};

  return(
    <div>
      {/* Live price header */}
      <div style={{...cardStyle,marginBottom:18,borderTop:"4px solid "+GOLD_C.gold}}>
        <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",flexWrap:"wrap",gap:12}}>
          <div style={{display:"flex",alignItems:"center",gap:20}}>
            <div>
              <div style={{fontSize:11,color:C.muted,fontWeight:600,textTransform:"uppercase",letterSpacing:"0.1em"}}>XAUUSD Live Price</div>
              <div style={{fontSize:36,fontWeight:900,color:GOLD_C.gold}}>
                {price?.price?`$${Number(price.price).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2})}`:"Fetching…"}
              </div>
              <div style={{fontSize:11,color:C.muted,marginTop:2}}>Source: {price?.source||"—"} · {price?.time?new Date(price.time).toLocaleTimeString():"—"}</div>
            </div>
            {signal&&signal.direction!=="WAIT"&&(
              <div style={{borderLeft:"2px solid "+C.borderGray,paddingLeft:20}}>
                <DirectionBadge direction={signal.direction}/>
                <div style={{marginTop:8}}>
                  <QualityBadge quality={signal.quality} color={signal.quality_color} score={signal.score}/>
                </div>
              </div>
            )}
          </div>
          <div style={{display:"flex",gap:8}}>
            {["15min","30min","1h","4h","1day"].map(tf=>(
              <button key={tf} onClick={()=>setInterval(tf)} style={{padding:"6px 12px",borderRadius:7,border:"1.5px solid",borderColor:interval===tf?GOLD_C.gold:C.borderGray,background:interval===tf?GOLD_C.goldLt:"transparent",color:interval===tf?GOLD_C.goldDk:C.muted,fontWeight:700,fontSize:11,cursor:"pointer",fontFamily:"inherit"}}>{tf}</button>
            ))}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div style={{display:"flex",gap:6,marginBottom:18}}>
        {[{id:"signal",l:"📡 Signal"},{id:"chart",l:"📈 Chart"},{id:"backtest",l:"🔬 Backtest"},{id:"demo",l:"🎮 Demo Trades"}].map(t=>(
          <button key={t.id} onClick={()=>setTab(t.id)} style={{padding:"9px 20px",borderRadius:9,border:"2px solid",borderColor:tab===t.id?GOLD_C.gold:C.borderGray,background:tab===t.id?GOLD_C.goldLt:"transparent",color:tab===t.id?GOLD_C.goldDk:C.muted,fontWeight:700,fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>{t.l}</button>
        ))}
      </div>

      {/* ── SIGNAL TAB ── */}
      {tab==="signal"&&(
        <div>
          {sigLoading&&!signal&&<Loader text="Analysing market…"/>}
          {signal&&(
            <div style={{display:"grid",gridTemplateColumns:"1.4fr 1fr",gap:18}}>
              {/* Main signal card */}
              <div style={{...cardStyle,borderTop:"4px solid "+(signal.direction==="BUY"?GOLD_C.bull:signal.direction==="SELL"?GOLD_C.bear:GOLD_C.wait)}}>
                <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:16}}>
                  <div>
                    <div style={{fontSize:11,color:C.muted,textTransform:"uppercase",letterSpacing:"0.1em",fontWeight:600,marginBottom:6}}>Current Signal</div>
                    <DirectionBadge direction={signal.direction}/>
                  </div>
                  <div style={{textAlign:"right"}}>
                    <QualityBadge quality={signal.quality||"—"} color={signal.quality_color||C.muted} score={signal.score||0}/>
                    <div style={{fontSize:10,color:C.muted,marginTop:4}}>Generated {signal.generated_at?new Date(signal.generated_at).toLocaleTimeString():"—"}</div>
                  </div>
                </div>

                {signal.entry&&(
                  <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:10,marginBottom:16}}>
                    {[
                      {l:"Entry",v:"$"+signal.entry,c:C.text},
                      {l:"Stop Loss",v:"$"+signal.sl,c:GOLD_C.bear},
                      {l:"TP1 (3:1)",v:"$"+signal.tp1,c:GOLD_C.bull},
                      {l:"TP2 (5:1)",v:"$"+signal.tp2,c:GOLD_C.bull},
                      {l:"Risk (SL dist)",v:"$"+signal.sl_pips,c:C.orange},
                      {l:"R:R",v:signal.rr+"×",c:GOLD_C.gold},
                    ].map(({l,v,c})=>(
                      <div key={l} style={{background:C.greenBg,borderRadius:9,padding:"10px 12px",border:"1px solid "+C.border}}>
                        <div style={{fontSize:10,color:C.muted,fontWeight:600,marginBottom:3}}>{l}</div>
                        <div style={{fontSize:15,fontWeight:800,color:c}}>{v}</div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Reasons */}
                <div style={{marginBottom:12}}>
                  <div style={{fontSize:11,fontWeight:700,color:C.text,marginBottom:8}}>Why this signal fired:</div>
                  {(signal.reasons||[]).map((r,i)=>(
                    <div key={i} style={{fontSize:12,color:GOLD_C.bull,marginBottom:4,display:"flex",alignItems:"flex-start",gap:6}}>
                      <span style={{flexShrink:0}}>✅</span>{r.replace(" ✅","")}
                    </div>
                  ))}
                  {(signal.warnings||[]).map((w,i)=>(
                    <div key={i} style={{fontSize:12,color:C.orange,marginBottom:4,display:"flex",alignItems:"flex-start",gap:6}}>
                      <span style={{flexShrink:0}}>⚠️</span>{w.replace(" ⚠️","")}
                    </div>
                  ))}
                  {!signal.reasons?.length&&!signal.warnings?.length&&(
                    <div style={{fontSize:12,color:C.muted}}>No active signal — {signal.reason||"waiting for setup"}</div>
                  )}
                </div>

                {/* ATR info */}
                <div style={{fontSize:11,color:C.muted,borderTop:"1px solid "+C.borderGray,paddingTop:10}}>
                  ATR(14): ${signal.atr} · Trend: {signal.trend==="bull"?"🟢 Bullish":signal.trend==="bear"?"🔴 Bearish":"⚪ Neutral"}
                </div>

                {/* Demo trade button */}
                {signal.entry&&signal.score>=35&&(
                  <div style={{marginTop:14,display:"flex",gap:10,alignItems:"center"}}>
                    <input value={lotSize} onChange={e=>setLotSize(e.target.value)} type="number" step="0.01" min="0.01"
                      placeholder="Lot size" style={{...inp,width:100}}/>
                    <button onClick={openDemoTrade} style={{flex:1,padding:"10px 0",borderRadius:9,border:"none",
                      background:signal.direction==="BUY"?"linear-gradient(135deg,"+GOLD_C.bull+",#3D8069)":"linear-gradient(135deg,"+GOLD_C.bear+",#b91c1c)",
                      color:"#fff",fontWeight:800,fontSize:14,cursor:"pointer"}}>
                      🎮 Open Demo {signal.direction}
                    </button>
                    <button onClick={refreshSignal} style={{padding:"10px 16px",borderRadius:9,border:"1px solid "+C.borderGray,background:"transparent",color:C.muted,fontSize:12,cursor:"pointer"}}>↻ Refresh</button>
                  </div>
                )}
              </div>

              {/* Indicator panel */}
              <div style={{display:"flex",flexDirection:"column",gap:14}}>
                {/* Indicators */}
                <div style={cardStyle}>
                  <div style={{fontSize:11,fontWeight:700,color:GOLD_C.gold,textTransform:"uppercase",letterSpacing:"0.1em",marginBottom:12}}>📊 Indicators</div>
                  {signal.indicators&&Object.entries({
                    "RSI(14)":      {v:signal.indicators.rsi,     good:v=>v>=40&&v<=60,  fmt:v=>v?.toFixed(1)},
                    "MACD Hist":    {v:signal.indicators.macd_hist,good:v=>v!==0,          fmt:v=>v?.toFixed(4)},
                    "EMA9":         {v:signal.indicators.ema9,    good:()=>true,           fmt:v=>"$"+v?.toFixed(2)},
                    "EMA21":        {v:signal.indicators.ema21,   good:()=>true,           fmt:v=>"$"+v?.toFixed(2)},
                    "EMA50(H4)":    {v:signal.indicators.ema50_h4, good:()=>true,          fmt:v=>"$"+v?.toFixed(2)},
                    "EMA200(H4)":   {v:signal.indicators.ema200_h4,good:()=>true,          fmt:v=>"$"+v?.toFixed(2)},
                  }).map(([name,{v,good,fmt}])=>(
                    <div key={name} style={{display:"flex",justifyContent:"space-between",padding:"7px 0",borderBottom:"1px solid "+C.borderGray}}>
                      <span style={{fontSize:12,color:C.muted}}>{name}</span>
                      <span style={{fontSize:12,fontWeight:700,color:good(v)?GOLD_C.bull:C.text}}>{fmt(v)}</span>
                    </div>
                  ))}
                </div>

                {/* S&R levels */}
                {signal.sr_levels&&(
                  <div style={cardStyle}>
                    <div style={{fontSize:11,fontWeight:700,color:GOLD_C.gold,textTransform:"uppercase",letterSpacing:"0.1em",marginBottom:10}}>🎯 Key Levels</div>
                    <div style={{fontSize:11,color:GOLD_C.bear,fontWeight:600,marginBottom:4}}>Resistance</div>
                    {(signal.sr_levels.resistance||[]).slice(0,3).map((l,i)=>(
                      <div key={i} style={{fontSize:12,color:C.text,padding:"3px 0",borderBottom:"1px dashed "+C.borderGray}}>${l.toFixed(2)}</div>
                    ))}
                    <div style={{fontSize:11,color:GOLD_C.bull,fontWeight:600,marginTop:8,marginBottom:4}}>Support</div>
                    {(signal.sr_levels.support||[]).slice(0,3).map((l,i)=>(
                      <div key={i} style={{fontSize:12,color:C.text,padding:"3px 0",borderBottom:"1px dashed "+C.borderGray}}>${l.toFixed(2)}</div>
                    ))}
                  </div>
                )}

                {/* Fibonacci */}
                {signal.fib_levels&&(
                  <div style={cardStyle}>
                    <div style={{fontSize:11,fontWeight:700,color:GOLD_C.gold,textTransform:"uppercase",letterSpacing:"0.1em",marginBottom:10}}>🌀 Fibonacci</div>
                    {["61%","50%","38%","23%"].map(k=>signal.fib_levels[k]&&(
                      <div key={k} style={{display:"flex",justifyContent:"space-between",padding:"4px 0",borderBottom:"1px dashed "+C.borderGray}}>
                        <span style={{fontSize:11,color:C.muted}}>{k}</span>
                        <span style={{fontSize:12,fontWeight:700,color:C.text}}>${signal.fib_levels[k]?.toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── CHART TAB ── */}
      {tab==="chart"&&(
        <div style={cardStyle}>
          <div style={{fontSize:13,fontWeight:700,color:C.text,marginBottom:16}}>XAUUSD — {interval}</div>
          {loading?<Loader text="Loading candles…"/>:<GoldPriceChart candles={candles.slice(-120)} height={380}/>}
          <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:10,marginTop:16}}>
            {candles.length>0&&[
              {l:"Last Close",v:"$"+(candles[candles.length-1]?.close||0).toFixed(2),c:GOLD_C.gold},
              {l:"RSI(14)",v:(candles[candles.length-1]?.rsi||0).toFixed(1),c:(candles[candles.length-1]?.rsi||50)>70?C.red:(candles[candles.length-1]?.rsi||50)<30?GOLD_C.bull:C.text},
              {l:"ATR(14)",v:"$"+(candles[candles.length-1]?.atr||0).toFixed(2),c:C.text},
              {l:"MACD Hist",v:(candles[candles.length-1]?.macd_hist||0).toFixed(4),c:(candles[candles.length-1]?.macd_hist||0)>0?GOLD_C.bull:GOLD_C.bear},
            ].map(({l,v,c})=>(
              <div key={l} style={{background:C.greenBg,borderRadius:9,padding:"10px 12px",border:"1px solid "+C.border}}>
                <div style={{fontSize:10,color:C.muted,fontWeight:600}}>{l}</div>
                <div style={{fontSize:16,fontWeight:800,color:c}}>{v}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── BACKTEST TAB ── */}
      {tab==="backtest"&&(
        <div>
          {/* Params */}
          <div style={{...cardStyle,marginBottom:18}}>
            <div style={{fontSize:13,fontWeight:700,color:C.text,marginBottom:14}}>🔬 Backtest Parameters</div>
            <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:12,marginBottom:14}}>
              <div>
                <div style={{fontSize:10,color:C.muted,fontWeight:600,marginBottom:4,textTransform:"uppercase"}}>Timeframe</div>
                <select value={btParams.interval} onChange={e=>setBtp("interval",e.target.value)} style={inp}>
                  {["15min","30min","1h","4h","1day"].map(tf=><option key={tf} value={tf}>{tf}</option>)}
                </select>
              </div>
              <div>
                <div style={{fontSize:10,color:C.muted,fontWeight:600,marginBottom:4,textTransform:"uppercase"}}>Start Date</div>
                <input type="date" value={btParams.start_date} onChange={e=>setBtp("start_date",e.target.value)} style={inp}/>
              </div>
              <div>
                <div style={{fontSize:10,color:C.muted,fontWeight:600,marginBottom:4,textTransform:"uppercase"}}>End Date</div>
                <input type="date" value={btParams.end_date} onChange={e=>setBtp("end_date",e.target.value)} style={inp}/>
              </div>
              <div>
                <div style={{fontSize:10,color:C.muted,fontWeight:600,marginBottom:4,textTransform:"uppercase"}}>ATR SL Multiplier</div>
                <input type="number" step="0.1" value={btParams.atr_sl_mult} onChange={e=>setBtp("atr_sl_mult",parseFloat(e.target.value))} style={inp}/>
              </div>
              <div>
                <div style={{fontSize:10,color:C.muted,fontWeight:600,marginBottom:4,textTransform:"uppercase"}}>ATR TP Multiplier (3:1 = SL×3)</div>
                <input type="number" step="0.1" value={btParams.atr_tp_mult} onChange={e=>setBtp("atr_tp_mult",parseFloat(e.target.value))} style={inp}/>
              </div>
              <div>
                <div style={{fontSize:10,color:C.muted,fontWeight:600,marginBottom:4,textTransform:"uppercase"}}>Min Signal Score (0-100)</div>
                <input type="number" step="5" min="0" max="100" value={btParams.min_score} onChange={e=>setBtp("min_score",parseInt(e.target.value))} style={inp}/>
              </div>
            </div>
            <button onClick={runBacktest} disabled={btRunning} style={{width:"100%",padding:13,borderRadius:9,border:"none",
              background:btRunning?"#d1d5db":"linear-gradient(135deg,"+GOLD_C.gold+","+GOLD_C.goldDk+")",
              color:btRunning?C.muted:"#fff",fontWeight:800,fontSize:14,cursor:btRunning?"not-allowed":"pointer"}}>
              {btRunning?"⏳ Running Backtest…":"▶ Run Backtest"}
            </button>
          </div>

          {/* Results */}
          {btResult&&!btResult.error&&(
            <div>
              {/* Stats */}
              <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:14,marginBottom:18}}>
                {[
                  {l:"Total Trades",v:btResult.stats.total_trades,c:C.text,tb:C.borderGray},
                  {l:"Win Rate",v:btResult.stats.win_rate+"%",c:btResult.stats.win_rate>=50?GOLD_C.bull:GOLD_C.bear,tb:btResult.stats.win_rate>=50?GOLD_C.bull:GOLD_C.bear},
                  {l:"Profit Factor",v:btResult.stats.profit_factor,c:btResult.stats.profit_factor>=1.5?GOLD_C.bull:GOLD_C.bear,tb:btResult.stats.profit_factor>=1.5?GOLD_C.bull:GOLD_C.bear},
                  {l:"Total Return",v:btResult.stats.return_pct+"%",c:btResult.stats.return_pct>=0?GOLD_C.bull:GOLD_C.bear,tb:btResult.stats.return_pct>=0?GOLD_C.bull:GOLD_C.bear},
                  {l:"Wins",v:btResult.stats.wins,c:GOLD_C.bull,tb:GOLD_C.bull},
                  {l:"Losses",v:btResult.stats.losses,c:GOLD_C.bear,tb:GOLD_C.bear},
                  {l:"Max Drawdown",v:btResult.stats.max_drawdown+"%",c:btResult.stats.max_drawdown>20?GOLD_C.bear:C.orange,tb:C.orange},
                  {l:"Final Balance",v:"$"+btResult.stats.final_balance.toLocaleString(),c:GOLD_C.gold,tb:GOLD_C.gold},
                ].map(({l,v,c,tb})=>(
                  <div key={l} style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:11,padding:"12px 14px",borderTop:"3px solid "+tb}}>
                    <div style={{fontSize:10,color:C.muted,fontWeight:600,marginBottom:3,textTransform:"uppercase"}}>{l}</div>
                    <div style={{fontSize:18,fontWeight:800,color:c}}>{v}</div>
                  </div>
                ))}
              </div>

              {/* Equity curve */}
              <div style={{...cardStyle,marginBottom:18}}>
                <div style={{fontSize:13,fontWeight:700,color:C.text,marginBottom:12}}>Equity Curve ($10,000 start)</div>
                <BacktestChart equity={btResult.equity_curve} height={200}/>
              </div>

              {/* Trade log */}
              <div style={cardStyle}>
                <div style={{fontSize:13,fontWeight:700,color:C.text,marginBottom:12}}>Trade Log ({btResult.trades.length} trades)</div>
                <div style={{overflowX:"auto"}}>
                  <table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
                    <thead>
                      <tr style={{background:C.greenBg,borderBottom:"2px solid "+C.border}}>
                        {["#","Dir","Entry","SL","TP1","Entry Date","Exit Date","Result","PnL","Score"].map(h=>(
                          <th key={h} style={{padding:"8px 10px",textAlign:"left",fontSize:10,color:C.muted,fontWeight:700,textTransform:"uppercase",whiteSpace:"nowrap"}}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {btResult.trades.map((t,i)=>(
                        <tr key={i} style={{borderBottom:"1px solid "+C.borderGray}}>
                          <td style={{padding:"7px 10px",color:C.dim}}>{i+1}</td>
                          <td style={{padding:"7px 10px",fontWeight:700,color:t.direction==="BUY"?GOLD_C.bull:GOLD_C.bear}}>{t.direction}</td>
                          <td style={{padding:"7px 10px"}}>${t.entry}</td>
                          <td style={{padding:"7px 10px",color:GOLD_C.bear}}>${t.sl}</td>
                          <td style={{padding:"7px 10px",color:GOLD_C.bull}}>${t.tp1}</td>
                          <td style={{padding:"7px 10px",color:C.muted,fontSize:11}}>{t.entry_date?.slice(0,10)}</td>
                          <td style={{padding:"7px 10px",color:C.muted,fontSize:11}}>{t.exit_date?.slice(0,10)||"—"}</td>
                          <td style={{padding:"7px 10px",fontWeight:700,color:t.result==="TP1"?GOLD_C.bull:t.result==="SL"?GOLD_C.bear:C.muted}}>{t.result||"—"}</td>
                          <td style={{padding:"7px 10px",fontWeight:700,color:(t.pnl||0)>=0?GOLD_C.bull:GOLD_C.bear}}>{t.pnl!=null?((t.pnl>=0?"+":"")+"$"+t.pnl.toFixed(2)):"—"}</td>
                          <td style={{padding:"7px 10px"}}><span style={{background:C.greenBg,borderRadius:4,padding:"2px 6px",fontSize:10,fontWeight:700}}>{t.score}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
          {btResult?.error&&<div style={{background:C.redLt,border:"1px solid "+C.red,borderRadius:10,padding:16,color:C.red,fontSize:13}}>{btResult.error}</div>}
        </div>
      )}

      {/* ── DEMO TRADES TAB ── */}
      {tab==="demo"&&(
        <div>
          {/* Performance */}
          <div style={{display:"grid",gridTemplateColumns:"repeat(5,1fr)",gap:14,marginBottom:18}}>
            {[
              {l:"Total Trades",v:demoData.performance?.total_trades||0,c:C.text,tb:C.borderGray},
              {l:"Wins",v:demoData.performance?.wins||0,c:GOLD_C.bull,tb:GOLD_C.bull},
              {l:"Losses",v:demoData.performance?.losses||0,c:GOLD_C.bear,tb:GOLD_C.bear},
              {l:"Win Rate",v:(demoData.performance?.win_rate||0)+"%",c:(demoData.performance?.win_rate||0)>=50?GOLD_C.bull:GOLD_C.bear,tb:(demoData.performance?.win_rate||0)>=50?GOLD_C.bull:GOLD_C.bear},
              {l:"Total PnL",v:"$"+(demoData.performance?.total_pnl||0).toFixed(2),c:(demoData.performance?.total_pnl||0)>=0?GOLD_C.bull:GOLD_C.bear,tb:GOLD_C.gold},
            ].map(({l,v,c,tb})=>(
              <div key={l} style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:11,padding:"12px 14px",borderTop:"3px solid "+tb}}>
                <div style={{fontSize:10,color:C.muted,fontWeight:600,marginBottom:3,textTransform:"uppercase"}}>{l}</div>
                <div style={{fontSize:18,fontWeight:800,color:c}}>{v}</div>
              </div>
            ))}
          </div>

          {/* Open trades */}
          {(demoData.performance?.open_trades||[]).length>0&&(
            <div style={{...cardStyle,marginBottom:18}}>
              <div style={{fontSize:13,fontWeight:700,color:C.text,marginBottom:12}}>Open Demo Trades</div>
              {(demoData.performance.open_trades||[]).map(t=>(
                <div key={t.id} style={{display:"flex",alignItems:"center",gap:12,padding:"12px 0",borderBottom:"1px solid "+C.borderGray,flexWrap:"wrap"}}>
                  <DirectionBadge direction={t.direction}/>
                  <div style={{flex:1}}>
                    <div style={{fontSize:13,fontWeight:700}}>Entry: ${t.entry} &nbsp;|&nbsp; SL: <span style={{color:GOLD_C.bear}}>${t.sl}</span> &nbsp;|&nbsp; TP1: <span style={{color:GOLD_C.bull}}>${t.tp1}</span></div>
                    <div style={{fontSize:11,color:C.muted}}>{new Date(t.open_date).toLocaleString()} · Lot: {t.lot_size} · Score: {t.score}</div>
                  </div>
                  <div style={{display:"flex",gap:8}}>
                    <button onClick={()=>closeDemoTrade(t.id,"TP1")} style={{padding:"7px 14px",borderRadius:7,border:"2px solid "+GOLD_C.bull,background:GOLD_C.bullLt,color:GOLD_C.bull,fontWeight:700,fontSize:12,cursor:"pointer"}}>✅ TP Hit</button>
                    <button onClick={()=>closeDemoTrade(t.id,"SL")} style={{padding:"7px 14px",borderRadius:7,border:"2px solid "+GOLD_C.bear,background:GOLD_C.bearLt,color:GOLD_C.bear,fontWeight:700,fontSize:12,cursor:"pointer"}}>❌ SL Hit</button>
                    <button onClick={()=>closeDemoTrade(t.id,"MANUAL")} style={{padding:"7px 14px",borderRadius:7,border:"1px solid "+C.borderGray,background:"transparent",color:C.muted,fontSize:12,cursor:"pointer"}}>Close</button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Trade history */}
          <div style={cardStyle}>
            <div style={{fontSize:13,fontWeight:700,color:C.text,marginBottom:12}}>Trade History</div>
            {!(demoData.trades||[]).filter(t=>t.status==="CLOSED").length?(
              <div style={{color:C.muted,fontSize:13,padding:"24px 0",textAlign:"center"}}>No closed trades yet. Open a demo trade from the Signal tab.</div>
            ):(
              <table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
                <thead>
                  <tr style={{background:C.greenBg,borderBottom:"2px solid "+C.border}}>
                    {["Dir","Entry","Close","Open Date","Result","PnL","Score"].map(h=>(
                      <th key={h} style={{padding:"8px 12px",textAlign:"left",fontSize:10,color:C.muted,fontWeight:700,textTransform:"uppercase"}}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(demoData.trades||[]).filter(t=>t.status==="CLOSED").reverse().map(t=>(
                    <tr key={t.id} style={{borderBottom:"1px solid "+C.borderGray}}>
                      <td style={{padding:"8px 12px",fontWeight:700,color:t.direction==="BUY"?GOLD_C.bull:GOLD_C.bear}}>{t.direction}</td>
                      <td style={{padding:"8px 12px"}}>${t.entry}</td>
                      <td style={{padding:"8px 12px"}}>${t.close_price}</td>
                      <td style={{padding:"8px 12px",color:C.muted,fontSize:11}}>{new Date(t.open_date).toLocaleDateString()}</td>
                      <td style={{padding:"8px 12px",fontWeight:700,color:t.result==="TP1"?GOLD_C.bull:GOLD_C.bear}}>{t.result}</td>
                      <td style={{padding:"8px 12px",fontWeight:700,color:(t.pnl||0)>=0?GOLD_C.bull:GOLD_C.bear}}>{t.pnl!=null?((t.pnl>=0?"+":"")+"$"+t.pnl.toFixed(2)):"—"}</td>
                      <td style={{padding:"8px 12px"}}><span style={{background:C.greenBg,borderRadius:4,padding:"2px 6px",fontSize:10,fontWeight:700}}>{t.score}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
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
    get("/api/stocks")
      .then(d=>{
        if(d.stocks?.length){setStocks(d.stocks);setLive(true);setOffline(false);}
        else{setStocks([]);setLive(false);}
      })
      .catch(()=>{setLive(false);setOffline(true);showToast("Cannot reach backend — check CMD window","error");});
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

  const goTo=(id)=>{setPage(id);setSelected(null);setSidebarOpen(false);};
  const openStock=useCallback((s)=>{setSelected(s.ticker);setPage("detail");},[]);
  const openTrade=(ticker,type)=>setModal({ticker,type});

  const navItems=[
    {id:"dashboard", icon:"⊞", l:"Dashboard"},
    {id:"screener",  icon:"⟳", l:"Screener"},
    {id:"watchlist", icon:"★", l:"Watchlist"},
    {id:"portfolio", icon:"◈", l:"Portfolio"},
    {id:"analytics", icon:"≋", l:"Analytics"},
    {id:"gold",      icon:"🥇", l:"Gold Trading"},
    {id:"freshness",  icon:"📡", l:"Data Status"},
  ];
  const titles={dashboard:"Dashboard",screener:"Stock Screener",watchlist:"Watchlist",portfolio:"My Portfolio",detail:"Stock Detail",analytics:"Analytics",gold:"Gold Trading — XAUUSD",freshness:"NSE Data Status & Freshness"};

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
                <div style={{position:"absolute",right:0,top:"110%",width:320,background:C.surface,border:"1px solid "+C.borderGray,borderRadius:12,boxShadow:"0 8px 32px #00000018",zIndex:100,maxHeight:400,overflowY:"auto"}}>
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
          {page==="dashboard" && <Dashboard  stocks={stocks} portfolio={portfolio} onSelect={openStock} onTrade={openTrade}/>}
          {page==="screener"  && <Screener   stocks={stocks} sectors={sectors}     onSelect={openStock} onTrade={openTrade}/>}
          {page==="watchlist" && <Watchlist  stocks={stocks} watchlist={watchlist}  onSelect={openStock} onTrade={openTrade}/>}
          {page==="portfolio" && <Portfolio  portfolio={portfolio} onAdd={()=>setModal({ticker:"",type:"BUY"})} onTrade={openTrade} stocks={stocks}/>}
          {page==="analytics" && <Analytics  analytics={analytics} stocks={stocks}/>}
          {page==="detail"&&selected && <StockDetail ticker={selected} onBack={()=>setPage("screener")} onTrade={openTrade} tickers={tickers} onToast={showToast}/>}
          {page==="gold"      && <GoldTrading onToast={showToast}/>}
          {page==="freshness" && <DataFreshness onToast={showToast} focusTicker={focusTicker} focusField={focusField}/>}
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
