/* ─── STATE ──────────────────────────────────────── */
let currentUser = "";
let currentType = "income";
let allTransactions = [];
let doughnutChart = null, barChart = null, lineChart = null;

/* ─── SIGNUP STATE ───────────────────────────────── */
let signupData = {};

function showSignup() {
  document.getElementById("loginPage").style.display  = "none";
  document.getElementById("signupPage").style.display = "flex";
  signupData = {};
  signupGoToStep(1);
}

function showLogin() {
  document.getElementById("signupPage").style.display = "none";
  document.getElementById("loginPage").style.display  = "flex";
}

function signupGoToStep(step) {
  [1,2,3].forEach(s => {
    document.getElementById(`signupStep${s}`).style.display = s === step ? "block" : "none";
    const ind = document.getElementById(`step${s}Ind`);
    ind.classList.toggle("active", s === step);
    ind.classList.toggle("done",   s < step);
  });
  document.getElementById("signupError").style.display   = "none";
  document.getElementById("signupSuccess").style.display = "none";
}

function signupNext(step) {
  const errEl = document.getElementById("signupError");
  errEl.style.display = "none";

  if (step === 1) {
    const fullname = document.getElementById("su_fullname").value.trim();
    const username = document.getElementById("su_username").value.trim();
    if (!fullname) { showSignupError("Please enter your full name."); return; }
    if (!username || username.length < 3) { showSignupError("Username must be at least 3 characters."); return; }
    if (/\s/.test(username)) { showSignupError("Username cannot contain spaces."); return; }
    signupData.fullname = fullname;
    signupData.username = username;
    signupData.email    = document.getElementById("su_email").value.trim();
    signupData.phone    = document.getElementById("su_phone").value.trim();
    signupGoToStep(2);
  } else if (step === 2) {
    const income = document.getElementById("su_income").value.trim();
    const source = document.getElementById("su_income_source").value;
    if (!income || parseFloat(income) < 0) { showSignupError("Please enter a valid monthly income."); return; }
    if (!source) { showSignupError("Please select your income source."); return; }
    signupData.monthly_income  = parseFloat(income);
    signupData.income_source   = source;
    signupData.monthly_budget  = parseFloat(document.getElementById("su_budget").value) || 0;
    signupData.savings_goal    = parseFloat(document.getElementById("su_savings_goal").value) || 0;
    signupGoToStep(3);
  }
}

function signupBack(step) {
  signupGoToStep(step - 1);
}

function showSignupError(msg) {
  const el = document.getElementById("signupError");
  el.textContent = msg;
  el.style.display = "block";
}

function togglePw(id, btn) {
  const input = document.getElementById(id);
  const isText = input.type === "text";
  input.type = isText ? "password" : "text";
  btn.style.color = isText ? "" : "var(--blue)";
}

function checkPasswordStrength() {
  const pw = document.getElementById("su_password").value;
  const bar = document.getElementById("pwBar");
  const label = document.getElementById("pwLabel");
  const wrap = document.getElementById("pwStrength");
  if (!pw) { wrap.style.display = "none"; return; }
  wrap.style.display = "flex";
  let score = 0;
  if (pw.length >= 6) score++;
  if (pw.length >= 10) score++;
  if (/[A-Z]/.test(pw)) score++;
  if (/[0-9]/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;
  const levels = [
    { pct: "20%", color: "#f04438", text: "Very Weak" },
    { pct: "40%", color: "#f79009", text: "Weak" },
    { pct: "60%", color: "#f59e0b", text: "Fair" },
    { pct: "80%", color: "#12b76a", text: "Strong" },
    { pct: "100%", color: "#027a48", text: "Very Strong" },
  ];
  const lv = levels[Math.min(score, 4)];
  bar.style.width = lv.pct;
  bar.style.background = lv.color;
  label.textContent = lv.text;
  label.style.color = lv.color;
}

async function submitSignup() {
  const password = document.getElementById("su_password").value;
  const confirm  = document.getElementById("su_confirm_password").value;
  const currency = document.getElementById("su_currency").value;

  if (!password || password.length < 4) { showSignupError("Password must be at least 4 characters."); return; }
  if (password !== confirm) { showSignupError("Passwords do not match."); return; }

  signupData.password = password;
  signupData.currency = currency;

  const btn     = document.getElementById("signupSubmitBtn");
  const btnText = document.getElementById("signupSubmitText");
  btn.disabled  = true;
  btnText.textContent = "Creating…";

  try {
    const res  = await fetch("/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(signupData)
    });
    const data = await res.json();
    if (res.ok && data.status === "ok") {
      const successEl = document.getElementById("signupSuccess");
      successEl.textContent = "Account created successfully! Signing you in…";
      successEl.style.display = "block";
      setTimeout(() => {
        currentUser = signupData.username;
        document.getElementById("navUsername").textContent = signupData.username;
        document.getElementById("userAvatar").textContent  = signupData.username.charAt(0).toUpperCase();
        setGreeting();
        document.getElementById("signupPage").style.display = "none";
        document.getElementById("appPage").style.display    = "block";
        loadData();
      }, 1200);
    } else {
      showSignupError(data.detail || "Registration failed. Please try again.");
    }
  } catch(e) {
    showSignupError("Server error. Make sure backend is running.");
  } finally {
    btn.disabled = false;
    btnText.textContent = "Create Account";
  }
}

/* ─── PROFILE MENU ───────────────────────────────── */
function toggleProfileMenu() {
  const dd = document.getElementById("profileDropdown");
  const isOpen = dd.classList.contains("open");
  closeAllPanels();
  if (!isOpen) {
    dd.classList.add("open");
    setTimeout(() => document.addEventListener("click", closeProfileOnOutside), 0);
  }
}

function closeProfileMenu() {
  document.getElementById("profileDropdown").classList.remove("open");
  document.removeEventListener("click", closeProfileOnOutside);
}

function closeProfileOnOutside(e) {
  const wrap = document.getElementById("profileWrap");
  if (!wrap.contains(e.target)) closeProfileMenu();
}

function closeAllPanels() {
  closeProfileMenu();
  closeSettings();
  closeMyAccount();
  closeNotif();
}

/* ─── DARK MODE ─────────────────────────────────── */
let isDark = localStorage.getItem("etms_dark") === "true";

function applyDarkMode(dark) {
  document.documentElement.classList.toggle("dark", dark);
  const toggle    = document.getElementById("darkModeToggle");
  const sToggle   = document.getElementById("settingsDarkToggle");
  const label     = document.getElementById("darkModeLabel");
  const icon      = document.getElementById("darkModeIcon");
  if (toggle)  toggle.classList.toggle("active", dark);
  if (sToggle) sToggle.classList.toggle("active", dark);
  if (label)   label.textContent = dark ? "Light Mode" : "Dark Mode";
  if (icon)    icon.innerHTML = dark
    ? `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>`
    : `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>`;
  localStorage.setItem("etms_dark", dark);
}

function toggleDarkMode() {
  isDark = !isDark;
  applyDarkMode(isDark);
}

// Apply on load
applyDarkMode(isDark);

/* ─── ACCENT COLOR ──────────────────────────────── */
function setAccent(color, dark) {
  document.documentElement.style.setProperty("--blue", color);
  document.documentElement.style.setProperty("--blue-dark", dark);
  document.documentElement.style.setProperty("--blue-light", color + "18");
  document.querySelectorAll(".swatch").forEach(s => s.classList.remove("active"));
  event.target.classList.add("active");
  localStorage.setItem("etms_accent", JSON.stringify({color, dark}));
}

// Apply saved accent
const savedAccent = localStorage.getItem("etms_accent");
if (savedAccent) { const a = JSON.parse(savedAccent); setAccent(a.color, a.dark); }

/* ─── FONT SIZE ─────────────────────────────────── */
function setFontSize(size) {
  document.documentElement.style.fontSize = size + "px";
  document.querySelectorAll(".fs-btn").forEach(b => b.classList.remove("active"));
  event.target.classList.add("active");
  localStorage.setItem("etms_fontsize", size);
}
const savedFs = localStorage.getItem("etms_fontsize");
if (savedFs) document.documentElement.style.fontSize = savedFs + "px";

/* ─── SETTINGS PANEL ────────────────────────────── */
function openSettings() {
  closeProfileMenu();
  document.getElementById("settingsPanel").classList.add("open");
  document.getElementById("settingsOverlay").classList.add("open");
}
function closeSettings() {
  document.getElementById("settingsPanel")?.classList.remove("open");
  document.getElementById("settingsOverlay")?.classList.remove("open");
}

/* ─── MY ACCOUNT PANEL ──────────────────────────── */
function openMyAccount() {
  closeProfileMenu();
  // Populate account info
  document.getElementById("accountAvatar").textContent = currentUser.charAt(0).toUpperCase();
  document.getElementById("accountName").textContent   = currentUser;
  document.getElementById("acUsername").textContent    = currentUser;
  document.getElementById("pdAvatar").textContent      = currentUser.charAt(0).toUpperCase();
  document.getElementById("pdName").textContent        = currentUser;
  // Stats from transactions
  if (allTransactions && allTransactions.length > 0) {
    const income  = allTransactions.filter(t => parseFloat(t.amount) > 0).reduce((s,t) => s+parseFloat(t.amount), 0);
    const expense = allTransactions.filter(t => parseFloat(t.amount) < 0).reduce((s,t) => s+Math.abs(parseFloat(t.amount)), 0);
    document.getElementById("acTotalTxns").textContent    = allTransactions.length;
    document.getElementById("acTotalIncome").textContent  = "₹" + income.toLocaleString("en-IN");
    document.getElementById("acTotalExpense").textContent = "₹" + expense.toLocaleString("en-IN");
  }
  document.getElementById("accountPanel").classList.add("open");
  document.getElementById("accountOverlay").classList.add("open");
}
function closeMyAccount() {
  document.getElementById("accountPanel")?.classList.remove("open");
  document.getElementById("accountOverlay")?.classList.remove("open");
}

/* ─── NOTIFICATIONS ─────────────────────────────── */
let notifications = JSON.parse(localStorage.getItem("etms_notifs") || "[]");

function toggleNotif() {
  const panel = document.getElementById("notifPanel");
  const isOpen = panel.classList.contains("open");
  closeAllPanels();
  if (!isOpen) {
    panel.classList.add("open");
    renderNotifications();
    document.getElementById("notifDot").style.display = "none";
    setTimeout(() => document.addEventListener("click", closeNotifOutside), 0);
  }
}
function closeNotif() {
  document.getElementById("notifPanel")?.classList.remove("open");
  document.removeEventListener("click", closeNotifOutside);
}
function closeNotifOutside(e) {
  const panel = document.getElementById("notifPanel");
  const btn   = document.getElementById("notifBtn");
  if (!panel?.contains(e.target) && !btn?.contains(e.target)) closeNotif();
}
function addNotification(msg, type="info") {
  notifications.unshift({ msg, type, time: new Date().toLocaleTimeString("en-IN", {hour:"2-digit",minute:"2-digit"}) });
  notifications = notifications.slice(0, 10);
  localStorage.setItem("etms_notifs", JSON.stringify(notifications));
  document.getElementById("notifDot").style.display = "block";
}
function renderNotifications() {
  const list = document.getElementById("notifList");
  if (notifications.length === 0) {
    list.innerHTML = `<div class="notif-empty"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/></svg><p>No notifications yet</p></div>`;
    return;
  }
  const icons = { info:"💡", success:"✅", warning:"⚠️", error:"🚨" };
  list.innerHTML = notifications.map(n => `
    <div class="notif-item notif-${n.type}">
      <span class="notif-icon">${icons[n.type]||"💡"}</span>
      <div class="notif-content"><p class="notif-msg">${n.msg}</p><span class="notif-time">${n.time}</span></div>
    </div>`).join("");
}
function clearNotifications() {
  notifications = [];
  localStorage.removeItem("etms_notifs");
  renderNotifications();
}

