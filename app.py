from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, validator
from pymongo import MongoClient
from dotenv import load_dotenv
import hashlib, uuid, os, json, io
from datetime import datetime
from collections import defaultdict
from google import genai as google_genai
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
#changebyansh
#changebyansh1

load_dotenv()

app = FastAPI(title="ETMS - Expense Tracker Management System")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client    = MongoClient(MONGO_URI)
db        = client["etms_db"]
users_col   = db["users"]
txns_col    = db["transactions"]
targets_col = db["targets"]

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyDKH9WAOyZWcB0Yn-NxryiFuCXtUNGAAcw")
gemini_client  = google_genai.Client(api_key=GEMINI_API_KEY)

def hash_password(p): return hashlib.sha256(p.encode()).hexdigest()
#changebyansh
# ── Models ─────────────────────────────────────────────
class User(BaseModel):
    username: str
    password: str
    @validator("username")
    def u(cls,v):
        v=v.strip()
        if len(v)<3: raise ValueError("Min 3 chars")
        return v
    @validator("password")
    def p(cls,v):
        if len(v)<4: raise ValueError("Min 4 chars")
        return v

class Transaction(BaseModel):
    amount: str
    category: str
    user: str
    @validator("amount")
    def a(cls,v):
        try: val=float(v)
        except: raise ValueError("Invalid amount")
        if val==0: raise ValueError("Cannot be zero")
        return v
    @validator("category")
    def c(cls,v):
        v=v.strip()
        if not v: raise ValueError("Empty category")
        return v


class RegisterUser(BaseModel):
    username: str
    password: str
    fullname: str
    email: str = ""
    phone: str = ""
    monthly_income: float = 0
    income_source: str = ""
    monthly_budget: float = 0
    savings_goal: float = 0
    currency: str = "INR"

class SMSEmailText(BaseModel):
    text: str
    user: str

class AnalyzeRequest(BaseModel):
    user: str

class ReportRequest(BaseModel):
    user: str
    month: int
    year: int

class Target(BaseModel):
    user: str
    target_name: str
    target_type: str   # "savings" | "spending_limit"
    category: str
    amount: float

    @validator("target_name")
    def tn(cls, v):
        v = v.strip()
        if not v: raise ValueError("Target name required")
        if len(v) < 2: raise ValueError("Min 2 characters")
        return v

    @validator("target_type")
    def tt(cls, v):
        if v not in ("savings", "spending_limit"):
            raise ValueError("Type must be savings or spending_limit")
        return v

    @validator("category")
    def cat(cls, v):
        v = v.strip()
        if not v: raise ValueError("Category required")
        return v

    @validator("amount")
    def amt(cls, v):
        if v <= 0: raise ValueError("Amount must be positive")
        return v

# ── POST /login ─────────────────────────────────────────
@app.post("/login")
def login(user: User):
    existing = users_col.find_one({"username": {"$regex": f"^{user.username}$", "$options": "i"}})
    hashed = hash_password(user.password)
    if existing:
        stored = existing["password"]
        if stored == hashed or stored == user.password:
            if stored == user.password:
                users_col.update_one({"_id": existing["_id"]}, {"$set": {"password": hashed}})
            return {"status": "ok", "message": "Login successful"}
        raise HTTPException(status_code=401, detail="Incorrect password")
    users_col.insert_one({"username": user.username, "password": hashed, "created_at": datetime.now().isoformat()})
    return {"status": "ok", "message": "Account created!"}

# ── POST /register ──────────────────────────────────────
@app.post("/register")
def register(u: RegisterUser):
    existing = users_col.find_one({"username": {"$regex": f"^{u.username}$", "$options": "i"}})
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken. Please choose another.")
    if len(u.username.strip()) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters.")
    if len(u.password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters.")
    hashed = hash_password(u.password)
    users_col.insert_one({
        "username": u.username,
        "password": hashed,
        "fullname": u.fullname,
        "email": u.email,
        "phone": u.phone,
        "monthly_income": u.monthly_income,
        "income_source": u.income_source,
        "monthly_budget": u.monthly_budget,
        "savings_goal": u.savings_goal,
        "currency": u.currency,
        "created_at": datetime.now().isoformat()
    })
    # Auto-add first income transaction if monthly income is provided
    if u.monthly_income > 0:
        txns_col.insert_one({
            "id": str(uuid.uuid4()),
            "amount": str(u.monthly_income),
            "category": f"{u.income_source or 'Salary'} — Monthly Income",
            "user": u.username,
            "created_at": datetime.now().strftime("%d %b %Y, %I:%M %p")
        })
    return {"status": "ok", "message": "Account created successfully!"}

# ── POST /add ───────────────────────────────────────────
@app.post("/add")
def add(t: Transaction):
    txn_id = str(uuid.uuid4())
    txns_col.insert_one({
        "id": txn_id, "amount": t.amount, "category": t.category,
        "user": t.user, "created_at": datetime.now().strftime("%d %b %Y, %I:%M %p")
    })
    return {"status": "ok", "id": txn_id}

# ── GET /data ───────────────────────────────────────────
@app.get("/data")
def get_data(user: str):
    if not user: raise HTTPException(status_code=400, detail="User required")
    return list(txns_col.find({"user": user}, {"_id": 0}))

# ── DELETE /delete/{id} ─────────────────────────────────
@app.delete("/delete/{transaction_id}")
def delete_transaction(transaction_id: str, user: str):
    result = txns_col.delete_one({"id": transaction_id, "user": user})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"status": "ok"}

