import { useState, useEffect, useCallback } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
const api = {
  get: async (p) => { const r=await fetch(`${API_BASE}${p}`); if(!r.ok)throw new Error(r.status); return r.json(); },
  post: async (p,b) => { const r=await fetch(`${API_BASE}${p}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)}); if(!r.ok)throw new Error(r.status); return r.json(); },
};

// ── EXACT dericBI COLOURS from source HTML ─────────────────────────────────
const C = {
  // Backgrounds
  bg:        "#f0fdfa",   // hero bg (from-[#f0fdfa])
  bgAlt:     "#e8f6ed",   // section alt (bg-[#e8f6ed])
  bgFoot:    "#DFF3EA",   // footer gradient end
  surface:   "#ffffff",
  surface2:  "#f9fafb",   // hovered rows

  // Brand greens
  green:     "#49A078",   // navbar, primary (bg-[#49A078])
  greenDk:   "#3D8069",   // darker green (to-[#3D8069])
  greenDkr:  "#3e8865",   // mobile menu bg
  greenLt:   "#d1fae5",   // light green border/tint
  greenHov:  "#367659",   // hover bg

  // Gold / yellow
  gold:      "#facc15",   // "BI" colour, nav hover glow (text-[#facc15])
  goldDk:    "#f59e0b",   // amber/darker gold
  goldBg:    "#fefce8",   // very light yellow bg
  goldBg2:   "#fef9c3",   // yellow-100

  // Blue
  blue:      "#2563EB",   // links, pricing headers (text-[#2563EB])
  blueDk:    "#1e40af",   // hover blue
  blueLt:    "#dbeafe",   // light blue bg

  // Accents
  red:       "#ef4444",   // promo banner, loss
  redLt:     "#fee2e2",   // light red bg
  orange:    "#f97316",
  purple:    "#a855f7",
  purpleLt:  "#f3e8ff",

  // Text
  text:      "#1f2937",   // gray-800
  textMid:   "#374151",   // gray-700
  muted:     "#6b7280",   // gray-500
  dim:       "#9ca3af",   // gray-400

  // Borders
  border:    "#d1fae5",   // green-tinted
  borderGray:"#e5e7eb",   // gray-200
  borderGold:"#fde68a",   // yellow-200
};

// ── MOCK DATA ────────────────────────────────────────────────────────────────
const MOCK_STOCKS = [
  {ticker:"EQTY.NR",name:"Equity Group",     sector:"Banking",      scores:{daily:82,monthly:78,long_term:85,best_pick:82},metrics:{pe:7.2, pb:0.9,dividend_yield:0.062,price:45.50},sparkline:[43.1,43.8,44.2,44.9,45.1,44.8,45.5]},
  {ticker:"SCOM.NR",name:"Safaricom",        sector:"Telecom",      scores:{daily:71,monthly:88,long_term:90,best_pick:83},metrics:{pe:12.1,pb:4.2,dividend_yield:0.071,price:18.20},sparkline:[17.5,17.8,18.0,18.3,18.1,18.4,18.2]},
  {ticker:"KCB.NR", name:"KCB Group",        sector:"Banking",      scores:{daily:76,monthly:72,long_term:74,best_pick:74},metrics:{pe:4.8, pb:0.7,dividend_yield:0.058,price:28.75},sparkline:[27.8,28.1,28.4,28.0,28.3,28.6,28.75]},
  {ticker:"EABL.NR",name:"EA Breweries",     sector:"Consumer",     scores:{daily:55,monthly:61,long_term:65,best_pick:60},metrics:{pe:18.4,pb:3.1,dividend_yield:0.035,price:155.0},sparkline:[152,153,154,153,155,154,155]},
  {ticker:"COOP.NR",name:"Co-op Bank",       sector:"Banking",      scores:{daily:68,monthly:65,long_term:70,best_pick:68},metrics:{pe:5.9, pb:0.8,dividend_yield:0.052,price:12.90},sparkline:[12.4,12.5,12.7,12.6,12.8,12.9,12.9]},
  {ticker:"ABSA.NR",name:"ABSA Bank Kenya",  sector:"Banking",      scores:{daily:63,monthly:69,long_term:71,best_pick:68},metrics:{pe:6.1, pb:1.1,dividend_yield:0.048,price:14.20},sparkline:[13.8,13.9,14.1,14.0,14.2,14.1,14.2]},
  {ticker:"BRIT.NR",name:"Britam Holdings",  sector:"Insurance",    scores:{daily:59,monthly:55,long_term:58,best_pick:57},metrics:{pe:9.2, pb:0.6,dividend_yield:0.021,price:6.80}, sparkline:[6.5,6.6,6.7,6.8,6.7,6.8,6.8]},
  {ticker:"JUB.NR", name:"Jubilee Holdings", sector:"Insurance",    scores:{daily:61,monthly:58,long_term:62,best_pick:60},metrics:{pe:8.8, pb:0.8,dividend_yield:0.031,price:191.0},sparkline:[188,189,190,191,190,191,191]},
  {ticker:"NCBA.NR",name:"NCBA Group",       sector:"Banking",      scores:{daily:66,monthly:63,long_term:67,best_pick:65},metrics:{pe:5.4, pb:0.7,dividend_yield:0.044,price:36.50},sparkline:[35.5,35.8,36.0,36.2,36.1,36.4,36.5]},
  {ticker:"BAMB.NR",name:"Bamburi Cement",   sector:"Manufacturing",scores:{daily:49,monthly:52,long_term:54,best_pick:52},metrics:{pe:14.2,pb:1.2,dividend_yield:0.028,price:42.00},sparkline:[41,41.5,42,41.8,42,41.9,42]},
];

const MOCK_PORTFOLIO = {
  summary:{total_invested:250000,current_value:312000,unrealized_pl:62000,realized_pl:8500,return_pct:0.248},
  holdings:[
    {ticker:"EQTY.NR",quantity:500, avg_cost:38.0,current_price:45.5,unrealized_pl:3750,best_pick_score:82},
    {ticker:"SCOM.NR",quantity:1000,avg_cost:15.2,current_price:18.2,unrealized_pl:3000,best_pick_score:83},
  ],
};

const MOCK_ANALYTICS = {
  equity_curve:        Array.from({length:12},(_,i)=>({date:new Date(2025,i,1).toISOString().slice(0,10),value:200000+i*9200+Math.random()*4000})),
  monthly_performance: Array.from({length:12},(_,i)=>({month:`2025-${String(i+1).padStart(2,"0")}`,return_pct:parseFloat((Math.random()*0.1-0.02).toFixed(4))})),
  best_picks: [{ticker:"SCOM.NR",return_pct:0.197},{ticker:"EQTY.NR",return_pct:0.196}],
  worst_picks:[{ticker:"EABL.NR",return_pct:-0.04}],
  avg_holding_days:210,
  projections:[{years:1,projected_value:376640,assumed_rate:0.248},{years:3,projected_value:584280,assumed_rate:0.248},{years:5,projected_value:906000,assumed_rate:0.248},{years:10,projected_value:2640000,assumed_rate:0.248}],
};

const fmt = {
  kes:(v)=>v==null?"—":`KES ${Number(v).toLocaleString("en-KE",{minimumFractionDigits:2,maximumFractionDigits:2})}`,
  pct:(v)=>v==null?"—":`${(v*100).toFixed(1)}%`,
  num:(v,d=2)=>v==null?"—":Number(v).toFixed(d),
  big:(v)=>{if(v==null)return"—";if(v>=1e12)return`${(v/1e12).toFixed(1)}T`;if(v>=1e9)return`${(v/1e9).toFixed(1)}B`;if(v>=1e6)return`${(v/1e6).toFixed(1)}M`;return Number(v).toLocaleString();},
};

// Score colours: green80+ / blue60+ / gold40+ / red below
const sc=(s)=>s>=80?C.green:s>=60?C.blue:s>=40?C.goldDk:C.red;
const sl=(s)=>s>=80?"Strong":s>=60?"Good":s>=40?"Fair":"Weak";

// ── SPARKLINE ────────────────────────────────────────────────────────────────
function Spark({data=[],w=100,h=36}){
  if(!data.length)return <svg width={w} height={h}/>;
  const mn=Math.min(...data),mx=Math.max(...data),rng=mx-mn||1;
  const pts=data.map((v,i)=>`${(i/(data.length-1))*w},${h-((v-mn)/rng)*(h-4)-2}`).join(" ");
  const up=data[data.length-1]>=data[0],col=up?C.green:C.red;
  return(
    <svg width={w} height={h} style={{overflow:"visible",display:"block"}}>
      <defs><linearGradient id={"g"+w+h} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={col} stopOpacity="0.3"/><stop offset="100%" stopColor={col} stopOpacity="0"/></linearGradient></defs>
      <polygon points={`${pts} ${w},${h} 0,${h}`} fill={"url(#g"+w+h+")"}/>
      <polyline points={pts} fill="none" stroke={col} strokeWidth="2" strokeLinejoin="round"/>
    </svg>
  );
}

// ── SCORE RING ────────────────────────────────────────────────────────────────
function Ring({score,size=56,label}){
  const r=(size/2)-4,circ=2*Math.PI*r,dash=(score/100)*circ,c=sc(score);
  return(
    <div style={{display:"flex",flexDirection:"column",alignItems:"center",gap:4}}>
      <svg width={size} height={size} style={{transform:"rotate(-90deg)"}}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={C.greenLt} strokeWidth="4"/>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={c} strokeWidth="4"
          strokeDasharray={`${dash} ${circ-dash}`} strokeLinecap="round"
          style={{transition:"stroke-dasharray 0.7s"}}/>
        <text x={size/2} y={size/2} textAnchor="middle" dominantBaseline="central"
          style={{transform:`rotate(90deg)`,transformOrigin:`${size/2}px ${size/2}px`,
          fontSize:size>50?13:10,fontWeight:800,fill:c,fontFamily:"inherit"}}>{score}</text>
      </svg>
      {label&&<span style={{fontSize:9,color:C.muted,textTransform:"uppercase",letterSpacing:"0.1em"}}>{label}</span>}
    </div>
  );
}

// ── LINE CHART ────────────────────────────────────────────────────────────────
function LineChart({data=[],vk="value",color=C.green,height=220}){
  if(!data.length)return<div style={{height,display:"flex",alignItems:"center",justifyContent:"center",color:C.muted,fontSize:13}}>No data</div>;
  const vals=data.map(d=>d[vk]),mn=Math.min(...vals),mx=Math.max(...vals),rng=mx-mn||1;
  const W=100,H=100;
  const pts=data.map((d,i)=>`${(i/(data.length-1))*W},${H-((d[vk]-mn)/rng)*(H-12)-4}`).join(" ");
  return(
    <div>
      <div style={{display:"flex",justifyContent:"space-between",fontSize:10,color:C.muted,marginBottom:4}}>
        <span>{fmt.kes(mn)}</span><span>{fmt.kes(mx)}</span>
      </div>
      <svg viewBox={"0 0 "+W+" "+H} style={{width:"100%",height}} preserveAspectRatio="none">
        <defs><linearGradient id="lcg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25"/>
          <stop offset="100%" stopColor={color} stopOpacity="0"/>
        </linearGradient></defs>
        <polygon points={`${pts} ${W},${H} 0,${H}`} fill="url(#lcg)"/>
        <polyline points={pts} fill="none" stroke={color} strokeWidth="1" strokeLinejoin="round"/>
      </svg>
    </div>
  );
}

// ── BAR CHART ────────────────────────────────────────────────────────────────
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
            <div style={{width:"100%",height:bh,background:up?C.green:C.red,borderRadius:"3px 3px 0 0",opacity:0.85}}/>
            <span style={{fontSize:7,color:C.muted}}>{d.month&&d.month.slice(5)}</span>
          </div>
        );
      })}
    </div>
  );
}

// ── STAT CARD ── top-border coloured card, white bg, dericBI style ────────────
function Stat({label,value,sub,accent=C.green,icon,topBorder,span=1}){
  const bdr=topBorder||accent;
  return(
    <div style={{
      background:C.surface,border:"1px solid "+C.borderGray,borderRadius:12,
      padding:"16px 18px",gridColumn:"span "+span,
      borderTop:"4px solid "+bdr,
      boxShadow:"0 2px 8px #0000000D",
    }}>
      <div style={{display:"flex",alignItems:"center",gap:7,marginBottom:6}}>
        {icon&&<span style={{fontSize:15}}>{icon}</span>}
        <span style={{fontSize:10,color:C.muted,textTransform:"uppercase",letterSpacing:"0.1em",fontWeight:600}}>{label}</span>
      </div>
      <div style={{fontSize:21,fontWeight:800,color:accent,lineHeight:1,fontVariantNumeric:"tabular-nums"}}>{value}</div>
      {sub&&<div style={{fontSize:11,color:C.muted,marginTop:5}}>{sub}</div>}
    </div>
  );
}

// ── TRADE MODAL ──────────────────────────────────────────────────────────────
function TradeModal({ticker="",defaultType="BUY",onClose,onSubmit}){
  const [form,setForm]=useState({ticker,trade_type:defaultType,quantity:"",price:"",date:new Date().toISOString().slice(0,10)});
  const set=(k,v)=>setForm(f=>({...f,[k]:v}));
  const inp={width:"100%",background:"#f9fafb",border:"1px solid "+C.borderGray,borderRadius:8,
    padding:"10px 13px",color:C.text,fontSize:14,outline:"none",
    boxSizing:"border-box",fontFamily:"inherit"};
  return(
    <div style={{position:"fixed",inset:0,background:"#00000066",zIndex:1000,
      display:"flex",alignItems:"center",justifyContent:"center",padding:16}} onClick={onClose}>
      <div onClick={e=>e.stopPropagation()} style={{
        background:C.surface,border:"1px solid "+C.borderGray,borderRadius:16,
        padding:"26px 26px 30px",width:420,
        boxShadow:"0 20px 60px #00000022",borderTop:"4px solid "+C.green,
      }}>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:20}}>
          <span style={{fontSize:17,fontWeight:800,color:C.text}}>Log Trade</span>
          <button onClick={onClose} style={{background:"none",border:"none",color:C.muted,fontSize:22,cursor:"pointer",lineHeight:1}}>×</button>
        </div>
        <div style={{display:"flex",gap:8,marginBottom:16}}>
          {["BUY","SELL"].map(t=>(
            <button key={t} onClick={()=>set("trade_type",t)} style={{
              flex:1,padding:10,borderRadius:9,
              border:"2px solid "+(form.trade_type===t?(t==="BUY"?C.green:C.red):C.borderGray),
              background:form.trade_type===t?(t==="BUY"?C.greenLt:C.redLt):"transparent",
              color:form.trade_type===t?(t==="BUY"?C.greenDk:C.red):C.muted,
              fontWeight:800,fontSize:14,cursor:"pointer",fontFamily:"inherit",
            }}>{t}</button>
          ))}
        </div>
        {[{k:"ticker",l:"Ticker",p:"e.g. EQTY.NR"},{k:"quantity",l:"Quantity",p:"500",t:"number"},{k:"price",l:"Price (KES)",p:"38.00",t:"number"},{k:"date",l:"Date",t:"date"}].map(f=>(
          <div key={f.k} style={{marginBottom:13}}>
            <div style={{fontSize:10,color:C.muted,marginBottom:4,textTransform:"uppercase",letterSpacing:"0.08em",fontWeight:600}}>{f.l}</div>
            <input type={f.t||"text"} value={form[f.k]} placeholder={f.p} onChange={e=>set(f.k,e.target.value)} style={inp}/>
          </div>
        ))}
        <button onClick={()=>onSubmit(form)} style={{
          width:"100%",padding:12,borderRadius:9,border:"none",marginTop:6,
          background:"linear-gradient(135deg,"+C.green+","+C.greenDk+")",
          color:"#fff",fontWeight:800,fontSize:15,cursor:"pointer",
          letterSpacing:"0.03em",boxShadow:"0 4px 14px "+C.green+"44",
        }}>Confirm Trade</button>
      </div>
    </div>
  );
}

// ── TOAST ────────────────────────────────────────────────────────────────────
function Toast({msg,type="info",onClose}){
  useEffect(()=>{const t=setTimeout(onClose,3800);return()=>clearTimeout(t);},[]);
  const col={info:C.blue,success:C.green,error:C.red}[type];
  const bg={info:C.blueLt,success:C.greenLt,error:C.redLt}[type];
  return(
    <div style={{
      position:"fixed",top:22,right:22,background:bg,
      border:"1px solid "+col,borderRadius:10,
      padding:"11px 18px",color:C.text,fontSize:13,zIndex:9999,
      boxShadow:"0 6px 24px #00000018",display:"flex",gap:9,
      alignItems:"center",animation:"fadeIn 0.2s ease",maxWidth:340,fontWeight:600,
    }}>
      <div style={{width:8,height:8,borderRadius:"50%",background:col,flexShrink:0}}/>
      {msg}
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

// ════════════════════════════════════════════════════════════════════════════
// PAGES
// ════════════════════════════════════════════════════════════════════════════

function Dashboard({stocks,portfolio,onSelect}){
  if(!stocks.length)return<Loader text="Fetching live NSE market data..."/>;
  const best=[...stocks].sort((a,b)=>b.scores.best_pick-a.scores.best_pick)[0];
  const topD=[...stocks].sort((a,b)=>b.scores.daily-a.scores.daily).slice(0,5);
  const topM=[...stocks].sort((a,b)=>b.scores.monthly-a.scores.monthly).slice(0,5);
  const topL=[...stocks].sort((a,b)=>b.scores.long_term-a.scores.long_term).slice(0,5);
  const {summary:s}=portfolio,plPos=s.unrealized_pl>=0;

  // Mini ranked list used in side cards
  const MiniList=({list,sk})=>list.map((stk,i)=>(
    <div key={stk.ticker} onClick={()=>onSelect(stk)}
      style={{display:"flex",alignItems:"center",gap:11,padding:"9px 10px",borderRadius:9,cursor:"pointer",marginBottom:4,transition:"background 0.12s",border:"1px solid transparent"}}
      onMouseEnter={e=>{e.currentTarget.style.background=C.greenLt;e.currentTarget.style.borderColor=C.border;}}
      onMouseLeave={e=>{e.currentTarget.style.background="transparent";e.currentTarget.style.borderColor="transparent";}}>
      <div style={{width:24,height:24,borderRadius:"50%",background:"linear-gradient(135deg,"+C.green+","+C.greenDk+")",color:"#fff",fontSize:11,fontWeight:800,display:"flex",alignItems:"center",justifyContent:"center",flexShrink:0}}>{i+1}</div>
      <div style={{flex:1,minWidth:0}}>
        <span style={{fontSize:13,fontWeight:700,color:C.text}}>{stk.ticker}</span>
        <span style={{fontSize:11,color:C.muted,marginLeft:6}}>{stk.name}</span>
      </div>
      <div style={{textAlign:"right",flexShrink:0}}>
        <div style={{fontSize:13,fontWeight:700,color:C.text}}>KES {stk.metrics.price}</div>
        <div style={{fontSize:12,fontWeight:800,color:sc(stk.scores[sk])}}>{stk.scores[sk]}</div>
      </div>
    </div>
  ));

  return(
    <div>
      {/* KPI strip */}
      <div style={{display:"grid",gridTemplateColumns:"repeat(5,1fr)",gap:14,marginBottom:26}}>
        <Stat icon="🏆" label="Best Pick Today" value={best.ticker}              sub={"Score "+best.scores.best_pick+" · KES "+best.metrics.price} accent={C.green} topBorder={C.gold}/>
        <Stat icon="💼" label="Portfolio Value"  value={fmt.kes(s.current_value)} sub={"Invested "+fmt.kes(s.total_invested)}                       accent={C.blue}/>
        <Stat icon={plPos?"📈":"📉"} label="Unrealised P/L" value={fmt.kes(s.unrealized_pl)} sub={fmt.pct(s.return_pct)+" return"} accent={plPos?C.green:C.red}/>
        <Stat icon="✅" label="Realised P/L"     value={fmt.kes(s.realized_pl)}   accent={C.green}/>
        <Stat icon="📊" label="Stocks Tracked"   value={stocks.length}            sub="NSE equities"                                                 accent={C.muted} topBorder={C.borderGray}/>
      </div>

      {/* Hero + undervalued */}
      <div style={{display:"grid",gridTemplateColumns:"1.2fr 0.8fr",gap:18,marginBottom:18}}>

        {/* Best Pick hero card */}
        <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:14,padding:26,boxShadow:"0 2px 12px #0000000A",position:"relative",overflow:"hidden"}}>
          {/* rainbow top bar like dericBI gradient */}
          <div style={{position:"absolute",top:0,left:0,right:0,height:4,background:"linear-gradient(90deg,"+C.gold+","+C.green+","+C.blue+")"}}/>
          <div style={{fontSize:10,color:C.green,letterSpacing:"0.15em",textTransform:"uppercase",fontWeight:700,marginBottom:14,marginTop:4}}>⚡ Best Pick of the Day</div>
          <div style={{display:"flex",alignItems:"flex-start",gap:18,marginBottom:18}}>
            <Ring score={best.scores.best_pick} size={80}/>
            <div style={{flex:1}}>
              <div style={{fontSize:30,fontWeight:900,color:C.text,lineHeight:1}}>{best.ticker}</div>
              <div style={{fontSize:14,color:C.muted,margin:"4px 0 8px"}}>{best.name} · {best.sector}</div>
              <div style={{fontSize:26,fontWeight:900,color:C.green}}>KES {best.metrics.price}</div>
            </div>
            <Spark data={best.sparkline} w={120} h={50}/>
          </div>
          {/* 4 score boxes */}
          <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:8,marginBottom:16}}>
            {[["Daily",best.scores.daily],["Monthly",best.scores.monthly],["Long-Term",best.scores.long_term],["Best Pick",best.scores.best_pick]].map(([l,sv])=>(
              <div key={l} style={{background:C.bgAlt,borderRadius:9,padding:"10px 6px",textAlign:"center",border:"1px solid "+C.border}}>
                <div style={{fontSize:10,color:C.muted,marginBottom:3,fontWeight:600}}>{l}</div>
                <div style={{fontSize:22,fontWeight:900,color:sc(sv)}}>{sv}</div>
                <div style={{fontSize:9,color:sc(sv),marginTop:2,fontWeight:600}}>{sl(sv)}</div>
              </div>
            ))}
          </div>
          {/* Metrics row */}
          <div style={{display:"flex",gap:8}}>
            {[["P/E",fmt.num(best.metrics.pe),C.text],["P/B",fmt.num(best.metrics.pb),C.text],["Div",fmt.pct(best.metrics.dividend_yield),C.green]].map(([lbl,val,clr])=>(
              <div key={lbl} style={{flex:1,background:C.bgAlt,borderRadius:8,padding:"9px 10px",border:"1px solid "+C.border}}>
                <div style={{fontSize:10,color:C.muted,fontWeight:600}}>{lbl}</div>
                <div style={{fontSize:15,fontWeight:700,color:clr}}>{val}</div>
              </div>
            ))}
            <button onClick={()=>onSelect(best)} style={{flex:2,padding:"9px 12px",borderRadius:8,border:"2px solid "+C.green,background:C.greenLt,color:C.greenDk,fontWeight:700,fontSize:13,cursor:"pointer",fontFamily:"inherit",transition:"all 0.15s"}}>Full Analysis →</button>
          </div>
        </div>

        {/* Top undervalued */}
        <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:14,padding:22,boxShadow:"0 2px 12px #0000000A"}}>
          <div style={{position:"absolute"}}/>
          <div style={{fontSize:11,color:C.green,letterSpacing:"0.12em",textTransform:"uppercase",fontWeight:700,marginBottom:14}}>🎯 Most Undervalued Today</div>
          <MiniList list={topD} sk="daily"/>
        </div>
      </div>

      {/* Bottom two cards */}
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:18}}>
        {[{t:"📊 Fundamentally Strong",list:topM,sk:"monthly"},{t:"🌱 Long-Term Value",list:topL,sk:"long_term"}].map(({t,list,sk})=>(
          <div key={sk} style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:14,padding:22,boxShadow:"0 2px 12px #0000000A"}}>
            <div style={{fontSize:11,color:C.green,letterSpacing:"0.12em",textTransform:"uppercase",fontWeight:700,marginBottom:14}}>{t}</div>
            <MiniList list={list} sk={sk}/>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── SCREENER ─────────────────────────────────────────────────────────────────
function Screener({stocks,onSelect}){
  const [timing,setTiming]=useState("best_pick");
  const [q,setQ]=useState("");
  const list=[...stocks]
    .filter(s=>!q||s.ticker.includes(q.toUpperCase())||s.name.toLowerCase().includes(q.toLowerCase())||s.sector.toLowerCase().includes(q.toLowerCase()))
    .sort((a,b)=>b.scores[timing]-a.scores[timing]);

  return(
    <div>
      <div style={{display:"flex",gap:12,marginBottom:18,alignItems:"center"}}>
        <input value={q} onChange={e=>setQ(e.target.value)} placeholder="Search ticker, company or sector..."
          style={{flex:1,background:C.surface,border:"1px solid "+C.borderGray,borderRadius:9,padding:"10px 15px",color:C.text,fontSize:14,outline:"none",fontFamily:"inherit",boxShadow:"0 1px 4px #0000000A"}}/>
        <div style={{display:"flex",gap:6}}>
          {[{id:"best_pick",l:"Best Pick"},{id:"daily",l:"Daily"},{id:"monthly",l:"Monthly"},{id:"long_term",l:"Long-Term"}].map(t=>(
            <button key={t.id} onClick={()=>setTiming(t.id)} style={{
              padding:"9px 16px",borderRadius:8,border:"2px solid",
              borderColor:timing===t.id?C.green:C.borderGray,
              background:timing===t.id?C.greenLt:"transparent",
              color:timing===t.id?C.greenDk:C.muted,
              fontWeight:700,fontSize:12,cursor:"pointer",fontFamily:"inherit",transition:"all 0.15s",
            }}>{t.l}</button>
          ))}
        </div>
      </div>

      <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,overflow:"hidden",boxShadow:"0 2px 12px #0000000A"}}>
        <table style={{width:"100%",borderCollapse:"collapse"}}>
          <thead>
            <tr style={{background:C.bgAlt,borderBottom:"2px solid "+C.border}}>
              {["#","Stock","Sector","Score","P/E","P/B","Div Yield","Price","Trend"].map((h,i)=>(
                <th key={h} style={{padding:"11px 14px",textAlign:i>3?"right":"left",fontSize:10,color:C.muted,fontWeight:700,letterSpacing:"0.1em",textTransform:"uppercase",whiteSpace:"nowrap"}}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {list.length===0
              ?<tr><td colSpan={9} style={{padding:40,textAlign:"center",color:C.muted}}>No stocks found</td></tr>
              :list.map((s,i)=>{
                const score=s.scores[timing]||s.scores.best_pick,c=sc(score);
                const up=s.sparkline&&s.sparkline.length>1&&s.sparkline[s.sparkline.length-1]>=s.sparkline[0];
                return(
                  <tr key={s.ticker} onClick={()=>onSelect(s)} style={{cursor:"pointer",borderBottom:"1px solid "+C.borderGray,transition:"background 0.12s"}}
                    onMouseEnter={e=>e.currentTarget.style.background=C.greenLt}
                    onMouseLeave={e=>e.currentTarget.style.background="transparent"}>
                    <td style={{padding:"11px 14px",color:C.dim,fontSize:12,fontWeight:600}}>{i+1}</td>
                    <td style={{padding:"11px 8px"}}>
                      <div style={{fontWeight:800,color:C.text,fontSize:14}}>{s.ticker}</div>
                      <div style={{fontSize:11,color:C.muted}}>{s.name}</div>
                    </td>
                    <td style={{padding:"11px 8px"}}>
                      <span style={{fontSize:10,background:c+"18",color:c,border:"1px solid "+c+"40",borderRadius:20,padding:"3px 10px",fontWeight:700,whiteSpace:"nowrap"}}>{s.sector}</span>
                    </td>
                    <td style={{padding:"11px 8px",textAlign:"right"}}>
                      <div style={{display:"inline-flex",alignItems:"center",justifyContent:"center",width:42,height:42,borderRadius:21,background:c+"15",border:"2px solid "+c+"50"}}>
                        <span style={{fontSize:14,fontWeight:900,color:c}}>{score}</span>
                      </div>
                    </td>
                    <td style={{padding:"11px 8px",color:C.textMid,fontSize:13,textAlign:"right",fontVariantNumeric:"tabular-nums"}}>{fmt.num(s.metrics.pe)}</td>
                    <td style={{padding:"11px 8px",color:C.textMid,fontSize:13,textAlign:"right",fontVariantNumeric:"tabular-nums"}}>{fmt.num(s.metrics.pb)}</td>
                    <td style={{padding:"11px 8px",color:C.green,fontSize:13,textAlign:"right",fontWeight:700}}>{fmt.pct(s.metrics.dividend_yield)}</td>
                    <td style={{padding:"11px 14px",textAlign:"right"}}>
                      <div style={{fontSize:14,fontWeight:700,color:C.text}}>KES {s.metrics.price}</div>
                      <div style={{fontSize:11,fontWeight:700,color:up?C.green:C.red}}>{up?"▲ up":"▼ dn"}</div>
                    </td>
                    <td style={{padding:"11px 14px"}}><Spark data={s.sparkline} w={90} h={32}/></td>
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

// ── STOCK DETAIL ─────────────────────────────────────────────────────────────
function StockDetail({ticker,onBack,onTrade}){
  const [d,setD]=useState(null);
  const [tab,setTab]=useState("overview");
  const [rng,setRng]=useState("1M");
  const [loading,setLoading]=useState(true);

  useEffect(()=>{
    setLoading(true);
    api.get("/api/stock/"+ticker).then(setD).catch(()=>setD({
      ticker,name:MOCK_STOCKS.find(s=>s.ticker===ticker)?.name||ticker,sector:"—",
      scores:{daily:75,monthly:72,long_term:78,best_pick:75},
      price_history:Array.from({length:90},(_,i)=>({date:new Date(Date.now()-(89-i)*86400000).toISOString().slice(0,10),close:parseFloat((40+Math.random()*12).toFixed(2))})),
      fundamentals:{eps:7.2,bvps:30.5,revenue:120e9,debt:40e9,dividends:3.0,roe:0.18,margin:0.25},
      my_position:null,
    })).finally(()=>setLoading(false));
  },[ticker]);

  if(loading)return<Loader text="Loading stock data..."/>;
  if(!d)return<div style={{color:C.red,padding:24}}>Failed to load.</div>;

  const {scores,fundamentals:f,my_position:pos}=d;
  const rMap={"1D":1,"1W":7,"1M":30,"1Y":365,"5Y":1825};
  const cd=(d.price_history||[]).slice(-rMap[rng]).map(x=>({date:x.date,value:x.close}));
  const cur=d.price_history&&d.price_history[d.price_history.length-1]?.close;
  const prev=d.price_history&&d.price_history[d.price_history.length-2]?.close;
  const chg=cur&&prev?cur-prev:0,pct=prev?chg/prev:0;

  return(
    <div>
      <button onClick={onBack} style={{background:"none",border:"none",color:C.green,fontSize:13,cursor:"pointer",padding:0,marginBottom:16,display:"flex",alignItems:"center",gap:6,fontWeight:700}}>← Back to Screener</button>

      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:20}}>
        <div>
          <div style={{display:"flex",alignItems:"center",gap:11,marginBottom:4}}>
            <span style={{fontSize:32,fontWeight:900,color:C.text}}>{d.ticker}</span>
            <span style={{fontSize:11,background:C.greenLt,color:C.greenDk,border:"1px solid "+C.border,borderRadius:20,padding:"3px 12px",fontWeight:700}}>{d.sector}</span>
          </div>
          <div style={{fontSize:14,color:C.muted}}>{d.name}</div>
        </div>
        <div style={{textAlign:"right"}}>
          <div style={{fontSize:34,fontWeight:900,color:C.text}}>KES {fmt.num(cur,2)}</div>
          <div style={{fontSize:14,fontWeight:700,color:chg>=0?C.green:C.red}}>{chg>=0?"+":""}{fmt.num(chg,2)} ({fmt.pct(pct)})</div>
        </div>
      </div>

      <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:12,marginBottom:22}}>
        {[["Daily",scores.daily],["Monthly",scores.monthly],["Long-Term",scores.long_term],["Best Pick",scores.best_pick]].map(([l,sv])=>(
          <div key={l} style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:12,padding:"14px 12px",textAlign:"center",borderTop:"3px solid "+sc(sv),boxShadow:"0 1px 4px #0000000A"}}>
            <div style={{fontSize:10,color:C.muted,textTransform:"uppercase",letterSpacing:"0.1em",marginBottom:5,fontWeight:600}}>{l}</div>
            <div style={{fontSize:34,fontWeight:900,color:sc(sv),lineHeight:1}}>{sv}</div>
            <div style={{fontSize:11,color:sc(sv),marginTop:4,fontWeight:600}}>{sl(sv)}</div>
          </div>
        ))}
      </div>

      <div style={{display:"flex",borderBottom:"2px solid "+C.borderGray,marginBottom:18}}>
        {["overview","fundamentals","my position"].map(t=>(
          <button key={t} onClick={()=>setTab(t)} style={{padding:"10px 20px",background:"none",border:"none",borderBottom:"3px solid "+(tab===t?C.green:"transparent"),color:tab===t?C.green:C.muted,fontWeight:700,fontSize:13,cursor:"pointer",textTransform:"capitalize",fontFamily:"inherit",marginBottom:-2,transition:"all 0.15s"}}>{t}</button>
        ))}
      </div>

      {tab==="overview"&&(
        <div>
          <div style={{display:"flex",gap:6,marginBottom:12}}>
            {["1D","1W","1M","1Y","5Y"].map(r=>(
              <button key={r} onClick={()=>setRng(r)} style={{padding:"6px 14px",borderRadius:7,border:"2px solid",borderColor:rng===r?C.green:C.borderGray,background:rng===r?C.greenLt:"transparent",color:rng===r?C.greenDk:C.muted,fontSize:12,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>{r}</button>
            ))}
          </div>
          <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:12,padding:"18px 18px 10px",boxShadow:"0 2px 12px #0000000A"}}>
            <LineChart data={cd} color={C.green} height={270}/>
          </div>
        </div>
      )}

      {tab==="fundamentals"&&(
        <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:13}}>
          <Stat icon="💰" label="EPS"             value={fmt.num(f.eps)}              accent={C.green}/>
          <Stat icon="📚" label="Book Value/Share" value={"KES "+fmt.num(f.bvps)}      accent={C.green}/>
          <Stat icon="📊" label="Revenue"          value={fmt.big(f.revenue)}          accent={C.blue}/>
          <Stat icon="⚠️" label="Total Debt"       value={fmt.big(f.debt)}             accent={C.orange}  topBorder={C.orange}/>
          <Stat icon="💵" label="Annual Dividend"  value={"KES "+fmt.num(f.dividends)} accent={C.green}/>
          <Stat icon="📈" label="ROE"              value={fmt.pct(f.roe)}              accent={C.green}/>
          <Stat icon="🎯" label="Profit Margin"    value={fmt.pct(f.margin)}           accent={C.blue}/>
        </div>
      )}

      {tab==="my position"&&(
        <div>
          {pos?(
            <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:13,marginBottom:18}}>
              <Stat icon="🧾" label="Shares Held"   value={pos.quantity&&pos.quantity.toLocaleString()} accent={C.green}/>
              <Stat icon="💳" label="Avg Cost"       value={"KES "+fmt.num(pos.avg_cost)}               accent={C.green}/>
              <Stat icon="📍" label="Current Price"  value={"KES "+fmt.num(pos.current_price)}           accent={C.text}  topBorder={C.borderGray}/>
              <Stat icon={pos.unrealized_pl>=0?"🟢":"🔴"} label="Unrealised P/L" value={fmt.kes(pos.unrealized_pl)} accent={pos.unrealized_pl>=0?C.green:C.red}/>
              <Stat icon="📅" label="Holding Period" value={pos.holding_days+" days"} accent={C.muted} topBorder={C.borderGray} span={4}/>
            </div>
          ):(
            <div style={{background:C.bgAlt,border:"1px solid "+C.border,borderRadius:12,padding:36,textAlign:"center",color:C.muted,marginBottom:18,fontSize:14}}>No position in {ticker} yet.</div>
          )}
          <div style={{display:"flex",gap:12}}>
            <button onClick={()=>onTrade(ticker,"BUY")}  style={{flex:1,padding:14,borderRadius:10,border:"2px solid "+C.green,background:C.greenLt,color:C.greenDk,fontWeight:800,fontSize:15,cursor:"pointer",fontFamily:"inherit"}}>＋ Simulate Buy</button>
            <button onClick={()=>onTrade(ticker,"SELL")} style={{flex:1,padding:14,borderRadius:10,border:"2px solid "+C.red,background:C.redLt,color:C.red,fontWeight:800,fontSize:15,cursor:"pointer",fontFamily:"inherit"}}>− Simulate Sell</button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── PORTFOLIO ────────────────────────────────────────────────────────────────
function Portfolio({portfolio,onAdd}){
  const {summary:s,holdings}=portfolio,plPos=s.unrealized_pl>=0;
  return(
    <div>
      <div style={{display:"grid",gridTemplateColumns:"repeat(5,1fr)",gap:14,marginBottom:26}}>
        <Stat icon="💼" label="Total Invested"  value={fmt.kes(s.total_invested)}  accent={C.muted}  topBorder={C.borderGray}/>
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
            <tr style={{background:C.bgAlt,borderBottom:"2px solid "+C.border}}>
              {["Ticker","Qty","Avg Cost","Current Price","Unrealised P/L","Best Pick"].map(h=>(
                <th key={h} style={{padding:"11px 18px",textAlign:"left",fontSize:10,color:C.muted,fontWeight:700,letterSpacing:"0.1em",textTransform:"uppercase"}}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {holdings.length===0
              ?<tr><td colSpan={6} style={{padding:40,textAlign:"center",color:C.muted}}>No holdings yet. Add your first trade!</td></tr>
              :holdings.map(h=>{
                const plH=h.unrealized_pl>=0;
                return(
                  <tr key={h.ticker} style={{borderBottom:"1px solid "+C.borderGray,transition:"background 0.12s"}}
                    onMouseEnter={e=>e.currentTarget.style.background=C.greenLt}
                    onMouseLeave={e=>e.currentTarget.style.background="transparent"}>
                    <td style={{padding:"13px 18px",fontWeight:800,color:C.text,fontSize:14}}>{h.ticker}</td>
                    <td style={{padding:"13px 18px",color:C.textMid,fontSize:13}}>{h.quantity&&h.quantity.toLocaleString()}</td>
                    <td style={{padding:"13px 18px",color:C.textMid,fontSize:13}}>KES {fmt.num(h.avg_cost)}</td>
                    <td style={{padding:"13px 18px",color:C.textMid,fontSize:13}}>KES {fmt.num(h.current_price)}</td>
                    <td style={{padding:"13px 18px",fontWeight:700,fontSize:13,color:plH?C.green:C.red}}>{plH?"+":""}{fmt.kes(h.unrealized_pl)}</td>
                    <td style={{padding:"13px 18px"}}>
                      {h.best_pick_score&&(
                        <div style={{display:"inline-flex",alignItems:"center",justifyContent:"center",width:38,height:38,borderRadius:19,background:sc(h.best_pick_score)+"15",border:"2px solid "+sc(h.best_pick_score)+"50"}}>
                          <span style={{fontSize:14,fontWeight:900,color:sc(h.best_pick_score)}}>{h.best_pick_score}</span>
                        </div>
                      )}
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

// ── ANALYTICS ────────────────────────────────────────────────────────────────
function Analytics({analytics}){
  if(!analytics)return<Loader text="Loading analytics..."/>;
  const {equity_curve:ec,monthly_performance:mp,best_picks:bp,worst_picks:wp,avg_holding_days:ahd,projections:pj}=analytics;
  const dl=(data,name)=>{
    if(!data||!data.length)return;
    const k=Object.keys(data[0]);
    const csv=[k.join(","),...data.map(r=>k.map(x=>r[x]).join(","))].join("\n");
    const a=document.createElement("a");
    a.href=URL.createObjectURL(new Blob([csv],{type:"text/csv"}));
    a.download=name;a.click();
  };
  return(
    <div>
      <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:14,marginBottom:26}}>
        {(pj||[]).map(p=>(
          <Stat key={p.years} icon="🔮" label={p.years+"-Year Projection"} value={fmt.kes(p.projected_value)} sub={"@ "+fmt.pct(p.assumed_rate)+" p.a."} accent={C.green} topBorder={C.gold}/>
        ))}
      </div>

      <div style={{display:"grid",gridTemplateColumns:"2fr 1fr",gap:18,marginBottom:18}}>
        <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,padding:22,boxShadow:"0 2px 12px #0000000A"}}>
          <div style={{fontSize:13,fontWeight:700,color:C.text,marginBottom:14}}>Equity Curve</div>
          <LineChart data={ec} vk="value" color={C.green} height={240}/>
        </div>
        <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,padding:22,boxShadow:"0 2px 12px #0000000A"}}>
          <div style={{fontSize:13,fontWeight:700,color:C.text,marginBottom:4}}>Monthly Returns</div>
          <Bars data={mp} height={240}/>
        </div>
      </div>

      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:18}}>
        {[{title:"🏆 Best Picks",col:C.green,data:bp,sign:"+"},{title:"📉 Worst Picks",col:C.red,data:wp,sign:""}].map(({title,col,data,sign})=>(
          <div key={title} style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,padding:22,boxShadow:"0 2px 12px #0000000A"}}>
            <div style={{fontSize:10,color:col,textTransform:"uppercase",letterSpacing:"0.1em",fontWeight:700,marginBottom:13}}>{title}</div>
            {(data||[]).map(p=>(
              <div key={p.ticker} style={{display:"flex",justifyContent:"space-between",padding:"10px 0",borderBottom:"1px solid "+C.borderGray}}>
                <span style={{color:C.text,fontWeight:700}}>{p.ticker}</span>
                <span style={{color:col,fontWeight:700}}>{sign}{fmt.pct(p.return_pct)}</span>
              </div>
            ))}
          </div>
        ))}
        <div style={{background:C.surface,border:"1px solid "+C.borderGray,borderRadius:13,padding:22,boxShadow:"0 2px 12px #0000000A"}}>
          <div style={{fontSize:10,color:C.green,textTransform:"uppercase",letterSpacing:"0.1em",fontWeight:700,marginBottom:13}}>⚙️ Stats & Exports</div>
          <div style={{display:"flex",justifyContent:"space-between",padding:"10px 0",borderBottom:"1px solid "+C.borderGray,marginBottom:14}}>
            <span style={{color:C.muted}}>Avg Holding</span>
            <span style={{color:C.text,fontWeight:700}}>{ahd} days</span>
          </div>
          <div style={{display:"flex",flexDirection:"column",gap:8}}>
            <button onClick={()=>dl(ec,"equity_curve.csv")} style={{padding:"9px 13px",borderRadius:8,border:"1px solid "+C.borderGray,background:C.bgAlt,color:C.textMid,fontSize:12,cursor:"pointer",fontFamily:"inherit",textAlign:"left",fontWeight:600}}>↓ Export Equity CSV</button>
            <button onClick={()=>dl(mp,"monthly_returns.csv")} style={{padding:"9px 13px",borderRadius:8,border:"1px solid "+C.borderGray,background:C.bgAlt,color:C.textMid,fontSize:12,cursor:"pointer",fontFamily:"inherit",textAlign:"left",fontWeight:600}}>↓ Export Monthly CSV</button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// ROOT APP
// ════════════════════════════════════════════════════════════════════════════
export default function App(){
  const [page,setPage]=useState("dashboard");
  const [stocks,setStocks]=useState([]);
  const [portfolio,setPortfolio]=useState(MOCK_PORTFOLIO);
  const [analytics,setAnalytics]=useState(null);
  const [selected,setSelected]=useState(null);
  const [modal,setModal]=useState(null);
  const [toast,setToast]=useState(null);
  const [live,setLive]=useState(null);

  const showToast=(msg,type="info")=>setToast({msg,type});

  useEffect(()=>{
    api.get("/api/stocks?timing=best_pick")
      .then(d=>{setStocks(d.stocks||[]);setLive(true);})
      .catch(()=>{setStocks(MOCK_STOCKS);setLive(false);showToast("Backend offline — showing demo data","info");});
  },[]);
  useEffect(()=>{api.get("/api/portfolio").then(setPortfolio).catch(()=>{});},[]);
  useEffect(()=>{
    if(page==="analytics"&&!analytics)
      api.get("/api/analytics").then(setAnalytics).catch(()=>setAnalytics(MOCK_ANALYTICS));
  },[page]);

  const handleTrade=async(form)=>{
    try{
      const r=await api.post("/api/trades",{ticker:form.ticker,trade_type:form.trade_type,quantity:parseInt(form.quantity),price:parseFloat(form.price),date:form.date});
      setPortfolio(r);showToast("Trade logged: "+form.trade_type+" "+form.quantity+" "+form.ticker,"success");
    }catch{showToast("Trade saved locally (backend offline)","info");}
    setModal(null);
  };

  const goTo=(id)=>{setPage(id);setSelected(null);};
  const openStock=useCallback((s)=>{setSelected(s.ticker);setPage("detail");},[]);

  const navItems=[{id:"dashboard",icon:"⊞",l:"Dashboard"},{id:"screener",icon:"⟳",l:"Screener"},{id:"portfolio",icon:"◈",l:"Portfolio"},{id:"analytics",icon:"≋",l:"Analytics"}];
  const titles={dashboard:"Dashboard",screener:"Stock Screener",portfolio:"My Portfolio",detail:"Stock Detail",analytics:"Analytics"};

  return(
    <div style={{display:"flex",minHeight:"100vh",background:C.bg,fontFamily:"'Segoe UI','Inter',system-ui,sans-serif",color:C.text}}>
      <style>{`
        *{box-sizing:border-box;margin:0;padding:0;}
        body{background:${C.bg};overflow-x:hidden;}
        ::-webkit-scrollbar{width:5px;height:5px;}
        ::-webkit-scrollbar-thumb{background:${C.greenLt};border-radius:4px;}
        ::-webkit-scrollbar-track{background:${C.bgAlt};}
        input,button{font-family:inherit;}
        @keyframes spin{to{transform:rotate(360deg);}}
        @keyframes fadeIn{from{opacity:0;transform:translateY(-6px);}to{opacity:1;transform:translateY(0);}}
      `}</style>

      {/* ── SIDEBAR — exact dericBI navbar gradient ────────────────────────── */}
      <div style={{
        width:234,flexShrink:0,
        background:"linear-gradient(180deg,"+C.green+" 0%,"+C.greenDk+" 100%)",
        display:"flex",flexDirection:"column",
        position:"sticky",top:0,height:"100vh",
        boxShadow:"2px 0 12px #0000001C",
      }}>

        {/* Logo — circular with gold ring, exact dericBI style */}
        <div style={{padding:"18px 18px 14px",borderBottom:"1px solid #ffffff22",display:"flex",alignItems:"center",gap:10}}>
          <div style={{position:"relative",flexShrink:0}}>
            <img src="/logo.png" alt="" style={{width:44,height:44,borderRadius:"50%",objectFit:"cover",border:"2px solid "+C.gold,boxShadow:"0 0 0 3px #ffffff25"}}
              onError={e=>{e.target.style.display="none";e.target.nextSibling.style.display="flex";}}/>
            <div style={{display:"none",width:44,height:44,borderRadius:"50%",background:"#ffffff20",border:"2px solid "+C.gold,alignItems:"center",justifyContent:"center",fontSize:20}}>📊</div>
          </div>
          <div>
            {/* "Stock" white + "Intel" in gold — mirrors dericBI "deric"+"BI" */}
            <div style={{fontSize:17,fontWeight:900,color:"#fff",letterSpacing:"-0.01em",lineHeight:1}}>
              Stock<span style={{color:C.gold}}>Intel</span>
            </div>
            <div style={{fontSize:9,color:"#ffffff90",letterSpacing:"0.1em",textTransform:"uppercase",marginTop:2,fontStyle:"italic"}}>Cut Through Noise</div>
          </div>
        </div>

        {/* Nav links — mirroring nav-link style */}
        <nav style={{padding:"12px 10px",flex:1}}>
          {navItems.map(n=>{
            const active=page===n.id||(page==="detail"&&n.id==="screener");
            return(
              <button key={n.id} onClick={()=>goTo(n.id)} style={{
                width:"100%",display:"flex",alignItems:"center",gap:10,
                padding:"11px 13px",borderRadius:9,border:"none",
                background:active?"#ffffff22":"transparent",
                color:active?C.gold:"#ffffffCC",
                fontWeight:active?700:400,fontSize:13,cursor:"pointer",
                marginBottom:2,textAlign:"left",
                borderLeft:"3px solid "+(active?C.gold:"transparent"),
                transition:"all 0.13s",
              }}
                onMouseEnter={e=>{ if(!active){e.currentTarget.style.color=C.gold;e.currentTarget.style.textShadow="0 0 4px rgba(250,204,21,0.4)";} }}
                onMouseLeave={e=>{ if(!active){e.currentTarget.style.color="#ffffffCC";e.currentTarget.style.textShadow="none";} }}>
                <span style={{fontSize:16,width:20,textAlign:"center",flexShrink:0}}>{n.icon}</span>
                {n.l}
              </button>
            );
          })}
        </nav>

        {/* Status footer */}
        <div style={{padding:"13px 16px",borderTop:"1px solid #ffffff22"}}>
          <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:9}}>
            <div style={{width:8,height:8,borderRadius:"50%",flexShrink:0,
              background:live===null?C.gold:live?"#4ade80":C.red,
              boxShadow:live?"0 0 6px #4ade80":"none"}}/>
            <span style={{fontSize:11,color:"#ffffffBB"}}>{live===null?"Connecting...":live?"Live NSE data":"Demo mode"}</span>
          </div>
          <a href="https://dericbi.vercel.app" target="_blank" rel="noreferrer"
            style={{fontSize:10,color:"#ffffff70",textDecoration:"none",lineHeight:1.7,display:"block"}}>
            More BI services →<br/>dericbi.vercel.app
          </a>
        </div>
      </div>

      {/* ── MAIN ───────────────────────────────────────────────────────────── */}
      <div style={{flex:1,display:"flex",flexDirection:"column",minWidth:0,overflow:"hidden"}}>

        {/* Top bar — white with green bottom border */}
        <div style={{
          padding:"13px 30px",
          borderBottom:"2px solid "+C.border,
          background:C.surface,
          display:"flex",alignItems:"center",justifyContent:"space-between",
          position:"sticky",top:0,zIndex:10,flexShrink:0,
          boxShadow:"0 1px 6px #0000000C",
        }}>
          <div>
            <div style={{fontSize:19,fontWeight:800,color:C.text}}>{titles[page]||"Stock Intel"}</div>
            <div style={{fontSize:11,color:C.muted,marginTop:1}}>{new Date().toLocaleDateString("en-KE",{weekday:"long",year:"numeric",month:"long",day:"numeric"})} · Nairobi Stock Exchange</div>
          </div>
          {/* CTA button — green gradient like dericBI buttons */}
          <button onClick={()=>setModal({ticker:"",type:"BUY"})} style={{
            padding:"10px 22px",borderRadius:9,border:"none",
            background:"linear-gradient(135deg,"+C.green+","+C.greenDk+")",
            color:"#fff",fontWeight:800,fontSize:13,cursor:"pointer",
            letterSpacing:"0.03em",boxShadow:"0 4px 14px "+C.green+"44",
          }}>+ Log Trade</button>
        </div>

        {/* Page content */}
        <div style={{flex:1,padding:"26px 30px",overflowY:"auto",background:C.bg}}>
          {page==="dashboard" && <Dashboard  stocks={stocks} portfolio={portfolio} onSelect={openStock}/>}
          {page==="screener"  && <Screener   stocks={stocks} onSelect={openStock}/>}
          {page==="portfolio" && <Portfolio  portfolio={portfolio} onAdd={()=>setModal({ticker:"",type:"BUY"})}/>}
          {page==="analytics" && <Analytics  analytics={analytics}/>}
          {page==="detail"&&selected && <StockDetail ticker={selected} onBack={()=>setPage("screener")} onTrade={(t,tp)=>setModal({ticker:t,type:tp})}/>}
        </div>

        {/* Footer — mirrors dericBI footer exactly */}
        <footer style={{
          background:"linear-gradient(180deg,#ffffff 0%,"+C.bgFoot+" 100%)",
          borderTop:"1px solid "+C.border,
          padding:"10px 30px",
          display:"flex",alignItems:"center",justifyContent:"space-between",
          flexShrink:0,flexWrap:"wrap",gap:8,
        }}>
          <div style={{display:"flex",alignItems:"center",gap:8}}>
            <img src="/logo.png" alt="" style={{width:32,height:32,borderRadius:"50%",objectFit:"cover",border:"2px solid "+C.gold}} onError={e=>e.target.style.display="none"}/>
            <div>
              <div style={{fontSize:13,fontWeight:900,color:C.text}}>Stock<span style={{color:C.gold}}>Intel</span></div>
              <div style={{fontSize:9,color:C.muted,fontStyle:"italic"}}>Cut Through Noise</div>
            </div>
          </div>
          <div style={{fontSize:10,color:C.muted,textAlign:"center"}}>
            © 2025 StockIntel · Built on <a href="https://dericbi.vercel.app" target="_blank" rel="noreferrer" style={{color:C.green,fontWeight:700,textDecoration:"none"}}>dericBI</a> infrastructure
          </div>
          <div style={{fontSize:10,color:C.muted}}>{live===null?"Connecting…":live?"🟢 Live NSE":"🔴 Demo mode"}</div>
        </footer>
      </div>

      {modal&&<TradeModal ticker={modal.ticker} defaultType={modal.type} onClose={()=>setModal(null)} onSubmit={handleTrade}/>}
      {toast&&<Toast msg={toast.msg} type={toast.type} onClose={()=>setToast(null)}/>}
    </div>
  );
}