/* ─── CONFIRM CLEAR DATA ────────────────────────── */
function confirmClearData() {
  if (confirm("⚠️ This will permanently delete ALL your transactions. This cannot be undone. Are you sure?")) {
    alert("Data cleared! (Feature coming soon — connect to backend)");
  }
}

/* ─── LOGIN ──────────────────────────────────────── */
async function login() {
  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value.trim();
  const errEl = document.getElementById("loginError");
  const btn   = document.getElementById("loginBtn");
  const btnText = document.getElementById("loginBtnText");
  errEl.style.display = "none";
  if (!username || !password) { errEl.textContent="Please enter username and password."; errEl.style.display="block"; return; }
  btn.disabled=true; btnText.textContent="Signing in…";
  try {
    const res  = await fetch("/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({username,password})});
    const data = await res.json();
    if (res.ok && data.status==="ok") {
      currentUser = username;
      document.getElementById("navUsername").textContent = username;
      document.getElementById("userAvatar").textContent  = username.charAt(0).toUpperCase();
      document.getElementById("pdAvatar").textContent    = username.charAt(0).toUpperCase();
      document.getElementById("pdName").textContent      = username;
      document.getElementById("acUsername").textContent  = username;
      setGreeting();
      addNotification(`Welcome back, ${username}! 👋`, "success");
      document.getElementById("loginPage").style.display = "none";
      document.getElementById("appPage").style.display   = "block";
      loadData();
    } else {
      errEl.textContent = data.detail || "Login failed.";
      errEl.style.display = "block";
    }
  } catch(e) {
    errEl.textContent="Server error. Make sure backend is running."; errEl.style.display="block";
  } finally { btn.disabled=false; btnText.textContent="Sign In"; }
}

/* ─── LOGOUT ─────────────────────────────────────── */
function logout() {
  // Save AOS history before logout
  saveAOSHistory();
  // Reset state
  currentUser   = "";
  allTransactions = [];
  aosHistory    = [];
  aosSessionCtx = {};
  aosInitialized = false;
  // Clear UI
  const msgEl = document.getElementById("aosMessages");
  if (msgEl) msgEl.innerHTML = "";
  document.getElementById("list").innerHTML   = "";
  document.getElementById("username").value  = "";
  document.getElementById("password").value  = "";
  document.getElementById("appPage").style.display   = "none";
  document.getElementById("loginPage").style.display = "flex";
}

/* ─── NAV TABS ───────────────────────────────────── */
function showSection(section, btn) {
  document.querySelectorAll(".nav-tab").forEach(b => b.classList.remove("active"));
  if (btn) btn.classList.add("active");
  document.getElementById("dashboardSection").style.display = section === "dashboard" ? "block" : "none";
  document.getElementById("reportSection").style.display    = section === "report"    ? "block" : "none";
  document.getElementById("targetsSection").style.display   = section === "targets"   ? "block" : "none";
  document.getElementById("splitsSection").style.display    = section === "splits"    ? "block" : "none";
  document.getElementById("fraudSection").style.display     = section === "fraud"     ? "block" : "none";
  document.getElementById("uploadSection").style.display    = section === "upload"    ? "block" : "none";
  document.getElementById("aosSection").style.display       = section === "aos"       ? "block" : "none";
  if (section === "targets") loadTargets();
  if (section === "splits")  loadSplitGroups();
  if (section === "upload")  { loadImportHistory(); loadMinLimit(); }
  if (section === "aos" && !aosInitialized) { initAOS(); aosInitialized = true; }
}

function openAOS() {
  const tab = document.querySelector(".nav-tab-aos");
  showSection("aos", tab);
}

/* ─── TYPE TOGGLE ────────────────────────────────── */
function setType(type) {
  currentType = type;
  const incBtn  = document.getElementById("incomeBtn");
  const expBtn  = document.getElementById("expenseBtn");
  const addBtn  = document.getElementById("addBtn");
  const addText = document.getElementById("addBtnText");
  if (type==="income") {
    incBtn.className="type-btn income-active"; expBtn.className="type-btn";
    addBtn.className="btn-primary full"; addText.textContent="Add Income";
  } else {
    expBtn.className="type-btn expense-active"; incBtn.className="type-btn";
    addBtn.className="btn-primary full expense-mode"; addText.textContent="Add Expense";
  }
}

/* ─── ADD TRANSACTION ────────────────────────────── */
async function addTransaction() {
  const rawAmount = document.getElementById("amount").value.trim();
  const category  = document.getElementById("category").value.trim();
  const note      = document.getElementById("note").value.trim();
  const alertEl   = document.getElementById("addAlert");
  const btn       = document.getElementById("addBtn");
  const btnText   = document.getElementById("addBtnText");
  alertEl.style.display="none";
  if (!rawAmount||parseFloat(rawAmount)<=0) { showAddAlert("error","Please enter a valid amount."); return; }
  if (!category) { showAddAlert("error","Please enter a category."); return; }
  const amount = currentType==="expense" ? -Math.abs(parseFloat(rawAmount)) : Math.abs(parseFloat(rawAmount));
  const label  = btnText.textContent;
  btn.disabled=true; btnText.textContent="Adding…";
  try {
    await fetch("/add",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({amount:String(amount),category:note?`${category} — ${note}`:category,user:currentUser})});
    document.getElementById("amount").value="";
    document.getElementById("category").value="";
    document.getElementById("note").value="";
    showAddAlert("success",`${currentType==="income"?"Income":"Expense"} of ₹${Math.abs(amount).toLocaleString("en-IN")} added!`);
    loadData();
  } catch(e) { showAddAlert("error","Failed to add transaction."); }
  finally { btn.disabled=false; btnText.textContent=label; }
}

function showAddAlert(type, msg) {
  const el = document.getElementById("addAlert");
  el.className=`alert alert-${type}`; el.textContent=msg; el.style.display="block";
  setTimeout(()=>{el.style.display="none";},3000);
}

/* ─── LOAD DATA ──────────────────────────────────── */
async function loadData() {
  try {
    const res  = await fetch(`/data?user=${currentUser}`);
    const data = await res.json();
    allTransactions = data;
    renderList(allTransactions);
    updateStats(allTransactions);
  } catch(e) { console.error("Load failed:",e); }
}

