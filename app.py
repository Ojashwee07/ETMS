from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, validator
from pymongo import MongoClient
from dotenv import load_dotenv
import hashlib, uuid, os, json, io, base64, csv, re
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
#changebyansh
#changebyansh

load_dotenv()

app = FastAPI(title="ETMS - Expense Tracker Management System")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client    = MongoClient(MONGO_URI)
db        = client["etms_db"]
users_col      = db["users"]
txns_col       = db["transactions"]
targets_col    = db["targets"]
aos_hist_col   = db["aos_chat_history"]
aos_ctx_col    = db["aos_user_context"]
aos_learn_col  = db["aos_learned_qa"]
import_hist_col = db["import_history"]
splits_col      = db["splits_groups"]

# ── Create indexes for performance ──────────────────
try:
    aos_hist_col.create_index([("user", 1)], unique=True)
    aos_ctx_col.create_index([("user", 1)], unique=True)
    aos_learn_col.create_index([("question", "text")])
    aos_learn_col.create_index([("question_hash", 1)], unique=True)
except Exception:
    pass  # Indexes may already exist

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


# ── POST /fraud/analyze ──────────────────────────────────
class FraudRequest(BaseModel):
    text: str = ""
    file_data: str = ""
    file_type: str = ""
    user: str = ""

