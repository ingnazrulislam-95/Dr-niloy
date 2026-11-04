"use strict";
const $ = s => document.querySelector(s);
const iso = d => { const t = new Date(d); return t.getFullYear() + "-" + String(t.getMonth() + 1).padStart(2, "0") + "-" + String(t.getDate()).padStart(2, "0"); };
const off = n => { const d = new Date(); d.setDate(d.getDate() + n); return iso(d); };
const TODAY = off(0);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const money = n => "€" + Number(n).toFixed(2);
const kb = n => n < 1024 ? n + " B" : n < 1048576 ? Math.round(n / 1024) + " KB" : (n / 1048576).toFixed(1) + " MB";
const LOCS = ["Savar clinic", "Enam clinic", "Private chamber"];
const CATS = ["Lab report", "Imaging", "Prescription", "Referral letter", "Consent form", "Other"];
const ROLE = { owner: "Clinic owner", doctor: "Doctor", receptionist: "Receptionist" };
let S = { doctors: [], patients: [], appts: [], inv: [], docs: [], users: [] };
let me = null, q = "";
const af = { q: "", c: "All" };
const P = id => S.patients.find(p => p.id === id) || { name: "Unknown", visits: [] };
const D = id => S.doctors.find(d => d.id === id) || { name: "Unknown" };
const status = i => i.paid >= i.amount ? "Paid" : i.paid > 0 ? "Partial" : "Unpaid";
const clinical = () => me && (me.role === "owner" || me.role === "doctor");
const opts = (arr, k, v, sel) => arr.map(x => `<option value="${esc(x[k])}"${x[k] === sel ? " selected" : ""}>${esc(typeof v === "function" ? v(x) : x[v])}</option>`).join("");
const isImg = n => /\.(png|jpe?g|webp|gif)$/i.test(n);

async function api(path, opt = {}) {
  const o = { credentials: "same-origin", ...opt };
  if (o.json !== undefined) { o.method = o.method || "POST"; o.headers = { "Content-Type": "application/json" }; o.body = JSON.stringify(o.json); delete o.json; }
  const r = await fetch("/api" + path, o);
  if (r.status === 401 && path !== "/login" && path !== "/me") { me = null; render(); throw new Error("Please sign in again."); }
  if (!r.ok) {
    let m = "Something went wrong. Try again.";
    try { const j = await r.json(); m = typeof j.detail === "string" ? j.detail : "Check the form and try again."; } catch (e) { }
    throw new Error(m);
  }
  return r.status === 204 ? null : r.json();
}
async function load() { S = await api("/state"); }
async function refresh() { await load(); render(); }

function msg(t, m) { const d = $("#dlg"); d.innerHTML = `<h2>${t}</h2><p>${m}</p><div class="acts"><button onclick="$('#dlg').close()">Close</button></div>`; d.showModal(); }
function dlg(title, body, onOk, okLabel) {
  const d = $("#dlg");
  d.innerHTML = `<h2>${title}</h2><div style="height:10px"></div><form method="dialog" id="f">${body}<div class="err" id="err" role="alert"></div><div class="acts"><button type="button" id="x">Cancel</button><button class="pri">${okLabel}</button></div></form>`;
  $("#x").onclick = () => d.close();
  $("#f").onsubmit = async e => {
    e.preventDefault();
    const btn = e.submitter; if (btn) btn.disabled = true;
    try {
      const fd = new FormData(e.target);
      const m = await onOk(Object.fromEntries(fd), fd);
      if (m) { $("#err").textContent = m; return; }
      d.close(); await refresh();
    } catch (x) { $("#err").textContent = x.message; } finally { if (btn) btn.disabled = false; }
  };
  d.showModal();
}
async function act(fn) { try { await fn(); await refresh(); } catch (e) { msg("Could not do that", esc(e.message)); } }