/* ─── RENDER LIST ────────────────────────────────── */
function renderList(transactions) {
  const list    = document.getElementById("list");
  const emptyEl = document.getElementById("emptyState");
  list.innerHTML="";
  const reversed = [...transactions].reverse();
  if (reversed.length===0) { emptyEl.style.display="flex"; return; }
  emptyEl.style.display="none";
  reversed.forEach((t,i) => {
    const amt    = parseFloat(t.amount);
    const isInc  = amt>=0;
    const absAmt = Math.abs(amt).toLocaleString("en-IN",{maximumFractionDigits:2});
    const parts  = t.category.split(" — ");
    const catLabel = parts[0];
    const noteText = parts.length>1 ? parts.slice(1).join(" — ") : "";
    const timeText = t.created_at||(isInc?"Income":"Expense");
    const li = document.createElement("li");
    li.className="tx-item"; li.dataset.type=isInc?"income":"expense";
    li.dataset.id=t.id||""; li.style.animationDelay=`${i*0.03}s`;
    li.innerHTML=`
      <div class="tx-icon ${isInc?"inc":"exp"}">
        ${isInc
          ?`<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="18,15 12,9 6,15"/></svg>`
          :`<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6,9 12,15 18,9"/></svg>`}
      </div>
      <div class="tx-info">
        <div class="tx-category">${escapeHtml(catLabel)}</div>
        <div class="tx-note">${noteText?escapeHtml(noteText)+" &middot; ":""}${escapeHtml(timeText)}</div>
      </div>
      <div class="tx-right">
        <div class="tx-amount ${isInc?"inc":"exp"}">${isInc?"+":"−"}₹${absAmt}</div>
        ${t.id?`<button class="btn-delete" onclick="deleteTransaction('${t.id}',this)" title="Delete">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="3,6 5,6 21,6"/><path d="M19,6l-1,14a2,2,0,0,1-2,2H8a2,2,0,0,1-2-2L5,6"/><path d="M10,11v6M14,11v6"/></svg>
        </button>`:""}
      </div>`;
    list.appendChild(li);
  });
}

/* ─── FILTER ─────────────────────────────────────── */
function filterList(type, btn) {
  document.querySelectorAll(".filter-btn").forEach(b=>b.classList.remove("active"));
  btn.classList.add("active");
  const filtered = type==="all" ? allTransactions : allTransactions.filter(t=>type==="income"?parseFloat(t.amount)>=0:parseFloat(t.amount)<0);
  renderList(filtered);
}

/* ─── UPDATE STATS ───────────────────────────────── */
function updateStats(transactions) {
  let income=0, expense=0, incCount=0, expCount=0;
  transactions.forEach(t=>{
    const amt=parseFloat(t.amount);
    if(amt>=0){income+=amt;incCount++;}
    else{expense+=Math.abs(amt);expCount++;}
  });
  const balance=income-expense;
  const pct=income>0?Math.min(100,Math.round((balance/income)*100)):0;
  document.getElementById("totalIncome").textContent  = "₹"+income.toLocaleString("en-IN",{maximumFractionDigits:0});
  document.getElementById("totalExpense").textContent = "₹"+expense.toLocaleString("en-IN",{maximumFractionDigits:0});
  document.getElementById("totalBalance").textContent = "₹"+balance.toLocaleString("en-IN",{maximumFractionDigits:0});
  document.getElementById("incomeBadge").textContent  = `${incCount} ${incCount===1?"entry":"entries"}`;
  document.getElementById("expenseBadge").textContent = `${expCount} ${expCount===1?"entry":"entries"}`;
  document.getElementById("balanceBar").style.width   = pct+"%";
  document.getElementById("balancePercent").textContent = `${pct}% saved`;
  document.getElementById("totalBalance").style.color = balance>=0?"var(--blue)":"var(--red)";
}

/* ─── DELETE ─────────────────────────────────────── */
async function deleteTransaction(id, btn) {
  if (!confirm("Delete this transaction?")) return;
  btn.disabled=true;
  try {
    const res = await fetch(`/delete/${id}?user=${currentUser}`,{method:"DELETE"});
    if (res.ok) {
      const li=btn.closest(".tx-item");
      li.style.cssText="opacity:0;transform:translateX(20px);transition:all 0.25s ease";
      setTimeout(()=>{li.remove();loadData();},250);
    } else { alert("Could not delete."); btn.disabled=false; }
  } catch(e) { alert("Server error."); btn.disabled=false; }
}

/* ─── GREETING ───────────────────────────────────── */
function setGreeting() {
  const hour=new Date().getHours();
  const emoji=hour<12?"🌅":hour<17?"☀️":"🌙";
  const word=hour<12?"Good morning":hour<17?"Good afternoon":"Good evening";
  document.getElementById("greetingText").textContent=`${word}, ${currentUser} ${emoji}`;
  const now=new Date();
  document.getElementById("greetingDate").textContent=now.toLocaleDateString("en-IN",{weekday:"long",year:"numeric",month:"long",day:"numeric"});
  document.getElementById("monthBadge").textContent=now.toLocaleDateString("en-IN",{month:"long",year:"numeric"});
  // also set target month badge
  const tmb = document.getElementById("targetMonthBadge");
  if (tmb) tmb.textContent = now.toLocaleDateString("en-IN",{month:"long",year:"numeric"});
  const sel=document.getElementById("reportMonth");
  if(sel) sel.value=String(now.getMonth()+1);
}

/* ─── AI EXTRACT ─────────────────────────────────── */
async function extractTransaction() {
  const text=document.getElementById("smsText").value.trim();
  const btn=document.getElementById("extractBtn");
  const btnText=document.getElementById("extractBtnText");
  const result=document.getElementById("extractResult");
  if(!text){result.style.display="block";result.className="ai-result ai-error";result.innerHTML="⚠️ Please paste an SMS or email.";return;}
  btn.disabled=true; btnText.textContent="Extracting…"; result.style.display="none";
  try {
    const res=await fetch("/ai/extract",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text,user:currentUser})});
    const data=await res.json();
    if(!res.ok) throw new Error(data.detail||"Failed");
    const d=data.data;
    if(!d.found){result.className="ai-result ai-error";result.innerHTML="❌ No transaction found. Try a bank SMS.";result.style.display="block";return;}
    const typeColor=d.type==="income"?"var(--green)":"var(--red)";
    const sign=d.type==="income"?"+":"-";
    result.className="ai-result ai-success";
    result.innerHTML=`<div class="extract-found">
      <div class="extract-top">
        <span class="extract-badge" style="background:${d.type==="income"?"var(--green-light)":"var(--red-light)"};color:${typeColor}">${d.type==="income"?"Income":"Expense"}</span>
        <strong class="extract-amount" style="color:${typeColor}">${sign}₹${parseFloat(d.amount).toLocaleString("en-IN")}</strong>
      </div>
      <div class="extract-meta">
        <span>📂 ${escapeHtml(d.category)}</span>
        ${d.note?`<span>📝 ${escapeHtml(d.note)}</span>`:""}
        ${d.date?`<span>📅 ${escapeHtml(d.date)}</span>`:""}
      </div>
      <button class="btn-add-extracted" onclick="addExtracted(${d.amount},'${escapeHtml(d.category)}','${escapeHtml(d.note||"")}','${d.type}')">➕ Add This Transaction</button>
    </div>`;
    result.style.display="block";
  } catch(e){result.className="ai-result ai-error";result.innerHTML=`❌ ${e.message}`;result.style.display="block";}
  finally{btn.disabled=false;btnText.textContent="Extract Transaction";}
}

async function addExtracted(amount,category,note,type) {
  const finalAmount=type==="expense"?-Math.abs(amount):Math.abs(amount);
  const fullCategory=note?`${category} — ${note}`:category;
  try {
    await fetch("/add",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({amount:String(finalAmount),category:fullCategory,user:currentUser})});
    document.getElementById("smsText").value="";
    const result=document.getElementById("extractResult");
    result.className="ai-result ai-success";result.innerHTML="✅ Transaction added!";result.style.display="block";
    setTimeout(()=>{result.style.display="none";},2500);
    loadData();
  } catch(e){alert("Failed to add.");}
}

/* ─── AI ANALYZE ─────────────────────────────────── */
async function analyzeSpending() {
  const btn=document.getElementById("analyzeBtn");
  const btnText=document.getElementById("analyzeBtnText");
  const result=document.getElementById("analysisResult");
  btn.disabled=true; btnText.textContent="Analyzing…"; result.style.display="none";
  try {
    const res=await fetch("/ai/analyze",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({user:currentUser})});
    const data=await res.json();
    if(!res.ok) throw new Error(data.detail||"Failed");
    const s=data.summary;
    document.getElementById("aiHighlights").style.display="flex";
    document.getElementById("h-income-val").textContent ="₹"+s.income.toLocaleString("en-IN");
    document.getElementById("h-expense-val").textContent="₹"+s.expense.toLocaleString("en-IN");
    document.getElementById("h-balance-val").textContent="₹"+s.balance.toLocaleString("en-IN");
    result.className="ai-result analysis-result";
    result.innerHTML=formatMarkdown(data.analysis);
    result.style.display="block";
  } catch(e){result.className="ai-result ai-error";result.innerHTML=`❌ ${e.message}`;result.style.display="block";}
  finally{btn.disabled=false;btnText.textContent="Analyze My Spending";}
}

/* ─── MONTHLY REPORT ─────────────────────────────── */
let reportData = null;
let incomeExpenseChart = null, incomeChart = null;

async function loadReport() {
  const month = parseInt(document.getElementById("reportMonth").value);
  const year  = parseInt(document.getElementById("reportYear").value);
  const btn   = document.getElementById("loadReportText");
  btn.textContent = "Loading…";
  document.getElementById("reportStats").style.display  = "none";
  document.getElementById("reportEmpty").style.display  = "none";
  document.getElementById("completeReportResult").style.display = "none";
  try {
    const res = await fetch(`/report/data?user=${currentUser}&month=${month}&year=${year}`);
    const d   = await res.json();
    if (!res.ok) throw new Error(d.detail || "Failed");
    if (d.total_txns === 0) { document.getElementById("reportEmpty").style.display = "flex"; return; }
    reportData = d;
    document.getElementById("reportStats").style.display = "block";

    // KPI cards
    const incomeTxns  = d.income_categories.reduce((s,c) => s + 1, 0);
    const expenseTxns = d.expense_categories.reduce((s,c) => s + 1, 0);
    const daysInMonth = new Date(year, month, 0).getDate();
    const avgPerDay   = d.expense > 0 ? Math.round(d.expense / daysInMonth) : 0;
    document.getElementById("rIncome").textContent      = "₹" + d.income.toLocaleString("en-IN");
    document.getElementById("rExpense").textContent     = "₹" + d.expense.toLocaleString("en-IN");
    document.getElementById("rSavings").textContent     = "₹" + d.savings.toLocaleString("en-IN");
    document.getElementById("rTxns").textContent        = d.total_txns;
    document.getElementById("rIncomeTxns").textContent  = `${d.income_categories.length} source${d.income_categories.length !== 1 ? "s" : ""}`;
    document.getElementById("rExpenseTxns").textContent = `${d.expense_categories.length} categor${d.expense_categories.length !== 1 ? "ies" : "y"}`;
    document.getElementById("rSavingsRate").textContent = `${d.savings_rate}% of income saved`;
    document.getElementById("rAvgExpense").textContent  = `₹${avgPerDay.toLocaleString("en-IN")} avg/day`;

    // Savings bar
    const pct = Math.min(100, d.savings_rate);
    document.getElementById("rSavingsRateBig").textContent = d.savings_rate + "%";
    document.getElementById("rSavingsRateBig").style.color = d.savings_rate >= 40 ? "var(--green)" : d.savings_rate >= 20 ? "var(--amber)" : "var(--red)";
    document.getElementById("rSavingsBar").style.width     = pct + "%";
    document.getElementById("rSavingsBar").style.background = d.savings_rate >= 40 ? "var(--green)" : d.savings_rate >= 20 ? "var(--amber)" : "var(--red)";

    renderCharts(d);
    renderCategoryTable(d.expense_categories, d.expense);
    renderBehaviourInsights(d);
  } catch(e) { alert("Error: " + e.message); }
  finally { btn.textContent = "Load Charts"; }
}

async function generateCompleteReport() {
  const month  = parseInt(document.getElementById("reportMonth").value);
  const year   = parseInt(document.getElementById("reportYear").value);
  const btn    = document.getElementById("completeReportBtnText");
  const result = document.getElementById("completeReportResult");
  btn.textContent = "Generating…";
  document.getElementById("completeReportBtn").disabled = true;
  result.style.display = "none";

  // Load charts first if not loaded yet
  if (document.getElementById("reportStats").style.display === "none") {
    await loadReport();
    if (document.getElementById("reportStats").style.display === "none") {
      btn.textContent = "Generate Complete Report";
      document.getElementById("completeReportBtn").disabled = false;
      return;
    }
  }

  try {
    const res  = await fetch("/ai/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user: currentUser, month, year })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed");

    document.getElementById("completeReportMonthName").textContent = data.month;
    document.getElementById("completeReportContent").innerHTML = formatCompleteReport(data.report);

    // Show download button
    document.getElementById("downloadBtn").style.display = "inline-flex";

    result.style.display = "block";
    result.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch(e) {
    alert("AI Error: " + e.message);
  } finally {
    btn.textContent = "Generate Complete Report";
    document.getElementById("completeReportBtn").disabled = false;
  }
}

function formatCompleteReport(text) {
  return text
    .replace(/^#{1,2}\s+(.+)$/gm, "<h3 class='cr-heading'>$1</h3>")
    .replace(/^###\s+(.+)$/gm, "<h4 class='cr-subheading'>$1</h4>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/^\d+\.\s+(.+)$/gm, "<div class='cr-list-item'><span class='cr-num'></span>$1</div>")
    .replace(/^[-•]\s+(.+)$/gm, "<div class='cr-bullet'>$1</div>")
    .replace(/\n\n/g, "<br/>")
    .replace(/\n/g, "<br/>");
}

function renderBehaviourInsights(d) {
  const section = document.getElementById("behaviourContent");
  const rate    = d.savings_rate;
  const topCat  = d.expense_categories[0];
  const topPct  = topCat && d.expense > 0 ? ((topCat.amount / d.expense) * 100).toFixed(1) : 0;
  const ratio   = d.income > 0 ? ((d.expense / d.income) * 100).toFixed(1) : 0;

  const scoreColor = rate >= 40 ? "var(--green)" : rate >= 20 ? "var(--amber)" : "var(--red)";
  const scoreLabel = rate >= 40 ? "Excellent Saver 🌟" : rate >= 20 ? "Good Progress 👍" : "Needs Improvement ⚠️";
  const spendLabel = ratio <= 50 ? "Very Controlled 🎯" : ratio <= 70 ? "Moderate Spender 💡" : "High Spender 🚨";
  const spendColor = ratio <= 50 ? "var(--green)" : ratio <= 70 ? "var(--amber)" : "var(--red)";

  section.innerHTML = `
    <div class="behaviour-item">
      <div class="beh-icon" style="background:${scoreColor}20;color:${scoreColor}">💰</div>
      <div class="beh-body">
        <span class="beh-title">Savings Behaviour</span>
        <span class="beh-value" style="color:${scoreColor}">${scoreLabel}</span>
        <span class="beh-desc">You saved ${rate}% of your income this month</span>
      </div>
    </div>
    <div class="behaviour-item">
      <div class="beh-icon" style="background:${spendColor}20;color:${spendColor}">📊</div>
      <div class="beh-body">
        <span class="beh-title">Spending Ratio</span>
        <span class="beh-value" style="color:${spendColor}">${spendLabel}</span>
        <span class="beh-desc">You spent ${ratio}% of your income this month</span>
      </div>
    </div>
    ${topCat ? `
    <div class="behaviour-item">
      <div class="beh-icon" style="background:var(--purple-light);color:var(--purple)">🏆</div>
      <div class="beh-body">
        <span class="beh-title">Top Expense Category</span>
        <span class="beh-value" style="color:var(--purple)">${topCat.name}</span>
        <span class="beh-desc">${topPct}% of total expenses — ₹${topCat.amount.toLocaleString("en-IN")}</span>
      </div>
    </div>` : ""}
    <div class="behaviour-item">
      <div class="beh-icon" style="background:var(--blue-light);color:var(--blue)">📅</div>
      <div class="beh-body">
        <span class="beh-title">Transaction Activity</span>
        <span class="beh-value" style="color:var(--blue)">${d.total_txns} transactions</span>
        <span class="beh-desc">${d.expense_categories.length} expense categories tracked</span>
      </div>
    </div>`;
}

/* ─── DOWNLOAD REPORT WITH CHARTS ───────────────── */
async function downloadReport() {
  const month  = parseInt(document.getElementById("reportMonth").value);
  const year   = parseInt(document.getElementById("reportYear").value);
  const btn    = document.getElementById("downloadBtn");
  const aiText = document.getElementById("completeReportContent")?.innerText || "";

  if (!reportData) {
    alert("Please click 'Load Charts' first before downloading.");
    return;
  }

  btn.disabled  = true;
  btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg> Building PDF…`;

  try {
    // ── Capture all charts as base64 PNG images ──
    function captureChart(id) {
      const canvas = document.getElementById(id);
      if (!canvas) return "";
      try { return canvas.toDataURL("image/png", 1.0).split(",")[1]; }
      catch(e) { return ""; }
    }

    const charts = {
      donut:          captureChart("doughnutChart"),
      bar:            captureChart("barChart"),
      line:           captureChart("lineChart"),
      income_expense: captureChart("incomeExpenseChart"),
      income_pie:     captureChart("incomeChart"),
    };

    // ── POST everything to backend ──
    const payload = {
      user:     currentUser,
      month,
      year,
      ai_report: aiText,
      charts,
    };

    btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg> Generating PDF…`;

    const res = await fetch("/report/pdf", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(payload),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to generate PDF");
    }

    const blob   = await res.blob();
    const url    = URL.createObjectURL(blob);
    const a      = document.createElement("a");
    const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    a.href       = url;
    a.download   = `ETMS_Report_${months[month-1]}_${year}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

  } catch(e) {
    alert("PDF Error: " + e.message);
  } finally {
    btn.disabled  = false;
    btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7,10 12,15 17,10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> Download PDF`;
  }
}

/* ─── CHARTS ─────────────────────────────────────── */
const COLORS = [
  "#3b6ef8","#12b76a","#f04438","#f79009","#7c3aed",
  "#06aed4","#ee46bc","#85cc34","#ff6b35","#4a9eff"
];

function renderCharts(d) {
  if(doughnutChart){doughnutChart.destroy();doughnutChart=null;}
  if(barChart){barChart.destroy();barChart=null;}
  if(lineChart){lineChart.destroy();lineChart=null;}
  if(incomeExpenseChart){incomeExpenseChart.destroy();incomeExpenseChart=null;}
  if(incomeChart){incomeChart.destroy();incomeChart=null;}

  const expCats  = d.expense_categories.slice(0,8);
  const labels   = expCats.map(c => c.name);
  const amounts  = expCats.map(c => c.amount);
  const chartDefaults = {
    responsive: true, maintainAspectRatio: true,
    plugins: { legend: { labels: { font: { size: 12, family: "Plus Jakarta Sans" }, padding: 14, boxWidth: 13 } } }
  };

  // Doughnut
  const dCtx = document.getElementById("doughnutChart").getContext("2d");
  doughnutChart = new Chart(dCtx, {
    type: "doughnut",
    data: { labels, datasets: [{ data: amounts, backgroundColor: COLORS, borderWidth: 3, borderColor: "white", hoverOffset: 8 }] },
    options: { ...chartDefaults, cutout: "68%",
      plugins: { ...chartDefaults.plugins,
        legend: { position: "bottom", labels: { font: { size: 11, family: "Plus Jakarta Sans" }, padding: 12, boxWidth: 12 } },
        tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ₹${ctx.parsed.toLocaleString("en-IN")} (${d.expense > 0 ? ((ctx.parsed/d.expense)*100).toFixed(1) : 0}%)` } }
      }
    }
  });

  // Bar
  const bCtx = document.getElementById("barChart").getContext("2d");
  barChart = new Chart(bCtx, {
    type: "bar",
    data: { labels, datasets: [{ label: "Expense (₹)", data: amounts, backgroundColor: COLORS, borderRadius: 10, borderSkipped: false }] },
    options: { ...chartDefaults, indexAxis: "y",
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => ` ₹${ctx.parsed.x.toLocaleString("en-IN")}` } } },
      scales: {
        x: { beginAtZero: true, grid: { color: "#f2f4f7" }, ticks: { callback: v => "₹" + (v >= 1000 ? (v/1000).toFixed(0)+"K" : v), font: { size: 11 } } },
        y: { grid: { display: false }, ticks: { font: { size: 11 } } }
      }
    }
  });

  // Line
  const lCtx = document.getElementById("lineChart").getContext("2d");
  const dailyLabels  = d.daily_expense.map(i => `${i.day}`);
  const dailyAmounts = d.daily_expense.map(i => i.amount);
  lineChart = new Chart(lCtx, {
    type: "line",
    data: { labels: dailyLabels, datasets: [{
      label: "Daily Spending (₹)", data: dailyAmounts,
      borderColor: "#3b6ef8", backgroundColor: "rgba(59,110,248,0.08)",
      borderWidth: 2.5, pointBackgroundColor: "#3b6ef8", pointBorderColor: "white",
      pointBorderWidth: 2, pointRadius: 5, pointHoverRadius: 7, fill: true, tension: 0.4
    }] },
    options: { ...chartDefaults,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => ` ₹${ctx.parsed.y.toLocaleString("en-IN")}` } } },
      scales: {
        y: { beginAtZero: true, grid: { color: "#f2f4f7" }, ticks: { callback: v => "₹" + (v >= 1000 ? (v/1000).toFixed(0)+"K" : v), font: { size: 11 } } },
        x: { grid: { display: false }, ticks: { font: { size: 11 } } }
      }
    }
  });

  // Income vs Expense grouped bar
  const ieCtx = document.getElementById("incomeExpenseChart").getContext("2d");
  incomeExpenseChart = new Chart(ieCtx, {
    type: "bar",
    data: {
      labels: ["This Month"],
      datasets: [
        { label: "Income", data: [d.income], backgroundColor: "#12b76a", borderRadius: 10, borderSkipped: false },
        { label: "Expense", data: [d.expense], backgroundColor: "#f04438", borderRadius: 10, borderSkipped: false },
        { label: "Savings", data: [Math.max(0, d.savings)], backgroundColor: "#3b6ef8", borderRadius: 10, borderSkipped: false }
      ]
    },
    options: { ...chartDefaults,
      plugins: { legend: { position: "bottom", labels: { font: { size: 12, family: "Plus Jakarta Sans" }, padding: 14, boxWidth: 13 } },
        tooltip: { callbacks: { label: ctx => ` ${ctx.dataset.label}: ₹${ctx.parsed.y.toLocaleString("en-IN")}` } }
      },
      scales: {
        y: { beginAtZero: true, grid: { color: "#f2f4f7" }, ticks: { callback: v => "₹" + (v >= 1000 ? (v/1000).toFixed(0)+"K" : v), font: { size: 11 } } },
        x: { grid: { display: false } }
      }
    }
  });

  // Income sources pie
  const incCats   = d.income_categories.slice(0, 6);
  const incLabels = incCats.map(c => c.name);
  const incAmts   = incCats.map(c => c.amount);
  const iCtx = document.getElementById("incomeChart").getContext("2d");
  incomeChart = new Chart(iCtx, {
    type: "pie",
    data: { labels: incLabels.length > 0 ? incLabels : ["No Income"], datasets: [{ data: incAmts.length > 0 ? incAmts : [1], backgroundColor: incAmts.length > 0 ? COLORS : ["#e4e7ec"], borderWidth: 3, borderColor: "white" }] },
    options: { ...chartDefaults,
      plugins: { legend: { position: "bottom", labels: { font: { size: 11, family: "Plus Jakarta Sans" }, padding: 12, boxWidth: 12 } },
        tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ₹${ctx.parsed.toLocaleString("en-IN")}` } }
      }
    }
  });
}

function renderCategoryTable(cats, totalExpense) {
  const div=document.getElementById("categoryTable");
  if(!cats||cats.length===0){div.innerHTML='<p style="padding:20px;color:var(--gray-400);text-align:center">No expense data</p>';return;}
  const rows=cats.map((c,i)=>{
    const pct=totalExpense>0?((c.amount/totalExpense)*100).toFixed(1):0;
    return `<div class="cat-row">
      <div class="cat-rank">${i+1}</div>
      <div class="cat-color" style="background:${COLORS[i%COLORS.length]}"></div>
      <div class="cat-name">${escapeHtml(c.name)}</div>
      <div class="cat-bar-wrap"><div class="cat-bar" style="width:${pct}%;background:${COLORS[i%COLORS.length]}"></div></div>
      <div class="cat-pct">${pct}%</div>
      <div class="cat-amt">₹${c.amount.toLocaleString("en-IN")}</div>
    </div>`;
  }).join("");
  div.innerHTML=rows;
}

/* ─── TARGETS ────────────────────────────────────── */
let currentTargetType = "savings";

function setTargetType(type) {
  currentTargetType = type;
  const sBtn    = document.getElementById("tgtSavingsBtn");
  const lBtn    = document.getElementById("tgtSpendingBtn");
  const addBtn  = document.getElementById("tgtAddBtn");
  const addText = document.getElementById("tgtAddBtnText");
  if (type === "savings") {
    sBtn.className = "type-btn income-active";
    lBtn.className = "type-btn";
    addBtn.className = "btn-primary full";
    addText.textContent = "Add Saving Goal";
  } else {
    lBtn.className = "type-btn expense-active";
    sBtn.className = "type-btn";
    addBtn.className = "btn-primary full expense-mode";
    addText.textContent = "Add Spending Limit";
  }
}

async function addTarget() {
  const name     = document.getElementById("tgtName").value.trim();
  const category = document.getElementById("tgtCategory").value.trim();
  const rawAmt   = document.getElementById("tgtAmount").value;
  const amount   = parseFloat(rawAmt);
  const btn      = document.getElementById("tgtAddBtn");
  const btnText  = document.getElementById("tgtAddBtnText");

  if (!name)              { showTgtAlert("error", "Please enter a target name."); return; }
  if (!category)          { showTgtAlert("error", "Please enter a category (or 'All')."); return; }
  if (!rawAmt || amount <= 0 || isNaN(amount)) { showTgtAlert("error", "Please enter a valid amount."); return; }

  const label = btnText.textContent;
  btn.disabled = true; btnText.textContent = "Adding…";
  try {
    const res = await fetch("/targets/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user: currentUser,
        target_name: name,
        target_type: currentTargetType,
        category,
        amount
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to add target");
    document.getElementById("tgtName").value     = "";
    document.getElementById("tgtCategory").value = "";
    document.getElementById("tgtAmount").value   = "";
    showTgtAlert("success", `"${name}" target added!`);
    loadTargets();
  } catch(e) {
    showTgtAlert("error", e.message);
  } finally {
    btn.disabled = false; btnText.textContent = label;
  }
}

function showTgtAlert(type, msg) {
  const el = document.getElementById("tgtAlert");
  el.className = `alert alert-${type}`;
  el.textContent = msg;
  el.style.display = "block";
  setTimeout(() => { el.style.display = "none"; }, 3500);
}

async function loadTargets() {
  try {
    const res  = await fetch(`/targets?user=${currentUser}`);
    const data = await res.json();
    renderTargets(data);
  } catch(e) {
    console.error("Targets load failed:", e);
  }
}

function renderTargets(targets) {
  const listEl   = document.getElementById("tgtList");
  const emptyEl  = document.getElementById("tgtEmptyState");
  const statGrid = document.getElementById("tgtStatGrid");
  listEl.innerHTML = "";

  if (!targets || targets.length === 0) {
    emptyEl.style.display = "flex";
    statGrid.style.display = "none";
    return;
  }

  emptyEl.style.display  = "none";
  statGrid.style.display = "grid";

  // Compute summary stats
  const savingsTargets  = targets.filter(t => t.target_type === "savings");
  const spendingTargets = targets.filter(t => t.target_type === "spending_limit");
  const totalSavingsAmt  = savingsTargets.reduce((s, t) => s + t.amount, 0);
  const totalSpendingAmt = spendingTargets.reduce((s, t) => s + t.amount, 0);

  document.getElementById("tgt-total-count").textContent    = targets.length;
  document.getElementById("tgt-active-badge").textContent   = `${targets.length} active`;
  document.getElementById("tgt-savings-count").textContent  = savingsTargets.length;
  document.getElementById("tgt-savings-badge").textContent  = `₹${totalSavingsAmt.toLocaleString("en-IN", {maximumFractionDigits:0})} target`;
  document.getElementById("tgt-spending-count").textContent = spendingTargets.length;
  document.getElementById("tgt-spending-badge").textContent = `₹${totalSpendingAmt.toLocaleString("en-IN", {maximumFractionDigits:0})} limit`;

  targets.forEach((t, i) => {
    const isSaving  = t.target_type === "savings";
    const pct       = t.pct       || 0;
    const progress  = t.progress  || 0;
    const remaining = Math.max(0, t.amount - progress);
    const isOver    = progress > t.amount;

    const accentColor = isSaving
      ? (pct >= 100 ? "var(--green)"  : "var(--blue)")
      : (isOver     ? "var(--red)"    : pct >= 80 ? "var(--amber)" : "var(--green)");

    const barGradient = isSaving
      ? (pct >= 100
          ? "linear-gradient(90deg,#6ee7b7,var(--green))"
          : "linear-gradient(90deg,#93c5fd,var(--blue))")
      : (isOver
          ? "linear-gradient(90deg,#fda29b,var(--red))"
          : pct >= 80
            ? "linear-gradient(90deg,#fde68a,var(--amber))"
            : "linear-gradient(90deg,#6ee7b7,var(--green))");

    const statusText = isSaving
      ? (pct >= 100
          ? "🎉 Goal reached!"
          : `₹${remaining.toLocaleString("en-IN",{maximumFractionDigits:0})} left to save`)
      : (isOver
          ? `⚠️ ₹${(progress - t.amount).toLocaleString("en-IN",{maximumFractionDigits:0})} over limit`
          : `₹${remaining.toLocaleString("en-IN",{maximumFractionDigits:0})} remaining`);

    const typeBg    = isSaving ? "var(--blue-light)"  : "var(--red-light)";
    const typeColor = isSaving ? "var(--blue)"         : "var(--red)";
    const typeLabel = isSaving ? "Saving Goal"         : "Spending Limit";

    const r    = 20;
    const circ = 2 * Math.PI * r;
    const dash = ((Math.min(pct, 100) / 100) * circ).toFixed(1);

    const card = document.createElement("div");
    card.className = "card tgt-card";
    card.style.animationDelay = `${i * 0.07}s`;
    card.innerHTML = `
      <div class="tgt-card-inner">
        <div class="tgt-card-top">
          <div class="tgt-card-left">
            <span class="tgt-type-badge" style="background:${typeBg};color:${typeColor}">${typeLabel}</span>
            <h3 class="tgt-name">${escapeHtml(t.target_name)}</h3>
            <span class="tgt-meta-row">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z"/></svg>
              ${escapeHtml(t.category)}
              <span class="tgt-meta-sep">·</span>
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
              ${escapeHtml(t.created_at || "")}
            </span>
          </div>
          <div class="tgt-card-right">
            <svg class="tgt-ring" width="56" height="56" viewBox="0 0 56 56">
              <circle cx="28" cy="28" r="${r}" fill="none" stroke="var(--gray-100)" stroke-width="5"/>
              <circle cx="28" cy="28" r="${r}" fill="none"
                stroke="${accentColor}" stroke-width="5"
                stroke-dasharray="${dash} ${circ}"
                stroke-dashoffset="0"
                stroke-linecap="round"
                transform="rotate(-90 28 28)"
                style="transition:stroke-dasharray 1s cubic-bezier(.4,0,.2,1)"/>
              <text x="28" y="33" text-anchor="middle"
                font-size="9" font-weight="700"
                font-family="'JetBrains Mono',monospace"
                fill="${accentColor}">${pct}%</text>
            </svg>
            <button class="btn-delete" onclick="deleteTarget('${t.id}', this)" title="Delete target">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="3,6 5,6 21,6"/><path d="M19,6l-1,14a2,2,0,0,1-2,2H8a2,2,0,0,1-2-2L5,6"/><path d="M10,11v6M14,11v6"/></svg>
            </button>
          </div>
        </div>
        <div class="tgt-progress-wrap">
          <div class="tgt-progress-track">
            <div class="tgt-progress-fill" style="width:${Math.min(pct,100)}%;background:${barGradient}"></div>
          </div>
        </div>
        <div class="tgt-card-bottom">
          <div class="tgt-amounts">
            <span class="tgt-current" style="font-family:var(--font-mono)">
              ₹${progress.toLocaleString("en-IN",{maximumFractionDigits:0})}
              <span style="color:var(--gray-400);font-weight:400"> / </span>
              ₹${t.amount.toLocaleString("en-IN",{maximumFractionDigits:0})}
            </span>
          </div>
          <span class="tgt-status" style="color:${accentColor}">${statusText}</span>
        </div>
      </div>`;
    listEl.appendChild(card);
  });
}

async function deleteTarget(id, btn) {
  if (!confirm("Delete this target?")) return;
  btn.disabled = true;
  try {
    const res = await fetch(`/targets/${id}?user=${currentUser}`, { method: "DELETE" });
    if (res.ok) {
      const card = btn.closest(".tgt-card");
      card.style.cssText = "opacity:0;transform:translateX(24px);transition:all 0.25s ease";
      setTimeout(() => { card.remove(); loadTargets(); }, 260);
    } else { alert("Could not delete target."); btn.disabled = false; }
  } catch(e) { alert("Server error."); btn.disabled = false; }
}

/* ─── UTILS ──────────────────────────────────────── */
function formatMarkdown(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g,"<strong>$1</strong>")
    .replace(/^#{1,3}\s+(.+)$/gm,"<h4>$1</h4>")
    .replace(/\n\n/g,"</p><p>")
    .replace(/\n/g,"<br/>")
    .replace(/^/,"<p>").replace(/$/,"</p>");
}

function escapeHtml(str) {
  return String(str).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

/* ─── FRAUD DETECTOR ─────────────────────────────── */
let fraudReportData = null;

function handleFraudDrop(e) {
  e.preventDefault();
  document.getElementById("fraudDropZone").classList.remove("drag-over");
  const files = e.dataTransfer.files;
  if (files.length > 0) handleFraudFile(files[0]);
}

function handleFraudDragOver(e) {
  e.preventDefault();
  document.getElementById("fraudDropZone").classList.add("drag-over");
}

function handleFraudDragLeave() {
  document.getElementById("fraudDropZone").classList.remove("drag-over");
}

function handleFraudFileInput(input) {
  if (input.files.length > 0) handleFraudFile(input.files[0]);
}

function handleFraudFile(file) {
  const reader = new FileReader();
  const isImage = file.type.startsWith("image/");
  const isPDF   = file.type === "application/pdf";
  const isText  = file.type.startsWith("text/") || file.name.endsWith(".txt");

  document.getElementById("fraudFileName").textContent = `📎 ${file.name}`;
  document.getElementById("fraudFileInfo").style.display = "flex";

  if (isImage) {
    reader.onload = e => {
      document.getElementById("fraudImagePreview").src = e.target.result;
      document.getElementById("fraudImagePreviewWrap").style.display = "block";
      document.getElementById("fraudFileData").value = e.target.result;
      document.getElementById("fraudFileType").value = "image";
    };
    reader.readAsDataURL(file);
  } else if (isText) {
    reader.onload = e => {
      document.getElementById("fraudInput").value = e.target.result;
      document.getElementById("fraudFileData").value = "";
      document.getElementById("fraudFileType").value = "text";
    };
    reader.readAsText(file);
  } else if (isPDF) {
    document.getElementById("fraudFileData").value = "";
    document.getElementById("fraudFileType").value = "pdf";
    document.getElementById("fraudInput").value = `[PDF file uploaded: ${file.name}]`;
  } else {
    reader.onload = e => {
      document.getElementById("fraudInput").value = e.target.result;
      document.getElementById("fraudFileData").value = "";
      document.getElementById("fraudFileType").value = "text";
    };
    reader.readAsText(file);
  }
}

function clearFraudFile() {
  document.getElementById("fraudFileInfo").style.display    = "none";
  document.getElementById("fraudImagePreviewWrap").style.display = "none";
  document.getElementById("fraudFileData").value  = "";
  document.getElementById("fraudFileType").value  = "";
  document.getElementById("fraudFileName").textContent = "";
  document.getElementById("fraudInput").value = "";
}

async function analyzeFraud() {
  const text     = document.getElementById("fraudInput").value.trim();
  const fileData = document.getElementById("fraudFileData").value;
  const fileType = document.getElementById("fraudFileType").value;
  const btn      = document.getElementById("fraudAnalyzeBtn");
  const btnText  = document.getElementById("fraudAnalyzeBtnText");

  if (!text && !fileData) {
    showFraudError("Please enter a message, URL, or upload a file to analyze.");
    return;
  }

  hideFraudError();
  document.getElementById("fraudResult").style.display      = "none";
  document.getElementById("fraudDownloadBtn").style.display = "none";
  btn.disabled   = true;
  btnText.textContent = "Analyzing…";

  try {
    const payload = { text, file_data: fileData, file_type: fileType, user: currentUser };
    const res     = await fetch("/fraud/analyze", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(payload)
    });
    // Safely parse JSON
    let data;
    const raw = await res.text();
    try { data = JSON.parse(raw); }
    catch(e) { throw new Error("Server returned an unexpected response. Please try again."); }

    if (!res.ok) throw new Error(data.detail || "Analysis failed. Please try again.");

    fraudReportData = data;
    renderFraudReport(data);
    document.getElementById("fraudResult").style.display      = "block";
    document.getElementById("fraudDownloadBtn").style.display = "inline-flex";
    document.getElementById("fraudResult").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch(e) {
    showFraudError("Error: " + e.message);
  } finally {
    btn.disabled = false;
    btnText.textContent = "Analyze for Fraud";
  }
}

function renderFraudReport(data) {
  const score   = data.fraud_score;
  const level   = data.risk_level;
  const color   = score >= 80 ? "#f04438" : score >= 60 ? "#f04438" : score >= 40 ? "#f79009" : score >= 20 ? "#f59e0b" : "#12b76a";
  const bgColor = score >= 60 ? "#fef3f2" : score >= 40 ? "#fffaeb" : score >= 20 ? "#fffaeb" : "#ecfdf3";
  const icon    = score >= 60 ? "🚨" : score >= 40 ? "⚠️" : score >= 20 ? "💡" : "✅";

  document.getElementById("fraudScoreNumber").textContent    = score;
  document.getElementById("fraudScoreNumber").style.color    = color;
  document.getElementById("fraudScoreLabel").textContent     = `${icon} ${level}`;
  document.getElementById("fraudScoreLabel").style.color     = color;
  document.getElementById("fraudScoreCard").style.background = bgColor;
  document.getElementById("fraudScoreCard").style.borderColor = color;
  document.getElementById("fraudScoreBar").style.width       = score + "%";
  document.getElementById("fraudScoreBar").style.background  = color;

  // Fraud type & confidence badges
  const metaEl = document.getElementById("fraudMeta");
  if (metaEl) {
    metaEl.innerHTML = `
      <span class="fraud-meta-item">🔎 Type: <strong>${data.fraud_type || "Unknown"}</strong></span>
      <span class="fraud-meta-sep">|</span>
      <span class="fraud-meta-item">📊 Confidence: <strong>${data.confidence || "Medium"}</strong></span>
      <span class="fraud-meta-sep">|</span>
      <span class="fraud-meta-item">🚩 Patterns: <strong>${data.patterns_triggered}</strong> triggered</span>
    `;
  }

  // Red flags
  const flagsEl = document.getElementById("fraudFlags");
  flagsEl.innerHTML = data.red_flags.length > 0
    ? data.red_flags.map(f => `<div class="fraud-flag-item"><span class="flag-dot"></span>${f}</div>`).join("")
    : `<div class="fraud-flag-item safe-flag">✅ No significant red flags detected</div>`;

  // Safe signals
  const safeEl = document.getElementById("fraudSafeSignals");
  safeEl.innerHTML = data.safe_signals.length > 0
    ? data.safe_signals.map(s => `<div class="fraud-safe-item"><span class="safe-dot"></span>${s}</div>`).join("")
    : `<div class="fraud-safe-item" style="color:var(--gray-400)">No safe signals identified</div>`;

  // Detailed analysis
  document.getElementById("fraudAnalysisText").innerHTML = formatCompleteReport(data.detailed_analysis);

  // Recommendation
  document.getElementById("fraudRecommendation").textContent         = data.recommendation;
  document.getElementById("fraudRecommendationBox").style.background  = bgColor;
  document.getElementById("fraudRecommendationBox").style.borderColor = color;
  document.getElementById("fraudRecommendationTitle").style.color     = color;
}

function showFraudError(msg) {
  const el = document.getElementById("fraudError");
  el.textContent = msg;
  el.style.display = "block";
}

function hideFraudError() {
  document.getElementById("fraudError").style.display = "none";
}

/* ─── FRAUD PDF DOWNLOAD ─────────────────────────── */
async function downloadFraudReport() {
  const btn     = document.getElementById("fraudDownloadBtn");
  const text    = document.getElementById("fraudInput").value.trim();
  if (!fraudReportData) { alert("Please analyze first."); return; }

  btn.disabled  = true;
  btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg> Generating PDF…`;

  try {
    const payload = {
      ...fraudReportData,
      analyzed_text: text.substring(0, 500)
    };
    const res = await fetch("/fraud/pdf", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(payload)
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "PDF generation failed");
    }
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = `ETMS_Fraud_Report_${new Date().toISOString().slice(0,10)}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch(e) {
    alert("PDF Error: " + e.message);
  } finally {
    btn.disabled  = false;
    btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7,10 12,15 17,10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> Download Report PDF`;
  }
}

/* ═══════════════════════════════════════════════════
   A.O.S — ACCOUNTING OVERFLOWS SYSTEM CHATBOT
   ═══════════════════════════════════════════════════ */

let aosHistory      = [];
let aosTyping       = false;
let aosInitialized  = false;
let aosSessionCtx   = {};        // financial facts remembered in session
let aosSaveTimer    = null;      // debounce save timer

// ── Save history to backend ──────────────────────────
async function saveAOSHistory() {
  if (!currentUser || aosHistory.length === 0) return;
  try {
    await fetch("/aos/history/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user: currentUser, messages: aosHistory })
    });
  } catch(e) {}
}

// ── Debounced save (saves 3s after last message) ─────
function scheduleSave() {
  clearTimeout(aosSaveTimer);
  aosSaveTimer = setTimeout(saveAOSHistory, 3000);
}

// ── Load history from backend ────────────────────────
async function loadAOSHistory() {
  if (!currentUser) return;
  try {
    const res  = await fetch(`/aos/history?user=${currentUser}`);
    const data = await res.json();
    const msgs = data.messages || [];
    if (msgs.length === 0) return;

    // Restore messages to UI
    const container = document.getElementById("aosMessages");
    if (!container) return;
    container.innerHTML = "";

    // Show a "history loaded" divider
    const divider = document.createElement("div");
    divider.className = "aos-history-divider";
    divider.innerHTML = `<span>Previous conversation</span>`;
    container.appendChild(divider);

    msgs.forEach(m => {
      addAOSMessage(m.role, m.content, true); // true = restore mode (no animation delay)
    });

    // Add current session divider
    const now = document.createElement("div");
    now.className = "aos-history-divider aos-history-now";
    now.innerHTML = `<span>Current session — ${new Date().toLocaleDateString("en-IN",{day:"numeric",month:"short"})}</span>`;
    container.appendChild(now);

    aosHistory = msgs;
    document.getElementById("aosQuickActions").style.display = "none";
    container.scrollTop = container.scrollHeight;
  } catch(e) {}
}

// ── Load saved session context from backend ──────────
async function loadAOSContext() {
  if (!currentUser) return;
  try {
    const res  = await fetch(`/aos/context?user=${currentUser}`);
    const data = await res.json();
    aosSessionCtx = data.context || {};
  } catch(e) {}
}

// ── Initialize with welcome message ─────────────────
async function initAOS() {
  const hour  = new Date().getHours();
  const greet = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const name  = currentUser ? `, ${currentUser}` : "";

  // Try to load persistent history first
  await loadAOSContext();
  await loadAOSHistory();

  // Only show welcome if no history
  if (aosHistory.length === 0) {
    addAOSMessage("aos", `${greet}${name}! 👋 I'm **A.O.S** — your Accounting Overflows System.

I'm here to help you with:
• 💰 **Tax saving** strategies & deductions
• 📊 **Budget planning** & expense limits
• 📈 **Investment advice** (SIP, PPF, NPS, ELSS)
• 🔍 **ETMS guidance** — just ask where anything is!
• 🧾 **Financial planning** & goal setting

What would you like help with today?`);
  }
}

// ── Send message ────────────────────────────────────
async function sendAOSMessage() {
  const input = document.getElementById("aosInput");
  const msg   = input.value.trim();
  if (!msg || aosTyping) return;

  addAOSMessage("user", msg);
  aosHistory.push({ role: "user", content: msg, time: new Date().toISOString() });
  input.value = "";
  aosAutoResize(input);

  document.getElementById("aosQuickActions").style.display = "none";

  aosTyping = true;
  const typingId = showAOSTyping();
  document.getElementById("aosSendBtn").disabled = true;

  try {
    const res = await fetch("/aos/chat", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        message:         msg,
        user:            currentUser || "",
        history:         aosHistory.slice(-14),
        session_context: aosSessionCtx
      })
    });
    // Safely handle response
    const raw = await res.text();
    let data;
    try { data = JSON.parse(raw); }
    catch(e) {
      removeAOSTyping(typingId);
      addAOSMessage("aos", "I'm having a small technical hiccup right now. Please try again in a moment! 🔄");
      return;
    }
    removeAOSTyping(typingId);
    const reply = data.reply || "I'm having trouble responding. Please try again!";
    addAOSMessage("aos", reply);
    aosHistory.push({ role: "aos", content: reply, time: new Date().toISOString() });
    if (aosHistory.length > 100) aosHistory = aosHistory.slice(-80);
    // Merge session context returned from backend
    if (data.session_context && Object.keys(data.session_context).length > 0) {
      aosSessionCtx = { ...aosSessionCtx, ...data.session_context };
    }
    // Auto-save history after every exchange
    scheduleSave();
  } catch(e) {
    removeAOSTyping(typingId);
    addAOSMessage("aos", "Connection issue — please make sure the ETMS backend is running and try again! 🔄");
  } finally {
    aosTyping = false;
    document.getElementById("aosSendBtn").disabled = false;
    document.getElementById("aosInput")?.focus();
  }
}