# ── GET /stats ──────────────────────────────────────────
@app.get("/stats")
def get_stats(user: str):
    if not user: raise HTTPException(status_code=400, detail="User required")
    txns    = list(txns_col.find({"user": user}, {"_id": 0}))
    income  = sum(float(t["amount"]) for t in txns if float(t["amount"]) > 0)
    expense = sum(abs(float(t["amount"])) for t in txns if float(t["amount"]) < 0)
    return {"income": round(income,2), "expense": round(expense,2), "balance": round(income-expense,2),
            "total_txns": len(txns), "income_txns": sum(1 for t in txns if float(t["amount"])>0),
            "expense_txns": sum(1 for t in txns if float(t["amount"])<0)}

# ── POST /ai/extract ────────────────────────────────────
@app.post("/ai/extract")
def ai_extract(body: SMSEmailText):
    if not body.text.strip(): raise HTTPException(status_code=400, detail="Text empty")
    prompt = f"""Extract transaction from this bank SMS/email:
\"\"\"{body.text}\"\"\"
Return ONLY valid JSON:
{{"found":true/false,"type":"income"/"expense","amount":number,"category":"short name","note":"brief desc","date":"date or empty"}}
Rules: debited/paid=expense, credited/received=income. Amount positive number only. No markdown."""
    try:
        raw = gemini_client.models.generate_content(model="gemini-2.0-flash", contents=prompt).text.strip()
        if raw.startswith("```"): raw = raw.split("```")[1]; raw = raw[4:] if raw.startswith("json") else raw
        return {"status": "ok", "data": json.loads(raw.strip())}
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Could not parse message")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI error: {str(e)}")