@app.post("/fraud/analyze")
def fraud_analyze(body: FraudRequest):
    content = body.text.strip()
    if not content and not body.file_data:
        raise HTTPException(status_code=400, detail="No content provided")

    import re, urllib.parse
    text_lower = content.lower()
    words      = text_lower.split()
    word_count = len(words)

    # ══════════════════════════════════════════════════
    # LAYER 1 — CONTEXT NEUTRALIZERS (run first)
    # Legitimate context that should reduce suspicion
    # ══════════════════════════════════════════════════
    neutralizers = []
    neutral_score = 0

    # Official government websites mentioned
    official_domains = ["incometax.gov.in", "india.gov.in", "rbi.org.in",
                        "sebi.gov.in", "uidai.gov.in", "mca.gov.in",
                        "npci.org.in", "indianrailways.gov.in"]
    if any(d in text_lower for d in official_domains):
        neutral_score += 30
        neutralizers.append("Official government domain mentioned — reduces impersonation risk")

    # Official bank helpline indicators
    if any(x in text_lower for x in ["1800", "toll free", "customer care", "helpline",
                                    "official app", "registered mobile"]):
        neutral_score += 10
        neutralizers.append("Official helpline/contact reference detected")

    # Transaction confirmation language (real bank messages)
    txn_words = ["credited", "debited", "transaction id", "txn id", "ref no",
                "reference number", "utr number", "available balance", "closing balance"]
    txn_found = [t for t in txn_words if t in text_lower]
    if len(txn_found) >= 2:
        neutral_score += 20
        neutralizers.append(f"Multiple transaction confirmation terms: {', '.join(txn_found[:3])}")

    # Explicit disclaimer of not asking for sensitive info
    safe_disclaimers = ["never ask for otp", "never share otp", "do not share otp",
                        "bank will never ask", "do not give", "beware of fraud",
                        "standard verification", "official government website only",
                        "visit only the official"]
    disc_found = [d for d in safe_disclaimers if d in text_lower]
    if disc_found:
        neutral_score += 25
        neutralizers.append(f"Safety disclaimer present: '{disc_found[0]}'")

    # Professional business communication markers
    if any(x in text_lower for x in ["invoice", "quotation", "purchase order",
                                    "as per our records", "kindly find attached",
                                    "with reference to"]):
        neutral_score += 15
        neutralizers.append("Professional business communication format")

    # Unsubscribe / legal footer
    if any(x in text_lower for x in ["unsubscribe", "privacy policy",
                                    "terms and conditions", "opt out"]):
        neutral_score += 10
        neutralizers.append("Contains legal/compliance footer (regulatory requirement)")

    # ══════════════════════════════════════════════════
    # LAYER 2 — PATTERN DETECTION (10 categories)
    # Weights are BASE scores — context-adjusted below
    # ══════════════════════════════════════════════════
    fraud_patterns = [

        # ── 1. URGENCY & PRESSURE TACTICS ──────────────────
        ("urgent_language", [
            # Time pressure
            "urgent", "act now", "act immediately", "act fast", "respond now",
            "limited time", "limited period", "limited slots", "limited offer",
            "last chance", "last opportunity", "final notice", "final reminder",
            "expires soon", "expiring today", "expires in 24", "expires in 1 hour",
            "within 24 hours", "within 48 hours", "within the next hour",
            "before it's too late", "don't miss this", "don't delay",
            "hurry", "hurry up", "rush", "immediately", "right now",
            "call now", "reply now", "respond immediately", "asap",
            "time sensitive", "time is running out", "running out of time",
            "today only", "offer ends today", "deadline today",
            "no time to waste", "quick action required", "immediate attention",
            # Fear of loss
            "will expire", "will be cancelled", "will be terminated",
            "will be deleted", "will be deactivated", "will be closed",
            "last warning", "final warning", "last opportunity"
        ], 10),

        # ── 2. PRIZE / LOTTERY / GIFT SCAMS ────────────────
        ("prize_lottery", [
            # Prize claims
            "you have won", "you've won", "you won", "you are the winner",
            "congratulations you", "selected as winner", "lucky winner",
            "prize winner", "grand prize", "bumper prize", "jackpot winner",
            # Lottery
            "lottery", "lucky draw", "lucky number", "lucky dip",
            "raffle", "sweepstakes", "mega draw", "bumper draw",
            # Gift & reward
            "free gift", "gift voucher", "gift card won", "reward points redeemed",
            "special reward", "you have been selected", "chosen randomly",
            "random selection", "our lucky customer",
            # KBC-style scams common in India
            "kbc lottery", "kbc winner", "kaun banega", "whatsapp lottery",
            "sim lottery", "jio lottery", "airtel lottery",
            "facebook lottery", "instagram lucky draw",
            # Claim language
            "claim your prize", "collect your prize", "claim reward",
            "claim gift", "to claim call", "call to collect"
        ], 20),

        # ── 3. BANKING & OTP FRAUD ─────────────────────────
        ("bank_request", [
            # OTP related
            "share your otp", "enter your otp", "provide otp", "send otp",
            "otp is required", "verify with otp", "otp verification",
            "one time password", "enter the otp sent",
            # PIN / Password
            "share your pin", "enter your pin", "atm pin", "debit pin",
            "share your password", "enter your password", "login password",
            "internet banking password", "net banking password",
            # Card details
            "share cvv", "card cvv", "share card number", "full card number",
            "16 digit card", "card expiry", "card details required",
            "debit card number", "credit card number",
            # Account details
            "share account number", "bank account number", "ifsc code required",
            "share net banking", "net banking credentials", "online banking details",
            "share upi pin", "upi password", "google pay pin", "phonepe pin",
            "paytm pin", "share upi id",
            # General banking
            "bank details required", "banking information", "verify your bank",
            "update bank details", "re-enter banking", "confirm bank account"
        ], 28),

        # ── 4. PERSONAL IDENTITY THEFT ─────────────────────
        ("personal_info", [
            # Aadhaar
            "share your aadhaar", "send aadhaar", "aadhaar number required",
            "aadhaar card details", "aadhaar otp", "aadhaar verification",
            "12 digit aadhaar",
            # PAN
            "share pan", "send pan", "pan card required", "pan number",
            "pan details", "pan card copy", "pan card photo",
            # Other identity
            "share passport", "passport number required", "passport copy",
            "voter id", "driving licence copy", "share driving licence",
            # Personal details
            "mother's name", "father's name", "date of birth required",
            "dob required", "share your dob", "place of birth",
            "personal details required", "personal information required",
            "submit your documents", "upload your id", "id proof required",
            "address proof", "kyc documents", "full kyc required",
            "video kyc", "complete your kyc", "kyc expired",
            "kyc pending", "kyc update required",
            # Financial identity
            "pan linked", "aadhaar linked", "link aadhaar",
            "gstin required", "gst number"
        ], 20),

        # ── 5. PHISHING LINKS ──────────────────────────────
        ("suspicious_links", [
            # URL shorteners
            "bit.ly", "tinyurl", "shorturl", "rb.gy", "t.ly",
            "ow.ly", "is.gd", "buff.ly", "tiny.cc", "short.io",
            "cutt.ly", "rebrand.ly", "smarturl",
            # Suspicious TLDs
            ".xyz", ".tk", ".ml", ".ga", ".cf", ".top",
            ".icu", ".club", ".online", ".site", ".win",
            # Phishing action words
            "click here to verify", "click here to claim", "click to collect",
            "click here to get", "click here immediately",
            "login here", "login now", "sign in here",
            "verify account now", "verify your account",
            "update your account", "confirm your account",
            "activate your account", "reactivate account",
            "secure your account", "unlock your account",
            # Link invitation
            "open the link", "visit the link", "follow the link",
            "tap the link", "use the link below", "click the button"
        ], 20),

        # ── 6. AUTHORITY IMPERSONATION ─────────────────────
        ("impersonation", [
            # Financial regulators
            "rbi has", "reserve bank of india notice", "rbi officer",
            "rbi helpline fraud", "fake rbi", "rbi is calling",
            "sebi notice", "sebi officer", "irdai notice",
            "npci alert", "nabard officer",
            # Tax authorities
            "income tax has", "income tax department notice",
            "income tax officer calling", "it department case",
            "gst department", "gst fraud detected", "tax evasion detected",
            # Law enforcement
            "police is coming", "police has registered", "police complaint",
            "cbi has", "cbi officer", "cbi investigation",
            "enforcement directorate", "ed officer", "ed raid",
            "cybercrime has detected", "cybercrime police",
            "crime branch", "anti fraud cell",
            # Courts
            "court has issued", "court order", "court summons",
            "high court notice", "supreme court order",
            "arrest warrant issued", "non-bailable warrant",
            # Customs & Narcotics
            "customs has seized", "narcotics found",
            "customs officer", "narcotics bureau",
            # Telecom
            "trai notice", "trai has detected", "sim will be blocked",
            "your number will be deactivated", "telecom department"
        ], 20),

        # ── 7. MONEY TRANSFER REQUESTS ─────────────────────
        ("money_transfer", [
            # Transfer requests
            "send money", "transfer money", "money transfer required",
            "transfer funds", "send funds", "wire transfer",
            "transfer to this account", "deposit to this account",
            # International transfer
            "western union", "money gram", "moneygram",
            "swift transfer", "iban transfer",
            # Crypto
            "send bitcoin", "send crypto", "pay in crypto",
            "bitcoin payment", "ethereum payment", "usdt payment",
            "pay in usdt", "send usdt", "crypto wallet",
            "bitcoin address", "wallet address",
            # Gift cards (common in scams)
            "pay via gift card", "itunes gift card", "amazon gift card",
            "google play gift card", "steam gift card", "gift card code",
            # Fees & charges (advance fee fraud)
            "registration fee", "processing fee", "advance fee",
            "security deposit", "refundable fee", "token amount",
            "joining fee", "activation fee", "admin fee",
            "handling fee", "delivery fee to release",
            "pay to claim", "fee to receive", "small fee required",
            "pay first to get", "deposit required to unlock",
            # UPI frauds
            "collect request", "upi collect", "scan and pay to receive",
            "pay rs to get rs", "pay small amount to unlock"
        ], 18),

        # ── 8. INVESTMENT & RETURNS SCAMS ──────────────────
        ("too_good", [
            # Return promises
            "guaranteed returns", "guaranteed profit", "guaranteed income",
            "100% guaranteed", "assured returns", "fixed returns",
            "risk free returns", "no risk investment", "zero risk",
            "100% safe investment", "fully guaranteed",
            # Unrealistic returns
            "double your money", "triple your money", "10x returns",
            "1000% returns", "500% profit", "200% profit",
            "1 lakh becomes 10 lakh", "money doubles in",
            "invest 1000 get 10000", "turn 500 into",
            # Easy money
            "easy money", "earn daily", "earn rs daily",
            "earn without working", "no work earn",
            "earn while sleeping", "passive income guaranteed",
            "automated income", "money works for you",
            # Per day income
            "rs 5000 per day", "rs 10000 daily", "earn 50000 monthly",
            "per day income guaranteed", "daily payout",
            # No experience needed
            "no experience needed", "no skills required",
            "anyone can do it", "no investment required",
            "zero investment earn", "free to join earn",
            # Get rich schemes
            "get rich quick", "financial freedom fast",
            "become crorepati", "crorepati scheme",
            "millionaire in months", "financially free in"
        ], 16),

        # ── 9. THREATS & LEGAL INTIMIDATION ────────────────
        ("threat_pressure", [
            # Arrest threats
            "will be arrested", "arrest warrant", "warrant issued",
            "police will arrest", "will face arrest", "arrested immediately",
            "non-bailable warrant", "bailable warrant issued",
            # FIR & Legal
            "fir registered", "fir has been filed", "case registered",
            "criminal case", "criminal charges", "legal case filed",
            "complaint filed against you", "case against your number",
            # Court
            "court case", "court summons", "appear in court",
            "court order issued", "contempt of court",
            # Account threats
            "account will be blocked", "account will be frozen",
            "account permanently blocked", "account will be closed",
            "sim will be blocked", "number will be deactivated",
            "services will be stopped",
            # Financial penalties
            "penalty imposed", "fine imposed", "penalty of rs",
            "tax penalty", "late fee penalty",
            # Jail
            "jail", "imprisonment", "behind bars",
            "custody", "taken into custody",
            # General legal threats
            "legal action", "legal notice", "legal proceedings",
            "last warning", "final warning", "immediate action"
        ], 22),

        # ── 10. JOB & INCOME SCAMS ─────────────────────────
        ("job_scam", [
            # Work from home
            "work from home", "work at home", "home based job",
            "work from anywhere", "remote earning opportunity",
            # Part time jobs
            "part time job", "part time earn", "earn part time",
            "flexible job", "flexible timing earn",
            # Data entry scams
            "data entry job", "data entry earn", "form filling job",
            "captcha solving job", "copy paste job",
            # Reseller scams
            "reseller program", "become a reseller", "product reselling",
            "amazon reseller", "flipkart reseller",
            # MLM & Network marketing
            "mlm", "network marketing", "multi level marketing",
            "direct selling", "downline", "upline", "matrix plan",
            "binary plan", "chain marketing", "pyramid scheme",
            # Refer & earn
            "refer and earn", "refer friends earn",
            "unlimited referral", "earn per referral",
            # Joining fees
            "joining fee", "registration charge", "starter kit fee",
            "training fee to start", "pay to join and earn",
            # Investment plans
            "investment plan daily returns", "forex trading guaranteed",
            "stock tips guaranteed profit", "crypto trading guaranteed"
        ], 16),

        # ── 11. ROMANCE & RELATIONSHIP SCAMS ───────────────
        ("romance_scam", [
            "met you online", "i like your profile",
            "want to be your friend", "lonely and rich",
            "foreign national", "stranded abroad", "stuck at airport",
            "customs holding my money", "need your help financially",
            "send me money i will repay", "i love you send money",
            "military officer abroad", "doctor working abroad",
            "widower looking for", "divorce settlement send",
            "inheritance stuck", "funds stuck in customs"
        ], 18),

        # ── 12. INSURANCE & POLICY SCAMS ───────────────────
        ("insurance_scam", [
            "insurance policy bonus", "policy matured claim now",
            "lic bonus unclaimed", "insurance refund pending",
            "policy surrender value", "insurance agent calling",
            "free insurance policy", "health cover free",
            "your policy expires", "policy renewal urgent",
            "insurance company selected you", "claim your insurance",
            "life insurance bonus credited", "term plan bonus"
        ], 16),

        # ── 13. LOAN & CREDIT SCAMS ────────────────────────
        ("loan_scam", [
            "instant loan approved", "pre-approved loan",
            "loan approved without documents", "no cibil check loan",
            "bad cibil loan approved", "instant personal loan",
            "loan in 5 minutes", "loan in 10 minutes",
            "processing fee for loan", "insurance for loan disbursement",
            "loan disbursement pending fee", "gst for loan release",
            "loan app", "instant cash app", "easy loan app",
            "zero interest loan", "cheap loan offer"
        ], 16),

        # ── 14. FAKE CUSTOMER CARE ─────────────────────────
        ("fake_support", [
            "customer care executive calling",
            "bank executive calling", "rbi executive",
            "calling from bank head office",
            "your account shows suspicious activity",
            "fraud detected in your account",
            "unauthorized transaction in your account",
            "we detected a login from unknown device",
            "your account will be suspended unless",
            "verify your details to protect your account",
            "kindly cooperate with our executive",
            "screen sharing required", "anydesk", "teamviewer",
            "install this app", "allow remote access"
        ], 22),

        # ── 15. CRYPTOCURRENCY & TRADING SCAMS ─────────────
        ("crypto_trading_scam", [
            "crypto investment guaranteed", "bitcoin investment plan",
            "crypto trading bot", "automated crypto trading",
            "forex trading signals", "fx trading guaranteed",
            "binary options", "trading platform register",
            "crypto doubler", "bitcoin doubler",
            "invest usdt earn", "nft investment guaranteed",
            "defi guaranteed returns", "yield farming guaranteed",
            "liquidity pool guaranteed", "staking guaranteed returns",
            "crypto mining investment", "cloud mining earn",
            "crypto signal group", "pump and dump signal",
            "insider trading tips", "100x altcoin"
        ], 18),

    ]

    triggered    = []
    safe_signals = []
    raw_score    = 0

    for pattern_name, keywords, base_weight in fraud_patterns:
        matched = [k for k in keywords if k in text_lower]
        if matched:
            # Smaller bonus — max +12 for many matches
            bonus  = min(len(matched) - 1, 3) * 4
            weight = base_weight + bonus
            triggered.append((pattern_name, matched, weight))
            raw_score += weight

    triggered_names = [p for p, _, _ in triggered]

    # ══════════════════════════════════════════════════
    # LAYER 3 — STRUCTURAL ANALYSIS (smaller weights)
    # ══════════════════════════════════════════════════
    structural_flags = []

    exclamation_count = content.count("!")
    if exclamation_count >= 4:
        raw_score += 8
        structural_flags.append(f"Excessive exclamation marks ({exclamation_count}) — pressure tactic")

    caps_words = [w for w in content.split() if w.isupper() and len(w) > 3
                and w not in ["HDFC","ICICI","SBI","AXIS","UPI","OTP","ATM","KYC","PAN","TXN"]]
    if len(caps_words) >= 3:
        raw_score += 7
        structural_flags.append(f"Multiple alarm ALL-CAPS words: {', '.join(caps_words[:3])}")

    if word_count < 25 and len(triggered) >= 2:
        raw_score += 8
        structural_flags.append("Very short message with multiple fraud indicators — typical scam SMS")

    urls = re.findall(r'https?://\S+|www\.\S+|bit\.ly\S*|tinyurl\S*', content, re.IGNORECASE)
    for url in urls:
        is_official = any(d in url.lower() for d in official_domains)
        if is_official:
            pass  # already handled by neutralizer
        elif any(x in url.lower() for x in ["bit.ly","tinyurl",".xyz",".tk","shorturl"]):
            raw_score += 15
            structural_flags.append(f"Shortened/suspicious URL: {url[:50]}")
        elif "http://" in url and not is_official:
            raw_score += 8
            structural_flags.append(f"Insecure HTTP link: {url[:50]}")

    money_pattern = re.findall(r'rs\.?\s*[\d,]+|₹\s*[\d,]+', text_lower)
    if money_pattern and len(triggered) >= 3:
        raw_score += 6
        structural_flags.append(f"Monetary amounts with multiple fraud patterns: {', '.join(money_pattern[:2])}")

    grammar_issues = ["kindly do the needful", "plz send", "pls reply urgently",
                    "asap send money", "dear sir/madam do needful"]
    if any(g in text_lower for g in grammar_issues):
        raw_score += 5
        structural_flags.append("Unusual phrasing common in scam messages")

    # ══════════════════════════════════════════════════
    # LAYER 4 — COMBINATION SCORING (moderate weights)
    # ══════════════════════════════════════════════════
    combo_flags = []
    if "urgent_language" in triggered_names and "bank_request" in triggered_names:
        raw_score += 15
        combo_flags.append("CRITICAL: Urgency + Bank detail request = Phishing attack pattern")
    if "too_good" in triggered_names and "money_transfer" in triggered_names:
        raw_score += 15
        combo_flags.append("CRITICAL: Unrealistic returns + Fee payment = Advance fee fraud")
    if "prize_lottery" in triggered_names and "money_transfer" in triggered_names:
        raw_score += 12
        combo_flags.append("HIGH: Prize claim + Money transfer = Lottery scam")
    if "impersonation" in triggered_names and "threat_pressure" in triggered_names:
        raw_score += 15
        combo_flags.append("CRITICAL: Authority impersonation + Threats = Government scam")
    if "suspicious_links" in triggered_names and "urgent_language" in triggered_names:
        raw_score += 12
        combo_flags.append("HIGH: Suspicious link + Urgency = Phishing attack")
    if "job_scam" in triggered_names and "money_transfer" in triggered_names:
        raw_score += 12
        combo_flags.append("HIGH: Job offer + Fee payment = Job scam")
    if len(triggered_names) >= 5:
        raw_score += 10
        combo_flags.append("Multiple fraud categories simultaneously triggered")

    # ══════════════════════════════════════════════════
    # LAYER 5 — SAFE SIGNALS (context-sensitive)
    # ══════════════════════════════════════════════════
    has_heavy_fraud = len(triggered) >= 3 or raw_score >= 60

    if not has_heavy_fraud:
        if any(x in text_lower for x in ["regards", "sincerely", "thank you for"]):
            safe_signals.append("Professional closing detected")
        if re.search(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', content):
            safe_signals.append("Verifiable email address present")
        if len(txn_found) >= 1:
            safe_signals.append("Contains transaction reference")
        if word_count > 80 and len(triggered) <= 1:
            safe_signals.append("Detailed content with minimal fraud indicators")

    # ══════════════════════════════════════════════════
    # FINAL SCORE — Apply neutralizers
    # ══════════════════════════════════════════════════
    safe_deduction    = len(safe_signals) * 3 if not has_heavy_fraud else 0
    raw_score         = max(0, raw_score - safe_deduction)

    # Neutralizers reduce final score proportionally
    effective_neutral = min(neutral_score, raw_score * 0.6)  # can reduce max 60% of score
    final_score       = max(0, raw_score - effective_neutral)

    # Normalize to realistic range — cap at 95 (nothing is 100% certain)
    fraud_score = min(95, int(final_score))

    # ══════════════════════════════════════════════════
    # RISK CLASSIFICATION
    # ══════════════════════════════════════════════════
    if fraud_score >= 80:
        risk_level   = "HIGH RISK"
        risk_emoji   = "🚨"
        confidence   = "Very High"
        recommendation = "🚨 IMMEDIATE ACTION REQUIRED: Do NOT respond, click any links, call any numbers, or share any information. Delete this message immediately. Block the sender. Report at cybercrime.gov.in or call National Cyber Crime Helpline 1930."
    elif fraud_score >= 60:
        risk_level   = "HIGH RISK"
        risk_emoji   = "🚨"
        confidence   = "High"
        recommendation = "🚨 HIGH FRAUD RISK: Do not engage with this content. Do NOT share bank details, OTP, or personal information. Verify independently through official channels only (official website/registered number)."
    elif fraud_score >= 40:
        risk_level   = "MEDIUM RISK"
        risk_emoji   = "⚠️"
        confidence   = "Medium"
        recommendation = "⚠️ PROCEED WITH CAUTION: Multiple suspicious indicators found. Do NOT share any sensitive information. Independently verify the sender's identity through official sources before taking any action."
    elif fraud_score >= 20:
        risk_level   = "LOW RISK"
        risk_emoji   = "💡"
        confidence   = "Medium"
        recommendation = "💡 STAY ALERT: Minor suspicious elements detected. Verify the source before responding. Never share OTP, PIN, or banking credentials with anyone, even if they claim to be from your bank."
    else:
        risk_level   = "SAFE"
        risk_emoji   = "✅"
        confidence   = "High"
        recommendation = "✅ APPEARS SAFE: No significant fraud indicators detected in this content. However, always stay vigilant — never share OTP, PIN, or passwords with anyone under any circumstances."

    # ══════════════════════════════════════════════════
    # BUILD PROFESSIONAL REPORT
    # ══════════════════════════════════════════════════
    flag_labels = {
        "urgent_language":    "Urgency & Pressure Tactics",
        "prize_lottery":      "Prize / Lottery Scam Indicators",
        "bank_request":       "Sensitive Banking Information Request",
        "personal_info":      "Personal Identity Information Request",
        "suspicious_links":   "Suspicious URLs / Phishing Links",
        "impersonation":      "Government / Authority Impersonation",
        "money_transfer":     "Money Transfer / Fee Payment Request",
        "too_good":           "Unrealistic Financial Promises",
        "threat_pressure":    "Threats & Legal Action Intimidation",
        "job_scam":           "Fake Job / MLM / Income Scheme",
        "romance_scam":       "Romance / Relationship Fraud",
        "insurance_scam":     "Fake Insurance / Policy Scam",
        "loan_scam":          "Fraudulent Loan / Credit Offer",
        "fake_support":       "Fake Customer Care / Remote Access Scam",
        "crypto_trading_scam":"Crypto / Forex / Trading Scam",
    }

    red_flags = []
    for p, m, w in triggered:
        red_flags.append(f"{flag_labels[p]} — Keywords: {', '.join(m[:4])}")
    for f in structural_flags:
        red_flags.append(f)
    for c in combo_flags:
        red_flags.append(c)

    # Fraud type classification
    fraud_type = "Unknown"
    if "prize_lottery" in triggered_names:            fraud_type = "Lottery / Prize Scam"
    elif "romance_scam" in triggered_names:           fraud_type = "Romance / Relationship Scam"
    elif "fake_support" in triggered_names:           fraud_type = "Fake Customer Care Scam"
    elif "crypto_trading_scam" in triggered_names:    fraud_type = "Crypto / Trading Scam"
    elif "loan_scam" in triggered_names:              fraud_type = "Fraudulent Loan Offer"
    elif "insurance_scam" in triggered_names:         fraud_type = "Fake Insurance / Policy Scam"
    elif "job_scam" in triggered_names:               fraud_type = "Fake Job / MLM Scam"
    elif "impersonation" in triggered_names:          fraud_type = "Government Impersonation Scam"
    elif "bank_request" in triggered_names:           fraud_type = "Banking Phishing Attempt"
    elif "suspicious_links" in triggered_names:       fraud_type = "Phishing / Link-based Attack"
    elif "too_good" in triggered_names:               fraud_type = "Investment / Returns Scam"
    elif "threat_pressure" in triggered_names:        fraud_type = "Threat-based Fraud"
    elif len(triggered) == 0:                         fraud_type = "No Fraud Detected"

    analysis_parts = []
    analysis_parts.append("## 📋 Executive Summary")
    if fraud_score >= 40:
        analysis_parts.append(
            f"This content has been classified as **{risk_level}** with a fraud score of **{fraud_score}/100**. "
            f"Our analysis detected **{len(triggered)} fraud pattern categories** and **{len(structural_flags)} structural anomalies**. "
            f"The likely fraud type is: **{fraud_type}**. "
            f"Detection confidence: **{confidence}**. "
            f"Immediate caution is advised."
        )
    else:
        analysis_parts.append(
            f"This content has been classified as **{risk_level}** with a fraud score of **{fraud_score}/100**. "
            f"{'No significant fraud indicators were detected.' if fraud_score < 20 else 'Minor indicators were detected — proceed with normal caution.'} "
            f"Detection confidence: **{confidence}**."
        )

    analysis_parts.append("\n## 🔍 Pattern Analysis")
    if triggered:
        for p, matches, w in triggered:
            analysis_parts.append(
                f"**{flag_labels[p]}** *(Score contribution: +{w} pts)*\n"
                f"Detected: `{', '.join(matches[:5])}`\n"
            )
    else:
        analysis_parts.append("No fraud patterns triggered in this content.")

    if structural_flags:
        analysis_parts.append("\n## 🏗️ Structural Red Flags")
        for f in structural_flags:
            analysis_parts.append(f"- {f}")

    if combo_flags:
        analysis_parts.append("\n## ⚡ Dangerous Combinations Detected")
        for c in combo_flags:
            analysis_parts.append(f"- {c}")

    if safe_signals:
        analysis_parts.append("\n## ✅ Safe Indicators Found")
        for s in safe_signals:
            analysis_parts.append(f"- {s}")

    analysis_parts.append("\n## 📊 Scoring Breakdown")
    analysis_parts.append(f"- **Base pattern score:** {sum(w for _,_,w in triggered)} pts")
    analysis_parts.append(f"- **Structural flags:** +{raw_score - sum(w for _,_,w in triggered)} pts")
    analysis_parts.append(f"- **Safe signal deduction:** -{safe_deduction} pts")
    analysis_parts.append(f"- **Final fraud score:** **{fraud_score}/100**")
    analysis_parts.append(f"- **Fraud type classified as:** {fraud_type}")
    analysis_parts.append(f"- **Patterns checked:** {len(fraud_patterns)}")
    analysis_parts.append(f"- **Patterns triggered:** {len(triggered)}")

    if fraud_score >= 40:
        analysis_parts.append("\n## ⚠️ How This Fraud Works")
        if fraud_type == "Lottery / Prize Scam":
            analysis_parts.append("Scammers claim you won a prize to create excitement, then ask for a 'processing fee' or your bank details to 'transfer the prize money'. Once you pay or share details, they disappear.")
        elif fraud_type == "Fake Job / Investment Scam":
            analysis_parts.append("Scammers promise easy income or high returns. They charge a registration/joining fee upfront. Once paid, they either disappear or keep asking for more fees.")
        elif fraud_type == "Government Impersonation Scam":
            analysis_parts.append("Scammers pretend to be police, RBI, or government officials. They threaten arrest or legal action to create fear, then demand money or personal information to 'resolve' the fake issue.")
        elif fraud_type == "Banking Phishing Attempt":
            analysis_parts.append("Scammers impersonate your bank and create urgency (account blocked, KYC pending). They collect your OTP, PIN, or card details to steal money from your account.")
        elif fraud_type == "Investment / Returns Scam":
            analysis_parts.append("Unrealistic return promises (100%, guaranteed profits) are used to lure victims. Initial small returns are paid using other victims' money (Ponzi scheme) until the scammer disappears.")

    analysis_parts.append("\n## 🛡️ How to Stay Protected")
    analysis_parts.append("- **Never share OTP, PIN, CVV, or passwords** — your bank will NEVER ask for these")
    analysis_parts.append("- **Verify independently** — call the official helpline (on the back of your card or official website)")
    analysis_parts.append("- **Do not click suspicious links** — type official URLs directly in your browser")
    analysis_parts.append("- **Report fraud** — cybercrime.gov.in or National Helpline **1930**")
    analysis_parts.append("- **When in doubt, don't** — it is better to miss an opportunity than lose money")

    # Try AI enhancement
    try:
        ai_q = (f"Fraud analysis Indian context. Score:{fraud_score}/100 Type:{fraud_type} "
                f"Patterns:{chr(44).join(triggered_names[:4])}. "
                f"Give 2-3 specific insights max 80 words.")
        ai_resp = gemini_client.models.generate_content(model="gemini-2.0-flash", contents=ai_q)
        analysis_parts.append(f"\n## 🤖 AI Expert Insights\n{ai_resp.text.strip()}")
    except:
        pass


    return {
        "fraud_score":        fraud_score,
        "risk_level":         risk_level,
        "fraud_type":         fraud_type,
        "confidence":         confidence,
        "red_flags":          red_flags,
        "safe_signals":       safe_signals,
        "detailed_analysis":  "\n".join(analysis_parts),
        "recommendation":     recommendation,
        "patterns_triggered": len(triggered),
        "analyzed_at":        datetime.now().strftime("%d %b %Y, %I:%M %p")
    }

# ── POST /fraud/pdf ──────────────────────────────────────
class FraudPDFRequest(BaseModel):
    fraud_score: int
    risk_level: str
    red_flags: list
    safe_signals: list
    detailed_analysis: str
    recommendation: str
    patterns_triggered: int
    analyzed_at: str
    analyzed_text: str = ""

@app.post("/fraud/pdf")
def fraud_pdf(body: FraudPDFRequest):
    import re
    buffer = io.BytesIO()
    doc    = SimpleDocTemplate(buffer, pagesize=A4,
                leftMargin=1.8*cm, rightMargin=1.8*cm,
                topMargin=1.8*cm, bottomMargin=1.8*cm)

    # Colors
    score      = body.fraud_score
    RISK_COLOR = (colors.HexColor("#f04438") if score >= 80 else
                  colors.HexColor("#f79009") if score >= 50 else
                  colors.HexColor("#f59e0b") if score >= 25 else
                  colors.HexColor("#12b76a"))
    RISK_BG    = (colors.HexColor("#fef3f2") if score >= 80 else
                  colors.HexColor("#fffaeb") if score >= 50 else
                  colors.HexColor("#fffaeb") if score >= 25 else
                  colors.HexColor("#ecfdf3"))
    BLUE    = colors.HexColor("#3b6ef8")
    RED     = colors.HexColor("#f04438")
    GREEN   = colors.HexColor("#12b76a")
    GRAY900 = colors.HexColor("#101828")
    GRAY700 = colors.HexColor("#344054")
    GRAY500 = colors.HexColor("#667085")
    GRAY100 = colors.HexColor("#f2f4f7")
    GRAY50  = colors.HexColor("#f9fafb")
    WHITE   = colors.white

    def S(name, **kw): return ParagraphStyle(name, **kw)
    title_s = S("T",  fontSize=18, textColor=WHITE,   fontName="Helvetica-Bold", leading=24)
    sub_s   = S("Su", fontSize=8,  textColor=colors.HexColor("#c7d7fe"), fontName="Helvetica", leading=12)
    h2_s    = S("H2", fontSize=11, textColor=GRAY900, fontName="Helvetica-Bold", leading=15, spaceBefore=4)
    h3_s    = S("H3", fontSize=9,  textColor=BLUE,    fontName="Helvetica-Bold", leading=13)
    body_s  = S("B",  fontSize=8.5,textColor=GRAY700, fontName="Helvetica",      leading=13)
    small_s = S("Sm", fontSize=7.5,textColor=GRAY500, fontName="Helvetica",      leading=11)
    foot_s  = S("F",  fontSize=6.5,textColor=GRAY500, fontName="Helvetica",      leading=9, alignment=TA_CENTER)
    score_s = S("Sc", fontSize=36, textColor=RISK_COLOR, fontName="Helvetica-Bold", leading=40, alignment=TA_CENTER)
    slbl_s  = S("Sl", fontSize=13, textColor=RISK_COLOR, fontName="Helvetica-Bold", leading=16, alignment=TA_CENTER)
    ctr_s   = S("Ct", fontSize=8,  textColor=GRAY500, fontName="Helvetica",      leading=11, alignment=TA_CENTER)

    story = []
    PW = 17.4 * cm

    # Header
    hdr = Table([[
        Paragraph("🔍 ETMS Financial Fraud Analysis Report", title_s),
        Paragraph(f"Analyzed: {body.analyzed_at}<br/>ETMS Fraud Detector", sub_s)
    ]], colWidths=[11*cm, 6.4*cm])
    hdr.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,-1), BLUE),
        ("ROWPADDING", (0,0),(-1,-1), 18),
        ("VALIGN",     (0,0),(-1,-1), "MIDDLE"),
        ("ALIGN",      (1,0),(1,0),   "RIGHT"),
    ]))
    story += [hdr, Spacer(1, 16)]

    # Score card
    icon = "🚨" if score >= 80 else ("⚠️" if score >= 50 else ("💡" if score >= 25 else "✅"))
    score_tbl = Table([[
        Paragraph(f"{score}", score_s),
        Paragraph("/100", S("S2", fontSize=14, textColor=GRAY500, fontName="Helvetica", leading=18, alignment=TA_CENTER)),
        Paragraph(f"Fraud Risk Score", ctr_s),
    ],[
        Paragraph(f"{icon} {body.risk_level}", slbl_s), "", ""
    ]], colWidths=[3*cm, 2*cm, 12.4*cm], rowHeights=[1.8*cm, 0.9*cm])
    score_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,-1), RISK_BG),
        ("SPAN",       (0,0),(0,0)),
        ("SPAN",       (0,1),(2,1)),
        ("ALIGN",      (0,0),(-1,-1), "CENTER"),
        ("VALIGN",     (0,0),(-1,-1), "MIDDLE"),
        ("ROWPADDING", (0,0),(-1,-1), 10),
        ("BOX",        (0,0),(-1,-1), 2, RISK_COLOR),
    ]))
    story += [score_tbl, Spacer(1, 14)]

    # Analyzed content
    if body.analyzed_text:
        story.append(Paragraph("📄 Analyzed Content", h2_s))
        story.append(Spacer(1, 4))
        content_tbl = Table([[Paragraph(body.analyzed_text[:400] + ("…" if len(body.analyzed_text) > 400 else ""), body_s)]],
                            colWidths=[PW])
        content_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0,0),(-1,-1), GRAY50),
            ("ROWPADDING", (0,0),(-1,-1), 10),
            ("BOX",        (0,0),(-1,-1), 0.5, GRAY100),
        ]))
        story += [content_tbl, Spacer(1, 12)]

    # Red flags & safe signals
    story.append(Paragraph("🚩 Red Flags Detected", h2_s))
    story.append(Spacer(1, 4))
    if body.red_flags:
        for flag in body.red_flags:
            flag_row = Table([[Paragraph(f"⚠ {flag}", body_s)]], colWidths=[PW])
            flag_row.setStyle(TableStyle([
                ("BACKGROUND", (0,0),(-1,-1), colors.HexColor("#fef3f2")),
                ("ROWPADDING", (0,0),(-1,-1), 7),
                ("BOX",        (0,0),(-1,-1), 0.5, RED),
                ("LEFTPADDING",(0,0),(-1,-1), 12),
            ]))
            story += [flag_row, Spacer(1, 3)]
    else:
        story.append(Paragraph("✅ No red flags detected", body_s))
    story.append(Spacer(1, 10))

    story.append(Paragraph("✅ Safe Signals", h2_s))
    story.append(Spacer(1, 4))
    if body.safe_signals:
        for sig in body.safe_signals:
            sig_row = Table([[Paragraph(f"✓ {sig}", body_s)]], colWidths=[PW])
            sig_row.setStyle(TableStyle([
                ("BACKGROUND", (0,0),(-1,-1), colors.HexColor("#ecfdf3")),
                ("ROWPADDING", (0,0),(-1,-1), 7),
                ("BOX",        (0,0),(-1,-1), 0.5, GREEN),
                ("LEFTPADDING",(0,0),(-1,-1), 12),
            ]))
            story += [sig_row, Spacer(1, 3)]
    else:
        story.append(Paragraph("No safe signals identified", body_s))
    story.append(Spacer(1, 12))

    # Detailed analysis
    story.append(HRFlowable(width="100%", thickness=0.5, color=GRAY100))
    story.append(Spacer(1, 8))
    story.append(Paragraph("🔎 Detailed Analysis", h2_s))
    story.append(Spacer(1, 6))
    for line in body.detailed_analysis.split("\n"):
        line = line.strip()
        if not line: story.append(Spacer(1, 3)); continue
        line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
        if line.startswith("## "): story.append(Paragraph(line[3:], h2_s))
        elif line.startswith("- "): story.append(Paragraph("• " + line[2:], body_s))
        else: story.append(Paragraph(line, body_s))
    story.append(Spacer(1, 12))

    # Recommendation
    story.append(HRFlowable(width="100%", thickness=0.5, color=GRAY100))
    story.append(Spacer(1, 8))
    story.append(Paragraph("💡 Our Recommendation", h2_s))
    story.append(Spacer(1, 4))
    rec_tbl = Table([[Paragraph(body.recommendation, body_s)]], colWidths=[PW])
    rec_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,-1), RISK_BG),
        ("ROWPADDING", (0,0),(-1,-1), 12),
        ("BOX",        (0,0),(-1,-1), 2, RISK_COLOR),
        ("LEFTPADDING",(0,0),(-1,-1), 14),
    ]))
    story += [rec_tbl, Spacer(1, 14)]

    # Footer
    story += [
        HRFlowable(width="100%", thickness=0.5, color=GRAY100),
        Spacer(1, 6),
        Paragraph("Generated by ETMS Fraud Detector  |  For suspicious activity report to cybercrime.gov.in or call 1930  |  " +
                  datetime.now().strftime("%d %b %Y"), foot_s)
    ]

    doc.build(story)
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=ETMS_Fraud_Report.pdf"})