// ── Quick action ─────────────────────────────────────
function sendQuick(msg) {
  document.getElementById("aosInput").value = msg;
  sendAOSMessage();
}

// ── Keyboard handler ─────────────────────────────────
function aosKeyDown(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendAOSMessage();
  }
}

// ── Auto resize textarea ──────────────────────────────
function aosAutoResize(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 120) + "px";
}

// ── Add message to chat ──────────────────────────────
function addAOSMessage(role, text, isRestore = false) {
  const container = document.getElementById("aosMessages");
  if (!container) return;
  const isAOS = role === "aos";
  const now   = new Date().toLocaleTimeString("en-IN", {hour:"2-digit", minute:"2-digit"});

  const div  = document.createElement("div");
  div.className = `aos-msg aos-msg-${role}`;

  const formatted = formatAOSText(text);
  div.innerHTML = `
    ${isAOS ? `<div class="aos-msg-avatar"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="3" y="8" width="18" height="8" rx="4"/><circle cx="8" cy="12" r="1.5" fill="currentColor"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/><circle cx="16" cy="12" r="1.5" fill="currentColor"/></svg></div>` : ""}
    <div class="aos-msg-bubble">
      <div class="aos-msg-content">${formatted}</div>
      <span class="aos-msg-time">${now}</span>
    </div>
    ${!isAOS ? `<div class="aos-msg-user-avatar">${currentUser ? currentUser.charAt(0).toUpperCase() : 'U'}</div>` : ""}
  `;

  container.appendChild(div);
  // Skip animation for restored history messages
  if (isRestore) {
    div.classList.add("visible");
    div.style.opacity = "0.85"; // slightly dimmed to show it's history
  } else {
    requestAnimationFrame(() => div.classList.add("visible"));
    container.scrollTop = container.scrollHeight;
  }
}