/* ---------- sign in ---------- */
function login() {
  return `<div class="split"><section class="hero"><div class="logo">Dr. MH Niloy’s Clinic</div><div><h1>Patients, appointments and billing in one place.</h1><p>Sign in to see today’s schedule and open patient records.</p></div><small>Authorised clinic staff only.</small></section><section class="panel"><form id="lf" novalidate><h2>Sign in</h2><p class="sub">Use your clinic account.</p><label>Email<input name="email" type="email" autocomplete="username"></label><label>Password<input name="pw" type="password" autocomplete="current-password"></label><div class="err" id="lerr" role="alert"></div><button class="pri wide">Sign in</button></form></section></div>`;
}
function bindLogin() {
  $("#lf").onsubmit = async e => {
    e.preventDefault();
    const f = e.target, em = f.email.value.trim();
    if (!/^\S+@\S+\.\S+$/.test(em)) return $("#lerr").textContent = "Enter a valid email address.";
    if (!f.pw.value) return $("#lerr").textContent = "Enter your password.";
    try { await api("/login", { json: { email: em, password: f.pw.value } }); me = await api("/me"); await load(); render(); }
    catch (x) { $("#lerr").textContent = x.message; }
  };
}

/* ---------- dashboard ---------- */
function dashboard() {
  const td = S.appts.filter(a => a.date === TODAY).sort((a, b) => a.time.localeCompare(b.time));
  const due = S.inv.reduce((s, i) => s + i.amount - i.paid, 0);
  const rev = S.inv.filter(i => i.date.startsWith(TODAY.slice(0, 7))).reduce((s, i) => s + i.paid, 0);
  const days = [...Array(7)].map((_, k) => off(k - 6));
  const vals = days.map(d => S.inv.filter(i => i.date === d).reduce((s, i) => s + i.paid, 0));
  const mx = Math.max(...vals, 1);
  return `<div class="top"><div><h1>Good day, ${esc(me.name)}</h1><p>${new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</p></div></div>
<div class="stats"><div class="stat"><b>${S.patients.length}</b><span>Registered patients</span></div><div class="stat"><b>${td.length}</b><span>Appointments today</span></div><div class="stat"><b>${S.doctors.length}</b><span>Doctors on staff</span></div><div class="stat"><b>${money(rev)}</b><span>Collected this month</span></div><div class="stat"><b>${money(due)}</b><span>Outstanding</span></div></div>
<div class="grid2"><div class="card"><h2>Today’s appointments</h2>${td.length ? `<div class="scroll"><table><tr><th>Time</th><th>Patient</th><th>Doctor</th><th>Place</th><th>Status</th></tr>${td.map(a => `<tr><td>${a.time}</td><td><a href="#patient-${a.pid.slice(2)}">${esc(P(a.pid).name)}</a></td><td>${esc(D(a.did).name)}</td><td>${esc(a.loc)}</td><td><span class="tag ${a.status}">${a.status}</span></td></tr>`).join("")}</table></div>` : `<p class="empty">No appointments today. Book one from the Appointments page.</p>`}</div>
<div class="card"><h2>Collected, last 7 days</h2><div class="bars">${vals.map((v, k) => `<div title="${money(v)}"><i style="height:${Math.round(v / mx * 100)}px;min-height:2px"></i>${days[k].slice(8)}</div>`).join("")}</div></div></div>`;
}

