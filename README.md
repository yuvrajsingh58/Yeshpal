# Khatushyam Ji Chasme Wale — Optical Shop Management System

Flask-based data management & billing system for an optical shop — products/stock, customers with
udhaar (credit) tracking, eye prescriptions, and a bill/order docket that matches your shop's real
printed bill format (S.No., Date, Delivery Date, Distance/Reading prescription grid, Frame/Glass,
Total/Advance/Balance, terms & conditions, signatory).

## Setup

1. Install Python 3.10+ and pip.
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run the app:
   ```
   python app.py
   ```
4. Open http://localhost:5000 in your browser.
5. Login with:
   - Username: `admin`
   - Password: `admin123`
   (Change this immediately from "Change Password" in the navbar!)

## Configuration (optional environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | random | Flask session secret |
| `DATABASE_PATH` | `database.db` | SQLite file location |
| `SHOP_NAME` | Khatushyam Ji Chasme Wale | Shown on bills |
| `SHOP_TAGLINE` | COMPUTERISED EYE TESTING | Shown under shop name |
| `SHOP_ADDRESS` | (your address) | Shown on bills |
| `SHOP_PHONE` | 8076274076 | Shown on bills |
| `SHOP_GSTIN` | (blank) | Shown on bills if set |
| `ADMIN_USERNAME` | admin | Login username |
| `ADMIN_PASSWORD` | admin123 | Initial login password (change via app after first login) |
| `LOW_STOCK_THRESHOLD` | 5 | Dashboard low-stock alert threshold |
| `STARTING_SNO` | 1430 | First bill S.No. issued (continues your existing register numbering) |

## What's included

- **Dashboard**: today/week/month sales, low stock alerts, best sellers, top pending udhaar customers.
- **Products**: Frame, Sunglasses, Lens, Contact Lens, Accessory — with brand, MRP, selling price,
  power/lens type, barcode.
- **Stock**: add/remove stock quantity, searchable inventory list.
- **Customers**: name, mobile, address; auto udhaar balance; payment recording; edit/delete
  (blocked if they have billing/payment history).
- **Prescriptions**: separate eye-prescription history per customer (Distance/Reading × R/L ×
  Sph/Cyl/Axis, PD, notes) — useful for repeat customers.
- **Billing (New Bill)**: the main order form — mirrors your paper docket exactly:
  - Customer name/mobile with auto-fill for returning customers (type mobile number)
  - Date + Delivery Date
  - Full prescription grid (Distance/Reading × R/L × Sph/Cyl/Axis)
  - Frame & Glass/Lens fields (with suggestions from your product catalog)
  - Bill Type (Cash / Credit-Udhaar), Total, Advance, auto-calculated Balance
- **Bill view/print**: bordered, monospace docket layout matching your physical bill — S.No., shop
  header, prescription table, Frame/Glass, terms & conditions, Total/Advance/Balance box, amount in
  words, E.&O.E./signatory line. Has Print, Edit, and Delete actions.
- **Sales Report**: date-range filter, Cash vs Credit totals, CSV export.
- Session-based login, CSRF-safe forms, hashed admin password (changeable in-app).

## Notes

- The bill's S.No. continues from `STARTING_SNO` (default 1430) automatically — set this once to
  match wherever your physical register left off.
- **Frame/Glass stock linking**: on the billing page, pick "✏️ Type manually" (default) to type a
  free-text Frame/Glass like your paper bill, or pick an actual product from the dropdown — doing
  so auto-fills the name and deducts 1 unit from that product's stock when the bill is saved.
  Switching the link (or deleting the bill) automatically restores the old stock.
- Never replace only some files without the others — always replace `app.py` + the whole
  `templates/` folder together, and never touch `database.db` (that's your live data).