// ── Format AOS text (markdown-lite) ─────────────────
function formatAOSText(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, "<code>$1</code>")
    .replace(/^### (.+)$/gm, "<h4>$1</h4>")
    .replace(/^## (.+)$/gm, "<h3>$1</h3>")
    .replace(/^• (.+)$/gm, "<div class='aos-bullet'>$1</div>")
    .replace(/^- (.+)$/gm, "<div class='aos-bullet'>$1</div>")
    .replace(/^\d+\. (.+)$/gm, "<div class='aos-numbered'>$1</div>")
    .replace(/\|(.+)\|/g, (match) => {
      const cells = match.split("|").filter(c => c.trim() && !c.match(/^[-\s|]+$/));
      if (!cells.length) return match;
      return `<div class="aos-table-row">${cells.map(c => `<span>${c.trim()}</span>`).join("")}</div>`;
    })
    .replace(/\n\n/g, "<br><br>")
    .replace(/\n/g, "<br>");
}

// ── Typing indicator ─────────────────────────────────
function showAOSTyping() {
  const container = document.getElementById("aosMessages");
  const id = "typing_" + Date.now();
  const div = document.createElement("div");
  div.className = "aos-msg aos-msg-aos";
  div.id = id;
  div.innerHTML = `
    <div class="aos-msg-avatar"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="3" y="8" width="18" height="8" rx="4"/><circle cx="8" cy="12" r="1.5" fill="currentColor"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/><circle cx="16" cy="12" r="1.5" fill="currentColor"/></svg></div>
    <div class="aos-msg-bubble">
      <div class="aos-typing-dots"><span></span><span></span><span></span></div>
    </div>
  `;
  container.appendChild(div);
  requestAnimationFrame(() => div.classList.add("visible"));
  container.scrollTop = container.scrollHeight;
  return id;
}

function removeAOSTyping(id) {
  document.getElementById(id)?.remove();
}

// ── Clear chat ───────────────────────────────────────
async function clearAOSChat() {
  if (!confirm("Clear the full chat history? This cannot be undone.")) return;
  document.getElementById("aosMessages").innerHTML = "";
  aosHistory    = [];
  aosSessionCtx = {};
  document.getElementById("aosQuickActions").style.display = "flex";
  // Clear from backend
  if (currentUser) {
    try {
      await fetch("/aos/history/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user: currentUser, messages: [] })
      });
      await fetch("/aos/context/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user: currentUser, context: {} })
      });
    } catch(e) {}
  }
  initAOS();
}