/* ---------- patients ---------- */
function patients() {
  return `<div class="top"><div><h1>Patients</h1><p>Search by ID, name or phone.</p></div><button class="pri" onclick="newPatient()">Register patient</button></div>
<div class="row"><input id="q" type="search" placeholder="Search patients" value="${esc(q)}" aria-label="Search patients" oninput="q=this.value;$('#pl').innerHTML=prows();labelTables()"></div>
<div class="card scroll"><table><thead><tr><th>ID</th><th>Name</th><th>Date of birth</th><th>Phone</th><th>Last visit</th></tr></thead><tbody id="pl">${prows()}</tbody></table></div>`;
}
function prows() {
  const t = q.trim().toLowerCase();
  const r = S.patients.filter(p => !t || [p.id, p.name, p.phone].some(x => x.toLowerCase().includes(t)));
  if (!r.length) return `<tr><td colspan="5" class="empty">No patient matches “${esc(q)}”. Check the spelling or register a new patient.</td></tr>`;
  return r.map(p => `<tr><td>${p.id}</td><td><a href="#patient-${p.id.slice(2)}">${esc(p.name)}</a></td><td>${p.dob}</td><td>${esc(p.phone)}</td><td>${p.last_visit || "No visits yet"}</td></tr>`).join("");
}
function newPatient() {
  dlg("Register patient", `<label>Full name<input name="name" required></label><label>Date of birth<input name="dob" type="date" required max="${TODAY}"></label><label>Phone<input name="phone" required placeholder="+420 …"></label><label>Allergies<input name="allergies" placeholder="None recorded"></label>`, f => {
    if (f.name.trim().length < 3) return "Enter the patient’s full name.";
    if (!/^[+\d][\d\s]{6,}$/.test(f.phone.trim())) return "Enter a phone number with at least 7 digits.";
    return api("/patients", { json: { name: f.name, dob: f.dob, phone: f.phone, allergies: f.allergies } }).then(() => null);
  }, "Register");
}
function patient(num) {
  const p = S.patients.find(x => x.id === "P-" + num);
  if (!p) return `<p class="empty">Patient not found. <a href="#patients">Back to patients</a></p>`;
  const inv = S.inv.filter(i => i.pid === p.id);
  const vis = [...p.visits].sort((a, b) => b.date.localeCompare(a.date));
  const docs = S.docs.filter(d => d.pid === p.id);
  return `<div class="top"><div><h1>${esc(p.name)}</h1><p>${p.id}</p></div><div class="noprint row"><button onclick="print()">Print record</button>${clinical() ? `<button class="pri" onclick="newVisit('${p.id}')">Add visit note</button>` : ""}</div></div>
<div class="card"><div class="meta"><div>Date of birth<b>${p.dob}</b></div><div>Phone<b>${esc(p.phone)}</b></div><div>Allergies<b>${esc(p.allergies)}</b></div><div>Open balance<b>${money(inv.reduce((s, i) => s + i.amount - i.paid, 0))}</b></div></div></div>
<div class="grid2" style="margin-top:16px">${clinical() ? `<div class="card"><h2>Visit history</h2>${vis.length ? vis.map(v => `<div class="visit"><b>${v.date}</b> <small>${esc(D(v.did).name)}</small><br><b>Symptoms:</b> ${esc(v.symptoms)}<br><b>Diagnosis:</b> ${esc(v.diagnosis)}<br><b>Prescription:</b> ${esc(v.rx || "None")}</div>`).join("") : `<p class="empty">No visits recorded. Add the first visit note.</p>`}</div>` : `<div class="card"><h2>Visit history</h2><p class="empty">Medical notes are visible to doctors only.</p></div>`}
<div class="card"><h2>Invoices</h2>${inv.length ? `<table>${inv.map(i => `<tr><td>${i.no}</td><td>${money(i.amount)}</td><td><span class="tag ${status(i)}">${status(i)}</span></td></tr>`).join("")}</table>` : `<p class="empty">No invoices yet.</p>`}</div></div>
${clinical() ? `<div class="card" style="margin-top:16px"><div class="row" style="justify-content:space-between;margin-bottom:6px"><h2 style="margin:0">Documents</h2><button class="noprint" onclick="upload('${p.id}')">Upload document</button></div>${docTable(docs, false)}</div>` : ""}`;
}
function newVisit(pid) {
  dlg("Add visit note", `<label>Doctor<select name="doctor_id">${opts(S.doctors, "id", "name", me.id)}</select></label><label>Symptoms<textarea name="symptoms" rows="2" required></textarea></label><label>Diagnosis<textarea name="diagnosis" rows="2" required></textarea></label><label>Prescription and plan<textarea name="rx" rows="2"></textarea></label><label>Consultation fee (€, optional)<input name="fee" type="number" min="0" step="0.01"></label>`, f => {
    if (!f.symptoms.trim() || !f.diagnosis.trim()) return "Enter symptoms and a diagnosis.";
    return api(`/patients/${pid}/visits`, { json: { doctor_id: +f.doctor_id, symptoms: f.symptoms, diagnosis: f.diagnosis, rx: f.rx, fee: +f.fee || 0 } }).then(() => null);
  }, "Save note");
}

