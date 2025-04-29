## Prerequisites
- Python 3.10+
- Python virtual environment

# How to run
### Platform specific
These steps differ on operating system used 

**Step 1**
Clone the repository to your local machine

**Step 2**
Create and activate python virtual environment inside extracted folder

### Platform Agnostic
**Step 3**
Install requirements using `pip install -r requirements.txt` 

**Step 4**
Run backend using `python main.py`

**Step 5**
Run main scraper script using `python EventManager.py`

---

# Configs

**Toggling headless mode**

At the top of `EventManager.py` there should be a constant named `HEADLESS_MODE`. The value of this constant represents headless mode toggle


**Changing event URL**

At the top of `EventManager.py` there should be a constant named `EVENT_URL`. The value of this constant represents the scraped event url
