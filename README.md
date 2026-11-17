# CloudBite demo: cancelled-order rescue

## Run (2 minutes)
```
pip install -r requirements.txt
uvicorn app:app --reload
```
Open http://localhost:8000  (API docs: http://localhost:8000/docs, metrics: /metrics, health: /health)

With Docker:
```
docker build -t cloudbite-demo .
docker run -p 8000:8000 cloudbite-demo
```
Run the rule tests: `python test_logic.py`

## Demo script (about 3 minutes)
Users: Harshit, Abhay, Priya (all Adyar) and Rahul (T Nagar). Use the "Acting as" dropdown.

**A. Paid order**
1. Harshit: tick "Pay online now", order Chicken Biryani (Rs 300).
2. Click "Cancel" right away: free cancel, full refund (shows early cancellation is not charged). Order again.
3. Click "Skip 5 min" (pretends cooking has started), then "Cancel".
   Result: charge Rs 90, refund Rs 210.
4. Switch to Abhay or Priya: notification appears with the discounted price (Rs 210). Click "Buy".
5. Switch to Priya: "already taken". Switch to Rahul: no alert (different area).

**B. Unpaid order**
1. Harshit: untick "Pay online now", order Biryani, "Skip 5 min", "Cancel".
2. Charges ledger shows Rs 90 pending.
3. Harshit orders Paneer Wrap (Rs 180): total becomes Rs 270, ledger shows the charge applied.

Top counters show late cancellations, meals rescued, food saved and charges recovered.

## Files
- logic.py: all rules (SQLite in memory, resets when the server restarts)
- app.py: FastAPI routes
- index.html: the web page
- test_logic.py: tests for refunds, charges, areas and the first-come rule
