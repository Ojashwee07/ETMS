# 📘 ETMS — Complete Project Explanation
### Expense Tracker Management System

---

## 🧭 Project Overview

ETMS (Expense Tracker Management System) is a full-stack web application that helps users track their income and expenses. It uses **Artificial Intelligence** to analyze spending patterns, extract transactions from bank messages, and generate detailed monthly financial reports with charts.

---

## 🗂️ Project Structure

```
ETMS/
├── app.py              → Backend (FastAPI + MongoDB + Gemini AI)
├── requirements.txt    → Python libraries list
├── .env                → Secret keys (MongoDB URI + Gemini API Key)
└── static/
    ├── index.html      → Complete UI (Login + Dashboard + Report)
    ├── style.css       → All styling and design
    └── script.js       → All frontend logic and API calls
```

---

## ⚙️ Tech Stack

| Part       | Technology Used            | Purpose                          |
|------------|----------------------------|----------------------------------|
| Backend    | Python + FastAPI           | Server, API endpoints            |
| Database   | MongoDB                    | Store users and transactions     |
| AI         | Google Gemini 2.0 Flash    | Smart analysis and reports       |
| Frontend   | HTML + CSS + JavaScript    | User Interface                   |
| Charts     | Chart.js                   | Visual graphs and charts         |
| PDF        | jsPDF                      | Download monthly reports as PDF  |
| Server     | Uvicorn                    | Run the FastAPI application      |

---

## 🔐 1. Authentication System

### What it does:
- User enters **username** and **password**
- If username is **new** → account is automatically created (auto-register)
- If username **exists** → password is verified
- Passwords are **never stored as plain text** — they are converted to SHA-256 hash

### How it works (app.py):
```
User enters credentials
      ↓
Check if username exists in MongoDB
      ↓
New user? → Create account with hashed password
Existing user? → Compare hashed passwords
      ↓
Return login success or error
```

### API Endpoint:
- `POST /login` — Handles both login and registration

---

## 💰 2. Transaction Management

### What it does:
- Users can add **Income** or **Expense** transactions
- Each transaction stores: amount, category, note, username, date & time
- Every transaction gets a **unique ID** (UUID)
- Transactions can be **filtered** (All / Income / Expense)
- Any transaction can be **deleted** with one click

### How amounts are stored:
- Income → stored as **positive number** (e.g. `5000`)
- Expense → stored as **negative number** (e.g. `-3200`)

### API Endpoints:
- `POST /add` — Add new transaction
- `GET /data?user=username` — Get all transactions for a user
- `DELETE /delete/{id}?user=username` — Delete a specific transaction
- `GET /stats?user=username` — Get income, expense, balance totals

---

## 📊 3. Dashboard

### What it shows:
- **Greeting** with user's name and current date
- **3 Stat Cards:**
  - 💚 Total Income (with entry count)
  - 🔴 Total Expense (with entry count)
  - 💙 Current Balance (with savings percentage bar)
- **Add Transaction Panel** — Toggle between Income/Expense
- **Recent Transactions List** — Shows all transactions with delete button

### Live Updates:
Every time a transaction is added or deleted, the dashboard automatically recalculates and updates all stats without page reload.

---

## 🤖 4. AI Features (Powered by Google Gemini 2.0)

### Feature 1: Smart Import (SMS/Email)

**What it does:**
User pastes a bank SMS or email message → AI automatically extracts:
- Transaction type (Income or Expense)
- Amount
- Category
- Date
- Short description

**Example:**
```
Input:  "Your account has been debited Rs.3,200 for Grocery Store on 08-May-2026"
Output: Type: Expense | Amount: ₹3,200 | Category: Grocery
```

**API Endpoint:** `POST /ai/extract`

---

### Feature 2: Spending Analysis

**What it does:**
AI analyzes ALL of the user's transactions and provides:
1. Spending Overview — overall financial health summary
2. Necessary vs Unnecessary expenses classification
3. Smart saving suggestions (4-5 personalized tips)
4. Financial Health Score out of 10

**API Endpoint:** `POST /ai/analyze`

---

## 📈 5. Monthly Report

### What it does:
User selects a **Month** and **Year** → system shows:

#### Charts (3 types using Chart.js):
1. **🍩 Doughnut Chart** — Category-wise expense percentage breakdown
2. **📊 Bar Chart** — Side-by-side category comparison
3. **📈 Line Chart** — Daily spending trend throughout the month