# ── GET /aos/history ──────────────────────────────────────
@app.get("/aos/history")
def get_aos_history(user: str):
    if not user:
        return {"messages": []}
    doc = aos_hist_col.find_one({"user": user}, {"_id": 0})
    if doc:
        return {"messages": doc.get("messages", [])[-60:]}  # last 60 messages
    return {"messages": []}

# ── POST /aos/history/save ────────────────────────────────
class AOSHistorySave(BaseModel):
    user: str
    messages: list

@app.post("/aos/history/save")
def save_aos_history(body: AOSHistorySave):
    if not body.user:
        return {"status": "ok"}
    # Keep only last 100 messages
    msgs = body.messages[-100:]
    aos_hist_col.update_one(
        {"user": body.user},
        {"$set": {"messages": msgs, "updated_at": datetime.now().isoformat()}},
        upsert=True
    )
    return {"status": "ok"}

# ── POST /aos/context/save ────────────────────────────────
class AOSContextSave(BaseModel):
    user: str
    context: dict

@app.post("/aos/context/save")
def save_aos_context(body: AOSContextSave):
    if not body.user:
        return {"status": "ok"}
    aos_ctx_col.update_one(
        {"user": body.user},
        {"$set": {"context": body.context, "updated_at": datetime.now().isoformat()}},
        upsert=True
    )
    return {"status": "ok"}