/* ---------- appointments ---------- */
function appointments() {
  const st = window.fs || "All", dc = window.fd || "All", lc = window.fl || "All";
  const r = S.appts.filter(a => (st === "All" || a.status === st) && (dc === "All" || String(a.did) === dc) && (lc === "All" || a.loc === lc)).sort((a, b) => (a.date + a.time).localeCompare(b.date + b.time));
  return `<div class="top"><div><h1>Appointments</h1><p>${S.appts.length} booked in total</p></div><button class="pri" onclick="newAppt()">Book appointment</button></div>
<div class="row"><select aria-label="Filter by status" onchange="fs=this.value;render()">${["All", "Pending", "Confirmed", "Completed", "Cancelled"].map(s => `<option${s === st ? " selected" : ""}>${s}</option>`).join("")}</select><select aria-label="Filter by doctor" onchange="fd=this.value;render()"><option value="All">All</option>${S.doctors.map(d => `<option value="${d.id}"${String(d.id) === dc ? " selected" : ""}>${esc(d.name)}</option>`).join("")}</select><select aria-label="Filter by place" onchange="fl=this.value;render()">${["All", ...LOCS].map(c => `<option${c === lc ? " selected" : ""}>${c}</option>`).join("")}</select></div>
<div class="card scroll">${r.length ? `<table><tr><th>Date</th><th>Time</th><th>Patient</th><th>Doctor</th><th>Place</th><th>Reason</th><th>Status</th></tr>${r.map(a => `<tr><td>${a.date}</td><td>${a.time}</td><td><a href="#patient-${a.pid.slice(2)}">${esc(P(a.pid).name)}</a></td><td>${esc(D(a.did).name)}</td><td>${esc(a.loc)}</td><td>${esc(a.reason)}</td><td><select aria-label="Status" style="width:auto;padding:3px 6px" onchange="setStatus(${a.id},this.value)">${["Pending", "Confirmed", "Completed", "Cancelled"].map(s => `<option${s === a.status ? " selected" : ""}>${s}</option>`).join("")}</select></td></tr>`).join("")}</table>` : `<p class="empty">No appointments match these filters.</p>`}</div>`;
}
function setStatus(id, v) { act(() => api("/appointments/" + id, { method: "PATCH", json: { status: v } })); }
function newAppt() {
  dlg("Book appointment", `<label>Patient<select name="patient_id">${opts(S.patients, "id", p => p.id + " – " + p.name)}</select></label><label>Doctor<select name="doctor_id">${opts(S.doctors, "id", d => d.name + (d.spec ? " (" + d.spec + ")" : ""), me.id)}</select></label><label>Place<select name="loc">${LOCS.map(c => `<option>${c}</option>`).join("")}</select></label><label>Date<input name="date" type="date" min="${TODAY}" value="${TODAY}" required></label><label>Time<input name="time" type="time" min="08:00" max="17:30" required></label><label>Reason<input name="reason" required></label>`, f => {
    if (f.date < TODAY) return "Choose today or a later date.";
    if (!f.time || f.time < "08:00" || f.time > "17:30") return "Clinic hours are 08:00 to 17:30.";
    if (!f.reason.trim()) return "Enter a reason for the visit.";
    return api("/appointments", { json: { patient_id: f.patient_id, doctor_id: +f.doctor_id, loc: f.loc, date: f.date, time: f.time, reason: f.reason } }).then(() => null);
  }, "Book");
}