/* ═══════════════════════════════════════════════════
   UPLOAD FILES — Automatic Transaction Import
   ═══════════════════════════════════════════════════ */

let uploadedFileData = null;   // base64 string
let uploadedFileName = "";
let uploadedFileType = "";
let extractedTxns    = [];     // preview rows from backend

/* ── Min limit ─────────────────────────────────────── */
function saveMinLimit() {
  const val = document.getElementById("minLimitSelect").value;
  localStorage.setItem("etms_min_limit", val);
}
function loadMinLimit() {
  const saved = localStorage.getItem("etms_min_limit") || "100";
  const sel   = document.getElementById("minLimitSelect");
  if (sel) sel.value = saved;
}

/* ── Drag & drop handlers ──────────────────────────── */
function handleUploadDragOver(e) {
  e.preventDefault();
  document.getElementById("uploadDropZone").classList.add("drag-over");
}
function handleUploadDragLeave() {
  document.getElementById("uploadDropZone").classList.remove("drag-over");
}
function handleUploadDrop(e) {
  e.preventDefault();
  document.getElementById("uploadDropZone").classList.remove("drag-over");
  const files = e.dataTransfer.files;
  if (files.length > 0) readUploadFile(files[0]);
}
function handleUploadFileSelect(input) {
  if (input.files.length > 0) readUploadFile(input.files[0]);
}