# ── GET /aos/context ──────────────────────────────────────
@app.get("/aos/context")
def get_aos_context(user: str):
    if not user:
        return {"context": {}}
    doc = aos_ctx_col.find_one({"user": user}, {"_id": 0})
    return {"context": doc.get("context", {}) if doc else {}}

# ── POST /aos/chat ────────────────────────────────────────
class AOSMessage(BaseModel):
    message: str
    user: str = ""
    history: list = []
    session_context: dict = {}   # financial facts extracted in this session

@app.post("/aos/chat")
def aos_chat(body: AOSMessage):
    import re as _re

    # ── Normalise message (typo-tolerant) ───────────────
    raw_msg   = body.message.strip()
    msg_lower = raw_msg.lower()

    # Common typo/shorthand normalisation
    typo_map = {
        "thnx":"thanks","thx":"thanks","ty":"thanks","tq":"thank you",
        "hw":"how","wht":"what","pls":"please","plz":"please","plss":"please",
        "kya":"what","kaisa":"how","batao":"tell me","chahiye":"want",
        "karo":"do","karna":"to do","mera":"my","mujhe":"me",
        "salary":"salary","sallary":"salary","salry":"salary",
        "invst":"invest","invesment":"investment","investement":"investment",
        "savng":"saving","saveing":"saving","sving":"saving",
        "buget":"budget","budjet":"budget","budgit":"budget",
        "expence":"expense","expnse":"expense",
        "insurence":"insurance","insuranse":"insurance",
        "retirment":"retirement","retiremen":"retirement",
    }
    words_norm = []
    for w in msg_lower.split():
        words_norm.append(typo_map.get(w, w))
    msg_normalised = " ".join(words_norm)

    # ── Generic / social messages ─────────────────────
    greetings = ["hi","hello","hey","hii","helo","heya","namaste","namaskar","good morning","good afternoon","good evening","good night","howdy"]
    thanks_words = ["thanks","thank you","thank u","tq","thnx","thx","ty","dhanyawad","shukriya","cheers"]
    bye_words = ["bye","goodbye","see you","take care","ok bye","good bye","later","cya"]
    praise_words = ["great","awesome","nice","good","helpful","excellent","perfect","amazing","wonderful","superb","brilliant","outstanding","fantastic","well done","good job","thank you so much","very helpful"]

    if any(g == msg_lower.strip() or msg_lower.strip().startswith(g + " ") or msg_lower.strip().endswith(" " + g) for g in greetings):
        hour = datetime.now().hour
        time_greet = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
        name_part = f", {body.user}" if body.user else ""
        return {"reply": f"""{time_greet}{name_part}! 👋 Great to have you here!

I'm **A.O.S** — your personal AI financial advisor inside ETMS. How can I help you today?

You can ask me about:
• 💰 **Saving money** — *"How do I save Rs.10,000/month?"*
• 🧾 **Tax saving** — *"How to save tax under 80C?"*
• 📈 **Investing** — *"Where should I invest Rs.5,000/month?"*
• 📊 **Budgeting** — *"Make a budget for Rs.50,000 salary"*
• 🔍 **ETMS help** — *"Where is the dark mode?"*

What's on your mind? 😊""", "source": "social", "session_context": {}}

    if any(t in msg_lower for t in thanks_words):
        return {"reply": "You're very welcome! 😊 Happy to help anytime. If you have more finance questions or need ETMS guidance, I'm always here!\n\nIs there anything else you'd like to know? 💪", "source": "social", "session_context": {}}

    if any(b in msg_lower for b in bye_words):
        return {"reply": f"Goodbye{', ' + body.user if body.user else ''}! 👋 Take care, and remember — small financial steps today lead to big results tomorrow! Feel free to come back anytime. 🌟", "source": "social", "session_context": {}}

    if any(p in msg_lower for p in praise_words) and len(msg_lower.split()) <= 5:
        return {"reply": "Thank you, that means a lot! 😊 I'm here whenever you need financial guidance. Is there anything else you'd like help with?", "source": "social", "session_context": {}}

    # ── Extract financial context from current message ──
    # (salary, investments, goals mentioned by user in chat)
    def extract_financial_facts(text, existing_ctx):
        ctx = dict(existing_ctx)  # copy existing
        t = text.lower().replace(",","").replace("₹","").replace("rs.","rs ").replace("rupees","").replace("rupee","")
        nums = [int(n) for n in _re.findall(r"\b(\d{3,8})\b", t) if 1000 <= int(n) <= 10000000]

        # Extract salary/income
        if any(w in t for w in ["salary","income","earn","package","ctc","take home","per month"]):
            if nums:
                ctx["salary"] = max(nums)

        # Extract savings target
        if any(w in t for w in ["save","saving","savings","bachana","want to save"]):
            if nums:
                ctx["savings_target"] = min(nums) if len(nums) > 1 else nums[0]

        # Extract investment amount
        if any(w in t for w in ["invest","sip","put","mutual fund","ppf","nps"]):
            if nums:
                ctx["investment_amount"] = nums[0]

        # Extract age
        age_match = _re.search(r"\b(1[8-9]|[2-6]\d)\s*(?:years?|yr|yrs)?\s*old\b|\baged?\s*(1[8-9]|[2-6]\d)\b|\bi am (1[8-9]|[2-6]\d)\b", t)
        if age_match:
            age_str = next(g for g in age_match.groups() if g)
            ctx["age"] = int(age_str)

        # Extract goal
        if any(w in t for w in ["house","car","wedding","education","retire","vacation","travel","child","daughter","son"]):
            for goal in ["house","car","wedding","education","retirement","vacation","travel"]:
                if goal in t:
                    ctx["financial_goal"] = goal
                    break

        # Extract risk profile
        if any(w in t for w in ["safe","conservative","low risk","no risk","guaranteed"]):
            ctx["risk_profile"] = "conservative"
        elif any(w in t for w in ["moderate","balanced","medium risk"]):
            ctx["risk_profile"] = "moderate"
        elif any(w in t for w in ["aggressive","high risk","equity","stocks","high return"]):
            ctx["risk_profile"] = "aggressive"

        return ctx

    # Merge: DB context + session context + extracted from this message
    session_ctx = dict(body.session_context)
    session_ctx = extract_financial_facts(msg_lower, session_ctx)

    # Save updated context to DB asynchronously (non-blocking)
    if body.user and session_ctx:
        try:
            aos_ctx_col.update_one(
                {"user": body.user},
                {"$set": {"context": session_ctx, "updated_at": datetime.now().isoformat()}},
                upsert=True
            )
        except:
            pass

    # ── Build personalised context string ───────────────
    user_txn_context = ""
    if body.user:
        try:
            all_txns = list(txns_col.find({"user": body.user}, {"_id": 0}))
            if all_txns:
                income  = sum(float(t["amount"]) for t in all_txns if float(t["amount"]) > 0)
                expense = sum(abs(float(t["amount"])) for t in all_txns if float(t["amount"]) < 0)
                savings = income - expense
                savings_rate = round((savings/income)*100,1) if income > 0 else 0
                from collections import defaultdict
                cats = defaultdict(float)
                for t in all_txns:
                    if float(t["amount"]) < 0:
                        cats[t["category"].split(" — ")[0].strip()] += abs(float(t["amount"]))
                top_cats = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:5]
                top_str  = ", ".join([f"{c}: Rs.{a:,.0f}" for c,a in top_cats])
                user_txn_context = f"""
ETMS TRANSACTION DATA:
- Total Income recorded: Rs.{income:,.0f}
- Total Expense recorded: Rs.{expense:,.0f}
- Net Savings: Rs.{savings:,.0f} ({savings_rate}% savings rate)
- Transactions count: {len(all_txns)}
- Top expense categories: {top_str or 'None yet'}"""
        except:
            pass

    # Build session context string
    ctx_parts = []
    if session_ctx.get("salary"):        ctx_parts.append(f"Monthly salary: Rs.{session_ctx['salary']:,}")
    if session_ctx.get("savings_target"):ctx_parts.append(f"Savings target: Rs.{session_ctx['savings_target']:,}/month")
    if session_ctx.get("investment_amount"): ctx_parts.append(f"Investment amount: Rs.{session_ctx['investment_amount']:,}/month")
    if session_ctx.get("age"):           ctx_parts.append(f"Age: {session_ctx['age']} years")
    if session_ctx.get("financial_goal"):ctx_parts.append(f"Financial goal: {session_ctx['financial_goal']}")
    if session_ctx.get("risk_profile"):  ctx_parts.append(f"Risk profile: {session_ctx['risk_profile']}")
    session_ctx_str = "\nSESSION CONTEXT (mentioned by user in this chat):\n" + "\n".join(f"- {p}" for p in ctx_parts) if ctx_parts else ""

    # ── Build conversation history (last 12 messages) ───
    history_text = ""
    if body.history:
        for msg in body.history[-12:]:
            role = "User" if msg.get("role") == "user" else "A.O.S"
            history_text += f"{role}: {msg.get('content','')[:300]}\n"

    # ── System prompt ────────────────────────────────────
    system_prompt = f"""You are A.O.S (Accounting Overflows System), a highly intelligent AI Chartered Accountant and financial assistant built into ETMS (Expense Tracker Management System) for Indian users.

PERSONALITY:
- Warm, professional, deeply knowledgeable — like a CA friend who genuinely cares
- Use simple language for complex financial concepts
- Be specific with numbers and examples (use Rs., Indian context)
- Remember everything discussed in this conversation
- Handle typos and grammatical mistakes gracefully — always understand the intent
- For short/unclear messages, ask ONE specific clarifying question
- Celebrate wins, gently correct mistakes, always encourage

CAPABILITIES (handle ALL of these):
1. Savings planning with exact monthly budgets
2. Tax saving (80C, 80D, 80CCD, HRA, LTA, NPS, 80G — with specific amounts)
3. Investment advice (SIP, ELSS, PPF, NPS, FD, Index Funds, REITs, Gold)
4. Budget creation (50-30-20, zero-based, custom)
5. Debt management (credit card, loans, EMI optimisation)
6. Retirement corpus planning (with age-based calculations)
7. Insurance guidance (term life, health, ULIP avoidance)
8. Emergency fund building
9. ETMS app navigation (exact step-by-step for every feature)
10. Financial goal planning (house, car, education, travel)
11. Crypto / trading risk awareness (Indian tax implications)

CRITICAL RULES:
- ALWAYS answer the CURRENT question. Use context/history to personalise but don't repeat past answers.
- If user switches topic, switch completely — don't mix topics.
- Remember facts from conversation: if they mentioned Rs.1,20,000 salary earlier, use it.
- Never say "I don't know" for finance questions — give best advice with appropriate caveats.
- For ETMS navigation: give exact numbered steps.
- Always add risk disclaimers for investment advice.
- For tax: always add "consult a CA for your specific situation."

ETMS NAVIGATION (for app help questions):
- Dark Mode: Profile photo (top-right) → Dark Mode toggle in dropdown
- Settings: Profile photo → Settings (colors, font, currency, notifications)  
- Monthly Report: Reports tab → Load Charts → Generate Complete Report → Download PDF
- Fraud Detector: Fraud Detector tab → paste message → Analyze for Fraud
- Add Transaction: Dashboard → enter amount (+ for income, - for expense) → Add
- Targets: Targets tab → Add Target → set category and amount
- My Account: Profile photo → My Account
- Sign Out: Profile photo → Sign Out
{user_txn_context}
{session_ctx_str}

RECENT CONVERSATION (use for context, DO NOT repeat):
{history_text}

CURRENT MESSAGE FROM USER: {raw_msg}

Respond now — be specific, helpful, warm, and professional:"""

    # ── Try Gemini ───────────────────────────────────────
    try:
        resp = gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=system_prompt
        )
        reply_text = resp.text.strip()

        # ── Self-learning: store good Q&A pairs ──────────
        if body.user and len(reply_text) > 100:
            try:
                # Store as training example if it's a substantive financial response
                financial_keywords = ["rs.","invest","save","tax","budget","sip","ppf","elss","nps","insurance","loan","emi","retire","emergency fund"]
                if any(kw in reply_text.lower() for kw in financial_keywords):
                    aos_learn_col.update_one(
                        {"question_hash": hash(raw_msg.lower()[:100])},
                        {"$set": {
                            "question": raw_msg[:500],
                            "answer": reply_text[:2000],
                            "used_count": 1,
                            "created_at": datetime.now().isoformat(),
                            "source": "gemini"
                        }},
                        upsert=True
                    )
            except:
                pass

        return {"reply": reply_text, "source": "ai", "session_context": session_ctx}

    except Exception:
        pass

    # ── Check learned Q&A (self-training lookup) ─────────
    try:
        learned = list(aos_learn_col.find(
            {"$text": {"$search": raw_msg[:100]}},
            {"_id": 0, "question": 1, "answer": 1, "used_count": 1}
        ).limit(3))
        if learned:
            # Find best match
            best = max(learned, key=lambda x: x.get("used_count", 0))
            if best.get("answer"):
                aos_learn_col.update_one(
                    {"question": best["question"]},
                    {"$inc": {"used_count": 1}}
                )
                return {"reply": best["answer"], "source": "learned", "session_context": session_ctx}
    except:
        pass

    # ══════════════════════════════════════════════════
    # SMART FALLBACK — Intent engine (AI unavailable)
    # Fixes: amounts from current msg only, strict intent
    # ══════════════════════════════════════════════════
    import re as _re

    msg_lower = body.message.lower().strip()
    msg_orig  = body.message.strip()

    # ── Extract amounts from CURRENT message ONLY ────────
    def extract_amounts_from(text):
        t = text.replace(",","").replace("₹","").replace("rs.","").replace("rs ","")
        t = t.replace("rupees","").replace("rupee","").replace("inr","")
        nums = _re.findall(r"\b(\d{3,8})\b", t)
        valid = [int(n) for n in nums if 1000 <= int(n) <= 10000000]
        return sorted(set(valid), reverse=True)

    amounts = extract_amounts_from(msg_lower)

    # ── Strict intent classifier (current message only) ──
    def score_intent(keywords):
        """Score how strongly the message matches an intent"""
        return sum(1 for k in keywords if k in msg_lower)

    # Define intents with their keywords
    INTENTS = {
        "savings_plan":   ["save","saving","savings","bachana","paisa bacha","bachat","how to save","save money","savings plan","monthly save","save per month","want to save"],
        "budget":         ["budget","budgeting","budget plan","monthly plan","plan my expense","how much to spend","50 30 20","50-30-20","allocation","distribute salary","salary plan"],
        "tax":            ["tax","80c","80d","hra","tds","itr","income tax","save tax","tax deduction","80ccd","nps tax","tax saving","tax slab","tax return","tax benefit","section 80"],
        "investment":     ["invest","investment","sip","mutual fund","mf","fd","ppf","nps","elss","share","stock","nifty","sensex","where to invest","portfolio","return","grow money","wealth","kahan lagaun","lump sum","index fund","equity","debt fund"],
        "emergency_fund": ["emergency fund","emergency","contingency","rainy day","safety net","buffer fund","liquid fund","unexpected expense"],
        "debt":           ["loan","emi","debt","credit card","borrow","interest","repay","outstanding","personal loan","home loan","car loan","balance transfer","credit score","cibil"],
        "retirement":     ["retire","retirement","pension","old age","corpus","provident fund","epf","vpf","long term","60 years","nps retirement"],
        "etms_help":      ["setting","settings","dark mode","theme","account","profile","report","monthly report","fraud","fraud detector","transaction","add expense","add income","logout","sign out","navigation","how to use","where is","find","locate","help me find","where do i","can you show","how do i"],
        "crypto":         ["crypto","bitcoin","ethereum","blockchain","nft","defi","usdt","altcoin","coin","token","web3","binance"],
        "insurance":      ["insurance","term plan","life insurance","health insurance","mediclaim","policy","cover","premium","lic","ulip","sum assured"],
    }

    # Score each intent
    scores = {intent: score_intent(keywords) for intent, keywords in INTENTS.items()}
    best_intent = max(scores, key=scores.get)
    best_score  = scores[best_intent]

    # ── Response generators ───────────────────────────────

    def savings_response():
        if len(amounts) >= 2:
            income_val = amounts[0]; save_val = amounts[1]
        elif len(amounts) == 1:
            if any(w in msg_lower for w in ["income","salary","earn","kama","milta","get"]):
                income_val = amounts[0]; save_val = round(income_val * 0.25)
            else:
                save_val = amounts[0]; income_val = round(save_val * 4)
        else:
            income_val, save_val = 50000, 12500
        save_pct = round((save_val / income_val) * 100) if income_val > 0 else 25
        needs = round(income_val * 0.50)
        wants = max(0, income_val - needs - save_val)
        sip   = round(save_val * 0.50); ppf = round(save_val * 0.25); ef = round(save_val * 0.25)
        return f"""Here's your **personalised savings plan** — income **Rs.{income_val:,}/month**, save target **Rs.{save_val:,}/month** ({save_pct}%):

**📊 Monthly Budget Breakdown:**
• 🏠 **Needs — Rs.{needs:,}** *(rent, groceries, transport, EMI, insurance)*
• 🎉 **Wants — Rs.{wants:,}** *(dining, entertainment, shopping)*
• 💰 **Savings — Rs.{save_val:,}** *({save_pct}% — {"🌟 Excellent!" if save_pct>=30 else "👍 Good!" if save_pct>=20 else "💪 Keep pushing!"})*

**✅ Your 5-Step Action Plan:**

**1. Auto-transfer on salary day 🏦**
The moment salary arrives, move Rs.{save_val:,} to a separate account immediately. "Pay yourself first" — this one habit changes everything.

**2. Split savings smartly 📈**
• Rs.{sip:,}/month → Nifty 50 Index Fund SIP *(wealth building)*
• Rs.{ppf:,}/month → PPF *(guaranteed 7.1%, tax-free)*
• Rs.{ef:,}/month → Emergency fund *(until you have 4 months saved)*

**3. Cut 2 recurring "want" expenses 🎯**
Review ETMS Monthly Report — most people find Rs.{round(income_val*0.05):,}–{round(income_val*0.08):,}/month in avoidable spends.

**4. Track every rupee in ETMS 📱**
Dashboard → add every transaction → Monthly Report shows exactly where money goes.

**5. 🧾 Tax bonus:** Rs.{min(12500,save_val):,}/month in ELSS = full 80C deduction = saves Rs.{round(min(150000,save_val*12)*0.20):,}/year in tax!

Want a deeper breakdown of any step? 😊"""

    def budget_response():
        income_val = amounts[0] if amounts else 50000
        return f"""Here's a **complete monthly budget** for Rs.{income_val:,} using the 50-30-20 rule:

**🏠 NEEDS — Rs.{round(income_val*0.50):,}/month (50%)**
• Rent/EMI: Rs.{round(income_val*0.25):,}
• Groceries: Rs.{round(income_val*0.10):,}
• Transport: Rs.{round(income_val*0.07):,}
• Utilities + phone: Rs.{round(income_val*0.04):,}
• Insurance: Rs.{round(income_val*0.04):,}

**🎉 WANTS — Rs.{round(income_val*0.30):,}/month (30%)**
• Dining out: Rs.{round(income_val*0.08):,}
• Entertainment: Rs.{round(income_val*0.05):,}
• Shopping: Rs.{round(income_val*0.09):,}
• Subscriptions: Rs.{round(income_val*0.04):,}
• Personal care: Rs.{round(income_val*0.04):,}

**💰 SAVINGS — Rs.{round(income_val*0.20):,}/month (20%)**
• Emergency fund: Rs.{round(income_val*0.07):,}
• Nifty 50 SIP: Rs.{round(income_val*0.08):,}
• PPF / Tax saving: Rs.{round(income_val*0.05):,}

**💡 Pro Tips:**
• Track everything in ETMS Dashboard
• Use Monthly Report to compare actual vs budget
• Increase savings rate by 1% every 3 months

Want me to adjust this for your actual income amount? 😊"""

    def tax_response():
        income_val = amounts[0] if amounts else 60000
        annual = income_val * 12
        return f"""Here's your **complete tax saving guide** for FY 2025-26:

**📌 Section 80C — Up to Rs.1,50,000 deduction**
• **ELSS Mutual Funds** — Best choice. 3-year lock-in, 10-14% historical returns
• **PPF** — Safest. 7.1% guaranteed, completely tax-free returns
• **EPF** — Already deducted for salaried employees (counts toward 80C)
• **5-year tax-saving FD** — 6-7% fixed returns
• **Life insurance premiums** — Term plan premium counts

**📌 Section 80D — Health Insurance (up to Rs.75,000)**
• Self + family premium: Rs.25,000 deduction
• Senior citizen parents: Up to Rs.50,000 additional

**📌 Section 80CCD(1B) — NPS Extra Rs.50,000**
*Over and above 80C!* Invest Rs.50,000 in NPS for additional deduction.

**📌 HRA Exemption** *(if you pay rent)*
Claim exemption — formula: minimum of actual HRA, 50%/40% of salary, or rent paid minus 10% of salary.

**📌 Section 80G — Donations**
Donations to eligible charities (50%-100% deduction)

**For Rs.{income_val:,}/month (Rs.{annual:,}/year):**
• Invest Rs.{min(12500, round(income_val*0.20)):,}/month in ELSS + PPF to max 80C
• Rs.25,000 health insurance for 80D
• Rs.4,167/month in NPS for extra Rs.50,000 deduction
• **Total potential saving: Rs.{round((min(150000,annual*0.20)+75000+50000)*0.20):,}–{round((min(150000,annual*0.20)+75000+50000)*0.30):,}/year** 🎉

⚠️ *Consult a CA for your exact tax slab calculation.*

Want details on any specific section? 😊"""

    def investment_response():
        monthly = amounts[0] if amounts else 5000
        years   = 20
        corpus  = round(monthly * 12 * ((1.01**240-1)/0.01))
        return f"""Here's your **complete investment guide** for Rs.{monthly:,}/month:

**📋 Checklist before investing:**
1. ✅ Emergency fund ready? (3-4 months expenses)
2. ✅ Term insurance? (10-15x annual income)
3. ✅ Health insurance? (min Rs.5-10 lakh)
*If all yes — you're ready!*

**📈 Recommended allocation for Rs.{monthly:,}/month:**

| Fund Type | Amount | Purpose |
| Nifty 50 Index Fund SIP | Rs.{round(monthly*0.45):,} | Core wealth building |
| ELSS Fund | Rs.{round(monthly*0.25):,} | Tax saving + growth |
| PPF | Rs.{round(monthly*0.20):,} | Guaranteed, tax-free |
| NPS Tier-2 | Rs.{round(monthly*0.10):,} | Retirement |

**⏰ Time horizon matters:**
• **1-3 years** → Liquid funds, debt MF, FD
• **3-7 years** → Balanced/hybrid funds
• **7+ years** → Pure equity index funds *(10-14% historical)*

**🚀 Power of compounding:**
Rs.{monthly:,}/month SIP for {years} years at 12% = **Rs.{corpus:,}**!

**🌟 Start today with:**
1. Open a Zerodha/Groww account
2. Start Rs.{min(500, monthly//10):,}/month SIP in Nifty 50 Index Fund
3. Enable auto-debit on salary date

⚠️ *Investments carry market risk. Past returns ≠ future returns.*

Which investment type would you like to explore further? 😊"""

    def etms_help_response():
        nav_map = {
            ("dark mode","night mode","dark theme"): """To enable **Dark Mode** in ETMS:
1. Look at the **top-right corner** of the screen
2. Click your **profile photo/avatar** (shows your initial letter)
3. In the dropdown menu, you'll see a **🌙 Dark Mode** toggle
4. Click it — the entire app switches to dark theme instantly!

Alternatively: Profile photo → **⚙️ Settings** → Appearance section → Dark Mode toggle.
Your preference is saved automatically! 🌙""",
            ("settings","theme color","accent","font size","color"): """To open **Settings** in ETMS:
1. Click your **profile photo** (top-right corner)
2. Click **⚙️ Settings** in the dropdown

Inside Settings you can:
• 🎨 Change accent color (6 color options)
• 🔤 Adjust font size (Small/Medium/Large)
• 🌙 Toggle Dark Mode
• 💰 Change currency (INR/USD/EUR/GBP)
• 🔔 Set notification preferences""",
            ("monthly report","generate report","load chart","download pdf","report"): """To generate a **Monthly Report**:
1. Click **📊 Reports** in the top navigation bar
2. Select the **month** and **year** from dropdowns
3. Click **Load Charts** → 5 interactive charts appear
4. Click **Generate Complete Report** → AI analysis generates
5. Click **Download PDF** → saves professional PDF to your device

The report includes income vs expense charts, category breakdown, spending behaviour insights, and AI recommendations! 📊""",
            ("fraud detector","fraud","suspicious","scam","check message"): """To use the **Fraud Detector**:
1. Click **🔍 Fraud Detector** in the top navigation bar
2. **Paste** the suspicious SMS, email, WhatsApp message, or URL in the text box
3. OR **drag and drop** an image/file
4. Click **Analyze for Fraud**
5. Get a fraud score (0-100), red flags, safe signals, and detailed analysis
6. Download a professional fraud report PDF

The detector checks for 15 fraud patterns including lottery scams, phishing, fake jobs, and crypto fraud! 🔍""",
            ("add transaction","add expense","add income","how to add","transaction"): """To **add a transaction** in ETMS:
1. Go to **🏠 Dashboard** (click Dashboard in the nav bar)
2. In the transaction form on the right:
   - Enter **amount**: positive number for income (e.g., 50000), negative for expense (e.g., -500)
   - Select or type a **category** (e.g., Food, Rent, Salary)
3. Click **Add**

💡 Tip: Use the **AI Extract from SMS/Email** button to auto-fill from bank messages!""",
            ("targets","set target","spending limit","goal","saving goal"): """To set **Financial Targets**:
1. Click **🎯 Targets** in the top navigation bar
2. Click **Add Target**
3. Choose:
   - **Spending Limit** — max amount to spend in a category
   - **Savings Goal** — target amount to save
4. Set category, target amount, and save
5. ETMS automatically tracks your progress against targets!""",
            ("aos","chatbot","a.o.s","this chatbot"): """You're already using **A.O.S** — Accounting Overflows System! 😊
I'm the AI financial assistant built into ETMS.

**What I can help with:**
• 💰 Tax saving strategies (80C, 80D, NPS, HRA)
• 📊 Budget planning and expense limits
• 📈 Investment advice (SIP, PPF, ELSS, NPS)
• 🔍 Finding any ETMS feature
• 🧾 Financial goal planning

Just ask me anything! You can access me anytime by clicking **🤖 A.O.S** in the top navigation bar.""",
            ("my account","profile","username","account detail"): """To view **My Account**:
1. Click your **profile photo** (top-right corner)
2. Click **👤 My Account**

You'll see:
• Your profile details (username, name, email)
• Financial profile (income, budget goals)
• Transaction statistics (total income, expense, count)
• Security settings""",
            ("sign out","logout","log out","how to logout"): """To **sign out** of ETMS:
1. Click your **profile photo** (top-right corner)
2. Scroll to the bottom of the dropdown
3. Click **🚪 Sign Out**

Your data is safely saved and you can log back in anytime!""",
        }
        for keywords, response in nav_map.items():
            if any(kw in msg_lower for kw in keywords):
                return response
        return f"""I'm here to help you navigate ETMS! You asked: *"{msg_orig}"*

Here's a quick guide to all sections:
• **🏠 Dashboard** → Add transactions, view balance, AI analysis
• **📊 Reports** → Monthly charts, AI report, PDF download
• **🎯 Targets** → Set spending limits & saving goals
• **🔍 Fraud Detector** → Analyze suspicious messages
• **🤖 A.O.S** → This chatbot — always here to help!
• **Profile photo** (top-right) → Settings, Dark Mode, My Account, Sign Out

What specific feature are you looking for? 😊"""

    def emergency_fund_response():
        income_val = amounts[0] if amounts else 40000
        target = income_val * 4
        monthly_save = round(target / 6)
        return f"""**Emergency Fund — Your #1 Financial Priority** 🛡️

**What is it?** Money set aside ONLY for real emergencies: job loss, medical crisis, urgent repairs. NOT for vacations or shopping!

**How much?**
• Minimum: 3 months expenses
• Recommended: **4-6 months expenses**
• For Rs.{income_val:,}/month → target **Rs.{target:,}**

**Where to keep it?** *(in order of recommendation)*
1. ✅ **Liquid Mutual Fund** — 4-5% returns, withdraw in 1 business day
2. ✅ **High-yield savings account** — 3-4%, instant access
3. ❌ NOT stocks (can crash when you need it most!)
4. ❌ NOT FD (penalty for early withdrawal)

**Building it:**
• Save Rs.{monthly_save:,}/month → fully built in **6 months** 🎯
• Add windfalls (bonus, gift money) directly to it
• Set up auto-transfer on salary day — it should feel "invisible"

**Golden Rule:** Once built, never invest this money. It's not supposed to grow — it's supposed to be there when everything goes wrong.

Want help figuring out your monthly expenses to set the right target? 😊"""

    def debt_response():
        return """**Smart Debt Management** 💳

**Step 1 — List everything:**
| Debt | Amount | Interest Rate | EMI |
List every debt with these 4 columns.

**Step 2 — Choose your strategy:**

**🔥 Avalanche Method** *(saves most money)*
Pay minimums on all. Extra money → highest interest rate first.
Best for: Credit cards (36-42%), personal loans

**❄️ Snowball Method** *(best motivation)*
Pay minimums on all. Extra money → smallest balance first.
Best for: People who need quick wins to stay motivated

**🚨 Credit Card — Priority #1:**
• 36-42% annual interest — the most expensive debt
• Always pay **full amount** (minimum payment = debt trap)
• If overwhelmed: balance transfer to 0% card

**💡 Smart moves:**
• Prepay home loan with annual bonus → saves lakhs in interest
• Never take personal loan to repay credit card — negotiate with bank instead
• Check if refinancing at lower rate is possible

**While in debt:** Pause discretionary investments. Paying 40% credit card debt = guaranteed 40% return!

Share your debt details and I'll help create a specific payoff plan! 😊"""

    def retirement_response():
        income_val = amounts[0] if amounts else 50000
        monthly_invest = round(income_val * 0.15)
        return f"""**Retirement Planning** 🌅

**The power of starting early:**
• Rs.5,000/month from age **25** → Rs.3.5 crore at 60
• Rs.5,000/month from age **35** → Rs.1.1 crore at 60
*Same amount, 10 years difference = 3x less wealth!*

**For Rs.{income_val:,}/month — recommended Rs.{monthly_invest:,}/month (15%) for retirement:**

| Tool | Amount | Benefit |
| NPS Tier-1 | Rs.{round(monthly_invest*0.40):,} | Extra 80C Rs.50,000 + pension |
| Equity Index Fund SIP | Rs.{round(monthly_invest*0.40):,} | Inflation-beating growth |
| PPF | Rs.{round(monthly_invest*0.20):,} | Tax-free, guaranteed |

**Estimating your corpus need:**
Monthly expenses needed × 300 = rough corpus needed
e.g., Rs.50,000/month needs → Rs.1.5 crore corpus

**Don't forget:**
• Employer EPF is also retirement savings
• Health insurance becomes critical post-retirement
• Review and rebalance portfolio every year

⚠️ *A certified financial planner can create a precise retirement plan for your situation.*

How many years until you plan to retire? I'll calculate your target corpus! 😊"""

    def crypto_response():
        return """**Cryptocurrency in Indian Context** ₿

**Regulatory status (2025):**
• Crypto is legal to buy/sell in India
• 30% flat tax on gains (no deductions, no loss offset)
• 1% TDS on transactions above Rs.50,000
• Must report in ITR under "income from virtual digital assets"

**My honest assessment as your CA friend:**
Crypto is highly speculative — not traditional "investment." Treat it like this:
• **Maximum allocation:** 5-10% of investable money
• **Only money you can afford to lose 100%**
• **Not for emergency fund or short-term goals**

**If you still want to invest:**
1. Use regulated Indian platforms (CoinDCX, WazirX, Zebpay)
2. Start with Bitcoin or Ethereum only (most established)
3. Use SIP approach — buy fixed amount monthly
4. Keep records for tax filing

**Better alternatives for wealth building:**
Nifty 50 Index Fund has given 12-14% CAGR over 20 years with much lower risk.

What's your investment goal? I can suggest the right instrument! 😊"""

    def insurance_response():
        income_val = amounts[0] if amounts else 50000
        annual = income_val * 12
        cover = annual * 15
        return f"""**Insurance Planning Guide** 🛡️

**Two insurances EVERYONE must have:**

**1. Term Life Insurance**
• Cover needed: **Rs.{cover:,}** (15x annual income of Rs.{annual:,})
• Premium for Rs.1 crore cover: Rs.8,000-15,000/year at age 25-30
• Buy ONLY term plan — not endowment/ULIP (they're expensive + low returns)
• Best options: LIC Tech Term, HDFC Click 2 Protect, ICICI iProtect Smart

**2. Health Insurance (Mediclaim)**
• Minimum: Rs.5-10 lakh individual cover
• Better: Rs.10-25 lakh family floater
• Premium: Rs.8,000-25,000/year depending on age
• Top-up plans can increase cover cheaply

**What to AVOID:**
• ❌ ULIP (Unit Linked Insurance Plan) — poor returns + high charges
• ❌ Endowment/money-back plans — better to buy term + invest separately
• ❌ Insurance as investment — it's protection, not wealth building

**Section 80D benefit:** Health insurance premiums up to Rs.25,000 (Rs.50,000 for senior citizens) are tax deductible!

For Rs.{income_val:,}/month income — budget Rs.{round(income_val*0.03):,}-{round(income_val*0.05):,}/month for both insurances.

Need help comparing specific plans? 😊"""

    # ── Map best intent to response ──────────────────────
    if best_score == 0:
        # No clear intent detected
        return {"reply": f"""I want to make sure I give you the most helpful answer for: *"{msg_orig}"*

As your **AI financial advisor**, I can help with:

• **💰 Savings plan** — *"My income is Rs.X, how do I save Rs.Y/month?"*
• **📊 Budget planning** — *"Create a budget for Rs.50,000 salary"*
• **🧾 Tax saving** — *"How do I save tax legally in India?"*
• **📈 Investments** — *"Where should I invest Rs.5,000/month?"*
• **🛡️ Emergency fund** — *"How do I build an emergency fund?"*
• **💳 Debt management** — *"How do I pay off my credit card?"*
• **🌅 Retirement planning** — *"How do I plan for retirement?"*
• **🔍 ETMS help** — *"Where is dark mode?" / "How do I add a transaction?"*

Just ask naturally — I'll understand! 😊""", "source": "clarify", "session_context": {}}

    # Route to best matching response
    response_map = {
        "savings_plan":   savings_response,
        "budget":         budget_response,
        "tax":            tax_response,
        "investment":     investment_response,
        "emergency_fund": emergency_fund_response,
        "debt":           debt_response,
        "retirement":     retirement_response,
        "etms_help":      etms_help_response,
        "crypto":         crypto_response,
        "insurance":      insurance_response,
    }

    reply_text = response_map[best_intent]()
    return {"reply": reply_text, "source": "smart", "session_context": {}}

