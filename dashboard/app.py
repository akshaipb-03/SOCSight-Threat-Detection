import streamlit as st
import pandas as pd
import requests
import re
import urllib.parse
from datetime import datetime
import plotly.express as px

# ==============================
# CONFIG
# ==============================
LOG_FILE = "../logs/dvwa/access.log"

TELEGRAM_TOKEN = "8653729765:AAE8eHoro-ppSGl4TfL_yLsIW2k5-OY-_ic"
CHAT_ID = "1441094177"

# ==============================
# UI
# ==============================
st.set_page_config(page_title="Cyber Defense Dashboard", layout="wide")
st.title("🛡️ Cyber Defense Dashboard")
st.caption("Live SOC + SOAR System")

# ==============================
# TELEGRAM ALERT
# ==============================
def send_alert(ip, attack_type, severity, location, count):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

        message = f"""
🚨 *SOC ALERT* 🚨

🔴 *Attack:* {attack_type}
🌐 *IP:* `{ip}`
📍 *Location:* {location}

📊 *Requests:* {count}
🔥 *Severity:* {severity}

🛡 *Action:* BLOCKED
⏰ {datetime.now().strftime('%H:%M:%S')}
"""

        requests.post(url, data={
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }, timeout=5)

    except Exception as e:
        print("Telegram error:", e)

# ==============================
# GEO
# ==============================
def get_geo(ip):
    if ip.startswith(("192.", "10.", "172.")):
        return None, None, "Internal Network"

    try:
        res = requests.get(f"http://ip-api.com/json/{ip}", timeout=3).json()
        return res.get("lat"), res.get("lon"), res.get("country")
    except:
        return None, None, "Unknown"

# ==============================
# MITRE MAPPING
# ==============================
def map_mitre(attack_type):
    mapping = {
        "SQL Injection": ("T1190", "Exploit Public-Facing Application"),
        "XSS": ("T1059", "Command Execution"),
        "Command Injection": ("T1059", "Command Execution"),
        "File Inclusion": ("T1005", "Data from Local System"),
        "Recon / Scanning": ("T1595", "Active Scanning")
    }
    return mapping.get(attack_type, ("N/A", "Unknown"))

# ==============================
# DETECTION
# ==============================
def detect_attack(log):
    decoded = urllib.parse.unquote(log).lower()
    decoded = decoded.replace("+", " ")

    # ================= SQL Injection =================
    if re.search(r"('\s*or\s*'1'='1|or\s+1=1|union\s+select|select\s.+from|--)", decoded):
        return "SQL Injection"

    # ================= XSS =================
    elif re.search(r"(<script>|javascript:|onerror=|alert\()", decoded):
        return "XSS"

    # ================= Command Injection =================
    elif re.search(r"(;|&&|\|\||\bcat\b|\bwget\b|\bcurl\b)", decoded):
        return "Command Injection"

    # ================= File Inclusion =================
    elif re.search(r"(\.\./|\betc/passwd\b|/proc/self/environ)", decoded):
        return "File Inclusion"

    # ================= Recon =================
    elif re.search(r"(nmap|nikto|sqlmap|dirbuster)", decoded):
        return "Recon / Scanning"

    return None

# ==============================
# ANOMALY
# ==============================
def anomaly_score(df):
    counts = df["ip"].value_counts()
    df["score"] = df["ip"].map(counts)

    df["anomaly"] = df["score"].apply(
        lambda x: "HIGH" if x > 20 else "MEDIUM" if x > 10 else "LOW"
    )
    return df

# ==============================
# LOAD LOGS
# ==============================
def load_logs():
    try:
        with open(LOG_FILE, "r") as f:
            logs = f.readlines()
    except:
        st.error("Log file not found")
        return pd.DataFrame()

    data = []

    for log in logs:
        try:
            ip = log.split(" ")[0]

            time_str = re.search(r"\[(.*?)\]", log).group(1)
            timestamp = datetime.strptime(time_str.split()[0], "%d/%b/%Y:%H:%M:%S")

            attack_type = detect_attack(log)
            mitre_id, mitre_desc = map_mitre(attack_type if attack_type else "Normal")

            data.append({
                "ip": ip,
                "timestamp": timestamp,
                "log": log,
                "attack": bool(attack_type),
                "attack_type": attack_type if attack_type else "Normal",
                "mitre_id": mitre_id,
                "mitre_desc": mitre_desc
            })

        except:
            continue

    df = pd.DataFrame(data)

    if not df.empty:
        df = anomaly_score(df)

    return df

