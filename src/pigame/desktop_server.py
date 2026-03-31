from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .core import GameEngine, PERK_DEFS, RECIPE_DEFS
from .device import TextRenderer
from .models import EquipmentSlot, Item, ItemType, SaveState, Specialization, zero_stats
from .storage import DEFAULT_SAVE_PATH, auto_equip_inventory, infer_slot, load_save, save_state


HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PiGame Manager</title>
<style>
:root{--bg:#f3ecdf;--panel:#fffaf1;--alt:#f7efdf;--line:#d1c0a7;--ink:#201a15;--muted:#675c4f;--accent:#7a4b2f;--accent2:#5d311b;--good:#27593b;--warn:#8a5b12;--bad:#8a2d20;--shadow:0 10px 28px rgba(39,27,18,.08)}
*{box-sizing:border-box}body{margin:0;color:var(--ink);background:radial-gradient(circle at top left,rgba(122,75,47,.14),transparent 28%),linear-gradient(180deg,#f8f1e2,#ece2ce 55%,#e4d7be);font-family:"Trebuchet MS","Segoe UI",sans-serif}
.shell{max-width:1320px;margin:0 auto;padding:18px;display:grid;gap:16px}.top{display:flex;justify-content:space-between;gap:12px;align-items:center;background:linear-gradient(135deg,#2c2119,#6d4025);color:#fff8ef;border-radius:22px;padding:18px 20px;box-shadow:var(--shadow)}
.title h1{margin:0;font-family:Georgia,"Times New Roman",serif;font-size:clamp(28px,4vw,42px);line-height:1}.sub,.row,.toolbar,.actions,.status{display:flex;flex-wrap:wrap;gap:8px}.sub{margin-top:8px}.chip,.pill{display:inline-flex;align-items:center;gap:6px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.08);border-radius:999px;padding:6px 10px;font-size:13px;white-space:nowrap}.chip{color:var(--ink);background:#fbf6eb;border-color:var(--line)}.good{color:var(--good)!important}.warn{color:var(--warn)!important}.bad{color:var(--bad)!important}
.workspace,.cols,.grid4,.grid3,.grid2,.stats,.list{display:grid;gap:12px}.workspace{grid-template-columns:minmax(0,1.45fr) minmax(320px,.95fr)}.grid4{grid-template-columns:repeat(4,minmax(0,1fr))}.grid3{grid-template-columns:repeat(3,minmax(0,1fr))}.grid2,.stats{grid-template-columns:repeat(2,minmax(0,1fr))}.stats{grid-template-columns:repeat(5,minmax(0,1fr))}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:18px;box-shadow:var(--shadow);overflow:hidden}.head{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:14px 16px;background:linear-gradient(180deg,#f9f2e5,#f1e5d2);border-bottom:1px solid var(--line)}.head h2,.head h3{margin:0;font-size:18px;font-family:Georgia,"Times New Roman",serif}.body{padding:16px;display:grid;gap:12px}
.card,.item{background:linear-gradient(180deg,#fffdf8,var(--alt));border:1px solid var(--line);border-radius:16px;padding:14px;display:grid;gap:8px}.item{grid-template-columns:minmax(0,1fr) auto;align-items:center}.metric{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}.big{font-size:clamp(20px,2vw,30px);font-weight:700;line-height:1}.muted{color:var(--muted);font-size:13px}
button,select,input{font:inherit;border-radius:12px;border:1px solid var(--line);padding:10px 12px;background:#fff;color:var(--ink)}button{cursor:pointer;background:linear-gradient(180deg,var(--accent),var(--accent2));color:#fff7ef;border-color:transparent;box-shadow:0 6px 14px rgba(93,49,27,.18)}button.secondary{background:#fff7ea;color:var(--ink);border-color:var(--line);box-shadow:none}button.ghost{background:transparent;color:var(--muted);border-color:var(--line);box-shadow:none}button:disabled{opacity:.45;cursor:default;box-shadow:none}
.preview{margin:0;background:#221a15;color:#f3e7d5;border-radius:14px;padding:14px;font-family:Consolas,monospace;white-space:pre-wrap;min-height:180px}.notice{position:sticky;top:12px;z-index:4;padding:12px 14px;border-radius:14px;border:1px solid var(--line);background:rgba(255,250,241,.95);box-shadow:var(--shadow);display:none}.notice.visible{display:block}.empty{padding:14px;border:1px dashed var(--line);border-radius:14px;color:var(--muted);background:#fffefb}pre.raw{margin:12px 0 0;padding:14px;border-radius:14px;border:1px solid var(--line);background:#fffef9;white-space:pre-wrap;overflow:auto;max-height:420px}.small{font-size:12px}
@media (max-width:1080px){.workspace{grid-template-columns:1fr}.grid4,.grid3,.grid2,.stats{grid-template-columns:repeat(2,minmax(0,1fr))}}@media (max-width:720px){.shell{padding:10px}.grid4,.grid3,.grid2,.stats{grid-template-columns:1fr}.item{grid-template-columns:1fr}}
</style></head><body><main class="shell"><div id="notice" class="notice"></div><div class="top"><div class="title"><h1>PiGame Manager</h1><div class="sub"><span class="pill">Live control</span><span class="pill">No page reloads</span><span class="pill">Local network</span></div></div><div class="row"><button class="secondary" data-action="refresh">Refresh</button><button class="secondary" data-action="tickQuick" data-ticks="1">Tick 1</button><button class="secondary" data-action="tickQuick" data-ticks="5">Tick 5</button><button class="secondary" data-action="tickQuick" data-ticks="15">Tick 15</button></div></div><div id="app" class="workspace"></div></main>
<script>
const store={data:null,sort:"recommended",filter:"all",search:"",busy:false};
const esc=v=>String(v??"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
const chip=(t,c="")=>`<span class="chip ${c}">${esc(t)}</span>`;
const metric=(l,v,n="")=>`<div class="card"><div class="metric">${esc(l)}</div><div class="big">${esc(v)}</div><div class="muted">${esc(n)}</div></div>`;
function itemCard(item,{equip=false,learn=false,craft=false}={}){const tags=[];if(item.equipped)tags.push(chip("Equipped","good"));if(item.recommended)tags.push(chip("Recommended","warn"));if(item.crafted)tags.push(chip("Crafted"));if(item.recipe_code)tags.push(chip(item.recipe_code));if(item.quantity>1)tags.push(chip(`x${item.quantity}`));const actions=[];if(equip&&item.can_equip)actions.push(`<button ${item.equipped?"disabled":""} data-action="equip" data-index="${item.index}">${item.equipped?"Equipped":"Equip"}</button>`);if(learn&&item.can_learn)actions.push(`<button data-action="learn" data-index="${item.index}">Learn</button>`);if(craft&&item.recipe_code)actions.push(`<button ${item.can_craft?"":"disabled"} data-action="craft" data-recipe="${esc(item.recipe_code)}">Craft</button>`);return `<div class="item"><div><div class="row"><strong>${esc(item.name)}</strong>${tags.join("")}</div><div class="row">${chip(`${item.type} · ${item.rarity}`)}${chip(`P ${item.power}`)}${chip(`Q ${item.quality}`)}${item.slot?chip(item.slot_label):""}${item.score?chip(`Score ${item.score}`):""}</div><div class="muted">${esc(item.summary)}</div></div><div class="actions">${actions.join("")}</div></div>`}
function left(data){const hero=data.hero;const eq=data.equipment.map(slot=>`<div class="card"><div class="metric">${esc(slot.label)}</div>${slot.current?itemCard(slot.current):`<div class="empty">Nothing equipped in ${esc(slot.label)}.</div>`}${slot.has_upgrade&&slot.recommended?`<div class="card"><div class="metric">Suggested Upgrade</div><strong>${esc(slot.recommended.name)}</strong><div class="muted">${esc(slot.recommended.summary)}</div><button data-action="equip" data-index="${slot.recommended.index}">Equip Suggested</button></div>`:`<div class="card"><div class="metric">Suggested Upgrade</div><div class="muted">Current item is already the best known pick.</div></div>`}</div>`).join("");return `<section class="cols"><section class="panel"><div class="head"><h2>${esc(hero.name)}</h2><div class="status">${chip(hero.title)}${chip(hero.specialization)}${chip(hero.activity)}${chip(hero.awaiting_text,hero.awaiting_player?"warn":"good")}</div></div><div class="body">${hero.summary?`<div class="muted">${esc(hero.summary)}</div>`:""}<div class="grid4">${metric("Level",hero.level,`${hero.experience} XP`)}${metric("Hero Power",hero.hero_power,"Estimated combat score")}${metric("Gold",hero.gold,`${hero.supplies} supplies`)}${metric("Depth",hero.depth,`${hero.wins}W / ${hero.losses}L`)}</div><div class="grid2">${metric("Stat Points",hero.unspent_stat_points,"Manual allocation")}${metric("Perk Points",hero.perk_points,`${hero.perks.length} learned`)}</div><div class="stats">${metric("Power",hero.stats.power,`Total ${hero.total_stats.power}`)}${metric("Vitality",hero.stats.vitality,`Total ${hero.total_stats.vitality}`)}${metric("Agility",hero.stats.agility,`Total ${hero.total_stats.agility}`)}${metric("Insight",hero.stats.insight,`Total ${hero.total_stats.insight}`)}${metric("Luck",hero.stats.luck,`Total ${hero.total_stats.luck}`)}</div></div></section><section class="panel"><div class="head"><h2>Gear Board</h2><div class="status">${chip(`${data.inventory_summary.equipped_count} equipped`)}${chip(`${data.inventory_summary.materials} materials`)}${chip(`${data.inventory_summary.blueprints} blueprints`)}</div></div><div class="body"><div class="grid3">${eq}</div><div class="row"><button data-action="autoequip">Auto Equip Best</button><button class="secondary" data-action="forge">Forge / Salvage</button></div></div></section><section class="panel"><div class="head"><h2>Inventory</h2><div class="toolbar"><select id="inventory-filter"><option value="all">All items</option><option value="equippable">Equippable</option><option value="equipped">Equipped only</option><option value="recipes">Blueprints</option><option value="materials">Materials</option></select><select id="inventory-sort"><option value="recommended">Recommended first</option><option value="score">Highest score</option><option value="power">Highest power</option><option value="quality">Highest quality</option><option value="rarity">Highest rarity</option><option value="name">Name</option><option value="newest">Newest first</option></select><input id="inventory-search" placeholder="Search item name" value=""></div></div><div id="inventory-panel" class="body"></div></section><section class="panel"><div class="head"><h2>Live Device Preview</h2><div class="status">${chip(data.device.battery_text,data.device.low_power_mode?"warn":"")}${chip(data.world.boss_status,data.world.boss_active?"bad":"")}</div></div><div class="body"><pre class="preview">${esc(data.screen_preview)}</pre></div></section></section>`}
function right(data){const attention=data.next_steps.length?data.next_steps.map(s=>`<div class="item"><div><div class="row">${chip(s.tone||"warn",s.tone||"warn")}<strong>${esc(s.title)}</strong></div><div class="muted">${esc(s.detail)}</div></div></div>`).join(""):`<div class="empty">No urgent interventions.</div>`;const statButtons=Object.entries(data.hero.stats).map(([k,v])=>`<div class="card"><div class="metric">${esc(k)}</div><div class="big">${esc(v)}</div><button ${data.hero.unspent_stat_points>0?"":"disabled"} data-action="stat" data-stat="${esc(k)}">Spend 1 point</button></div>`).join("");const learned=data.perks.learned.length?data.perks.learned.map(p=>`<div class="card"><strong>${esc(p.name)}</strong><div class="muted">${esc(p.description)}</div></div>`).join(""):`<div class="empty">No perks learned yet.</div>`;const avail=data.perks.available.length?data.perks.available.map(p=>`<div class="card"><div class="metric">${esc(p.code)}</div><strong>${esc(p.name)}</strong><div class="muted">${esc(p.description)}</div><button ${data.hero.perk_points>0?"":"disabled"} data-action="perk" data-perk="${esc(p.code)}">Learn Perk</button></div>`).join(""):`<div class="empty">No perk choices available right now.</div>`;const known=data.recipes.known.length?data.recipes.known.map(r=>`<div class="card"><div class="row"><strong>${esc(r.name)}</strong>${chip(r.code)}${r.can_craft?chip("Ready","good"):chip("Missing parts","warn")}</div><div class="muted">Needs ${r.materials} materials and ${r.gold} gold. ${esc(r.status)}</div><button ${r.can_craft?"":"disabled"} data-action="craft" data-recipe="${esc(r.code)}">Craft</button></div>`).join(""):`<div class="empty">No learned recipes yet.</div>`;const drops=data.recipes.blueprints.length?data.recipes.blueprints.map(i=>itemCard(i,{learn:true})).join(""):`<div class="empty">No blueprint drops waiting.</div>`;const log=data.activity_log.length?data.activity_log.map(line=>`<div class="card"><div class="muted">${esc(line)}</div></div>`).join(""):`<div class="empty">No recent activity yet.</div>`;return `<aside class="cols"><section class="panel"><div class="head"><h2>What Needs You</h2><div class="status">${chip(`Loss streak ${data.hero.loss_streak}`,data.hero.loss_streak>=2?"bad":"")}${chip(`Danger ${data.world.danger_rating}`)}</div></div><div class="body"><div class="list">${attention}</div><div class="grid3"><div class="card"><div class="metric">Specialization</div><select id="specialization-select">${data.specializations.map(s=>`<option value="${esc(s)}" ${s===data.hero.specialization?"selected":""}>${esc(s)}</option>`).join("")}</select><button data-action="specialization">Apply</button></div><div class="card"><div class="metric">Manual Time Advance</div><input id="ticks-input" type="number" min="1" max="50" value="3"><button data-action="tick">Run Ticks</button></div><div class="card"><div class="metric">Camp Hold</div><div class="muted">${esc(data.hero.awaiting_text)}</div><button ${data.hero.awaiting_player?"":"disabled"} data-action="resume">Resume Runs</button></div></div></div></section><section class="panel"><div class="head"><h2>World and Battery</h2><div class="status">${chip(data.world.region)}${chip(data.world.threat)}</div></div><div class="body"><div class="grid2">${metric("Biome Tier",data.world.biome_tier,`Danger ${data.world.danger_rating}`)}${metric("Battery",data.device.battery_percent??"?",data.device.battery_detail)}</div><div class="card"><div class="metric">Boss</div><strong>${esc(data.world.boss_status)}</strong><div class="muted">${esc(data.world.last_event)}</div></div><div class="card"><div class="metric">Specialization Passives</div>${(data.passives||[]).map(line=>`<div class="muted">${esc(line)}</div>`).join("")||`<div class="muted">No passive summary.</div>`}</div></div></section><section class="panel"><div class="head"><h2>Progression</h2><div class="status">${chip(`${data.recipes.known.length} recipes`)}${chip(`${data.perks.learned.length} perks`)}</div></div><div class="body"><div class="panel"><div class="head"><h3>Stat Spending</h3></div><div class="body"><div class="stats">${statButtons}</div></div></div><div class="panel"><div class="head"><h3>Perks</h3></div><div class="body"><div class="grid2">${learned}</div><div class="grid2">${avail}</div></div></div><div class="panel"><div class="head"><h3>Recipes</h3></div><div class="body"><div class="grid2">${known}</div><div class="grid2">${drops}</div></div></div></div></section><section class="panel"><div class="head"><h2>Recent Activity</h2><button class="ghost" data-action="refresh">Refresh</button></div><div class="body"><div class="list">${log}</div></div></section><section class="panel"><div class="head"><h2>Developer Tools</h2><span class="muted small">Keep hidden during normal play</span></div><div class="body"><details><summary>Open raw save and manual grants</summary><div class="grid3" style="margin-top:12px"><div class="card"><div class="metric">Add Supplies</div><input id="dev-supplies" type="number" value="5"><button data-action="supplies">Apply</button></div><div class="card"><div class="metric">Add Gold</div><input id="dev-gold" type="number" value="100"><button data-action="gold">Apply</button></div><div class="card"><div class="metric">Add XP</div><input id="dev-xp" type="number" value="50"><button data-action="xp">Apply</button></div></div><pre class="raw">${esc(JSON.stringify(data.raw_state,null,2))}</pre></details></div></section></aside>`}
function match(item){if(store.filter==="equippable"&&!item.can_equip)return false;if(store.filter==="equipped"&&!item.equipped)return false;if(store.filter==="recipes"&&item.type!=="recipe")return false;if(store.filter==="materials"&&item.type!=="material")return false;if(store.search&&!item.name.toLowerCase().includes(store.search.toLowerCase()))return false;return true}
function sortItems(items){const rr={common:0,uncommon:1,rare:2,epic:3,mythic:4};const list=[...items].filter(match);list.sort((a,b)=>{if(store.sort==="name")return a.name.localeCompare(b.name);if(store.sort==="power")return b.power-a.power||b.quality-a.quality;if(store.sort==="quality")return b.quality-a.quality||b.power-a.power;if(store.sort==="rarity")return (rr[b.rarity]??0)-(rr[a.rarity]??0)||b.power-a.power;if(store.sort==="score")return (b.score??0)-(a.score??0)||b.power-a.power;if(store.sort==="newest")return b.index-a.index;return Number(b.recommended)-Number(a.recommended)||Number(b.equipped)-Number(a.equipped)||(b.score??0)-(a.score??0)});return list}
function renderInventory(){const panel=document.getElementById("inventory-panel");if(!panel||!store.data)return;const items=sortItems(store.data.inventory);panel.innerHTML=items.length?`<div class="list">${items.map(i=>itemCard(i,{equip:true,learn:true})).join("")}</div>`:`<div class="empty">Nothing matches this inventory view.</div>`;const f=document.getElementById("inventory-filter"),s=document.getElementById("inventory-sort"),q=document.getElementById("inventory-search");if(f)f.value=store.filter;if(s)s.value=store.sort;if(q)q.value=store.search}
function render(){const app=document.getElementById("app");if(!app||!store.data)return;app.innerHTML=`${left(store.data)}${right(store.data)}`;renderInventory()}
function localNotice(action,payload,data,serverMsg){if(action==="equip"){const item=data.inventory.find(i=>i.index===payload.index);return store.lang==="ru"?`Надето: ${item?.name||""}.`:`Equipped: ${item?.name||""}.`}if(action==="learn"){const item=data.inventory.find(i=>i.index===payload.index);return store.lang==="ru"?(item?`Изучено: ${item.name}.`:"Чертёж изучен."):(item?`Learned: ${item.name}.`:"Blueprint learned.")}if(action==="craft"){return store.lang==="ru"?"Крафт выполнен.":"Craft completed."}if(action==="perk"){return store.lang==="ru"?"Пассивка изучена.":"Perk learned."}if(action==="stat"){return store.lang==="ru"?"Характеристика улучшена.":"Stat increased."}if(action==="specialization"){return store.lang==="ru"?"Специализация изменена.":"Specialization updated."}if(action==="resume"){return store.lang==="ru"?"Герой снова отправлен в автономный режим.":"Hero released to autonomous mode."}if(action==="autoequip"){return store.lang==="ru"?"Лучший известный набор надет.":"Best known set equipped."}if(action==="forge"){return store.lang==="ru"?"Шаг ковки/разбора выполнен.":"Forge step completed."}if(action==="tick"){return store.lang==="ru"?"Тики выполнены.":"Ticks advanced."}if(action==="refresh"){return store.lang==="ru"?"Состояние обновлено.":"State refreshed."}return serverMsg|| (store.lang==="ru"?"Действие выполнено.":"Action completed.")}
function notice(msg,t="good"){const n=document.getElementById("notice");if(!n)return;n.textContent=msg;n.className=`notice visible ${t}`;clearTimeout(notice.timer);notice.timer=setTimeout(()=>n.className="notice",3200)}
async function fetchState(silent=false){if(!silent)store.busy=true;const r=await fetch("/api/manager-state");store.data=await r.json();render();store.busy=false}
async function run(action,payload={}){if(store.busy)return;store.busy=true;try{const r=await fetch("/api/action",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action,...payload})});const data=await r.json();if(!r.ok||!data.ok)throw new Error(data.message||`Action failed: ${action}`);store.data=data.state;render();notice(data.message||"Action completed.")}catch(e){notice(e.message||"Action failed.","bad")}finally{store.busy=false}}
document.addEventListener("change",e=>{const t=e.target;if(t.id==="inventory-filter"){store.filter=t.value;renderInventory()}if(t.id==="inventory-sort"){store.sort=t.value;renderInventory()}if(t.id==="inventory-search"){store.search=t.value;renderInventory()}});document.addEventListener("input",e=>{const t=e.target;if(t.id==="inventory-search"){store.search=t.value;renderInventory()}});
document.addEventListener("click",async e=>{const b=e.target.closest("[data-action]");if(!b)return;const a=b.dataset.action;if(a==="refresh"){await fetchState(true);notice("State refreshed.");return}if(a==="equip"){await run("equip",{index:Number(b.dataset.index)});return}if(a==="learn"){await run("learn",{index:Number(b.dataset.index)});return}if(a==="craft"){await run("craft",{recipe_code:b.dataset.recipe});return}if(a==="perk"){await run("perk",{perk_code:b.dataset.perk});return}if(a==="stat"){await run("stat",{stat:b.dataset.stat});return}if(a==="tickQuick"){await run("tick",{ticks:Number(b.dataset.ticks||"1")});return}if(a==="tick"){await run("tick",{ticks:Number(document.getElementById("ticks-input")?.value||"1")});return}if(a==="specialization"){await run("specialization",{specialization:document.getElementById("specialization-select")?.value||""});return}if(a==="supplies"||a==="gold"||a==="xp"){await run(a,{amount:Number(document.getElementById(`dev-${a}`)?.value||"0")});return}await run(a)});
fetchState().catch(e=>notice(e.message||"Failed to load manager.","bad"));
</script></body></html>"""


def build_html() -> str:
    return """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PiGame Manager</title>
<style>
:root{--bg:#ebe4d4;--panel:#fffaf1;--panel2:#f4ead7;--line:#d0bda3;--ink:#221b15;--muted:#6d6255;--brand:#5f7fa3;--brand2:#3c5976;--accent:#8a5b2d;--good:#246244;--warn:#9a6915;--bad:#963223;--shadow:0 12px 30px rgba(38,28,18,.08)}
*{box-sizing:border-box}body{margin:0;background:linear-gradient(180deg,#f3ecde,#e7dbc4);color:var(--ink);font-family:"Trebuchet MS","Segoe UI",sans-serif}
.app{min-height:100vh;display:grid;grid-template-columns:260px 1fr}.side{background:linear-gradient(180deg,#f6efdf,#ecdfc8);border-right:1px solid var(--line);padding:16px;display:grid;gap:12px;align-content:start;position:sticky;top:0;height:100vh}.brand{padding:14px 16px;border-radius:20px;background:linear-gradient(135deg,var(--brand),var(--brand2));color:#f7fbff;box-shadow:var(--shadow)}.brand h1{margin:0;font:700 30px Georgia,"Times New Roman",serif}.brand p{margin:6px 0 0;font-size:13px;opacity:.88}
.nav{display:grid;gap:6px}.nav button{width:100%;justify-content:flex-start;text-align:left;background:#fff9ef;color:var(--ink);border:1px solid var(--line);box-shadow:none;padding:11px 12px}.nav button.active{background:linear-gradient(135deg,var(--brand),var(--brand2));color:#fff;border-color:transparent}.side .meta{display:grid;gap:8px}.chip,.pill{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:6px 10px;font-size:12px;white-space:nowrap;border:1px solid var(--line);background:#fdf8ef}.good{color:var(--good)!important}.warn{color:var(--warn)!important}.bad{color:var(--bad)!important}
.main{padding:18px;display:grid;gap:16px}.notice{padding:12px 14px;border-radius:14px;border:1px solid var(--line);background:rgba(255,250,241,.92);display:none;box-shadow:var(--shadow)}.notice.visible{display:block}.top{display:grid;gap:14px;background:linear-gradient(135deg,#31251b,#6e4428);color:#fff8ef;border-radius:22px;padding:18px 20px;box-shadow:var(--shadow)}.top h2{margin:0;font:700 28px Georgia,"Times New Roman",serif}.row,.toolbar,.actions,.status,.hero-tags,.readiness{display:flex;flex-wrap:wrap;gap:8px}
.readiness-card{display:grid;gap:10px;padding:12px 14px;border-radius:16px;background:rgba(255,248,239,.08);border:1px solid rgba(255,255,255,.14)}
.hero-grid,.grid4,.grid3,.grid2,.list,.cards{display:grid;gap:12px}.grid4{grid-template-columns:repeat(4,minmax(0,1fr))}.grid3{grid-template-columns:repeat(3,minmax(0,1fr))}.grid2{grid-template-columns:repeat(2,minmax(0,1fr))}.hero-grid{grid-template-columns:repeat(5,minmax(0,1fr))}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:20px;box-shadow:var(--shadow);overflow:hidden}.head{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:14px 16px;background:linear-gradient(180deg,#fbf4e6,#f0e4d1);border-bottom:1px solid var(--line)}.head h3,.head h2{margin:0;font:700 18px Georgia,"Times New Roman",serif}.body{padding:16px;display:grid;gap:12px}
.card,.item{background:linear-gradient(180deg,#fffdf9,var(--panel2));border:1px solid var(--line);border-radius:16px;padding:14px;display:grid;gap:8px}.item{grid-template-columns:minmax(0,1fr) auto;align-items:center}.metric{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}.big{font-size:clamp(18px,2vw,30px);font-weight:700;line-height:1}.muted{color:var(--muted);font-size:13px}.focus{border-color:var(--brand);box-shadow:0 0 0 3px rgba(95,127,163,.18)}.compare{display:grid;grid-template-columns:1fr 1fr;gap:10px}.delta.up{color:var(--good);font-weight:700}.delta.down{color:var(--bad);font-weight:700}
button,select,input{font:inherit;border-radius:12px;border:1px solid var(--line);padding:10px 12px;background:#fff;color:var(--ink)}button{cursor:pointer;background:linear-gradient(180deg,var(--accent),#6f431b);color:#fff7ef;border-color:transparent;box-shadow:0 6px 14px rgba(93,49,27,.18)}button.secondary{background:#fff7ea;color:var(--ink);border-color:var(--line);box-shadow:none}button.ghost{background:transparent;color:var(--muted);border-color:var(--line);box-shadow:none}button:disabled{opacity:.45;cursor:default;box-shadow:none}
.preview{margin:0;background:#221a15;color:#f3e7d5;border-radius:14px;padding:14px;font-family:Consolas,monospace;white-space:pre-wrap;min-height:180px}.empty{padding:14px;border:1px dashed var(--line);border-radius:14px;color:var(--muted);background:#fffefb}pre.raw{margin:0;padding:14px;border-radius:14px;border:1px solid var(--line);background:#fffef9;white-space:pre-wrap;overflow:auto;max-height:420px}
@media (max-width:1100px){.app{grid-template-columns:1fr}.side{position:static;height:auto}.grid4,.grid3,.grid2,.hero-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media (max-width:720px){.main,.side{padding:10px}.grid4,.grid3,.grid2,.hero-grid{grid-template-columns:1fr}.item{grid-template-columns:1fr}}
</style></head><body><div class="app"><aside class="side"><div class="brand"><h1>PiGame</h1><p>Local manager for your e-ink companion.</p></div><nav id="sidebar" class="nav"></nav><div id="side-meta" class="meta"></div></aside><main class="main"><div id="notice" class="notice"></div><section id="topbar" class="top"></section><section id="content"></section></main></div>
<script>
const VIEWS=["overview","gear","crafting","progression","activity"];
const store={data:null,view:"overview",sort:"recommended",filter:"all",search:"",busy:false,flash:null,lang:localStorage.getItem("pigame-lang")||"en"};
const I18N={en:{overview:"Overview",gear:"Gear",crafting:"Crafting",progression:"Progression",activity:"Activity",hero:"Hero",needs_you:"Needs You",readiness:"Readiness",refresh:"Refresh",tick1:"Tick 1",tick5:"Tick 5",tick15:"Tick 15",hero_snapshot:"Hero Snapshot",world_device:"World and Device",equipped_slots:"Equipped Slots",inventory:"Inventory",crafting_overview:"Crafting Overview",craftable_recipes:"Craftable Recipes",blueprint_drops:"Blueprint Drops",allocation:"Allocation",perks:"Perks",recent_activity:"Recent Activity",device_preview:"Device Preview",developer_tools:"Developer Tools",debug_only:"debug only",ready:"Ready",attention:"Attention",level:"Level",hero_power:"Hero Power",gold:"Gold",depth:"Depth",power:"Power",vitality:"Vitality",agility:"Agility",insight:"Insight",luck:"Luck",materials:"Materials",blueprints:"Blueprints",ready_recipes:"Ready Recipes",biome_tier:"Biome Tier",battery:"Battery",specialization:"Specialization",manual_time:"Manual Time Advance",camp_hold:"Camp Hold",run_ticks:"Run ticks",apply_specialization:"Apply specialization",resume_runs:"Resume autonomous runs",learn_perk:"Learn perk",equip_best:"Equip best known set",refresh_checks:"Refresh after manual checks",equip_now:"Equip now",equip_suggested:"Equip suggested now",suggested_upgrade:"Suggested Upgrade",current:"Current",suggested:"Suggested",current_best:"Current item is already the best known pick.",last_equip:"Last equipment action",equip_refreshed:"The slot and inventory list were refreshed from live save state.",craft_now:"Craft now",forge_step:"Forge / Salvage step",refresh_materials:"Refresh materials",no_recipes:"No learned recipes yet.",no_blueprints:"No blueprint drops waiting.",all_items:"All items",equippable:"Equippable",equipped_only:"Equipped only",recipes:"Blueprints",materials_filter:"Materials",suggested_first:"Suggested first",highest_score:"Highest score",highest_power:"Highest power",highest_quality:"Highest quality",highest_rarity:"Highest rarity",name:"Name",newest:"Newest first",search_item:"Search item name",state:"State",stats_pts:"stat pts",perk_pts:"perk pts",recipes_ready:"recipes ready",hero_card:"Hero",hold:"Hold",needs_setup:"Needs Setup",gear_available:"Gear Available",readiness_hold:"Hero is refusing deeper runs until you intervene.",readiness_setup_both:"Spend stat points and choose a perk before sending the hero back out.",readiness_setup_stats:"Unspent stat points are lowering effective power.",readiness_setup_perks:"A perk choice is waiting and should be resolved before progression.",readiness_gear_prefix:"Better items are available for ",readiness_gear_suffix:".",readiness_ready:"No obvious blockers. The hero can run autonomously.",activity_autonomous:"Autonomous",learn:"Learn",equipped:"Equipped",crafted:"Crafted",suggested_tag:"Suggested"},ru:{overview:"Обзор",gear:"Снаряжение",crafting:"Крафт",progression:"Прокачка",activity:"Активность",hero:"Герой",needs_you:"Требует внимания",readiness:"Готовность",refresh:"Обновить",tick1:"Тик 1",tick5:"Тик 5",tick15:"Тик 15",hero_snapshot:"Состояние героя",world_device:"Мир и устройство",equipped_slots:"Экипированные слоты",inventory:"Инвентарь",crafting_overview:"Обзор крафта",craftable_recipes:"Доступные рецепты",blueprint_drops:"Выпавшие чертежи",allocation:"Распределение",perks:"Пассивки",recent_activity:"Последние события",device_preview:"Превью устройства",developer_tools:"Инструменты разработчика",debug_only:"только отладка",ready:"Готов",attention:"Внимание",level:"Уровень",hero_power:"Сила героя",gold:"Золото",depth:"Глубина",power:"Сила",vitality:"Живучесть",agility:"Ловкость",insight:"Проницательность",luck:"Удача",materials:"Материалы",blueprints:"Чертежи",ready_recipes:"Готовые рецепты",biome_tier:"Тир биома",battery:"Батарея",specialization:"Специализация",manual_time:"Ручная перемотка",camp_hold:"Ожидание в лагере",run_ticks:"Прогнать тики",apply_specialization:"Применить специализацию",resume_runs:"Вернуть в автономный режим",learn_perk:"Изучить пассивку",equip_best:"Надеть лучший набор",refresh_checks:"Обновить проверку",equip_now:"Надеть",equip_suggested:"Надеть рекомендованное",suggested_upgrade:"Рекомендуемая замена",current:"Текущее",suggested:"Рекомендуемое",current_best:"Текущий предмет уже лучший из доступных.",last_equip:"Последнее действие с экипировкой",equip_refreshed:"Слот и список инвентаря обновлены из живого сейва.",craft_now:"Скрафтить",forge_step:"Ковка / разбор",refresh_materials:"Обновить ресурсы",no_recipes:"Изученных рецептов пока нет.",no_blueprints:"Ожидающих чертежей нет.",all_items:"Все предметы",equippable:"Экипируемое",equipped_only:"Только надетое",recipes:"Чертежи",materials_filter:"Материалы",suggested_first:"Сначала рекомендованные",highest_score:"Лучший score",highest_power:"Макс. сила",highest_quality:"Макс. качество",highest_rarity:"Макс. редкость",name:"Имя",newest:"Сначала новые",search_item:"Поиск по имени",state:"Состояние",stats_pts:"очк. статов",perk_pts:"очк. пассивок",recipes_ready:"рецептов готово",hero_card:"Герой",hold:"Стоп",needs_setup:"Нужно настроить",gear_available:"Есть апгрейд",readiness_hold:"Герой отказывается идти дальше, пока ты не вмешаешься.",readiness_setup_both:"Распредели статы и выбери пассивку перед следующим забегом.",readiness_setup_stats:"Нераспределённые статы снижают реальную силу героя.",readiness_setup_perks:"Есть доступная пассивка, её стоит выбрать до дальнейшего прогресса.",readiness_gear_prefix:"Доступны улучшения для: ",readiness_gear_suffix:".",readiness_ready:"Явных блокеров нет. Герой готов к автономным забегам.",activity_autonomous:"Автономно",learn:"Изучить",equipped:"Надето",crafted:"Скрафчено",suggested_tag:"Рекомендовано"}};
const esc=v=>String(v??"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
const t=k=>I18N[store.lang]?.[k]??I18N.en[k]??k;
const setLang=lang=>{store.lang=lang; localStorage.setItem("pigame-lang",lang); render();}
const chip=(t,c="")=>`<span class="chip ${c}">${esc(t)}</span>`;
const metric=(l,v,n="")=>`<div class="card"><div class="metric">${esc(l)}</div><div class="big">${esc(v)}</div><div class="muted">${esc(n)}</div></div>`;
function itemCard(item,{equip=false,learn=false}={}){const tags=[];if(item.equipped)tags.push(chip(t("equipped"),"good"));if(item.recommended)tags.push(chip(t("suggested_tag"),"warn"));if(item.crafted)tags.push(chip(t("crafted")));if(item.recipe_code)tags.push(chip(item.recipe_code));if(item.quantity>1)tags.push(chip(`x${item.quantity}`));const actions=[];if(equip&&item.can_equip)actions.push(`<button ${item.equipped?"disabled":""} data-action="equip" data-index="${item.index}">${item.equipped?t("equipped"):t("equip_now")}</button>`);if(learn&&item.can_learn)actions.push(`<button data-action="learn" data-index="${item.index}">${t("learn")}</button>`);const focused=store.flash&&store.flash.index===item.index;return `<div class="item ${focused?"focus":""}"><div><div class="row"><strong>${esc(item.name)}</strong>${tags.join("")}</div><div class="row">${chip(`${item.type} · ${item.rarity}`)}${chip(`P ${item.power}`)}${chip(`Q ${item.quality}`)}${item.slot?chip(item.slot_label):""}${item.score?chip(`Score ${item.score}`):""}</div><div class="muted">${esc(item.summary)}</div></div><div class="actions">${actions.join("")}</div></div>`}
function readinessLabel(d){return t(d.hero.readiness_code||"ready")}
function readinessDetail(d){if(d.hero.readiness_code==="hold")return d.hero.awaiting_text&&d.hero.awaiting_text!==I18N.en.activity_autonomous?d.hero.awaiting_text:t("readiness_hold");if(d.hero.readiness_code==="needs_setup"){if(d.hero.unspent_stat_points>0&&d.hero.perk_points>0)return t("readiness_setup_both");if(d.hero.unspent_stat_points>0)return t("readiness_setup_stats");if(d.hero.perk_points>0)return t("readiness_setup_perks")}if(d.hero.readiness_code==="gear_available")return `${t("readiness_gear_prefix")}${d.hero.readiness_targets||""}${t("readiness_gear_suffix")}`;return t("readiness_ready")}
function renderSidebar(){const side=document.getElementById("sidebar"),meta=document.getElementById("side-meta"),d=store.data;if(!side||!meta||!d)return;side.innerHTML=VIEWS.map(id=>`<button class="${store.view===id?"active":""}" data-view="${id}">${t(id)}</button>`).join("");meta.innerHTML=`<div class="card"><div class="metric">${t("hero_card")}</div><strong>${esc(d.hero.name)}</strong><div class="row">${chip(d.hero.specialization)}${chip(`Lv ${d.hero.level}`)}${chip(`Pwr ${d.hero.hero_power}`)}</div></div><div class="card"><div class="metric">${t("readiness")}</div><strong class="${d.hero.readiness_tone}">${esc(readinessLabel(d))}</strong><div class="muted">${esc(readinessDetail(d))}</div></div><div class="card"><div class="metric">${t("needs_you")}</div><div class="row">${chip(`${d.hero.unspent_stat_points} ${t("stats_pts")}`,d.hero.unspent_stat_points?"warn":"")}${chip(`${d.hero.perk_points} ${t("perk_pts")}`,d.hero.perk_points?"warn":"")}${chip(`${d.inventory_summary.blueprints} ${t("blueprints")}`,d.inventory_summary.blueprints?"warn":"")}</div><div class="row"><button class="${store.lang==='en'?'active':''}" data-lang="en">EN</button><button class="${store.lang==='ru'?'active':''}" data-lang="ru">RU</button></div></div>`}
function heroStateChip(d){return d.hero.awaiting_player?t("needs_you"):t("activity_autonomous")}
function renderTopbar(){const top=document.getElementById("topbar"),d=store.data;if(!top||!d)return;top.innerHTML=`<div class="row" style="justify-content:space-between;align-items:start;"><div><h2>${esc(t(store.view)||"Manager")}</h2><div class="hero-tags">${chip(d.hero.title)}${chip(d.hero.activity)}${chip(heroStateChip(d),d.hero.awaiting_player?"warn":"good")}</div></div><div class="row"><button class="secondary" data-action="refresh">${t("refresh")}</button><button class="secondary" data-action="tickQuick" data-ticks="1">${t("tick1")}</button><button class="secondary" data-action="tickQuick" data-ticks="5">${t("tick5")}</button><button class="secondary" data-action="tickQuick" data-ticks="15">${t("tick15")}</button><button class="secondary" data-lang="en">EN</button><button class="secondary" data-lang="ru">RU</button></div></div><div class="readiness-card"><div class="readiness">${chip(`${t("state")}: ${readinessLabel(d)}`,d.hero.readiness_tone)}${chip(`${d.hero.unspent_stat_points} ${t("stats_pts")}`,d.hero.unspent_stat_points?"warn":"")}${chip(`${d.hero.perk_points} ${t("perk_pts")}`,d.hero.perk_points?"warn":"")}${chip(`${d.inventory_summary.blueprints} ${t("blueprints")}`,d.inventory_summary.blueprints?"warn":"")}${chip(`${d.recipes.ready_count} ${t("recipes_ready")}`,d.recipes.ready_count?"good":"")}</div><div class="muted">${esc(readinessDetail(d))}</div></div>`}
function stepText(step){if(step.code==="camp_hold")return{title:store.lang==="ru"?"Герой ждёт в лагере.":"Hero is waiting in camp.",detail:step.reason|| (store.lang==="ru"?"Нужно вмешательство игрока перед следующим выходом.":"Resolve progression choices before sending the hero out again.")};if(step.code==="stat_points")return{title:store.lang==="ru"?`${step.count} очков статов не распределено.`:`${step.count} stat points unspent.`,detail:store.lang==="ru"?"Распредели их перед следующим глубоким забегом.":"Spend them before deeper runs so the hero stops wasting progression."};if(step.code==="perk_points")return{title:store.lang==="ru"?`${step.count} очков пассивок доступно.`:`${step.count} perk points available.`,detail:store.lang==="ru"?"Выбери пассивку специализации, это сильно влияет на силу героя.":"Pick a specialization perk. These are a major part of the power curve now."};if(step.code==="blueprints_waiting")return{title:store.lang==="ru"?`${step.count} чертежей ждут изучения.`:`${step.count} blueprint drops waiting.`,detail:store.lang==="ru"?"Изучи их, чтобы ранние находки превращались в развитие экипировки.":"Learn them first so future runs can turn into better gear."};if(step.code==="gear_upgrades")return{title:store.lang==="ru"?"Лучшие вещи уже в сумке.":"Better gear is already in the bag.",detail:store.lang==="ru"?`Есть улучшения для ${step.targets||""}. Надень их перед следующим спуском.`:`Suggested upgrades exist for ${step.targets||""}. Equip them before pushing deeper.`};if(step.code==="craft_ready")return{title:store.lang==="ru"?`${step.count} рецептов можно крафтить прямо сейчас.`:`${step.count} recipes are craftable now.`,detail:store.lang==="ru"?"Используй крафт, чтобы пробивать стенки прогрессии, а не ждать случайный лут.":"Use crafting to break gear walls instead of waiting for random drops."};return{title:store.lang==="ru"?"Автономность в норме.":"Autonomy is healthy.",detail:store.lang==="ru"?"Явных блокеров нет. Можно дать герою поработать самому.":"No obvious blockers right now. Let the hero run or push a few manual ticks."}}
function overview(d){const steps=d.next_steps.length?d.next_steps.map(s=>{const text=stepText(s);return `<div class="item"><div><div class="row">${chip(s.tone==="good"?t("ready"):t("attention"),s.tone||"warn")}<strong>${esc(text.title)}</strong></div><div class="muted">${esc(text.detail)}</div></div></div>`}).join(""):`<div class="empty">${store.lang==="ru"?"Срочных действий нет.":"No urgent interventions."}</div>`;return `<div class="cards"><section class="panel"><div class="head"><h3>${t("hero_snapshot")}</h3><div class="status">${chip(`Loss ${d.hero.loss_streak}`,d.hero.loss_streak>=2?"bad":"")}${chip(`Bosses ${d.hero.bosses_defeated}`)}${chip(d.world.boss_status,d.world.boss_active?"bad":"")}</div></div><div class="body"><div class="card"><div class="metric">${t("readiness")}</div><div class="big ${d.hero.readiness_tone}">${esc(readinessLabel(d))}</div><div class="muted">${esc(readinessDetail(d))}</div></div><div class="muted">${esc(d.hero.summary)}</div><div class="grid4">${metric(t("level"),d.hero.level,`${d.hero.experience} XP`)}${metric(t("hero_power"),d.hero.hero_power,"Estimated combat score")}${metric(t("gold"),d.hero.gold,`${d.hero.supplies} supplies`)}${metric(t("depth"),d.hero.depth,`${d.hero.wins}W / ${d.hero.losses}L`)}</div><div class="hero-grid">${metric(t("power"),d.hero.stats.power,`Total ${d.hero.total_stats.power}`)}${metric(t("vitality"),d.hero.stats.vitality,`Total ${d.hero.total_stats.vitality}`)}${metric(t("agility"),d.hero.stats.agility,`Total ${d.hero.total_stats.agility}`)}${metric(t("insight"),d.hero.stats.insight,`Total ${d.hero.total_stats.insight}`)}${metric(t("luck"),d.hero.stats.luck,`Total ${d.hero.total_stats.luck}`)}</div></div></section><section class="panel"><div class="head"><h3>${t("needs_you")}</h3><div class="status">${chip(`${d.recipes.known.length} ${t("recipes")}`)}${chip(`${d.inventory_summary.blueprints} ${t("blueprints")}`,d.inventory_summary.blueprints?"warn":"")}</div></div><div class="body">${steps}</div></section><section class="panel"><div class="head"><h3>${t("world_device")}</h3><div class="status">${chip(d.world.region)}${chip(d.world.threat)}</div></div><div class="body"><div class="grid2">${metric(t("biome_tier"),d.world.biome_tier,`Danger ${d.world.danger_rating}`)}${metric(t("battery"),d.device.battery_percent??"?",d.device.battery_detail)}</div><pre class="preview">${esc(d.screen_preview)}</pre></div></section></div>`}
function gear(d){const slots=d.equipment.map(slot=>{const current=slot.current?itemCard(slot.current):`<div class="empty">${store.lang==="ru"?`В слоте ${esc(slot.label)} ничего не надето.`:`Nothing equipped in ${esc(slot.label)}.`}</div>`;let compare=`<div class="muted">${t("current_best")}</div>`;if(slot.has_upgrade&&slot.recommended){const delta=slot.score_delta||0;compare=`<div class="compare"><div class="card"><div class="metric">${t("current")}</div>${slot.current?`<strong>${esc(slot.current.name)}</strong><div class="muted">${esc(slot.current.summary)}</div><div class="row">${chip(`Score ${slot.current.score||0}`)}</div>`:`<div class="muted">${store.lang==="ru"?"Пустой слот":"Empty slot"}</div>`}</div><div class="card ${store.flash&&store.flash.index===slot.recommended.index?"focus":""}"><div class="metric">${t("suggested")}</div><strong>${esc(slot.recommended.name)}</strong><div class="muted">${esc(slot.recommended.summary)}</div><div class="row">${chip(`Score ${slot.recommended.score||0}`)}<span class="delta ${delta>=0?"up":"down"}">${delta>=0?"+":""}${delta}</span></div><button data-action="equip" data-index="${slot.recommended.index}">${t("equip_suggested")}</button></div></div>`}return `<div class="card ${store.flash&&store.flash.slot===slot.slot?"focus":""}"><div class="metric">${esc(slot.label)}</div>${current}${compare}</div>`}).join("");const equippedNow=store.flash&&store.flash.action==="equip"?`<div class="card focus"><div class="metric">${t("last_equip")}</div><strong>${esc(store.flash.name||t("equipped"))}</strong><div class="muted">${t("equip_refreshed")}</div></div>`:"";return `<div class="cards"><section class="panel"><div class="head"><h3>${t("equipped_slots")}</h3><div class="status">${chip(`${d.inventory_summary.equipped_count} ${t("equipped")}`)}${chip(`${d.hero.hero_power} ${t("hero_power")}`)}</div></div><div class="body">${equippedNow}<div class="grid3">${slots}</div><div class="row"><button data-action="autoequip">${t("equip_best")}</button><button class="secondary" data-action="refresh">${t("refresh_checks")}</button></div></div></section><section class="panel"><div class="head"><h3>${t("inventory")}</h3><div class="toolbar"><select id="inventory-filter"><option value="all">${t("all_items")}</option><option value="equippable">${t("equippable")}</option><option value="equipped">${t("equipped_only")}</option><option value="recipes">${t("recipes")}</option><option value="materials">${t("materials_filter")}</option></select><select id="inventory-sort"><option value="recommended">${t("suggested_first")}</option><option value="score">${t("highest_score")}</option><option value="power">${t("highest_power")}</option><option value="quality">${t("highest_quality")}</option><option value="rarity">${t("highest_rarity")}</option><option value="name">${t("name")}</option><option value="newest">${t("newest")}</option></select><input id="inventory-search" placeholder="${t("search_item")}"></div></div><div id="inventory-panel" class="body"></div></section></div>`}
function crafting(d){const recipes=d.recipes.known.length?d.recipes.known.map(r=>`<div class="card ${store.flash&&store.flash.recipe_code===r.code?"focus":""}"><div class="row"><strong>${esc(r.name)}</strong>${chip(r.code)}${r.can_craft?chip(store.lang==="ru"?"Можно":"Craftable","good"):chip(store.lang==="ru"?"Нет ресурсов":"Blocked","warn")}</div><div class="row">${chip(`${r.materials} ${t("materials")}`)}${chip(`${r.gold} ${t("gold")}`)}${chip(`${r.craftable_count}x ${store.lang==="ru"?"сейчас":"now"}`,r.craftable_count?"good":"")}</div><div class="muted">${esc(r.status)}</div><div class="row">${r.missing_materials?chip(`${store.lang==="ru"?"Не хватает": "Missing"} ${r.missing_materials} ${store.lang==="ru"?"мат." : "mats"}`,"warn"):""}${r.missing_gold?chip(`${store.lang==="ru"?"Не хватает": "Missing"} ${r.missing_gold} ${t("gold")}`,"warn"):""}</div><button ${r.can_craft?"":"disabled"} data-action="craft" data-recipe="${esc(r.code)}">${t("craft_now")}</button></div>`).join(""):`<div class="empty">${t("no_recipes")}</div>`;const drops=d.recipes.blueprints.length?d.recipes.blueprints.map(i=>itemCard(i,{learn:true})).join(""):`<div class="empty">${t("no_blueprints")}</div>`;const readyCount=d.recipes.known.filter(r=>r.can_craft).length;return `<div class="cards"><section class="panel"><div class="head"><h3>${t("crafting_overview")}</h3><div class="status">${chip(`${d.inventory_summary.materials} ${t("materials")}`)}${chip(`${d.hero.gold} ${t("gold")}`)}${chip(`${d.recipes.known.length} ${t("recipes")}`)}</div></div><div class="body"><div class="grid4">${metric(t("materials"),d.inventory_summary.materials,store.lang==="ru"?"Разбор и добыча":"Salvage and dungeon drops")}${metric(t("gold"),d.hero.gold,store.lang==="ru"?"Тратится на крафт":"Used by crafting and upgrades")}${metric(t("blueprints"),d.inventory_summary.blueprints,store.lang==="ru"?"Неизученные чертежи":"Unlearned recipe drops")}${metric(t("ready_recipes"),readyCount,store.lang==="ru"?"Можно крафтить прямо сейчас":"Can be crafted right now")}</div><div class="row"><button data-action="forge">${t("forge_step")}</button><button class="secondary" data-action="refresh">${t("refresh_materials")}</button></div></div></section><section class="panel"><div class="head"><h3>${t("craftable_recipes")}</h3><div class="status">${chip(`${readyCount} ${t("ready")}`,readyCount?"good":"")}</div></div><div class="body"><div class="grid2">${recipes}</div></div></section><section class="panel"><div class="head"><h3>${t("blueprint_drops")}</h3><div class="status">${chip(`${d.recipes.blueprints.length} ${store.lang==="ru"?"ожидают":"waiting"}`,d.recipes.blueprints.length?"warn":"")}</div></div><div class="body"><div class="grid2">${drops}</div></div></section></div>`}
function progression(d){const statButtons=Object.entries(d.hero.stats).map(([k,v])=>`<div class="card"><div class="metric">${esc(k)}</div><div class="big">${esc(v)}</div><button ${d.hero.unspent_stat_points>0?"":"disabled"} data-action="stat" data-stat="${esc(k)}">${store.lang==="ru"?"Добавить 1":"Spend 1 point"}</button></div>`).join("");const learned=d.perks.learned.length?d.perks.learned.map(p=>`<div class="card"><strong>${esc(p.name)}</strong><div class="muted">${esc(p.description)}</div></div>`).join(""):`<div class="empty">${store.lang==="ru"?"Пассивки ещё не изучены.":"No perks learned yet."}</div>`;const available=d.perks.available.length?d.perks.available.map(p=>`<div class="card"><div class="metric">${esc(p.code)}</div><strong>${esc(p.name)}</strong><div class="muted">${esc(p.description)}</div><button ${d.hero.perk_points>0?"":"disabled"} data-action="perk" data-perk="${esc(p.code)}">${t("learn_perk")}</button></div>`).join(""):`<div class="empty">${store.lang==="ru"?"Доступных пассивок сейчас нет.":"No perk choices available right now."}</div>`;return `<div class="cards"><section class="panel"><div class="head"><h3>${t("allocation")}</h3><div class="status">${chip(`${d.hero.unspent_stat_points} ${t("stats_pts")}`,d.hero.unspent_stat_points?"warn":"")}${chip(`${d.hero.perk_points} ${t("perk_pts")}`,d.hero.perk_points?"warn":"")}</div></div><div class="body"><div class="grid3"><div class="card"><div class="metric">${t("specialization")}</div><select id="specialization-select">${d.specializations.map(s=>`<option value="${esc(s)}" ${s===d.hero.specialization?"selected":""}>${esc(s)}</option>`).join("")}</select><button data-action="specialization">${t("apply_specialization")}</button></div><div class="card"><div class="metric">${t("manual_time")}</div><input id="ticks-input" type="number" min="1" max="50" value="3"><button data-action="tick">${t("run_ticks")}</button></div><div class="card"><div class="metric">${t("camp_hold")}</div><div class="muted">${esc(d.hero.awaiting_text)}</div><button ${d.hero.awaiting_player?"":"disabled"} data-action="resume">${t("resume_runs")}</button></div></div><div class="hero-grid">${statButtons}</div></div></section><section class="panel"><div class="head"><h3>${t("perks")}</h3><div class="status">${chip(`${d.perks.learned.length} ${store.lang==="ru"?"изучено":"learned"}`)}${chip(`${d.perks.available.length} ${store.lang==="ru"?"доступно":"available"}`)}</div></div><div class="body"><div class="grid2">${learned}</div><div class="grid2">${available}</div></div></section></div>`}
function activity(d){const log=d.activity_log.length?d.activity_log.map(line=>`<div class="card"><div class="muted">${esc(line)}</div></div>`).join(""):`<div class="empty">${store.lang==="ru"?"Недавних событий пока нет.":"No recent activity yet."}</div>`;return `<div class="cards"><section class="panel"><div class="head"><h3>${t("recent_activity")}</h3><div class="status">${chip(d.world.last_event)}</div></div><div class="body">${log}</div></section><section class="panel"><div class="head"><h3>${t("device_preview")}</h3><div class="status">${chip(d.device.battery_text,d.device.low_power_mode?"warn":"")}</div></div><div class="body"><pre class="preview">${esc(d.screen_preview)}</pre></div></section><section class="panel"><div class="head"><h3>${t("developer_tools")}</h3><div class="status">${chip(t("debug_only"))}</div></div><div class="body"><div class="grid3"><div class="card"><div class="metric">${store.lang==="ru"?"Добавить припасы":"Add Supplies"}</div><input id="dev-supplies" type="number" value="5"><button data-action="supplies">${store.lang==="ru"?"Применить":"Apply"}</button></div><div class="card"><div class="metric">${store.lang==="ru"?"Добавить золото":"Add Gold"}</div><input id="dev-gold" type="number" value="100"><button data-action="gold">${store.lang==="ru"?"Применить":"Apply"}</button></div><div class="card"><div class="metric">${store.lang==="ru"?"Добавить XP":"Add XP"}</div><input id="dev-xp" type="number" value="50"><button data-action="xp">${store.lang==="ru"?"Применить":"Apply"}</button></div></div><pre class="raw">${esc(JSON.stringify(d.raw_state,null,2))}</pre></div></section></div>`}
function match(item){if(store.filter==="equippable"&&!item.can_equip)return false;if(store.filter==="equipped"&&!item.equipped)return false;if(store.filter==="recipes"&&item.type!=="recipe")return false;if(store.filter==="materials"&&item.type!=="material")return false;if(store.search&&!item.name.toLowerCase().includes(store.search.toLowerCase()))return false;return true}
function sortItems(items){const rr={common:0,uncommon:1,rare:2,epic:3,mythic:4};const list=[...items].filter(match);list.sort((a,b)=>{if(store.sort==="name")return a.name.localeCompare(b.name);if(store.sort==="power")return b.power-a.power||b.quality-a.quality;if(store.sort==="quality")return b.quality-a.quality||b.power-a.power;if(store.sort==="rarity")return (rr[b.rarity]??0)-(rr[a.rarity]??0)||b.power-a.power;if(store.sort==="score")return (b.score??0)-(a.score??0)||b.power-a.power;if(store.sort==="newest")return b.index-a.index;return Number(b.recommended)-Number(a.recommended)||Number(b.equipped)-Number(a.equipped)||(b.score??0)-(a.score??0)});return list}
function renderInventory(){const panel=document.getElementById("inventory-panel");if(!panel||!store.data)return;const items=sortItems(store.data.inventory);panel.innerHTML=items.length?items.map(i=>itemCard(i,{equip:true,learn:true})).join(""):`<div class="empty">Nothing matches this inventory view.</div>`;const f=document.getElementById("inventory-filter"),s=document.getElementById("inventory-sort"),q=document.getElementById("inventory-search");if(f)f.value=store.filter;if(s)s.value=store.sort;if(q)q.value=store.search}
function content(){const d=store.data;if(!d)return "";if(store.view==="gear")return gear(d);if(store.view==="crafting")return crafting(d);if(store.view==="progression")return progression(d);if(store.view==="activity")return activity(d);return overview(d)}
function render(){if(!store.data)return;renderSidebar();renderTopbar();const c=document.getElementById("content");if(c)c.innerHTML=content();renderInventory()}
function notice(msg,t="good"){const n=document.getElementById("notice");if(!n)return;n.textContent=msg;n.className=`notice visible ${t}`;clearTimeout(notice.timer);notice.timer=setTimeout(()=>n.className="notice",3200)}
async function fetchState(silent=false){if(!silent)store.busy=true;const r=await fetch("/api/manager-state");store.data=await r.json();render();store.busy=false}
async function run(action,payload={}){if(store.busy)return;store.busy=true;try{const map={equip:"gear",autoequip:"gear",forge:"crafting",learn:"crafting",craft:"crafting",perk:"progression",stat:"progression"};const r=await fetch("/api/action",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action,...payload})});const data=await r.json();if(!r.ok||!data.ok)throw new Error(data.message||`Action failed: ${action}`);store.data=data.state;if(map[action])store.view=map[action];if(action==="equip"){const item=store.data.inventory.find(i=>i.index===payload.index);store.flash={action,index:payload.index,slot:item?.slot,name:item?.name||""}}else if(action==="craft"){store.flash={action,recipe_code:payload.recipe_code}}else if(action==="learn"){store.flash={action,index:payload.index}}else{store.flash={action}}render();notice(localNotice(action,payload,store.data,data.message));setTimeout(()=>{store.flash=null;render();},1800)}catch(e){notice(e.message|| (store.lang==="ru"?"Действие завершилось ошибкой.":"Action failed."),"bad")}finally{store.busy=false}}
document.addEventListener("change",e=>{const t=e.target;if(t.id==="inventory-filter"){store.filter=t.value;renderInventory()}if(t.id==="inventory-sort"){store.sort=t.value;renderInventory()}if(t.id==="inventory-search"){store.search=t.value;renderInventory()}});
document.addEventListener("input",e=>{const t=e.target;if(t.id==="inventory-search"){store.search=t.value;renderInventory()}});
document.addEventListener("click",async e=>{const lang=e.target.closest("[data-lang]");if(lang){setLang(lang.dataset.lang);return}const v=e.target.closest("[data-view]");if(v){store.view=v.dataset.view;render();return}const b=e.target.closest("[data-action]");if(!b)return;const a=b.dataset.action;if(a==="refresh"){await fetchState(true);notice(store.lang==="ru"?"Состояние обновлено.":"State refreshed.");return}if(a==="equip"){await run("equip",{index:Number(b.dataset.index)});return}if(a==="learn"){await run("learn",{index:Number(b.dataset.index)});return}if(a==="craft"){await run("craft",{recipe_code:b.dataset.recipe});return}if(a==="perk"){await run("perk",{perk_code:b.dataset.perk});return}if(a==="stat"){await run("stat",{stat:b.dataset.stat});return}if(a==="tickQuick"){await run("tick",{ticks:Number(b.dataset.ticks||"1")});return}if(a==="tick"){await run("tick",{ticks:Number(document.getElementById("ticks-input")?.value||"1")});return}if(a==="specialization"){await run("specialization",{specialization:document.getElementById("specialization-select")?.value||""});return}if(a==="supplies"||a==="gold"||a==="xp"){await run(a,{amount:Number(document.getElementById(`dev-${a}`)?.value||"0")});return}await run(a)});
fetchState().catch(e=>notice(e.message||"Failed to load manager.","bad"));
</script></body></html>"""


class ManagerHandler(BaseHTTPRequestHandler):
    save_path = DEFAULT_SAVE_PATH
    engine = GameEngine()
    renderer = TextRenderer()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        state = load_save(self.save_path)
        if parsed.path == "/api/state":
            self._send_json(state.to_dict())
            return
        if parsed.path == "/api/manager-state":
            self._send_json(self._build_manager_state(state))
            return
        if parsed.path != "/":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._send_html(build_html())

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        state = load_save(self.save_path)
        payload = self._parse_payload()
        if parsed.path == "/api/action":
            self._handle_api_action(state, str(payload.get("action", "")), payload)
            return
        action = parsed.path.lstrip("/")
        if not action:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._handle_legacy_action(state, action, payload)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _parse_payload(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        content_type = self.headers.get("Content-Type", "")
        if "application/json" in content_type:
            try:
                parsed = json.loads(raw or "{}")
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        form = parse_qs(raw, keep_blank_values=True)
        return {key: values[0] if values else "" for key, values in form.items()}

    def _handle_api_action(self, state: SaveState, action: str, payload: dict[str, object]) -> None:
        ok, message = self._apply_action(state, action, payload)
        if ok:
            save_state(state, self.save_path)
        final_state = load_save(self.save_path) if ok else state
        status = HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST
        self._send_json(
            {"ok": ok, "message": message, "state": self._build_manager_state(final_state)},
            status=status,
        )

    def _handle_legacy_action(self, state: SaveState, action: str, payload: dict[str, object]) -> None:
        ok, _message = self._apply_action(state, action, payload)
        if ok:
            save_state(state, self.save_path)
        self._redirect_home()

    def _apply_action(self, state: SaveState, action: str, payload: dict[str, object]) -> tuple[bool, str]:
        if action == "grant":
            item_type = str(payload.get("item_type", "material"))
            item = Item(
                name=str(payload.get("name", "Item")),
                item_type=item_type,
                rarity=str(payload.get("rarity", "common")),
                power=self._to_int(payload.get("power"), 0),
                level=self._to_int(payload.get("level"), 1),
                quality=self._to_int(payload.get("quality"), 0),
                quantity=1,
                slot=infer_slot(item_type),
                stat_bonuses=zero_stats(),
                recipe_code=str(payload.get("recipe_code", "")),
            )
            state.inventory.append(item)
            state.activity_log.append(f"Manager granted item: {item.name}.")
            return True, f"Granted item: {item.name}."

        if action == "supplies":
            amount = self._to_int(payload.get("amount"), 0)
            state.character.supplies += amount
            state.activity_log.append(f"Manager added {amount} supplies.")
            return True, f"Added {amount} supplies."

        if action == "gold":
            amount = self._to_int(payload.get("amount"), 0)
            state.character.gold += amount
            state.activity_log.append(f"Manager added {amount} gold.")
            return True, f"Added {amount} gold."

        if action == "xp":
            amount = self._to_int(payload.get("amount"), 0)
            state.character.experience += amount
            state.activity_log.append(f"Manager added {amount} XP.")
            return True, f"Added {amount} XP."

        if action == "specialization":
            chosen = str(payload.get("specialization", state.character.specialization))
            valid = {spec.value for spec in Specialization}
            if chosen not in valid:
                return False, "Unknown specialization."
            state.character.specialization = chosen
            self._clear_hold(state)
            state.activity_log.append(f"Manager set specialization to {chosen}.")
            return True, f"Specialization changed to {chosen}."

        if action == "stat":
            stat_name = str(payload.get("stat", "power"))
            if state.character.unspent_stat_points <= 0:
                return False, "No stat points available."
            if not hasattr(state.character.stats, stat_name):
                return False, "Unknown stat."
            setattr(state.character.stats, stat_name, getattr(state.character.stats, stat_name) + 1)
            state.character.unspent_stat_points -= 1
            self._clear_hold(state)
            state.activity_log.append(f"Manager spent 1 stat point on {stat_name}.")
            return True, f"Spent 1 point on {stat_name}."

        if action == "equip":
            index = self._to_int(payload.get("index"), -1)
            if not (0 <= index < len(state.inventory)):
                return False, "No such inventory item."
            item = state.inventory[index]
            if item.slot is None:
                return False, "This item cannot be equipped."
            for other in state.inventory:
                if other.slot == item.slot:
                    other.equipped = False
            item.equipped = True
            self._clear_hold(state)
            state.activity_log.append(f"Manager equipped {item.name}.")
            return True, f"Equipped {item.name}."

        if action == "autoequip":
            if not auto_equip_inventory(state):
                return False, "Current gear is already optimal."
            self._clear_hold(state)
            state.activity_log.append("Manager triggered auto-equip.")
            return True, "Equipped the best known items."

        if action == "tick":
            ticks = max(1, min(50, self._to_int(payload.get("ticks"), 1)))
            for _ in range(ticks):
                self.engine.tick(state)
            state.activity_log.append(f"Manager advanced {ticks} ticks.")
            return True, f"Advanced {ticks} ticks."

        if action == "forge":
            summary, _loot = self.engine.forge(state)
            state.activity_log.append(f"Manager triggered forge: {summary}")
            return True, summary

        if action == "learn":
            summary = self.engine.learn_recipe(state, self._to_int(payload.get("index"), -1))
            state.activity_log.append(f"Manager learn action: {summary}")
            bad = summary.startswith("No such") or "not a recipe" in summary
            return not bad, summary

        if action == "craft":
            summary, _loot = self.engine.craft_recipe(state, str(payload.get("recipe_code", "")))
            state.activity_log.append(f"Manager craft action: {summary}")
            bad = "unknown" in summary.lower() or "not enough" in summary.lower()
            return not bad, summary

        if action == "resume":
            self._clear_hold(state)
            state.activity_log.append("Manager released hero from camp hold.")
            return True, "Hero released from camp hold."

        if action == "perk":
            summary = self.engine.choose_perk(state, str(payload.get("perk_code", "")))
            state.activity_log.append(f"Manager perk action: {summary}")
            bad = (
                "No perk points" in summary
                or "Unknown perk" in summary
                or "does not match" in summary
                or "already chosen" in summary
            )
            return not bad, summary

        return False, "Unknown action."

    def _build_manager_state(self, state: SaveState) -> dict[str, object]:
        frame = self.renderer.build_frame(state, self.engine)
        c = state.character
        total_stats = self.engine.total_stats(state)
        inventory = self._serialize_inventory(state)
        equipment = self._build_equipment(state, inventory)
        materials = self._material_count(state)
        blueprints = [item for item in inventory if item["type"] == ItemType.RECIPE.value]
        known_recipes = self._build_known_recipes(state, materials)
        return {
            "hero": {
                "name": c.name,
                "title": c.title,
                "specialization": c.specialization,
                "activity": c.current_activity,
                "summary": self._hero_summary(state),
                "level": c.level,
                "experience": c.experience,
                "gold": c.gold,
                "supplies": c.supplies,
                "depth": c.dungeon_depth,
                "mood": c.mood,
                "wins": c.wins,
                "losses": c.losses,
                "loss_streak": c.loss_streak,
                "unspent_stat_points": c.unspent_stat_points,
                "perk_points": c.perk_points,
                "stats": {
                    "power": c.stats.power,
                    "vitality": c.stats.vitality,
                    "agility": c.stats.agility,
                    "insight": c.stats.insight,
                    "luck": c.stats.luck,
                },
                "total_stats": {
                    "power": total_stats.power,
                    "vitality": total_stats.vitality,
                    "agility": total_stats.agility,
                    "insight": total_stats.insight,
                    "luck": total_stats.luck,
                },
                "hero_power": self.engine.hero_power(state),
                "awaiting_player": c.awaiting_player,
                "awaiting_text": c.awaiting_reason or "Autonomous",
                "bosses_defeated": c.bosses_defeated,
                "readiness_label": self._readiness_label(state),
                "readiness_tone": self._readiness_tone(state),
                "readiness_detail": self._readiness_detail(state),
                "readiness_code": self._readiness_code(state),
                "readiness_targets": self._readiness_targets(state),
                "perks": [
                    {
                        "code": code,
                        "name": PERK_DEFS.get(code, {}).get("name", code),
                        "description": PERK_DEFS.get(code, {}).get("description", ""),
                    }
                    for code in c.perks
                ],
            },
            "world": {
                "region": state.world.current_region,
                "threat": state.world.current_threat,
                "danger_rating": state.world.danger_rating,
                "biome_tier": state.world.biome_tier,
                "boss_active": state.world.boss_active,
                "boss_status": self._boss_status(state),
                "last_event": state.world.last_event,
            },
            "device": {
                "battery_percent": state.device.battery_percent,
                "battery_detail": self._format_battery_detail(state),
                "battery_text": self._format_battery_text(state),
                "low_power_mode": state.device.low_power_mode,
            },
            "inventory_summary": {
                "count": len(inventory),
                "equipped_count": sum(1 for item in inventory if item["equipped"]),
                "materials": materials,
                "blueprints": len(blueprints),
            },
            "inventory": inventory,
            "equipment": equipment,
            "passives": self.engine.passive_effects(state),
            "recipes": {
                "known": known_recipes,
                "blueprints": blueprints,
                "ready_count": sum(1 for recipe in known_recipes if recipe["can_craft"]),
            },
            "perks": {
                "learned": [
                    {
                        "code": code,
                        "name": PERK_DEFS.get(code, {}).get("name", code),
                        "description": PERK_DEFS.get(code, {}).get("description", ""),
                    }
                    for code in c.perks
                ],
                "available": self.engine.available_perks(state),
            },
            "activity_log": list(reversed(state.activity_log[-8:])),
            "screen_preview": self.renderer.render_to_text(frame),
            "specializations": [spec.value for spec in Specialization],
            "next_steps": self._build_next_steps(state, equipment, blueprints, known_recipes),
            "raw_state": state.to_dict(),
        }

    def _serialize_inventory(self, state: SaveState) -> list[dict[str, object]]:
        best_indices = self._best_indices_by_slot(state)
        items: list[dict[str, object]] = []
        for index, item in enumerate(state.inventory):
            parts = []
            if item.slot:
                parts.append(self._slot_label(item.slot))
            if item.affixes:
                parts.append(", ".join(item.affixes))
            if any(vars(item.stat_bonuses).values()):
                parts.append(
                    " ".join(
                        f"{stat[0].upper()}+{value}"
                        for stat, value in vars(item.stat_bonuses).items()
                        if value
                    )
                )
            if item.recipe_code:
                recipe = RECIPE_DEFS.get(item.recipe_code)
                if recipe:
                    parts.append(f"Crafts {recipe['item_type']}")
            items.append(
                {
                    "index": index,
                    "name": item.name,
                    "type": item.item_type,
                    "rarity": item.rarity,
                    "power": item.power,
                    "quality": item.quality,
                    "level": item.level,
                    "slot": item.slot,
                    "slot_label": self._slot_label(item.slot),
                    "equipped": item.equipped,
                    "crafted": item.crafted,
                    "quantity": item.quantity,
                    "recipe_code": item.recipe_code,
                    "summary": " | ".join(part for part in parts if part) or "No extra modifiers.",
                    "score": self._item_score(item) if item.slot else 0,
                    "recommended": bool(item.slot and best_indices.get(item.slot) == index and not item.equipped),
                    "can_equip": item.slot in {
                        EquipmentSlot.MAIN_HAND.value,
                        EquipmentSlot.BODY.value,
                        EquipmentSlot.CHARM.value,
                    },
                    "can_learn": item.item_type == ItemType.RECIPE.value and bool(item.recipe_code),
                }
            )
        return items

    def _build_equipment(self, state: SaveState, inventory: list[dict[str, object]]) -> list[dict[str, object]]:
        equipped_by_slot = {slot.value: None for slot in EquipmentSlot}
        for item in inventory:
            if item["equipped"] and item["slot"]:
                equipped_by_slot[str(item["slot"])] = item
        best_indices = self._best_indices_by_slot(state)
        by_index = {item["index"]: item for item in inventory}
        result = []
        for slot in EquipmentSlot:
            current = equipped_by_slot.get(slot.value)
            recommended = by_index.get(best_indices.get(slot.value, -1))
            result.append(
                {
                    "slot": slot.value,
                    "label": self._slot_label(slot.value),
                    "current": current,
                    "recommended": recommended,
                    "score_delta": (
                        int(recommended["score"]) - int(current["score"])
                        if recommended and current
                        else int(recommended["score"]) if recommended else 0
                    ),
                    "has_upgrade": bool(recommended and (current is None or recommended["index"] != current["index"])),
                }
            )
        return result

    def _build_known_recipes(self, state: SaveState, materials: int) -> list[dict[str, object]]:
        recipes = []
        for code in state.character.known_recipes:
            recipe = RECIPE_DEFS.get(code)
            if recipe is None:
                continue
            enough_materials = materials >= recipe["materials"]
            enough_gold = state.character.gold >= recipe["gold"]
            if enough_materials and enough_gold:
                status = "Ready to craft right now."
            else:
                missing = []
                if not enough_materials:
                    missing.append(f"{recipe['materials'] - materials} materials")
                if not enough_gold:
                    missing.append(f"{recipe['gold'] - state.character.gold} gold")
                status = "Missing " + ", ".join(missing) + "."
            recipes.append(
                {
                    "code": code,
                    "name": recipe["name"],
                    "item_type": recipe["item_type"],
                    "materials": recipe["materials"],
                    "gold": recipe["gold"],
                    "quality": recipe["quality"],
                    "can_craft": enough_materials and enough_gold,
                    "craftable_count": min(
                        materials // recipe["materials"] if recipe["materials"] > 0 else 0,
                        state.character.gold // recipe["gold"] if recipe["gold"] > 0 else 0,
                    ),
                    "missing_materials": max(0, recipe["materials"] - materials),
                    "missing_gold": max(0, recipe["gold"] - state.character.gold),
                    "status": status,
                }
            )
        return recipes

    def _build_next_steps(
        self,
        state: SaveState,
        equipment: list[dict[str, object]],
        blueprints: list[dict[str, object]],
        known_recipes: list[dict[str, object]],
    ) -> list[dict[str, str]]:
        steps: list[dict[str, str]] = []
        c = state.character
        if c.awaiting_player:
            steps.append(
                {
                    "code": "camp_hold",
                    "tone": "bad",
                    "title": "Hero is waiting in camp.",
                    "detail": c.awaiting_reason or "Resolve progression choices before sending the hero out again.",
                    "reason": c.awaiting_reason,
                }
            )
        if c.unspent_stat_points > 0:
            steps.append(
                {
                    "code": "stat_points",
                    "tone": "warn",
                    "title": f"{c.unspent_stat_points} stat points unspent.",
                    "detail": "Spend them before deeper runs so the hero stops wasting progression.",
                    "count": c.unspent_stat_points,
                }
            )
        if c.perk_points > 0:
            steps.append(
                {
                    "code": "perk_points",
                    "tone": "warn",
                    "title": f"{c.perk_points} perk points available.",
                    "detail": "Pick a specialization perk. These are a major part of the power curve now.",
                    "count": c.perk_points,
                }
            )
        if blueprints:
            steps.append(
                {
                    "code": "blueprints_waiting",
                    "tone": "warn",
                    "title": f"{len(blueprints)} blueprint drops waiting.",
                    "detail": "Learn them first so future runs can turn into better gear.",
                    "count": len(blueprints),
                }
            )
        upgrades = [slot for slot in equipment if slot["has_upgrade"]]
        if upgrades:
            names = ", ".join(str(slot["label"]) for slot in upgrades[:3])
            steps.append(
                {
                    "code": "gear_upgrades",
                    "tone": "warn",
                    "title": "Better gear is already in the bag.",
                    "detail": f"Suggested upgrades exist for {names}. Equip them before pushing deeper.",
                    "targets": names,
                }
            )
        craft_ready = [recipe for recipe in known_recipes if recipe["can_craft"]]
        if craft_ready:
            steps.append(
                {
                    "code": "craft_ready",
                    "tone": "good",
                    "title": f"{len(craft_ready)} recipes are craftable now.",
                    "detail": "Use crafting to break gear walls instead of waiting for random drops.",
                    "count": len(craft_ready),
                }
            )
        if not steps:
            steps.append(
                {
                    "code": "autonomy_healthy",
                    "tone": "good",
                    "title": "Autonomy is healthy.",
                    "detail": "No obvious blockers right now. Let the hero run or push a few manual ticks.",
                }
            )
        return steps[:6]

    def _best_indices_by_slot(self, state: SaveState) -> dict[str, int]:
        best: dict[str, tuple[int, int]] = {}
        for index, item in enumerate(state.inventory):
            if item.slot is None:
                continue
            score = self._item_score(item)
            current = best.get(item.slot)
            if current is None or score > current[0]:
                best[item.slot] = (score, index)
        return {slot: index for slot, (_score, index) in best.items()}

    @staticmethod
    def _item_score(item: Item) -> int:
        return (
            item.power
            + item.stat_bonuses.power
            + item.stat_bonuses.vitality
            + item.stat_bonuses.agility
            + item.stat_bonuses.insight
            + item.stat_bonuses.luck
            + item.quality * 3
        )

    @staticmethod
    def _slot_label(slot: str | None) -> str:
        if slot == EquipmentSlot.MAIN_HAND.value:
            return "Weapon"
        if slot == EquipmentSlot.BODY.value:
            return "Armor"
        if slot == EquipmentSlot.CHARM.value:
            return "Charm"
        return "-"

    @staticmethod
    def _material_count(state: SaveState) -> int:
        return sum(item.quantity for item in state.inventory if item.item_type == ItemType.MATERIAL.value)

    @staticmethod
    def _to_int(value: object, default: int) -> int:
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _clear_hold(state: SaveState) -> None:
        state.character.awaiting_player = False
        state.character.awaiting_reason = ""
        state.character.loss_streak = 0

    def _boss_status(self, state: SaveState) -> str:
        if state.world.boss_active:
            return f"{state.world.boss_name} lvl {state.world.boss_level}"
        return f"Next boss in {state.world.boss_countdown} clears"

    def _format_battery_text(self, state: SaveState) -> str:
        if state.device.battery_percent is None:
            return "Battery ?"
        return f"Battery {state.device.battery_percent}%"

    def _format_battery_detail(self, state: SaveState) -> str:
        if state.device.battery_percent is None and state.device.battery_voltage is None:
            return "No battery telemetry."
        percent = "?" if state.device.battery_percent is None else f"{state.device.battery_percent}%"
        voltage = "?" if state.device.battery_voltage is None else f"{state.device.battery_voltage:.2f}V"
        charging = "charging" if state.device.charging else "not charging"
        low = "low power" if state.device.low_power_mode else "normal"
        return f"{percent} · {voltage} · {charging} · {low}"

    def _hero_summary(self, state: SaveState) -> str:
        c = state.character
        parts = [
            f"{c.specialization} at depth {c.dungeon_depth}",
            f"mood {c.mood}",
            f"{c.bosses_defeated} bosses defeated",
        ]
        if c.awaiting_player:
            parts.append(f"waiting: {c.awaiting_reason or 'player input needed'}")
        return " | ".join(parts)

    def _readiness_code(self, state: SaveState) -> str:
        c = state.character
        if c.awaiting_player:
            return "hold"
        if c.unspent_stat_points > 0 or c.perk_points > 0:
            return "needs_setup"
        if any(slot["has_upgrade"] for slot in self._build_equipment(state, self._serialize_inventory(state))):
            return "gear_available"
        return "ready"

    def _readiness_targets(self, state: SaveState) -> str:
        inventory = self._serialize_inventory(state)
        equipment = self._build_equipment(state, inventory)
        upgrades = [str(slot["label"]) for slot in equipment if slot["has_upgrade"]]
        return ", ".join(upgrades[:3])

    def _readiness_label(self, state: SaveState) -> str:
        code = self._readiness_code(state)
        if code == "hold":
            return "Hold"
        if code == "needs_setup":
            return "Needs Setup"
        if code == "gear_available":
            return "Gear Available"
        return "Ready"

    def _readiness_tone(self, state: SaveState) -> str:
        label = self._readiness_label(state)
        if label == "Ready":
            return "good"
        if label == "Hold":
            return "bad"
        return "warn"

    def _readiness_detail(self, state: SaveState) -> str:
        c = state.character
        if c.awaiting_player:
            return c.awaiting_reason or "Hero is refusing deeper runs until you intervene."
        if c.unspent_stat_points > 0 and c.perk_points > 0:
            return "Spend stat points and choose a perk before sending the hero back out."
        if c.unspent_stat_points > 0:
            return "Unspent stat points are lowering effective power."
        if c.perk_points > 0:
            return "A perk choice is waiting and should be resolved before progression."
        inventory = self._serialize_inventory(state)
        equipment = self._build_equipment(state, inventory)
        upgrades = [slot["label"] for slot in equipment if slot["has_upgrade"]]
        if upgrades:
            return f"Better items are available for {', '.join(upgrades[:3])}."
        return "No obvious blockers. The hero can run autonomously."

    def _send_html(self, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _redirect_home(self) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/")
        self.end_headers()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PiGame desktop manager")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--save", type=Path, default=DEFAULT_SAVE_PATH)
    args = parser.parse_args(argv)

    ManagerHandler.save_path = args.save
    server = ThreadingHTTPServer((args.host, args.port), ManagerHandler)
    print(f"PiGame manager listening on http://{args.host}:{args.port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