/* ---------- archive ---------- */
function adocs() { const t = af.q.trim().toLowerCase(); return S.docs.filter(d => (af.c === "All" || d.cat === af.c) && (!t || [d.name, d.note || "", d.pid, P(d.pid).name].some(x => x.toLowerCase().includes(t)))); }
function docTable(r, showP) {
  if (!r.length) return `<p class="empty">No documents stored. Upload a report, scan or letter.</p>`;
  return `<div class="scroll"><table><tr><th>Document</th>${showP ? "<th>Patient</th>" : ""}<th>Category</th><th>Added</th><th>Size</th><th></th></tr>${r.map(d => `<tr><td>${esc(d.name)}${d.note ? `<br><small style="color:var(--mute)">${esc(d.note)}</small>` : ""}</td>${showP ? `<td><a href="#patient-${d.pid.slice(2)}">${esc(P(d.pid).name)}</a></td>` : ""}<td>${esc(d.cat)}</td><td>${d.date}</td><td>${kb(d.size)}</td><td>${isImg(d.name) ? `<button class="sm" onclick="viewDoc(${d.id})">View</button> ` : ""}<button class="sm" onclick="dlDoc(${d.id})">Download</button> <button class="sm" onclick="delDoc(${d.id})">Delete</button></td></tr>`).join("")}</table></div>`;
}
function archive() {
  const used = S.docs.reduce((s, d) => s + d.size, 0);
  return `<div class="top"><div><h1>Archive</h1><p>Reports, scans and letters filed by patient.</p></div><button class="pri" onclick="upload()">Upload document</button></div>
<div class="stats"><div class="stat"><b>${S.docs.length}</b><span>Documents stored</span></div><div class="stat"><b>${kb(used)}</b><span>Space used</span></div></div>
<div class="row"><input type="search" placeholder="Search by file, patient or note" value="${esc(af.q)}" aria-label="Search documents" oninput="af.q=this.value;$('#dl').innerHTML=docTable(adocs(),true);labelTables()"><select aria-label="Filter by category" onchange="af.c=this.value;render()">${["All", ...CATS].map(c => `<option${c === af.c ? " selected" : ""}>${c}</option>`).join("")}</select></div>
<div class="card" id="dl">${docTable(adocs(), true)}</div>`;
}
function upload(pid) {
  dlg("Upload document", `<label>Patient<select name="patient_id">${opts(S.patients, "id", p => p.id + " – " + p.name, pid)}</select></label><label>Category<select name="cat">${CATS.map(c => `<option>${c}</option>`).join("")}</select></label><label>File (PDF, image, text, Word, Excel or CSV, up to 10 MB)<input name="file" type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.gif,.txt,.docx,.xlsx,.csv"></label><label>Note (optional)<input name="note"></label>`, (f, fd) => {
    const file = f.file;
    if (!file || !file.size) return "Choose a file to upload.";
    if (!/\.(pdf|png|jpe?g|webp|gif|txt|docx|xlsx|csv)$/i.test(file.name)) return "This file type is not supported. Use PDF, image, text, Word, Excel or CSV.";
    if (file.size > 10485760) return "This file is over 10 MB. Compress it first.";
    return api("/documents", { method: "POST", body: fd }).then(() => null);
  }, "Upload");
}
function viewDoc(id) { const d = S.docs.find(x => x.id === id), el = $("#dlg"); el.innerHTML = `<h2>${esc(d.name)}</h2><img alt="${esc(d.name)}" style="max-width:100%;border-radius:8px;margin:12px 0" src="/api/documents/${id}/file"><div class="acts"><button onclick="$('#dlg').close()">Close</button></div>`; el.showModal(); }
function dlDoc(id) { const a = document.createElement("a"); a.href = `/api/documents/${id}/file?download=1`; document.body.appendChild(a); a.click(); a.remove(); }
function delDoc(id) {
  const d = S.docs.find(x => x.id === id);
  dlg("Delete document", `<p style="margin-top:0">Delete “${esc(d.name)}” for ${esc(P(d.pid).name)}? This cannot be undone.</p>`, () => api("/documents/" + id, { method: "DELETE" }).then(() => null), "Delete");
}

