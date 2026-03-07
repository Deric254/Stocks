import { useState, useEffect, useCallback, useRef } from "react";

const API = "http://localhost:8000";
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

// ══════════════════════════════════════════════════════════════════════════
// ROOT APP
// ══════════════════════════════════════════════════════════════════════════
export default function App(){
  const [page,setPage]           = useState("dashboard");
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

  const goTo=(id)=>{setPage(id);setSelected(null);};
  const openStock=useCallback((s)=>{setSelected(s.ticker);setPage("detail");},[]);
  const openTrade=(ticker,type)=>setModal({ticker,type});

  const navItems=[
    {id:"dashboard", icon:"⊞", l:"Dashboard"},
    {id:"screener",  icon:"⟳", l:"Screener"},
    {id:"watchlist", icon:"★", l:"Watchlist"},
    {id:"portfolio", icon:"◈", l:"Portfolio"},
    {id:"analytics", icon:"≋", l:"Analytics"},
  ];
  const titles={dashboard:"Dashboard",screener:"Stock Screener",watchlist:"Watchlist",portfolio:"My Portfolio",detail:"Stock Detail",analytics:"Analytics"};

  return(
    <div style={{display:"flex",minHeight:"100vh",background:C.bg,fontFamily:"'Segoe UI','Inter',system-ui,sans-serif",color:C.text}}>
      <style>{`
        *{box-sizing:border-box;margin:0;padding:0;}
        body{background:${C.bg};overflow-x:hidden;}
        ::-webkit-scrollbar{width:5px;height:5px;}
        ::-webkit-scrollbar-thumb{background:${C.greenLt};border-radius:4px;}
        input,button,select{font-family:inherit;}
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

        {/* Page content */}
        <div style={{flex:1,padding:"24px 28px",overflowY:"auto",background:C.bg}}>
          {offline&&<OfflineBanner/>}
          {page==="dashboard" && <Dashboard  stocks={stocks} portfolio={portfolio} onSelect={openStock} onTrade={openTrade}/>}
          {page==="screener"  && <Screener   stocks={stocks} sectors={sectors}     onSelect={openStock} onTrade={openTrade}/>}
          {page==="watchlist" && <Watchlist  stocks={stocks} watchlist={watchlist}  onSelect={openStock} onTrade={openTrade}/>}
          {page==="portfolio" && <Portfolio  portfolio={portfolio} onAdd={()=>setModal({ticker:"",type:"BUY"})} onTrade={openTrade} stocks={stocks}/>}
          {page==="analytics" && <Analytics  analytics={analytics} stocks={stocks}/>}
          {page==="detail"&&selected && <StockDetail ticker={selected} onBack={()=>setPage("screener")} onTrade={openTrade} tickers={tickers} onToast={showToast}/>}
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