# ==============================
# LOAD DATA
# ==============================
df = load_logs()

if df.empty:
    st.warning("No logs found")
    st.stop()

attacks = df[df["attack"] == True]

# ==============================
# METRICS
# ==============================
col1, col2, col3 = st.columns(3)

col1.metric("Total Logs", len(df))
col2.metric("Attacks", len(attacks))

threat = "HIGH" if len(attacks) > 50 else "MEDIUM" if len(attacks) > 10 else "LOW"
col3.metric("Threat Level", threat)

# ==============================
# TREND
# ==============================
st.subheader("📊 Attack Trend")

df["minute"] = df["timestamp"].dt.strftime("%H:%M")
trend = df.groupby("minute").size().reset_index(name="count")
st.plotly_chart(px.line(trend, x="minute", y="count"), use_container_width=True)

# ==============================
# ATTACK TYPES
# ==============================
st.subheader("📊 Attack Type Distribution")

counts = attacks["attack_type"].value_counts()
if not counts.empty:
    st.bar_chart(counts)

# ==============================
# MAP
# ==============================
st.subheader("🌍 Attack Map")

locations = []
for ip in attacks["ip"].unique():
    lat, lon, _ = get_geo(ip)
    if lat:
        locations.append({"lat": lat, "lon": lon})

if locations:
    st.map(pd.DataFrame(locations))
else:
    st.info("No external attack locations")

# ==============================
# ALERTS
# ==============================
st.subheader("🚨 Alerts")

alert_tracker = {}
COOLDOWN = 60

for ip, group in attacks.groupby("ip"):
    count = len(group)
    severity = "HIGH" if count > 20 else "MEDIUM" if count > 10 else "LOW"

    _, _, location = get_geo(ip)
    attack_type = group["attack_type"].value_counts().index[0]

    if ip not in alert_tracker or (datetime.now() - alert_tracker[ip]).seconds > COOLDOWN:
        send_alert(ip, attack_type, severity, location, count)
        alert_tracker[ip] = datetime.now()

    st.error(f"🚨 {ip} | {attack_type} | {severity} | {count} req")

# ==============================
# LOG TABLE
# ==============================
st.subheader("📜 Recent Logs")
st.dataframe(df.tail(20), use_container_width=True)

# ==============================
# PROFILING
# ==============================
st.subheader("🧠 Attacker Profiling")

attacker_stats = attacks.groupby("ip").agg({
    "log": "count",
    "timestamp": "max"
}).rename(columns={"log": "attack_count", "timestamp": "last_seen"}).reset_index()

attacker_stats["anomaly"] = attacker_stats["ip"].map(
    df.groupby("ip")["anomaly"].max().to_dict()
)

# ==============================
# RISK + THREAT SCORE
# ==============================
def calculate_risk(row):
    score = row["attack_count"] * 2
    if row["anomaly"] == "HIGH": score += 30
    elif row["anomaly"] == "MEDIUM": score += 15

    minutes = (datetime.now() - row["last_seen"]).seconds / 60
    if minutes < 5: score += 20
    elif minutes < 15: score += 10

    return score

attacker_stats["risk_score"] = attacker_stats.apply(calculate_risk, axis=1)

attack_map = df.groupby("ip")["attack_type"].agg(lambda x: x.value_counts().index[0]).to_dict()
attacker_stats["attack_type"] = attacker_stats["ip"].map(attack_map)

def threat_score(row):
    score = row["risk_score"]
    if row["attack_type"] == "SQL Injection": score += 30
    elif row["attack_type"] == "Command Injection": score += 25
    elif row["attack_type"] == "XSS": score += 15
    return min(score, 100)

attacker_stats["threat_score"] = attacker_stats.apply(threat_score, axis=1)

# ==============================
# MITRE PANEL
# ==============================
st.subheader("🧠 MITRE ATT&CK Mapping")

st.dataframe(
    df[df["attack"]][["ip","attack_type","mitre_id","mitre_desc"]]
    .drop_duplicates()
    .head(10),
    use_container_width=True
)

# ==============================
# THREAT PANEL
# ==============================
st.subheader("🔥 Threat Intelligence Panel")

st.dataframe(
    attacker_stats.sort_values("threat_score", ascending=False)
    [["ip","attack_type","risk_score","threat_score"]]
    .head(10),
    use_container_width=True
)