/* ---------- billing ---------- */
function billing() {
  const tot = S.inv.reduce((s, i) => s + i.amount, 0), pd = S.inv.reduce((s, i) => s + i.paid, 0);
  const r = [...S.inv].sort((a, b) => b.date.localeCompare(a.date) || b.no.localeCompare(a.no));
  return `<div class="top"><div><h1>Billing</h1><p>Invoices and payments</p></div><button class="pri" onclick="newInv()">Create invoice</button></div>
<div class="stats"><div class="stat"><b>${money(tot)}</b><span>Invoiced</span></div><div class="stat"><b>${money(pd)}</b><span>Collected</span></div><div class="stat"><b>${money(tot - pd)}</b><span>Outstanding</span></div></div>
<div class="card scroll"><table><tr><th>Invoice</th><th>Date</th><th>Patient</th><th>Doctor</th><th>Amount</th><th>Paid</th><th>Status</th><th></th></tr>${r.map(i => `<tr><td>${i.no}</td><td>${i.date}</td><td>${esc(P(i.pid).name)}</td><td>${esc(D(i.did).name)}</td><td>${money(i.amount)}</td><td>${money(i.paid)}</td><td><span class="tag ${status(i)}">${status(i)}</span></td><td>${i.paid < i.amount ? `<button class="sm" onclick="pay('${i.no}')">Record payment</button>` : ""}</td></tr>`).join("")}</table></div>`;
}
function newInv() {
  dlg("Create invoice", `<label>Patient<select name="patient_id">${opts(S.patients, "id", p => p.id + " – " + p.name)}</select></label><label>Doctor<select name="doctor_id">${opts(S.doctors, "id", "name", me.id)}</select></label><label>Amount (€)<input name="amount" type="number" min="1" step="0.01" required></label>`, f => {
    if (!(+f.amount > 0)) return "Enter an amount greater than zero.";
    return api("/invoices", { json: { patient_id: f.patient_id, doctor_id: +f.doctor_id, amount: +f.amount } }).then(() => null);
  }, "Create");
}
function pay(no) {
  const i = S.inv.find(x => x.no === no), left = Math.round((i.amount - i.paid) * 100) / 100;
  dlg("Record payment for " + no, `<p style="margin-top:0">Balance due: <b>${money(left)}</b></p><label>Amount (€)<input name="amt" type="number" step="0.01" value="${left.toFixed(2)}" required></label><label>Method<select name="m"><option>Cash</option><option>Card</option><option>Bank transfer</option><option>Other</option></select></label>`, f => {
    if (!(+f.amt > 0) || +f.amt > left + 0.001) return "Enter an amount between 0.01 and " + left.toFixed(2) + ".";
    return api(`/invoices/${no}/pay`, { json: { amount: +f.amt, method: f.m } }).then(() => null);
  }, "Record payment");
}