# ═══════════════════════════════════════════════════════
# UPLOAD FILES — Automatic Transaction Import
# ═══════════════════════════════════════════════════════

class UploadFileRequest(BaseModel):
    user: str
    filename: str
    file_type: str          # pdf | csv | xlsx | xls
    file_data: str          # base64
    min_limit: float = 100.0

class ImportRequest(BaseModel):
    user: str
    filename: str
    file_type: str
    transactions: list

# ── Helpers ──────────────────────────────────────────────

CATEGORY_KEYWORDS = {
    "Salary":       ["salary","sal","payroll","wages","stipend","pay credit","neft cr","imps cr"],
    "Groceries":    ["grocery","supermarket","bigbasket","zepto","blinkit","swiggy instamart","dmart","reliance fresh","more store","spencer","nature basket"],
    "Food":         ["restaurant","zomato","swiggy","food","cafe","dominos","mcdonald","kfc","pizza","burger","biryani","dhaba","eat"],
    "Transport":    ["uber","ola","rapido","auto","taxi","bus","metro","train","irctc","petrol","fuel","diesel","rapido","rickshaw"],
    "Shopping":     ["amazon","flipkart","myntra","ajio","meesho","nykaa","shop","mall","fashion","clothing","apparel","store"],
    "Utilities":    ["electricity","water","gas","broadband","internet","airtel","jio","vodafone","bsnl","tata sky","dish tv","utility","bill"],
    "Healthcare":   ["hospital","clinic","pharmacy","medplus","apollo","1mg","netmeds","diagnostic","lab","doctor","health","medicine"],
    "Entertainment":["netflix","hotstar","spotify","prime video","youtube","bookmyshow","pvr","inox","game","steam"],
    "Rent":         ["rent","pg","hostel","accommodation","housing","maintenance","society"],
    "Education":    ["school","college","university","course","udemy","coursera","fee","tuition","book"],
    "Insurance":    ["lic","insurance","premium","hdfc life","sbi life","bajaj allianz","star health","max life"],
    "Investment":   ["mutual fund","sip","ppf","nps","zerodha","groww","upstox","demat","ipo","fd","rd","deposit"],
    "EMI":          ["emi","loan","bajaj finance","hdfc bank emi","axis bank emi","icici emi","home loan","car loan"],
    "ATM":          ["atm","cash withdrawal","cash cdm"],
    "Transfer":     ["transfer","neft","rtgs","imps","upi","phonepe","paytm","gpay","google pay","bhim"],
}

