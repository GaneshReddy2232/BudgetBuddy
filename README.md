#  BudgetBuddy – Flask Expense Tracker  
A clean, fast, beginner-friendly **Flask web application** to manage expenses with full **CRUD operations**, **monthly comparison**,
**SVG-based charts**, and **server-side filtering**

-----------------------------------------------------

##  Features

###  Expense Management (CRUD)
- Add new expenses  
- Edit existing expenses  
- Delete expenses with confirmation  
- View all expenses in a clean, sorted table  

-----------------------------------------------------

###  Server-Side Filtering (No JavaScript)
Filter expenses based on:
- Title search  
- Category (Food, Travel, Bills, etc.)  
- Month & Year  

Filtering also updates the **total expense amount** dynamically.

-----------------------------------------------------

###  Visual Analytics (100% SVG)
BudgetBuddy includes **fully server-generated SVG charts**:

####  1. Bar Chart Comparison
Compare two months across all categories:
- Side-by-side bars (Primary vs Compare month)  
- Automatically scaled  
- SVG exported in one click  

####  2. Pie Charts (Primary & Compare Month)
- Category distribution  
- Smooth colors  
- Percentage labels  
- SVG-based and fully scalable  

-----------------------------------------------------

###  Download Summary as SVG
One-click download of a **high-quality SVG report** containing:
- Bar chart  
- Primary month pie chart  
- Compare month pie chart  
- Legend & labels  

Perfect for documentation or reports.

-----------------------------------------------------

##  Tech Stack

| Component | Technology |
|----------|------------|
| Backend  | Flask (Python) |
| Database | SQLite (SQLAlchemy ORM) |
| Templates | Jinja2 |
| Styling | Bootstrap 5 |
| Charts | Pure SVG (no JavaScript) |
| Server Filtering | SQLAlchemy queries |