function readUploadFile(file) {
  const allowed = ["application/pdf","text/csv","application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"];
  const ext = file.name.split(".").pop().toLowerCase();
  if (!["pdf","csv","xlsx","xls"].includes(ext)) {
    showUploadError("Unsupported file type. Please upload PDF, CSV, XLSX, or XLS.");
    return;
  }
  hideUploadError();
  uploadedFileName = file.name;
  uploadedFileType = ext;
  document.getElementById("uploadFileName").textContent = "📎 " + file.name;
  document.getElementById("uploadFileInfo").style.display = "flex";
  document.getElementById("uploadProcessBtn").style.display = "inline-flex";
  document.getElementById("uploadPreviewCard").style.display = "none";
  extractedTxns = [];

  const reader = new FileReader();
  reader.onload = e => {
    uploadedFileData = e.target.result.split(",")[1]; // base64
  };
  reader.readAsDataURL(file);
}

function clearUploadFile() {
  uploadedFileData = null; uploadedFileName = ""; uploadedFileType = "";
  extractedTxns = [];
  document.getElementById("uploadFileInfo").style.display  = "none";
  document.getElementById("uploadProcessBtn").style.display = "none";
  document.getElementById("uploadPreviewCard").style.display = "none";
  document.getElementById("uploadFileInput").value = "";
  document.getElementById("uploadProgress").style.display  = "none";
  hideUploadError();
}

/* ── Process file (send to backend) ───────────────── */
async function processUploadedFile() {
  if (!uploadedFileData) { showUploadError("No file selected."); return; }
  const btn     = document.getElementById("uploadProcessBtn");
  const btnText = document.getElementById("uploadProcessBtnText");
  const minLimit = parseInt(document.getElementById("minLimitSelect").value) || 100;

  btn.disabled = true; btnText.textContent = "Extracting…";
  showUploadProgress(10, "Uploading file…");
  hideUploadError();

  try {
    showUploadProgress(30, "Parsing file…");
    const res = await fetch("/upload-file", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user: currentUser,
        filename: uploadedFileName,
        file_type: uploadedFileType,
        file_data: uploadedFileData,
        min_limit: minLimit
      })
    });
    showUploadProgress(70, "Extracting transactions…");
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Extraction failed");
    showUploadProgress(100, "Done!");

    extractedTxns = data.transactions || [];
    renderUploadPreview(extractedTxns, data.stats);
    setTimeout(() => { document.getElementById("uploadProgress").style.display = "none"; }, 600);
  } catch(e) {
    showUploadError("Error: " + e.message);
    document.getElementById("uploadProgress").style.display = "none";
  } finally {
    btn.disabled = false; btnText.textContent = "Extract Transactions";
  }
}

function showUploadProgress(pct, label) {
  document.getElementById("uploadProgress").style.display = "block";
  document.getElementById("uploadProgressFill").style.width = pct + "%";
  document.getElementById("uploadProgressLabel").textContent = label;
}

/* ── Render preview table ─────────────────────────── */
function renderUploadPreview(txns, stats) {
  const card    = document.getElementById("uploadPreviewCard");
  const tbody   = document.getElementById("uploadPreviewBody");
  const countEl = document.getElementById("uploadPreviewCount");

  card.style.display = "block";
  countEl.textContent = `${txns.length} transactions found`;
  tbody.innerHTML = "";

  txns.forEach((t, i) => {
    const isDupe    = t.status === "duplicate";
    const isBelow   = t.status === "below_limit";
    const isValid   = t.status === "valid";
    const statusBadge = isDupe
      ? `<span class="upload-badge upload-badge-dupe">Duplicate</span>`
      : isBelow
        ? `<span class="upload-badge upload-badge-ignored">Below Limit</span>`
        : `<span class="upload-badge upload-badge-valid">Ready</span>`;
    const typeColor = t.type === "income" ? "var(--green)" : "var(--red)";
    const sign      = t.type === "income" ? "+" : "−";
    const disabled  = !isValid ? "disabled" : "";
    const checked   = isValid ? "checked" : "";

    tbody.innerHTML += `<tr class="${isDupe ? 'upload-row-dupe' : isBelow ? 'upload-row-ignored' : ''}">
      <td><input type="checkbox" class="upload-row-check" data-idx="${i}" ${checked} ${disabled}></td>
      <td class="upload-td-date">${escapeHtml(t.date || "—")}</td>
      <td class="upload-td-desc">${escapeHtml(t.description || "—")}</td>
      <td><span class="upload-cat-tag">${escapeHtml(t.category || "Other")}</span></td>
      <td style="color:${typeColor};font-weight:700">${t.type === "income" ? "📈 Income" : "📉 Expense"}</td>
      <td style="font-family:var(--font-mono);font-weight:700;color:${typeColor}">${sign}₹${parseFloat(t.amount).toLocaleString("en-IN")}</td>
      <td>${statusBadge}</td>
    </tr>`;
  });

  // Update summary cards
  if (stats) {
    document.getElementById("uploadSummaryCards").style.display = "grid";
    document.getElementById("uc-total").textContent     = stats.total      || 0;
    document.getElementById("uc-imported").textContent  = "—";
    document.getElementById("uc-dupes").textContent     = stats.duplicates || 0;
    document.getElementById("uc-ignored").textContent   = stats.ignored    || 0;
    document.getElementById("uc-belowlimit").textContent= stats.below_limit|| 0;
  }
  updateSelectionHint();

  // Checkbox listeners
  document.querySelectorAll(".upload-row-check").forEach(cb => {
    cb.addEventListener("change", updateSelectionHint);
  });
}

function toggleSelectAll(masterCb) {
  document.querySelectorAll(".upload-row-check:not([disabled])").forEach(cb => {
    cb.checked = masterCb.checked;
  });
  updateSelectionHint();
}

function updateSelectionHint() {
  const checked = document.querySelectorAll(".upload-row-check:checked").length;
  document.getElementById("uploadSelectionHint").textContent =
    `${checked} transaction${checked !== 1 ? "s" : ""} selected`;
}