def categorize_transaction(desc: str) -> str:
    d = desc.lower()
    for cat, keys in CATEGORY_KEYWORDS.items():
        if any(k in d for k in keys):
            return cat
    return "Other"

def detect_type(desc: str, amount: float) -> str:
    """Income if positive credit, expense if debit."""
    d = desc.lower()
    income_signals  = ["credit","cr ","credited","received","salary","refund","cashback","interest cr","imps cr","neft cr","reversal cr"]
    expense_signals = ["debit","dr ","debited","paid","payment","purchase","withdrawal","emi","bill"]
    if any(s in d for s in income_signals) or amount > 0:
        return "income"
    return "expense"

def parse_amount(raw) -> float:
    """Convert various amount formats to float."""
    if isinstance(raw, (int, float)):
        return abs(float(raw))
    s = str(raw).replace(",","").replace("₹","").replace("Rs.","").replace("INR","").strip()
    s = re.sub(r"[^\d.]", "", s)
    try:
        return abs(float(s))
    except:
        return 0.0

def parse_date(raw) -> str:
    if not raw:
        return datetime.now().strftime("%d %b %Y")
    s = str(raw).strip()
    fmts = ["%d/%m/%Y","%Y-%m-%d","%d-%m-%Y","%d %b %Y","%d-%b-%Y",
            "%d/%m/%y","%m/%d/%Y","%Y/%m/%d","%d.%m.%Y"]
    for fmt in fmts:
        try:
            return datetime.strptime(s[:10], fmt).strftime("%d %b %Y")
        except:
            pass
    # Try pandas
    try:
        import pandas as pd
        return pd.to_datetime(s).strftime("%d %b %Y")
    except:
        pass
    return s[:10]