/* ---------- team (owner) ---------- */
function team() {
  return `<div class="top"><div><h1>Team</h1><p>Accounts for doctors and staff.</p></div><button class="pri" onclick="newUser()">Add account</button></div>
<div class="card scroll"><table><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th></th></tr>${S.users.map(u => `<tr><td>${esc(u.name)}</td><td>${esc(u.email)}</td><td>${ROLE[u.role]}</td><td><span class="tag ${u.active ? "Paid" : "Cancelled"}">${u.active ? "Active" : "Disabled"}</span></td><td><button class="sm" onclick="resetPw(${u.id})">Reset password</button> ${u.id !== me.id ? `<button class="sm" onclick="toggleUser(${u.id},${u.active ? 0 : 1})">${u.active ? "Disable" : "Enable"}</button>` : ""}</td></tr>`).join("")}</table></div>`;
}
function newUser() {
  dlg("Add account", `<label>Full name<input name="name" required></label><label>Email (used to sign in)<input name="email" type="email" required></label><label>Role<select name="role"><option value="doctor">Doctor</option><option value="receptionist">Receptionist</option><option value="owner">Clinic owner</option></select></label><label>Speciality (doctors)<input name="spec"></label><label>Temporary password (10+ characters)<input name="password" type="password" autocomplete="new-password" required></label>`, f => {
    if (f.password.length < 10) return "Use a password with at least 10 characters.";
    return api("/users", { json: { email: f.email, name: f.name, role: f.role, spec: f.spec, password: f.password } }).then(() => null);
  }, "Add account");
}
function resetPw(id) {
  const u = S.users.find(x => x.id === id);
  dlg("Reset password for " + esc(u.name), `<label>New password (10+ characters)<input name="password" type="password" autocomplete="new-password" required></label>`, f => {
    if (f.password.length < 10) return "Use a password with at least 10 characters.";
    return api("/users/" + id, { method: "PATCH", json: { password: f.password } }).then(() => null);
  }, "Reset password");
}
function toggleUser(id, a) { act(() => api("/users/" + id, { method: "PATCH", json: { active: !!a } })); }
function changePw() {
  dlg("Change your password", `<label>Current password<input name="current" type="password" autocomplete="current-password" required></label><label>New password (10+ characters)<input name="new" type="password" autocomplete="new-password" required></label><label>Repeat new password<input name="again" type="password" autocomplete="new-password" required></label>`, f => {
    if (f.new.length < 10) return "Use a password with at least 10 characters.";
    if (f.new !== f.again) return "The new passwords do not match.";
    return api("/me/password", { json: { current: f.current, new: f.new } }).then(() => null);
  }, "Save password");
}

/* ---------- mobile: let CSS turn tables into cards ---------- */
function labelTables() {
  document.querySelectorAll("table").forEach(t => {
    const heads = [...t.querySelectorAll("th")].map(x => x.textContent.trim());
    t.querySelectorAll("tr").forEach(tr => {
      tr.classList.toggle("hd", !!tr.querySelector("th"));
      [...tr.children].forEach((td, i) => { if (td.tagName === "TD" && td.colSpan < 2 && heads[i]) td.dataset.label = heads[i]; });
    });
  });
}

/* ---------- router ---------- */
function render() {
  $("#auth").hidden = !!me; document.querySelector(".app").hidden = !me;
  if (!me) { $("#auth").innerHTML = login(); bindLogin(); return; }
  $("#who").innerHTML = `<b>${esc(me.name)}</b>${esc(ROLE[me.role])}`;
  let h = location.hash.slice(1) || "dashboard";
  const pages = { dashboard, patients, appointments, billing, ...(clinical() ? { archive } : {}), ...(me.role === "owner" ? { team } : {}) };
  const route = h.startsWith("patient-") ? "patients" : (pages[h] ? h : "dashboard");
  document.querySelectorAll("nav a").forEach(a => {
    const roles = a.dataset.roles; a.hidden = !!roles && !roles.split(",").includes(me.role);
    a.classList.toggle("on", a.dataset.r === route);
  });
  $("#view").innerHTML = h.startsWith("patient-") ? patient(h.slice(8)) : pages[route]();
  labelTables();
}
addEventListener("hashchange", () => { q = ""; if (me) { render(); scrollTo(0, 0); } });
$("#out").onclick = async () => { try { await api("/logout", { method: "POST" }); } catch (e) { } me = null; S = { doctors: [], patients: [], appts: [], inv: [], docs: [], users: [] }; render(); };
$("#pw").onclick = changePw;
(async () => { try { me = await api("/me"); await load(); } catch (e) { me = null; } render(); })();