/* ── Import selected transactions ─────────────────── */
async function importTransactions() {
  const checked = [...document.querySelectorAll(".upload-row-check:checked")];
  if (checked.length === 0) { showUploadError("Please select at least one transaction to import."); return; }

  const indices  = checked.map(cb => parseInt(cb.dataset.idx));
  const toImport = indices.map(i => extractedTxns[i]).filter(t => t.status === "valid");

  if (toImport.length === 0) { showUploadError("No valid transactions selected (duplicates/below-limit cannot be imported)."); return; }

  const btn     = document.getElementById("uploadImportBtn");
  const btnText = document.getElementById("uploadImportBtnText");
  btn.disabled  = true; btnText.textContent = "Importing…";

  try {
    const res  = await fetch("/import-transactions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user: currentUser,
        filename: uploadedFileName,
        file_type: uploadedFileType,
        transactions: toImport
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Import failed");

    // Update cards
    document.getElementById("uc-imported").textContent = data.imported_count || 0;
    addNotification(`✅ Imported ${data.imported_count} transactions from ${uploadedFileName}`, "success");
    loadData(); // refresh dashboard
    loadImportHistory();

    // Show success alert
    const errEl = document.getElementById("uploadError");
    errEl.className = "alert alert-success";
    errEl.textContent = `✅ Successfully imported ${data.imported_count} transaction(s)! Dashboard updated.`;
    errEl.style.display = "block";
    setTimeout(() => { errEl.style.display = "none"; }, 4000);

    // Disable imported rows
    checked.forEach(cb => {
      cb.disabled = true; cb.checked = false;
      const row = cb.closest("tr");
      row.querySelectorAll("td:last-child")[0].innerHTML = `<span class="upload-badge upload-badge-valid">Imported ✓</span>`;
    });
    updateSelectionHint();
  } catch(e) {
    showUploadError("Import error: " + e.message);
  } finally {
    btn.disabled = false; btnText.textContent = "Import Selected";
  }
}

/* ── Import history ───────────────────────────────── */
async function loadImportHistory() {
  if (!currentUser) return;
  try {
    const res  = await fetch(`/import-history?user=${currentUser}`);
    const data = await res.json();
    renderImportHistory(data.history || []);
  } catch(e) {}
}

function renderImportHistory(history) {
  const el = document.getElementById("importHistoryList");
  if (!history.length) {
    el.innerHTML = `<div class="empty-state" style="padding:32px">
      <div class="empty-icon"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/></svg></div>
      <p>No import history yet</p><span>Uploaded files will appear here</span>
    </div>`;
    return;
  }
  el.innerHTML = history.map(h => `
    <div class="import-history-row">
      <div class="ih-icon">📄</div>
      <div class="ih-body">
        <span class="ih-name">${escapeHtml(h.filename)}</span>
        <span class="ih-meta">${escapeHtml(h.file_type.toUpperCase())} · ${escapeHtml(h.upload_time)}</span>
      </div>
      <div class="ih-stats">
        <span class="ih-stat green">${h.imported_records} imported</span>
        <span class="ih-stat purple">${h.duplicate_records} dupes</span>
        <span class="ih-stat red">${h.ignored_records} ignored</span>
      </div>
    </div>`).join("");
}

function showUploadError(msg) {
  const el = document.getElementById("uploadError");
  el.className = "alert alert-error";
  el.textContent = msg; el.style.display = "block";
}
function hideUploadError() {
  document.getElementById("uploadError").style.display = "none";
}

/* ══════════════════════════════════════════════════
   SPLIT EXPENSE — Full Frontend Logic
══════════════════════════════════════════════════ */

let splitGroupMembers = [];   // members being added in create-group modal
let currentExpenseGroup = {}; // group context when adding expense

// ── Load & render all groups ──────────────────────
async function loadSplitGroups() {
  const user = localStorage.getItem("etms_user");
  if (!user) return;
  try {
    const res  = await fetch(`/splits?user=${encodeURIComponent(user)}`);
    const data = await res.json();
    renderSplitGroups(Array.isArray(data) ? data : []);
  } catch (e) {
    console.error("loadSplitGroups error", e);
  }
}

function renderSplitGroups(groups) {
  const container = document.getElementById("splitsGroupsList");
  const empty     = document.getElementById("splitsEmpty");
  if (!groups.length) {
    container.innerHTML = "";
    empty.style.display = "block";
    return;
  }
  empty.style.display = "none";
  const user = localStorage.getItem("etms_user");

  container.innerHTML = groups.map(g => {
    const balances = g.balances || {};
    const net      = balances.net || {};
    const debts    = balances.debts || [];
    const myNet    = net[user] || 0;

    // Summary badge
    let myBadge = "";
    if (Math.abs(myNet) < 0.01) {
      myBadge = `<span class="split-badge split-settled">✓ Settled</span>`;
    } else if (myNet > 0) {
      myBadge = `<span class="split-badge split-owed">+₹${myNet.toFixed(2)} owed to you</span>`;
    } else {
      myBadge = `<span class="split-badge split-owe">-₹${Math.abs(myNet).toFixed(2)} you owe</span>`;
    }

    // Debts summary
    const debtsHtml = debts.length
      ? debts.map(d =>
          `<div class="split-debt-row">
            <span class="split-debt-from">${d.from}</span>
            <span class="split-debt-arrow">→</span>
            <span class="split-debt-to">${d.to}</span>
            <span class="split-debt-amt">₹${d.amount.toFixed(2)}</span>
            ${(d.from === user || d.to === user)
              ? `<button class="btn-settle" onclick="settleUp('${g.id}','${d.from}','${d.to}',${d.amount})">Settle</button>`
              : ""}
          </div>`
        ).join("")
      : `<p style="color:var(--gray-400); font-size:0.82rem; padding:6px 0">All settled up ✓</p>`;

    // Expenses list
    const expHtml = (g.expenses || []).length
      ? [...g.expenses].reverse().map(e =>
          `<div class="split-exp-row">
            <div class="split-exp-info">
              <span class="split-exp-desc">${e.description}</span>
              <span class="split-exp-meta">${e.paid_by} paid · split ${e.split_among.length} ways · ${e.date}</span>
            </div>
            <div style="display:flex; align-items:center; gap:10px">
              <span class="split-exp-amt">₹${e.amount.toFixed(2)}</span>
              <button class="split-del-btn" onclick="deleteExpense('${g.id}','${e.id}')" title="Delete">🗑</button>
            </div>
          </div>`
        ).join("")
      : `<p style="color:var(--gray-400); font-size:0.82rem; padding:6px 0">No expenses yet</p>`;

    const isCreator = g.created_by === user;
    return `
      <div class="card split-group-card" style="margin-bottom:20px">
        <div class="split-group-header">
          <div>
            <h3 class="split-group-name">${g.name}</h3>
            <span class="split-group-meta">👥 ${g.members.join(", ")} · ${g.created_at}</span>
          </div>
          <div style="display:flex; align-items:center; gap:10px">
            ${myBadge}
            <button class="btn-primary" onclick="openAddExpenseModal('${g.id}','${g.name}',${JSON.stringify(g.members).replace(/"/g,'&quot;')})" style="padding:6px 14px; font-size:0.82rem">+ Expense</button>
            ${isCreator ? `<button class="split-del-btn" onclick="deleteGroup('${g.id}')" title="Delete group" style="font-size:1rem">🗑</button>` : ""}
          </div>
        </div>

        <div style="margin-top:16px">
          <p class="split-sub-title">📋 Expenses</p>
          ${expHtml}
        </div>

        <div style="margin-top:16px">
          <p class="split-sub-title">💸 Who Owes Whom</p>
          ${debtsHtml}
        </div>
      </div>`;
  }).join("");
}

// ── Create Group Modal ────────────────────────────
function openCreateGroupModal() {
  splitGroupMembers = [];
  document.getElementById("newGroupName").value = "";
  document.getElementById("newMemberInput").value = "";
  document.getElementById("memberTagsWrap").innerHTML = "";
  document.getElementById("createGroupError").style.display = "none";
  document.getElementById("createGroupModal").style.display = "flex";
  setTimeout(() => document.getElementById("newGroupName").focus(), 50);
}
function closeCreateGroupModal() {
  document.getElementById("createGroupModal").style.display = "none";
}
function closeSplitModal(e) {
  if (e.target.classList.contains("modal-overlay")) {
    document.querySelectorAll(".modal-overlay").forEach(m => m.style.display = "none");
  }
}

function addMemberTag() {
  const input = document.getElementById("newMemberInput");
  const val   = input.value.trim().toLowerCase();
  const me    = localStorage.getItem("etms_user");
  if (!val) return;
  if (val === me) { showSplitError("createGroupError", "You are added automatically"); input.value=""; return; }
  if (splitGroupMembers.includes(val)) { showSplitError("createGroupError", `${val} already added`); input.value=""; return; }
  splitGroupMembers.push(val);
  renderMemberTags();
  input.value = "";
  document.getElementById("createGroupError").style.display = "none";
}

function removeMemberTag(name) {
  splitGroupMembers = splitGroupMembers.filter(m => m !== name);
  renderMemberTags();
}

function renderMemberTags() {
  const wrap = document.getElementById("memberTagsWrap");
  wrap.innerHTML = splitGroupMembers.map(m =>
    `<span class="member-tag">${m} <button onclick="removeMemberTag('${m}')" class="tag-remove">×</button></span>`
  ).join("");
}

async function createGroup() {
  const name    = document.getElementById("newGroupName").value.trim();
  const user    = localStorage.getItem("etms_user");
  const errEl   = document.getElementById("createGroupError");
  const btn     = document.getElementById("createGroupBtnText");

  if (!name) { showSplitError("createGroupError", "Enter a group name"); return; }
  if (!splitGroupMembers.length) { showSplitError("createGroupError", "Add at least one other member"); return; }

  btn.textContent = "Creating…";
  try {
    const res  = await fetch("/splits/create", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ name, created_by: user, members: [user, ...splitGroupMembers] })
    });
    const data = await res.json();
    if (!res.ok) { showSplitError("createGroupError", data.detail || "Error creating group"); btn.textContent="Create Group"; return; }
    closeCreateGroupModal();
    loadSplitGroups();
  } catch (e) {
    showSplitError("createGroupError", "Network error");
  }
  btn.textContent = "Create Group";
}

// ── Add Expense Modal ─────────────────────────────
function openAddExpenseModal(groupId, groupName, members) {
  currentExpenseGroup = { id: groupId, name: groupName, members };
  document.getElementById("expenseGroupId").value = groupId;
  document.getElementById("expenseDesc").value = "";
  document.getElementById("expenseAmount").value = "";
  document.getElementById("addExpenseError").style.display = "none";
  document.getElementById("splitPreview").textContent = "";

  // Populate paid-by dropdown
  const paidSel = document.getElementById("expensePaidBy");
  paidSel.innerHTML = members.map(m => `<option value="${m}">${m}</option>`).join("");
  const me = localStorage.getItem("etms_user");
  paidSel.value = me;

  // Populate split-among checkboxes (all checked by default)
  const checksWrap = document.getElementById("splitAmongChecks");
  checksWrap.innerHTML = members.map(m =>
    `<label class="split-check-label">
      <input type="checkbox" value="${m}" checked onchange="updateSplitPreview()"> ${m}
    </label>`
  ).join("");

  document.getElementById("expenseAmount").oninput = updateSplitPreview;
  document.getElementById("addExpenseModal").style.display = "flex";
  setTimeout(() => document.getElementById("expenseDesc").focus(), 50);
}

function closeAddExpenseModal() {
  document.getElementById("addExpenseModal").style.display = "none";
}

function updateSplitPreview() {
  const amt      = parseFloat(document.getElementById("expenseAmount").value) || 0;
  const checked  = [...document.querySelectorAll("#splitAmongChecks input:checked")];
  const preview  = document.getElementById("splitPreview");
  if (amt > 0 && checked.length > 0) {
    const per = (amt / checked.length).toFixed(2);
    preview.textContent = `₹${per} per person (${checked.length} people)`;
  } else {
    preview.textContent = "";
  }
}

async function submitAddExpense() {
  const user    = localStorage.getItem("etms_user");
  const groupId = document.getElementById("expenseGroupId").value;
  const desc    = document.getElementById("expenseDesc").value.trim();
  const amount  = parseFloat(document.getElementById("expenseAmount").value);
  const paidBy  = document.getElementById("expensePaidBy").value;
  const checked = [...document.querySelectorAll("#splitAmongChecks input:checked")].map(c => c.value);
  const btn     = document.getElementById("addExpenseBtnText");

  if (!desc)              { showSplitError("addExpenseError","Enter a description"); return; }
  if (!amount || amount<=0){ showSplitError("addExpenseError","Enter valid amount"); return; }
  if (!checked.length)    { showSplitError("addExpenseError","Select at least one person to split with"); return; }

  btn.textContent = "Adding…";
  try {
    const res  = await fetch("/splits/add-expense", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ group_id:groupId, description:desc, amount, paid_by:paidBy, split_among:checked, user })
    });
    const data = await res.json();
    if (!res.ok) { showSplitError("addExpenseError", data.detail || "Error"); btn.textContent="Add Expense"; return; }
    closeAddExpenseModal();
    loadSplitGroups();
  } catch(e) {
    showSplitError("addExpenseError","Network error");
  }
  btn.textContent = "Add Expense";
}

// ── Settle Up ─────────────────────────────────────
async function settleUp(groupId, fromUser, toUser, amount) {
  const user = localStorage.getItem("etms_user");
  if (!confirm(`Mark ₹${amount.toFixed(2)} paid from ${fromUser} to ${toUser}?`)) return;
  try {
    const res = await fetch("/splits/settle", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ group_id:groupId, from_user:fromUser, to_user:toUser, amount, user })
    });
    if (res.ok) loadSplitGroups();
  } catch(e) { alert("Network error"); }
}

// ── Delete Expense ────────────────────────────────
async function deleteExpense(groupId, expenseId) {
  const user = localStorage.getItem("etms_user");
  if (!confirm("Delete this expense?")) return;
  try {
    const res = await fetch(`/splits/expense/${groupId}/${expenseId}?user=${encodeURIComponent(user)}`, { method:"DELETE" });
    if (res.ok) loadSplitGroups();
  } catch(e) { alert("Network error"); }
}

// ── Delete Group ──────────────────────────────────
async function deleteGroup(groupId) {
  const user = localStorage.getItem("etms_user");
  if (!confirm("Delete this entire group? This cannot be undone.")) return;
  try {
    const res = await fetch(`/splits/group/${groupId}?user=${encodeURIComponent(user)}`, { method:"DELETE" });
    if (res.ok) loadSplitGroups();
  } catch(e) { alert("Network error"); }
}

// ── Util ──────────────────────────────────────────
function showSplitError(elId, msg) {
  const el = document.getElementById(elId);
  el.textContent = msg;
  el.style.display = "block";
}