def is_duplicate(user: str, date: str, amount: float, category: str) -> bool:
    """Check if a nearly identical transaction exists already."""
    existing = txns_col.find({"user": user}, {"_id": 0, "amount": 1, "category": 1, "created_at": 1})
    for t in existing:
        try:
            ex_amt = abs(float(t["amount"]))
            # Same amount (within ₹1) AND same category root
            if abs(ex_amt - amount) < 1 and category.lower() in t["category"].lower():
                return True
        except:
            pass
    return False

def ai_categorize(descriptions: list) -> dict:
    """Use Gemini to categorize a batch of unknown transactions."""
    if not descriptions:
        return {}
    prompt = (
        "For each bank transaction description below, reply ONLY with JSON mapping "
        "the exact description to a one-word category from: "
        "Salary,Groceries,Food,Transport,Shopping,Utilities,Healthcare,Entertainment,"
        "Rent,Education,Insurance,Investment,EMI,ATM,Transfer,Other\n\n"
        + "\n".join(f"- {d}" for d in descriptions[:20])
        + "\n\nRespond ONLY with JSON like: {\"desc1\":\"Food\",\"desc2\":\"Salary\"}"
    )
    try:
        raw = gemini_client.models.generate_content(model="gemini-2.0-flash", contents=prompt).text.strip()
        raw = re.sub(r"```json|```", "", raw).strip()
        return json.loads(raw)
    except:
        return {}

def extract_from_pdf(raw_bytes: bytes) -> list:
    """Extract rows from PDF bank statement."""
    import pdfplumber
    rows = []
    try:
        with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
            for page in pdf.pages:
                # Try tables first
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if not row:
                            continue
                        row_text = [str(c).strip() if c else "" for c in row]
                        rows.append(row_text)
                # Fallback: raw text lines
                if not tables:
                    text = page.extract_text() or ""
                    for line in text.split("\n"):
                        rows.append([line])
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"PDF parse error: {str(e)}")
    return rows

def extract_from_csv(raw_bytes: bytes) -> list:
    text = raw_bytes.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    return list(reader)

def extract_from_excel(raw_bytes: bytes, ext: str) -> list:
    try:
        import pandas as pd
        df = pd.read_excel(io.BytesIO(raw_bytes), engine="openpyxl" if ext == "xlsx" else "xlrd")
        df = df.fillna("")
        rows = [list(df.columns.astype(str))]
        for _, r in df.iterrows():
            rows.append([str(v) for v in r.values])
        return rows
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Excel parse error: {str(e)}")

def rows_to_transactions(rows: list, user: str, min_limit: float) -> tuple:
    """
    Heuristically parse raw rows into transaction dicts.
    Returns (transactions, stats).
    """
    txns = []
    stats = {"total": 0, "valid": 0, "duplicates": 0, "below_limit": 0, "ignored": 0}

    # Find header row — look for row containing date/amount keywords
    header_idx = 0
    header_map = {}
    date_keys   = ["date","txn date","value date","transaction date","posting date"]
    desc_keys   = ["description","narration","particulars","remarks","details","transaction details","txn","particulars"]
    amount_keys = ["amount","debit","credit","withdrawal","deposit","txn amount","transaction amount"]
    debit_keys  = ["debit","withdrawal","dr","dr amount"]
    credit_keys = ["credit","deposit","cr","cr amount"]

    for i, row in enumerate(rows[:20]):
        row_lower = [str(c).lower().strip() for c in row]
        if any(any(k in cell for k in date_keys) for cell in row_lower):
            header_idx = i
            for j, cell in enumerate(row_lower):
                for k in date_keys:
                    if k in cell: header_map.setdefault("date", j)
                for k in desc_keys:
                    if k in cell: header_map.setdefault("desc", j)
                for k in amount_keys:
                    if k in cell: header_map.setdefault("amount", j)
                for k in debit_keys:
                    if k in cell: header_map.setdefault("debit", j)
                for k in credit_keys:
                    if k in cell: header_map.setdefault("credit", j)
            break

    # Collect unknown descriptions for AI batch categorization
    unknown_descs = []

    for row in rows[header_idx + 1:]:
        if not row or all(str(c).strip() == "" for c in row):
            continue

        # Extract date
        date_val = ""
        if "date" in header_map and header_map["date"] < len(row):
            date_val = parse_date(row[header_map["date"]])
        else:
            # Scan row for date-like value
            for cell in row:
                s = str(cell).strip()
                if re.search(r"\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}", s):
                    date_val = parse_date(s)
                    break
            if not date_val:
                date_val = datetime.now().strftime("%d %b %Y")

        # Extract description
        desc = ""
        if "desc" in header_map and header_map["desc"] < len(row):
            desc = str(row[header_map["desc"]]).strip()
        else:
            # Use longest text cell
            desc = max((str(c) for c in row), key=len, default="")

        # Extract amount — prefer separate debit/credit columns
        amount = 0.0
        txn_type = "expense"
        if "debit" in header_map and "credit" in header_map:
            dv = parse_amount(row[header_map["debit"]] if header_map["debit"] < len(row) else "")
            cv = parse_amount(row[header_map["credit"]] if header_map["credit"] < len(row) else "")
            if cv > 0:
                amount = cv; txn_type = "income"
            elif dv > 0:
                amount = dv; txn_type = "expense"
        elif "amount" in header_map and header_map["amount"] < len(row):
            amount = parse_amount(row[header_map["amount"]])
            txn_type = detect_type(desc, amount)
        else:
            # Scan for numeric cell
            for cell in row:
                a = parse_amount(cell)
                if a > 0:
                    amount = a
                    txn_type = detect_type(desc, a)
                    break

        if amount <= 0 or not desc:
            stats["ignored"] += 1
            continue

        stats["total"] += 1
        category = categorize_transaction(desc)
        if category == "Other":
            unknown_descs.append(desc)

        # Status checks
        if amount < min_limit:
            status = "below_limit"
            stats["below_limit"] += 1
        elif is_duplicate(user, date_val, amount, category):
            status = "duplicate"
            stats["duplicates"] += 1
        else:
            status = "valid"
            stats["valid"] += 1

        txns.append({
            "date": date_val,
            "description": desc[:120],
            "category": category,
            "type": txn_type,
            "amount": round(amount, 2),
            "status": status
        })

    # AI batch categorize unknowns
    if unknown_descs:
        ai_cats = ai_categorize(list(set(unknown_descs)))
        for t in txns:
            if t["category"] == "Other" and t["description"] in ai_cats:
                t["category"] = ai_cats[t["description"]]

    return txns, stats