# ── POST /ai/analyze ────────────────────────────────────
@app.post("/ai/analyze")
def ai_analyze(body: AnalyzeRequest):
    txns = list(txns_col.find({"user": body.user}, {"_id": 0}))
    if not txns: raise HTTPException(status_code=400, detail="No transactions found")
    income  = sum(float(t["amount"]) for t in txns if float(t["amount"]) > 0)
    expense = sum(abs(float(t["amount"])) for t in txns if float(t["amount"]) < 0)
    cats = defaultdict(float)
    for t in txns:
        if float(t["amount"]) < 0:
            cats[t["category"].split(" — ")[0].strip()] += abs(float(t["amount"]))
    sorted_cats = sorted(cats.items(), key=lambda x: x[1], reverse=True)
    summary = f"Income: Rs.{income:,.0f} | Expense: Rs.{expense:,.0f} | Balance: Rs.{income-expense:,.0f}\nTop expenses: {', '.join([f'{c}: Rs.{a:,.0f}' for c,a in sorted_cats[:5]])}"
    prompt = f"""Personal finance advisor for Indian user.\n{summary}\nGive analysis with:\n1. **Spending Overview**\n2. **Necessary vs Unnecessary**\n3. **Smart Saving Tips** (4-5 tips)\n4. **Financial Health Score /10**\nBe friendly, use emojis, Indian context."""
    try:
        resp = gemini_client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        return {"status":"ok","analysis":resp.text.strip(),
                "summary":{"income":income,"expense":expense,"balance":income-expense,"top_categories":sorted_cats[:5]}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI error: {str(e)}")

# ── GET /report/data ────────────────────────────────────
@app.get("/report/data")
def report_data(user: str, month: int, year: int):
    if not user: raise HTTPException(status_code=400, detail="User required")
    all_txns = list(txns_col.find({"user": user}, {"_id": 0}))

    # Filter by month & year
    txns = []
    for t in all_txns:
        try:
            dt = datetime.strptime(t["created_at"], "%d %b %Y, %I:%M %p")
            if dt.month == month and dt.year == year:
                txns.append({**t, "_dt": dt})
        except:
            pass

    income  = sum(float(t["amount"]) for t in txns if float(t["amount"]) > 0)
    expense = sum(abs(float(t["amount"])) for t in txns if float(t["amount"]) < 0)

    # Category breakdown (expenses only)
    cats = defaultdict(float)
    for t in txns:
        if float(t["amount"]) < 0:
            cats[t["category"].split(" — ")[0].strip()] += abs(float(t["amount"]))

    # Daily spending (expenses)
    daily = defaultdict(float)
    for t in txns:
        if float(t["amount"]) < 0:
            day = t["_dt"].strftime("%d")
            daily[day] += abs(float(t["amount"]))

    # Income categories
    income_cats = defaultdict(float)
    for t in txns:
        if float(t["amount"]) > 0:
            income_cats[t["category"].split(" — ")[0].strip()] += float(t["amount"])

    sorted_expense_cats = sorted(cats.items(), key=lambda x: x[1], reverse=True)
    sorted_income_cats  = sorted(income_cats.items(), key=lambda x: x[1], reverse=True)
    sorted_daily = sorted(daily.items())

    return {
        "month": month, "year": year,
        "income": round(income, 2), "expense": round(expense, 2),
        "savings": round(income - expense, 2),
        "savings_rate": round((income-expense)/income*100, 1) if income > 0 else 0,
        "total_txns": len(txns),
        "expense_categories": [{"name": k, "amount": round(v, 2)} for k, v in sorted_expense_cats],
        "income_categories":  [{"name": k, "amount": round(v, 2)} for k, v in sorted_income_cats],
        "daily_expense": [{"day": k, "amount": round(v, 2)} for k, v in sorted_daily]
    }

# ── POST /ai/report ─────────────────────────────────────
@app.post("/ai/report")
def ai_report(body: ReportRequest):
    all_txns = list(txns_col.find({"user": body.user}, {"_id": 0}))
    txns = []
    for t in all_txns:
        try:
            dt = datetime.strptime(t["created_at"], "%d %b %Y, %I:%M %p")
            if dt.month == body.month and dt.year == body.year:
                txns.append({**t, "_dt": dt})
        except:
            pass

    if not txns:
        raise HTTPException(status_code=400, detail="No transactions for this month")

    income   = sum(float(t["amount"]) for t in txns if float(t["amount"]) > 0)
    expense  = sum(abs(float(t["amount"])) for t in txns if float(t["amount"]) < 0)
    savings  = income - expense
    savings_r = round((savings / income) * 100, 1) if income > 0 else 0
    ratio     = round((expense / income) * 100, 1) if income > 0 else 0

    cats = defaultdict(float)
    income_cats = defaultdict(float)
    daily = defaultdict(float)
    for t in txns:
        amt = float(t["amount"])
        cat = t["category"].split(" — ")[0].strip()
        if amt < 0:
            cats[cat] += abs(amt)
            daily[t["_dt"].strftime("%d")] += abs(amt)
        else:
            income_cats[cat] += amt

    sorted_cats   = sorted(cats.items(), key=lambda x: x[1], reverse=True)
    sorted_income = sorted(income_cats.items(), key=lambda x: x[1], reverse=True)
    month_name    = datetime(body.year, body.month, 1).strftime("%B %Y")

    # ── Try Gemini first ─────────────────────────────────
    try:
        import time
        top_cats = ", ".join([f"{c}:Rs.{a:,.0f}" for c,a in sorted_cats[:5]])
        prompt = f"""Financial report for Indian user. Month:{month_name} Income:Rs.{income:,.0f} Expense:Rs.{expense:,.0f} Savings:Rs.{savings:,.0f}({savings_r}%) Transactions:{len(txns)} Top expenses:{top_cats}

Write a friendly report with these 6 sections using ## headings and emojis:
## 📋 Executive Summary
## 💰 Income & Savings Analysis
## 📊 Expense Breakdown
## 💸 Unnecessary Expenses
## 💡 Budget Recommendations for Next Month
## ✅ 5 Action Steps

Use Rs. for currency. Be specific. Keep each section 3-5 lines. Friendly encouraging tone."""

        for attempt in range(2):
            try:
                resp = gemini_client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
                return {
                    "status": "ok", "month": month_name,
                    "report": resp.text.strip(), "source": "ai",
                    "stats": {"income": income, "expense": expense, "savings": savings,
                              "savings_rate": savings_r, "top_categories": sorted_cats[:5], "total_txns": len(txns)}
                }
            except Exception as e:
                if attempt == 0:
                    time.sleep(5)
                    continue
                break
    except:
        pass

    # ── Fallback: Smart Python-generated report ──────────
    savings_label = "🌟 Excellent" if savings_r >= 40 else ("👍 Good" if savings_r >= 20 else "⚠️ Needs Improvement")
    spend_label   = "Very Controlled 🎯" if ratio <= 50 else ("Moderate 💡" if ratio <= 70 else "High 🚨")
    top_cat       = sorted_cats[0] if sorted_cats else None
    top_pct       = round((top_cat[1] / expense) * 100, 1) if top_cat and expense > 0 else 0
    busiest_day   = max(daily.items(), key=lambda x: x[1])[0] if daily else "N/A"
    avg_per_day   = round(expense / 30, 0)

    # Build category breakdown
    cat_lines = []
    for i, (cat, amt) in enumerate(sorted_cats[:8]):
        pct  = round((amt / expense) * 100, 1) if expense > 0 else 0
        tip  = "Consider reducing this" if pct > 30 else ("This looks reasonable" if pct > 15 else "Well controlled ✅")
        cat_lines.append(f"  **{i+1}. {cat}** — Rs.{amt:,.0f} ({pct}% of expenses) → {tip}")
    cat_breakdown = "\n".join(cat_lines)

    # Budget recommendations
    budget_lines = []
    for cat, amt in sorted_cats[:8]:
        suggested = round(amt * 0.85, 0) if amt > 1000 else amt
        budget_lines.append(f"  • {cat}: Rs.{suggested:,.0f} (currently Rs.{amt:,.0f})")
    budget_text = "\n".join(budget_lines)

    # Income sources
    income_text = ", ".join([f"{c} (Rs.{a:,.0f})" for c, a in sorted_income[:3]]) if sorted_income else "Not recorded"

    report = f"""## 📋 Executive Summary
{month_name} was a **{savings_label}** month for you financially. You earned Rs.{income:,.0f} and spent Rs.{expense:,.0f}, saving Rs.{savings:,.0f} which is {savings_r}% of your income. Your spending behaviour is **{spend_label}** — you spent {ratio}% of your income. {"Great job keeping expenses in check! 🎉" if ratio <= 60 else "There is room to cut down expenses next month. 💪"}

## 💰 Income & Savings Analysis
**Total Income:** Rs.{income:,.0f} from {income_text}
**Total Savings:** Rs.{savings:,.0f} ({savings_r}% savings rate) — {savings_label}
{"✅ You are above the recommended 20% savings rate — excellent financial discipline!" if savings_r >= 20 else "⚠️ The recommended savings rate is at least 20%. Try to cut Rs." + str(round(expense * 0.15, 0)) + " from expenses next month."}
Your daily average expense was Rs.{avg_per_day:,.0f} and your busiest spending day was Day {busiest_day} of the month.

## 📊 Expense Breakdown
You had **{len(sorted_cats)} expense categories** totalling Rs.{expense:,.0f}:
{cat_breakdown}
{"⚠️ Your top category **" + top_cat[0] + "** took up " + str(top_pct) + "% of your expenses — keep an eye on this!" if top_cat else ""}

## 💸 Unnecessary Expenses
{"⚠️ **" + sorted_cats[0][0] + "** (Rs." + f"{sorted_cats[0][1]:,.0f}" + ") — Your highest expense. Review if all of this was necessary." if len(sorted_cats) > 0 else ""}
{"💡 **" + sorted_cats[1][0] + "** (Rs." + f"{sorted_cats[1][1]:,.0f}" + ") — Check if this can be reduced by 10-15%." if len(sorted_cats) > 1 else ""}
{"🔍 **" + sorted_cats[2][0] + "** (Rs." + f"{sorted_cats[2][1]:,.0f}" + ") — Small savings here add up over the year." if len(sorted_cats) > 2 else ""}
Even saving 10% on your top 3 categories would save Rs.{round(sum(a for _,a in sorted_cats[:3]) * 0.10, 0):,.0f} next month!

## 💡 Budget Recommendations for Next Month
Based on your spending, here are suggested budgets (15% reduction target):
{budget_text}
**Total suggested budget: Rs.{round(expense * 0.85, 0):,.0f}** vs current Rs.{expense:,.0f} — potential saving of Rs.{round(expense * 0.15, 0):,.0f} 💰

## ✅ 5 Action Steps
1. 🎯 **Set a daily spending limit** of Rs.{round(expense * 0.85 / 30, 0):,.0f}/day (your current average is Rs.{avg_per_day:,.0f}/day)
2. 💰 **Auto-save Rs.{round(income * 0.20, 0):,.0f}** at the start of next month (20% of income) before spending anything
3. 📉 **Reduce {sorted_cats[0][0] if sorted_cats else "top expense"} by 15%** — target Rs.{round(sorted_cats[0][1] * 0.85, 0) if sorted_cats else 0:,.0f} instead of Rs.{round(sorted_cats[0][1], 0) if sorted_cats else 0:,.0f}
4. 📊 **Track every expense daily** — even small ones add up to Rs.{round(expense * 0.05, 0):,.0f}+ per month
5. 🏦 **Target savings of Rs.{round(income * 0.25, 0):,.0f}** next month (25% of income) — {"you're already close! 🎉" if savings_r >= 20 else "an increase of Rs." + str(round(income * 0.25 - savings, 0)) + " from this month"}"""

    return {
        "status": "ok", "month": month_name,
        "report": report, "source": "smart",
        "stats": {"income": income, "expense": expense, "savings": savings,
                  "savings_rate": savings_r, "top_categories": sorted_cats[:5], "total_txns": len(txns)}
    }

# ── POST /report/pdf ────────────────────────────────────
class PDFRequest(BaseModel):
    user: str
    month: int
    year: int
    ai_report: str = ""
    charts: dict = {}

@app.post("/report/pdf")
def download_report_pdf(body: PDFRequest):
    import base64, re
    from reportlab.platypus import Image as RLImage

    # ── Fetch & compute data ─────────────────────────────
    all_txns = list(txns_col.find({"user": body.user}, {"_id": 0}))
    txns = []
    for t in all_txns:
        try:
            dt = datetime.strptime(t["created_at"], "%d %b %Y, %I:%M %p")
            if dt.month == body.month and dt.year == body.year:
                txns.append({**t, "_dt": dt})
        except:
            pass

    if not txns:
        raise HTTPException(status_code=400, detail="No transactions for this month")

    income  = sum(float(t["amount"]) for t in txns if float(t["amount"]) > 0)
    expense = sum(abs(float(t["amount"])) for t in txns if float(t["amount"]) < 0)
    savings = income - expense
    savings_rate = round((savings / income) * 100, 1) if income > 0 else 0

    cats = defaultdict(float)
    income_cats = defaultdict(float)
    daily = defaultdict(float)
    for t in txns:
        amt = float(t["amount"])
        cat = t["category"].split(" — ")[0].strip()
        if amt < 0:
            cats[cat] += abs(amt)
            daily[t["_dt"].strftime("%d")] += abs(amt)
        else:
            income_cats[cat] += amt

    sorted_exp_cats    = sorted(cats.items(), key=lambda x: x[1], reverse=True)
    sorted_income_cats = sorted(income_cats.items(), key=lambda x: x[1], reverse=True)
    month_name = datetime(body.year, body.month, 1).strftime("%B %Y")

    # ── Decode chart images ──────────────────────────────
    def b64_to_image(b64str, w, h):
        if not b64str:
            return None
        try:
            img_data = base64.b64decode(b64str)
            buf = io.BytesIO(img_data)
            return RLImage(buf, width=w, height=h)
        except:
            return None

    cm_to_pt = lambda x: x * cm

    # ── Build PDF ────────────────────────────────────────
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
        topMargin=1.8*cm, bottomMargin=1.8*cm
    )

    # ── Colours ──────────────────────────────────────────
    BLUE    = colors.HexColor("#3b6ef8")
    BLUE_D  = colors.HexColor("#1a4fd6")
    GREEN   = colors.HexColor("#12b76a")
    RED     = colors.HexColor("#f04438")
    AMBER   = colors.HexColor("#f79009")
    PURPLE  = colors.HexColor("#7c3aed")
    GRAY900 = colors.HexColor("#101828")
    GRAY700 = colors.HexColor("#344054")
    GRAY500 = colors.HexColor("#667085")
    GRAY300 = colors.HexColor("#d0d5dd")
    GRAY100 = colors.HexColor("#f2f4f7")
    GRAY50  = colors.HexColor("#f9fafb")
    WHITE   = colors.white

    CHART_COLORS = [
        colors.HexColor("#3b6ef8"), colors.HexColor("#12b76a"),
        colors.HexColor("#f04438"), colors.HexColor("#f79009"),
        colors.HexColor("#7c3aed"), colors.HexColor("#06aed4"),
        colors.HexColor("#ee46bc"), colors.HexColor("#85cc34"),
    ]

    # ── Styles ───────────────────────────────────────────
    def S(name, **kw): return ParagraphStyle(name, **kw)

    title_s   = S("T",  fontSize=20, textColor=WHITE,   fontName="Helvetica-Bold", leading=26)
    sub_s     = S("Su", fontSize=9,  textColor=colors.HexColor("#c7d7fe"), fontName="Helvetica", leading=14)
    h2_s      = S("H2", fontSize=12, textColor=GRAY900, fontName="Helvetica-Bold", leading=16, spaceBefore=4)
    h3_s      = S("H3", fontSize=10, textColor=BLUE,    fontName="Helvetica-Bold", leading=14, spaceBefore=4)
    body_s    = S("B",  fontSize=8.5,textColor=GRAY700, fontName="Helvetica",      leading=13)
    small_s   = S("Sm", fontSize=7.5,textColor=GRAY500, fontName="Helvetica",      leading=11)
    kv_s      = S("KV", fontSize=15, textColor=GRAY900, fontName="Helvetica-Bold", leading=20, alignment=TA_CENTER)
    kl_s      = S("KL", fontSize=7,  textColor=GRAY500, fontName="Helvetica",      leading=10, alignment=TA_CENTER)
    ks_s      = S("KS", fontSize=6.5,textColor=GRAY500, fontName="Helvetica",      leading=9,  alignment=TA_CENTER)
    foot_s    = S("F",  fontSize=6.5,textColor=GRAY300, fontName="Helvetica",      leading=9,  alignment=TA_CENTER)
    ch_title  = S("CT", fontSize=9,  textColor=GRAY700, fontName="Helvetica-Bold", leading=12, alignment=TA_CENTER)
    rate_col  = GREEN if savings_rate >= 40 else (AMBER if savings_rate >= 20 else RED)

    story = []
    PW = 17.4 * cm   # usable page width

    # ════════════════════════════════════════════════════
    # 1. HEADER BANNER
    # ════════════════════════════════════════════════════
    hdr = Table([[
        Paragraph("📊 ETMS Monthly Financial Report", title_s),
        Paragraph(f"{month_name}<br/>"
                  f"<font size='8'>Generated: {datetime.now().strftime('%d %b %Y, %I:%M %p')}</font><br/>"
                  f"<font size='8'>User: {body.user}</font>", sub_s)
    ]], colWidths=[11*cm, 6.4*cm])
    hdr.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,-1), BLUE),
        ("ROWPADDING", (0,0),(-1,-1), 18),
        ("VALIGN",     (0,0),(-1,-1), "MIDDLE"),
        ("ALIGN",      (1,0),(1,0),   "RIGHT"),
    ]))
    story += [hdr, Spacer(1, 14)]

    # ════════════════════════════════════════════════════
    # 2. KPI SUMMARY CARDS
    # ════════════════════════════════════════════════════
    story.append(Paragraph("📈 Financial Summary", h2_s))
    story.append(Spacer(1, 6))

    kpi_bg = [
        colors.HexColor("#ecfdf3"), colors.HexColor("#fef3f2"),
        colors.HexColor("#eff3ff"), colors.HexColor("#f5f3ff"),
    ]
    kpi_colors = [GREEN, RED, BLUE, PURPLE]
    kpi_vals   = [f"₹{income:,.0f}", f"₹{expense:,.0f}", f"₹{savings:,.0f}", str(len(txns))]
    kpi_labels = ["Total Income", "Total Expense", "Net Savings", "Transactions"]
    kpi_subs   = [
        f"{len(sorted_income_cats)} source(s)",
        f"{len(sorted_exp_cats)} categor{'y' if len(sorted_exp_cats)==1 else 'ies'}",
        f"{savings_rate}% of income",
        f"{sum(1 for t in txns if float(t['amount'])>0)} in / {sum(1 for t in txns if float(t['amount'])<0)} out",
    ]

    kpi_data = [[
        Paragraph(f"<font color='#{kpi_colors[i].hexval()[2:]}'>{kpi_vals[i]}</font>", kv_s)
        for i in range(4)
    ],[
        Paragraph(kpi_labels[i], kl_s) for i in range(4)
    ],[
        Paragraph(kpi_subs[i], ks_s) for i in range(4)
    ]]
    kpi_t = Table(kpi_data, colWidths=[PW/4]*4, rowHeights=[1.1*cm, 0.55*cm, 0.45*cm])
    kpi_t.setStyle(TableStyle([
        *[(("BACKGROUND",(i,0),(i,2), kpi_bg[i])) for i in range(4)],
        ("ALIGN",      (0,0),(-1,-1), "CENTER"),
        ("VALIGN",     (0,0),(-1,-1), "MIDDLE"),
        ("ROWPADDING", (0,0),(-1,-1), 6),
        ("GRID",       (0,0),(-1,-1), 1.5, WHITE),
    ]))
    story += [kpi_t, Spacer(1, 8)]

    # Savings rate banner
    rate_label = "🌟 Excellent Saver" if savings_rate>=40 else ("👍 Good Progress" if savings_rate>=20 else "⚠️ Needs Improvement")
    rate_row = Table([[
        Paragraph(f"<font color='#{rate_col.hexval()[2:]}'><b>Savings Rate: {savings_rate}%  —  {rate_label}</b></font>", body_s),
    ]], colWidths=[PW])
    rate_row.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,-1), colors.HexColor("#ecfdf3") if savings_rate>=40 else (colors.HexColor("#fffaeb") if savings_rate>=20 else colors.HexColor("#fef3f2"))),
        ("ROWPADDING", (0,0),(-1,-1), 10),
    ]))
    story += [rate_row, Spacer(1, 16), HRFlowable(width="100%", thickness=0.5, color=GRAY100), Spacer(1, 12)]

    # ════════════════════════════════════════════════════
    # 3. CHARTS — Row 1: Donut + Bar
    # ════════════════════════════════════════════════════
    story.append(Paragraph("📊 Visual Analysis", h2_s))
    story.append(Spacer(1, 8))

    half_w = (PW - 0.5*cm) / 2
    chart_h = 7.5 * cm

    donut_img = b64_to_image(body.charts.get("donut",""), half_w, chart_h)
    bar_img   = b64_to_image(body.charts.get("bar",""),   half_w, chart_h)

    def chart_cell(img, title):
        content = []
        content.append(Paragraph(title, ch_title))
        content.append(Spacer(1,4))
        if img:
            content.append(img)
        else:
            content.append(Paragraph("Chart not available", small_s))
        return content

    if donut_img or bar_img:
        row1 = Table([[
            chart_cell(donut_img, "🍩 Expense by Category"),
            chart_cell(bar_img,   "📊 Top Spending Categories"),
        ]], colWidths=[half_w, half_w], rowHeights=[chart_h + 1.2*cm])
        row1.setStyle(TableStyle([
            ("BACKGROUND", (0,0),(-1,-1), GRAY50),
            ("ROWPADDING", (0,0),(-1,-1), 10),
            ("VALIGN",     (0,0),(-1,-1), "TOP"),
            ("ALIGN",      (0,0),(-1,-1), "CENTER"),
            ("GRID",       (0,0),(-1,-1), 1, WHITE),
        ]))
        story += [row1, Spacer(1, 8)]

    # ── Row 2: Line chart (full width) ──
    line_img = b64_to_image(body.charts.get("line",""), PW, 6*cm)
    if line_img:
        line_cell = Table([[chart_cell(line_img, "📈 Daily Spending Trend")]], colWidths=[PW], rowHeights=[6*cm + 1.2*cm])
        line_cell.setStyle(TableStyle([
            ("BACKGROUND", (0,0),(-1,-1), GRAY50),
            ("ROWPADDING", (0,0),(-1,-1), 10),
            ("VALIGN",     (0,0),(-1,-1), "TOP"),
            ("ALIGN",      (0,0),(-1,-1), "CENTER"),
        ]))
        story += [line_cell, Spacer(1, 8)]

    # ── Row 3: Income vs Expense + Income Pie ──
    ie_img  = b64_to_image(body.charts.get("income_expense",""), half_w, 6*cm)
    pie_img = b64_to_image(body.charts.get("income_pie",""),     half_w, 6*cm)
    if ie_img or pie_img:
        row3 = Table([[
            chart_cell(ie_img,  "⚖️ Income vs Expense vs Savings"),
            chart_cell(pie_img, "🎯 Income Sources"),
        ]], colWidths=[half_w, half_w], rowHeights=[6*cm + 1.2*cm])
        row3.setStyle(TableStyle([
            ("BACKGROUND", (0,0),(-1,-1), GRAY50),
            ("ROWPADDING", (0,0),(-1,-1), 10),
            ("VALIGN",     (0,0),(-1,-1), "TOP"),
            ("ALIGN",      (0,0),(-1,-1), "CENTER"),
            ("GRID",       (0,0),(-1,-1), 1, WHITE),
        ]))
        story += [row3, Spacer(1, 12)]

    story += [HRFlowable(width="100%", thickness=0.5, color=GRAY100), Spacer(1, 12)]

    # ════════════════════════════════════════════════════
    # 4. EXPENSE CATEGORY BREAKDOWN TABLE
    # ════════════════════════════════════════════════════
    if sorted_exp_cats:
        story.append(Paragraph("📋 Expense Category Breakdown", h2_s))
        story.append(Spacer(1, 6))

        hdr_row = [
            Paragraph("<b>Rank</b>", small_s), Paragraph("<b>Category</b>", small_s),
            Paragraph("<b>Amount</b>", small_s), Paragraph("<b>% of Total</b>", small_s),
            Paragraph("<b>Visual Bar</b>", small_s),
        ]
        rows = [hdr_row]
        for i, (cat, amt) in enumerate(sorted_exp_cats[:12]):
            pct  = (amt/expense*100) if expense > 0 else 0
            bars = int(pct/4)
            c    = CHART_COLORS[i % len(CHART_COLORS)]
            rows.append([
                Paragraph(str(i+1), small_s),
                Paragraph(cat[:30], small_s),
                Paragraph(f"₹{amt:,.0f}", small_s),
                Paragraph(f"{pct:.1f}%", small_s),
                Paragraph(f"<font color='#{c.hexval()[2:]}'>{'█'*bars}</font>{'░'*(25-bars)}", small_s),
            ])
        cat_t = Table(rows, colWidths=[1*cm, 5.5*cm, 3*cm, 2.5*cm, 5.4*cm])
        cat_t.setStyle(TableStyle([
            ("BACKGROUND",     (0,0),(-1,0), BLUE),
            ("TEXTCOLOR",      (0,0),(-1,0), WHITE),
            ("FONTNAME",       (0,0),(-1,0), "Helvetica-Bold"),
            ("ROWPADDING",     (0,0),(-1,-1), 7),
            ("ROWBACKGROUNDS", (0,1),(-1,-1), [WHITE, GRAY50]),
            ("GRID",           (0,0),(-1,-1), 0.5, GRAY100),
            ("VALIGN",         (0,0),(-1,-1), "MIDDLE"),
        ]))
        story += [cat_t, Spacer(1, 12)]

    # ════════════════════════════════════════════════════
    # 5. INCOME SOURCES TABLE
    # ════════════════════════════════════════════════════
    if sorted_income_cats:
        story.append(Paragraph("💰 Income Sources", h2_s))
        story.append(Spacer(1, 6))
        inc_rows = [[Paragraph("<b>Source</b>", small_s), Paragraph("<b>Amount</b>", small_s), Paragraph("<b>% of Income</b>", small_s)]]
        for cat, amt in sorted_income_cats:
            pct = (amt/income*100) if income > 0 else 0
            inc_rows.append([Paragraph(cat[:35], small_s), Paragraph(f"₹{amt:,.0f}", small_s), Paragraph(f"{pct:.1f}%", small_s)])
        inc_t = Table(inc_rows, colWidths=[9*cm, 4.5*cm, 3.9*cm])
        inc_t.setStyle(TableStyle([
            ("BACKGROUND",     (0,0),(-1,0), GREEN),
            ("TEXTCOLOR",      (0,0),(-1,0), WHITE),
            ("FONTNAME",       (0,0),(-1,0), "Helvetica-Bold"),
            ("ROWPADDING",     (0,0),(-1,-1), 7),
            ("ROWBACKGROUNDS", (0,1),(-1,-1), [WHITE, GRAY50]),
            ("GRID",           (0,0),(-1,-1), 0.5, GRAY100),
            ("VALIGN",         (0,0),(-1,-1), "MIDDLE"),
        ]))
        story += [inc_t, Spacer(1, 12)]

    # ════════════════════════════════════════════════════
    # 6. SPENDING BEHAVIOUR INSIGHTS
    # ════════════════════════════════════════════════════
    story += [HRFlowable(width="100%", thickness=0.5, color=GRAY100), Spacer(1, 10)]
    story.append(Paragraph("🧠 Spending Behaviour Insights", h2_s))
    story.append(Spacer(1, 6))

    ratio       = round((expense/income)*100,1) if income > 0 else 0
    spend_label = "Very Controlled 🎯" if ratio<=50 else ("Moderate Spender 💡" if ratio<=70 else "High Spender 🚨")
    top_cat     = sorted_exp_cats[0] if sorted_exp_cats else None
    top_pct     = round((top_cat[1]/expense)*100,1) if top_cat and expense>0 else 0

    beh_items = [
        ("💰 Savings Behaviour", rate_label, f"Saved {savings_rate}% of income this month", rate_col),
        ("📊 Spending Ratio",    spend_label, f"Spent {ratio}% of income this month",
         GREEN if ratio<=50 else (AMBER if ratio<=70 else RED)),
        ("🏆 Top Expense",       top_cat[0] if top_cat else "N/A",
         f"{top_pct}% of expenses — ₹{top_cat[1]:,.0f}" if top_cat else "No expenses", PURPLE),
        ("📅 Activity",          f"{len(txns)} Transactions",
         f"{len(sorted_exp_cats)} expense categories tracked", BLUE),
    ]
    beh_data = [[
        Paragraph(
            f"<b>{title}</b><br/>"
            f"<font size='8' color='#{col.hexval()[2:]}'>{value}</font><br/>"
            f"<font size='7' color='#667085'>{desc}</font>",
            body_s
        )
        for title, value, desc, col in beh_items
    ]]
    beh_t = Table(beh_data, colWidths=[PW/4]*4)
    beh_t.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,-1), GRAY50),
        ("ROWPADDING", (0,0),(-1,-1), 12),
        ("GRID",       (0,0),(-1,-1), 1.5, WHITE),
        ("VALIGN",     (0,0),(-1,-1), "TOP"),
    ]))
    story += [beh_t, Spacer(1, 14)]

    # ════════════════════════════════════════════════════
    # 7. AI ANALYSIS
    # ════════════════════════════════════════════════════
    if body.ai_report.strip():
        story += [HRFlowable(width="100%", thickness=0.5, color=GRAY100), Spacer(1, 10)]
        story.append(Paragraph("🤖 AI Analysis — Gemini", h2_s))
        story.append(Spacer(1, 6))
        for line in body.ai_report.split("\n"):
            line = line.strip()
            if not line:
                story.append(Spacer(1, 3))
                continue
            line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
            if re.match(r"^#{1,2}\s", line):
                story.append(Paragraph(line.lstrip("#").strip(), h2_s))
            elif re.match(r"^###\s", line):
                story.append(Paragraph(line.lstrip("#").strip(), h3_s))
            elif line.startswith("- ") or line.startswith("• "):
                story.append(Paragraph("• " + line[2:], body_s))
            elif re.match(r"^\d+\.", line):
                story.append(Paragraph(line, body_s))
            else:
                story.append(Paragraph(line, body_s))
        story.append(Spacer(1, 12))

    # ════════════════════════════════════════════════════
    # 8. FOOTER
    # ════════════════════════════════════════════════════
    story += [
        HRFlowable(width="100%", thickness=0.5, color=GRAY100),
        Spacer(1, 6),
        Paragraph(
            f"Generated by ETMS — Expense Tracker Management System  |  "
            f"Powered by Gemini AI  |  {datetime.now().strftime('%d %b %Y')}",
            foot_s
        )
    ]

    # ── Build & stream ───────────────────────────────────
    doc.build(story)
    buffer.seek(0)
    filename = f"ETMS_Report_{month_name.replace(' ','_')}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# ── POST /targets/add ────────────────────────────────────