#### Category Table:
- Rank, Category name, Progress bar, Percentage, Amount
- Sorted from highest to lowest expense

#### Stats Cards:
- Month's total Income, Expense, Savings, Savings Rate

### API Endpoint: `GET /report/data?user=...&month=...&year=...`

---

## 📄 6. AI Monthly Report + PDF Download

### AI Report:
User clicks **"Generate AI Report"** → Gemini AI creates a detailed report with:
1. Executive Summary
2. Income Analysis
3. Expense Breakdown
4. Savings Performance
5. Unnecessary Expenses
6. Budget Recommendations for next month
7. Action Plan (3 specific things to do)

**API Endpoint:** `POST /ai/report`

### PDF Download:
User clicks **"Download PDF"** → A professionally formatted PDF is generated with:
- ETMS header with blue background
- Month name and generation date
- Income / Expense / Savings cards
- Complete AI analysis text
- Page numbers on every page
- Footer on each page
- File saved as: `ETMS_Report_May_2026_username.pdf`

**Technology:** jsPDF library (runs entirely in browser, no server needed)

---

## 🗄️ 7. Database Structure (MongoDB)

**Database Name:** `etms_db`

### Collection 1: `users`
```json
{
  "username": "ojashwee",
  "password": "a665a45920422f9d417e4867efdc4fb8...",
  "created_at": "2026-05-08T10:00:00"
}
```

### Collection 2: `transactions`
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "amount": "-3200",
  "category": "Groceries — weekly shopping",
  "user": "ojashwee",
  "created_at": "08 May 2026, 10:22 AM"
}
```

---

## 🌐 8. All API Endpoints

| Method   | Endpoint                        | Description                          |
|----------|---------------------------------|--------------------------------------|
| POST     | `/login`                        | Login or auto-register user          |
| POST     | `/add`                          | Add new transaction                  |
| GET      | `/data?user=X`                  | Get all transactions of user         |
| DELETE   | `/delete/{id}?user=X`           | Delete a specific transaction        |
| GET      | `/stats?user=X`                 | Get income/expense/balance totals    |
| POST     | `/ai/extract`                   | Extract transaction from SMS/Email   |
| POST     | `/ai/analyze`                   | AI spending analysis & suggestions   |
| GET      | `/report/data?user&month&year`  | Get monthly chart data               |
| POST     | `/ai/report`                    | Generate AI monthly report           |

---

## 🎨 9. Frontend Design

### Design System:
- **Font:** Plus Jakarta Sans (modern, clean)
- **Monospace Font:** JetBrains Mono (for amounts)
- **Color Palette:**
  - Blue `#3b6ef8` — Primary, Balance
  - Green `#12b76a` — Income
  - Red `#f04438` — Expense
  - Purple `#7c3aed` — AI features

### Key UI Components:
- **Stat Cards** — Colored top border, hover lift effect
- **Type Toggle** — Smooth switch between Income/Expense
- **Transaction List** — Animated slide-in, hover highlight
- **Charts** — Responsive, interactive with tooltips
- **AI Section** — Purple gradient theme
- **Download Button** — Animated, disabled state during generation

### Pages:
1. **Login Page** — Split layout (blue left panel + white right form)
2. **Dashboard** — Stats + Add form + Transaction list + AI tools
3. **Monthly Report** — Month selector + Charts + AI report + PDF download

---

## 🔒 10. Security Features

| Feature | Implementation |
|---------|---------------|
| Password Storage | SHA-256 hashing (never plain text) |
| Old Password Upgrade | Auto-upgrades plain text to hashed on login |
| Input Validation | Pydantic validators on all inputs |
| User Isolation | Every transaction filtered by username |
| .env Protection | API keys never hardcoded (except Gemini key) |

---

## 🚀 How to Run

```bash
# 1. Start MongoDB
brew services start mongodb-community

# 2. Activate virtual environment
source .venv/bin/activate

# 3. Install dependencies (first time only)
pip install -r requirements.txt

# 4. Start server
uvicorn app:app --reload

# 5. Open browser
http://localhost:8000
```

---

## 📦 Dependencies (requirements.txt)

```
fastapi           → Web framework for building APIs
uvicorn           → ASGI server to run FastAPI
pymongo           → MongoDB connection and queries
python-dotenv     → Load .env file variables
google-generativeai → Google Gemini AI API
```

---

*Built with ❤️ by Ojashwee — [GitHub](https://github.com/Ojashwee07/ETMS)*