# ── POST /upload-file ───────────────────────────────────
@app.post("/upload-file")
def upload_file(body: UploadFileRequest):
    if not body.file_data:
        raise HTTPException(status_code=400, detail="No file data provided")
    if body.file_type not in ("pdf", "csv", "xlsx", "xls"):
        raise HTTPException(status_code=400, detail="Unsupported file type")

    try:
        raw_bytes = base64.b64decode(body.file_data)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 file data")

    if len(raw_bytes) == 0:
        raise HTTPException(status_code=400, detail="File is empty")

    # Parse file into raw rows
    if body.file_type == "pdf":
        rows = extract_from_pdf(raw_bytes)
    elif body.file_type == "csv":
        rows = extract_from_csv(raw_bytes)
    else:
        rows = extract_from_excel(raw_bytes, body.file_type)

    if not rows:
        raise HTTPException(status_code=400, detail="No data found in file")

    txns, stats = rows_to_transactions(rows, body.user, body.min_limit)

    if not txns:
        raise HTTPException(status_code=400, detail="No valid transactions could be extracted from this file")

    return {"transactions": txns, "stats": stats}


# ── POST /import-transactions ───────────────────────────
@app.post("/import-transactions")
def import_transactions(body: ImportRequest):
    if not body.transactions:
        raise HTTPException(status_code=400, detail="No transactions to import")

    imported = 0
    for t in body.transactions:
        if t.get("status") != "valid":
            continue
        amount = float(t["amount"])
        if t["type"] == "expense":
            amount = -abs(amount)
        category = t.get("category", "Other")
        desc     = t.get("description", "")
        full_cat = f"{category} — {desc}" if desc else category
        dt_str   = t.get("date", datetime.now().strftime("%d %b %Y"))
        # Normalize date to expected format
        try:
            dt_obj = datetime.strptime(dt_str, "%d %b %Y")
            created_at = dt_obj.strftime("%d %b %Y, 12:00 PM")
        except:
            created_at = datetime.now().strftime("%d %b %Y, %I:%M %p")

        txns_col.insert_one({
            "id": str(uuid.uuid4()),
            "amount": str(amount),
            "category": full_cat,
            "user": body.user,
            "created_at": created_at
        })
        imported += 1

    # Save to import history
    import_hist_col.insert_one({
        "id": str(uuid.uuid4()),
        "username": body.user,
        "filename": body.filename,
        "file_type": body.file_type,
        "total_records": len(body.transactions),
        "imported_records": imported,
        "duplicate_records": sum(1 for t in body.transactions if t.get("status") == "duplicate"),
        "ignored_records": sum(1 for t in body.transactions if t.get("status") not in ("valid","duplicate","below_limit")),
        "below_limit_records": sum(1 for t in body.transactions if t.get("status") == "below_limit"),
        "upload_time": datetime.now().strftime("%d %b %Y, %I:%M %p")
    })

    return {"status": "ok", "imported_count": imported}


# ── GET /import-history ─────────────────────────────────
@app.get("/import-history")
def get_import_history(user: str):
    if not user:
        return {"history": []}
    docs = list(
        import_hist_col
        .find({"username": user}, {"_id": 0})
        .sort("upload_time", -1)
        .limit(20)
    )
    for d in docs:
        d.pop("id", None)
    return {"history": docs}



# ═══════════════════════════════════════════════════════
# SPLIT EXPENSE — Group expense sharing (Splitwise-style)
# ═══════════════════════════════════════════════════════

class SplitGroupCreate(BaseModel):
    name: str
    created_by: str
    members: list   # list of usernames (strings)

    @validator("name")
    def validate_name(cls, v):
        v = v.strip()
        if len(v) < 2: raise ValueError("Group name min 2 characters")
        return v

    @validator("members")
    def validate_members(cls, v, values):
        members = [m.strip().lower() for m in v if m.strip()]
        creator = values.get("created_by", "").strip().lower()
        if creator and creator not in members:
            members.insert(0, creator)
        if len(members) < 2:
            raise ValueError("At least 2 members required")
        return members

class SplitExpenseAdd(BaseModel):
    group_id: str
    description: str
    amount: float
    paid_by: str        # username who paid
    split_among: list   # list of usernames to split between
    user: str           # current logged-in user (for auth)

    @validator("amount")
    def validate_amount(cls, v):
        if v <= 0: raise ValueError("Amount must be positive")
        return round(v, 2)

    @validator("description")
    def validate_desc(cls, v):
        v = v.strip()
        if not v: raise ValueError("Description required")
        return v

class SplitSettleUp(BaseModel):
    group_id: str
    from_user: str
    to_user: str
    amount: float
    user: str           # current logged-in user

# ── POST /splits/create ────────────────────────────────
@app.post("/splits/create")
def create_split_group(body: SplitGroupCreate):
    # Verify all members exist in DB
    missing = []
    for m in body.members:
        if m != body.created_by and not users_col.find_one({"username": m}):
            missing.append(m)
    if missing:
        raise HTTPException(status_code=400, detail=f"Users not found: {', '.join(missing)}")

    gid = str(uuid.uuid4())
    splits_col.insert_one({
        "id": gid,
        "name": body.name.strip(),
        "created_by": body.created_by,
        "members": body.members,
        "expenses": [],
        "settlements": [],
        "created_at": datetime.now().strftime("%d %b %Y, %I:%M %p")
    })
    return {"status": "ok", "group_id": gid}

# ── GET /splits ────────────────────────────────────────
@app.get("/splits")
def get_split_groups(user: str):
    if not user:
        raise HTTPException(status_code=400, detail="User required")
    # Return all groups where user is a member
    groups = list(splits_col.find({"members": user}, {"_id": 0}))

    # For each group, compute balances
    for g in groups:
        g["balances"] = _compute_balances(g)

    return groups

# ── POST /splits/add-expense ───────────────────────────
@app.post("/splits/add-expense")
def add_split_expense(body: SplitExpenseAdd):
    group = splits_col.find_one({"id": body.group_id})
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    if body.user not in group["members"]:
        raise HTTPException(status_code=403, detail="Not a group member")
    if body.paid_by not in group["members"]:
        raise HTTPException(status_code=400, detail="Paid-by user not in group")

    # Validate split_among are all group members
    invalid = [m for m in body.split_among if m not in group["members"]]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Not group members: {', '.join(invalid)}")

    per_person = round(body.amount / len(body.split_among), 2)
    expense = {
        "id": str(uuid.uuid4()),
        "description": body.description,
        "amount": body.amount,
        "paid_by": body.paid_by,
        "split_among": body.split_among,
        "per_person": per_person,
        "added_by": body.user,
        "date": datetime.now().strftime("%d %b %Y, %I:%M %p")
    }

    splits_col.update_one(
        {"id": body.group_id},
        {"$push": {"expenses": expense}}
    )
    return {"status": "ok", "expense_id": expense["id"], "per_person": per_person}

# ── DELETE /splits/expense ─────────────────────────────
@app.delete("/splits/expense/{group_id}/{expense_id}")
def delete_split_expense(group_id: str, expense_id: str, user: str):
    group = splits_col.find_one({"id": group_id})
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    if user not in group["members"]:
        raise HTTPException(status_code=403, detail="Not a group member")

    splits_col.update_one(
        {"id": group_id},
        {"$pull": {"expenses": {"id": expense_id}}}
    )
    return {"status": "ok"}

# ── POST /splits/settle ────────────────────────────────
@app.post("/splits/settle")
def settle_up(body: SplitSettleUp):
    group = splits_col.find_one({"id": body.group_id})
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    if body.user not in group["members"]:
        raise HTTPException(status_code=403, detail="Not a group member")

    settlement = {
        "id": str(uuid.uuid4()),
        "from_user": body.from_user,
        "to_user": body.to_user,
        "amount": round(body.amount, 2),
        "date": datetime.now().strftime("%d %b %Y, %I:%M %p")
    }
    splits_col.update_one(
        {"id": body.group_id},
        {"$push": {"settlements": settlement}}
    )
    return {"status": "ok"}

# ── DELETE /splits/group/{id} ──────────────────────────
@app.delete("/splits/group/{group_id}")
def delete_split_group(group_id: str, user: str):
    group = splits_col.find_one({"id": group_id})
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    if group["created_by"] != user:
        raise HTTPException(status_code=403, detail="Only creator can delete group")
    splits_col.delete_one({"id": group_id})
    return {"status": "ok"}

# ── Helper: compute net balances for a group ───────────
def _compute_balances(group: dict) -> dict:
    """
    Returns net balance per user.
    Positive = others owe this person
    Negative = this person owes others
    """
    net = {m: 0.0 for m in group["members"]}

    for exp in group.get("expenses", []):
        paid_by     = exp["paid_by"]
        split_among = exp["split_among"]
        per_person  = round(exp["amount"] / len(split_among), 2)

        # Payer gets credit for full amount
        net[paid_by] = round(net.get(paid_by, 0) + exp["amount"], 2)
        # Each person in split owes their share
        for m in split_among:
            net[m] = round(net.get(m, 0) - per_person, 2)

    # Apply settlements
    for s in group.get("settlements", []):
        net[s["from_user"]] = round(net.get(s["from_user"], 0) + s["amount"], 2)
        net[s["to_user"]]   = round(net.get(s["to_user"], 0)   - s["amount"], 2)

    # Compute simplified debts: who owes whom how much
    debts = _simplify_debts(net)
    return {"net": net, "debts": debts}

def _simplify_debts(net: dict) -> list:
    """Greedy debt simplification — minimize number of transactions."""
    creditors = sorted([(u, v) for u, v in net.items() if v > 0.005], key=lambda x: -x[1])
    debtors   = sorted([(u, abs(v)) for u, v in net.items() if v < -0.005], key=lambda x: -x[1])
    debts = []
    i, j = 0, 0
    creditors = [list(x) for x in creditors]
    debtors   = [list(x) for x in debtors]
    while i < len(creditors) and j < len(debtors):
        creditor, credit = creditors[i]
        debtor,   debt   = debtors[j]
        amount = round(min(credit, debt), 2)
        if amount > 0:
            debts.append({"from": debtor, "to": creditor, "amount": amount})
        creditors[i][1] = round(credit - amount, 2)
        debtors[j][1]   = round(debt   - amount, 2)
        if creditors[i][1] < 0.005: i += 1
        if debtors[j][1]   < 0.005: j += 1
    return debts


app.mount("/", StaticFiles(directory="static", html=True), name="static")