@app.post("/targets/add")
def add_target(t: Target):
    tid = str(uuid.uuid4())
    targets_col.insert_one({
        "id": tid,
        "user": t.user,
        "target_name": t.target_name,
        "target_type": t.target_type,
        "category": t.category,
        "amount": t.amount,
        "created_at": datetime.now().strftime("%d %b %Y, %I:%M %p")
    })
    return {"status": "ok", "id": tid}

# ── GET /targets ──────────────────────────────────────────
@app.get("/targets")
def get_targets(user: str):
    if not user: raise HTTPException(status_code=400, detail="User required")
    docs = list(targets_col.find({"user": user}, {"_id": 0}))

    # Compute progress from current month's transactions
    txns = list(txns_col.find({"user": user}, {"_id": 0}))
    now  = datetime.now()

    for tgt in docs:
        cat = tgt["category"].lower().strip()
        spent  = 0.0
        earned = 0.0
        for tx in txns:
            try:
                dt = datetime.strptime(tx["created_at"], "%d %b %Y, %I:%M %p")
                if dt.month != now.month or dt.year != now.year:
                    continue
            except:
                continue
            tx_cat = tx["category"].split(" — ")[0].lower().strip()
            amt    = float(tx["amount"])
            # Match: "all" matches everything; otherwise match if tx category contains target category
            if cat == "all" or tx_cat == cat or cat in tx_cat or tx_cat in cat:
                if amt < 0:
                    spent  += abs(amt)
                else:
                    earned += amt

        tgt["progress"] = round(spent if tgt["target_type"] == "spending_limit" else earned, 2)
        tgt["pct"]      = min(100, round((tgt["progress"] / tgt["amount"]) * 100, 1)) if tgt["amount"] > 0 else 0

    return docs

# ── DELETE /targets/{id} ──────────────────────────────────
@app.delete("/targets/{target_id}")
def delete_target(target_id: str, user: str):
    result = targets_col.delete_one({"id": target_id, "user": user})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Target not found")
    return {"status": "ok"}

app.mount("/", StaticFiles(directory="static", html=True), name="static")
